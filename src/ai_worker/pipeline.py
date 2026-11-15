"""End-to-end local bounty workflow with explicit human approval boundaries."""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from ai_worker.developer import PatchError, apply_patch_in_sandbox, draft_patch
from ai_worker.planner import OllamaError, plan_github_issue
from ai_worker.sandbox import DEFAULT_IMAGE, DEFAULT_NODE_IMAGE, SandboxError, run_in_sandbox
from ai_worker.sources.github_issue import GitHubIssueError, inspect_github_issue
from ai_worker.workspace import WorkspaceError, clone_public_github_repo


class PipelineError(RuntimeError):
    pass


@dataclass(slots=True)
class PipelineResult:
    status: str
    issue_url: str
    issue_title: str
    repository: str
    workspace: str
    output_dir: str
    model: str
    reward_amount: float | None
    currency: str
    estimated_effort_hours: float
    estimated_gross_per_hour: float | None
    changed_files: list[str]
    compile_exit_code: int | None
    tests_exit_code: int | None
    tests_detected: bool
    compile_log: str
    tests_log: str
    node_static_exit_code: int | None
    node_static_log: str
    message: str

    def to_dict(self) -> dict:
        return asdict(self)


def resolve_eligible_gig(gig_id: str, gigs: list, min_reward: float = 5.0):
    """Return only a currently eligible Jobbi record; never claim or reserve it."""
    from ai_worker.scoring import evaluate

    matches = [gig for gig in gigs if gig.id == gig_id]
    if len(matches) != 1:
        raise PipelineError("Gig ID was not found uniquely in the latest public feed")
    gig = matches[0]
    eligible, _score, reasons = evaluate(gig, min_reward=min_reward)
    if not eligible:
        raise PipelineError("Gig no longer passes the safety filters: " + "; ".join(reasons))
    return gig


def _write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _has_python_files(workspace: Path) -> bool:
    return any(path.is_file() and not path.is_symlink() for path in workspace.rglob("*.py"))


def _has_python_tests(workspace: Path) -> bool:
    for path in workspace.rglob("*.py"):
        if path.is_symlink():
            continue
        if path.name.startswith("test_") or path.name.endswith("_test.py"):
            return True
        if "tests" in path.relative_to(workspace).parts:
            return True
    return False


def run_pipeline(
    issue_url: str,
    *,
    scratch_root: str | Path,
    output_root: str | Path = ".ai-worker/proposals",
    image: str = DEFAULT_IMAGE,
    node_image: str = DEFAULT_NODE_IMAGE,
    model: str | None = None,
    reward_amount: float | None = None,
    currency: str = "",
    timeout: int = 600,
) -> PipelineResult:
    """Inspect, clone, plan, draft, apply and test; stop before external submission."""
    if not isinstance(timeout, int) or not 30 <= timeout <= 1800:
        raise PipelineError("Pipeline timeout must be between 30 and 1800 seconds")

    scratch = Path(scratch_root).expanduser().resolve()
    output_base = Path(output_root).expanduser().resolve()
    scratch.mkdir(parents=True, exist_ok=True)
    output_base.mkdir(parents=True, exist_ok=True)

    try:
        brief = inspect_github_issue(issue_url)
        if brief.state.lower() != "open":
            raise PipelineError("Only currently open GitHub issues can enter the work pipeline")
        run_id = uuid.uuid4().hex[:10]
        workspace = scratch / f"task-{brief.repository.replace('/', '-')}-{brief.number}-{run_id}"
        output_dir = output_base / f"{brief.repository.replace('/', '-')}-{brief.number}-{run_id}"
        output_dir.mkdir(parents=True, exist_ok=False)

        _write_json(output_dir / "issue.json", brief.to_dict())
        clone_public_github_repo(
            brief.repository,
            workspace,
            scratch_root=scratch,
            timeout_seconds=min(timeout, 900),
        )

        task_plan = plan_github_issue(brief, model=model, timeout=min(timeout, 900))
        _write_json(output_dir / "plan.json", task_plan.to_dict())
        estimated_effort = float(task_plan.estimated_effort_hours)
        estimated_gross_per_hour = (
            round(reward_amount / estimated_effort, 2)
            if reward_amount is not None and estimated_effort > 0
            else None
        )

        proposal = draft_patch(
            brief,
            workspace,
            model=model,
            timeout=min(timeout, 900),
        )
        _write_json(output_dir / "proposal.json", proposal.to_dict())
        if proposal.status == "patch":
            (output_dir / "proposal.patch").write_text(proposal.diff, encoding="utf-8")

        node_static_code = None
        node_static_log = ""
        if proposal.status == "needs_information":
            status = "needs_human_clarification"
            message = "The model did not produce a safe diff. Review the plan and questions; no patch was applied."
            compile_code = tests_code = None
            tests_detected = False
            compile_log = tests_log = ""
        elif (
            proposal.questions
            or task_plan.blockers
            or not task_plan.acceptance_checklist
            or task_plan.risk_level == "high"
            or (reward_amount is not None and reward_amount > 500)
        ):
            status = "blocked_for_human_review"
            message = "The plan has unresolved questions, blockers, missing acceptance checks, high risk, or a reward above $500 requiring manual scope/escrow verification. The proposed diff was saved but not applied."
            compile_code = tests_code = None
            tests_detected = False
            compile_log = tests_log = ""
        else:
            applied = apply_patch_in_sandbox(
                proposal.diff,
                workspace,
                scratch_root=scratch,
                image=image,
                timeout_seconds=min(timeout, 300),
            )
            if not applied.applied:
                status = "patch_rejected"
                message = applied.message
                compile_code = tests_code = None
                tests_detected = False
                compile_log = tests_log = ""
            else:
                compile_code = tests_code = None
                compile_log = tests_log = ""
                tests_detected = _has_python_tests(workspace)
                if _has_python_files(workspace):
                    compile_result = run_in_sandbox(
                        workspace,
                        ["python", "-m", "compileall", "-q", "."],
                        scratch_root=scratch,
                        image=image,
                        timeout_seconds=min(timeout, 300),
                    )
                    compile_code = compile_result.exit_code
                    compile_log = (compile_result.stdout + "\n" + compile_result.stderr).strip()
                    (output_dir / "compile.log").write_text(compile_log, encoding="utf-8")
                node_changed_files = [
                    path for path in proposal.changed_files
                    if Path(path).suffix.lower() in {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"}
                ]
                if node_changed_files:
                    node_result = run_in_sandbox(
                        workspace,
                        ["esbuild", *node_changed_files, "--outdir=/tmp/ai-worker-check"],
                        scratch_root=scratch,
                        image=node_image,
                        timeout_seconds=min(timeout, 300),
                    )
                    node_static_code = node_result.exit_code
                    node_static_log = (node_result.stdout + "\n" + node_result.stderr).strip()
                    (output_dir / "node-static.log").write_text(node_static_log, encoding="utf-8")
                if (
                    (compile_code is not None and compile_code != 0)
                    or (node_static_code is not None and node_static_code != 0)
                ):
                    status = "compile_failed"
                    message = "The isolated Python syntax check failed. Review sandbox logs before proceeding."
                elif tests_detected:
                    test_result = run_in_sandbox(
                        workspace,
                        ["python", "-m", "pytest", "-q"],
                        scratch_root=scratch,
                        image=image,
                        timeout_seconds=min(timeout, 600),
                    )
                    tests_code = test_result.exit_code
                    tests_log = (test_result.stdout + "\n" + test_result.stderr).strip()
                    (output_dir / "pytest.log").write_text(tests_log, encoding="utf-8")
                    if tests_code == 0:
                        status = "ready_for_human_review"
                        message = "Patch applied in the disposable sandbox; Python compile and detected pytest suite passed. No submission was made."
                    else:
                        status = "tests_failed"
                        message = "The patch was applied, but the isolated pytest run failed. Review logs and missing dependencies."
                elif compile_code is None and node_static_code is None:
                    status = "no_automated_tests_detected"
                    message = "No supported source files or Python tests were detected; no language-specific test runner is configured. Human review is required."
                else:
                    status = "static_check_passed_no_tests"
                    checks = []
                    if compile_code == 0:
                        checks.append("Python syntax check passed")
                    if node_static_code == 0:
                        checks.append("JavaScript/TypeScript syntax transpilation passed with esbuild")
                    message = "; ".join(checks) + ". No dependency-aware JavaScript/TypeScript test suite was run. Human review is required."

        result = PipelineResult(
            status=status,
            issue_url=brief.url,
            issue_title=brief.title,
            repository=brief.repository,
            workspace=str(workspace),
            output_dir=str(output_dir),
            model=proposal.model,
            reward_amount=reward_amount,
            currency=currency,
            estimated_effort_hours=estimated_effort,
            estimated_gross_per_hour=estimated_gross_per_hour,
            changed_files=proposal.changed_files,
            compile_exit_code=compile_code,
            tests_exit_code=tests_code,
            tests_detected=tests_detected,
            compile_log=compile_log,
            tests_log=tests_log,
            node_static_exit_code=node_static_code,
            node_static_log=node_static_log,
            message=message,
        )
        _write_json(output_dir / "pipeline-result.json", result.to_dict())
        lines = [
            "# AI-Worker task proposal",
            "",
            f"- Status: {status}",
            f"- Generated: {datetime.now(timezone.utc).isoformat()}",
            f"- Issue: {brief.url}",
            f"- Repository: {brief.repository}",
            f"- Workspace: {workspace}",
            f"- Model: {proposal.model}",
            f"- Listed reward: {reward_amount:g} {currency}" if reward_amount is not None else "- Listed reward: Not provided",
            f"- Estimated effort: {estimated_effort:g} hours",
            f"- Estimated gross/hour: ${estimated_gross_per_hour:g}" if estimated_gross_per_hour is not None else "- Estimated gross/hour: Not calculable",
            f"- Changed files: {', '.join(proposal.changed_files) or 'None'}",
            f"- Python compile exit: {compile_code if compile_code is not None else 'Not run'}",
            f"- Pytest detected: {'yes' if tests_detected else 'no'}",
            f"- Pytest exit: {tests_code if tests_code is not None else 'Not run'}",
            f"- Compile log: {'compile.log' if compile_code is not None else 'Not generated'}",
            f"- Pytest log: {'pytest.log' if tests_code is not None else 'Not generated'}",
            f"- JavaScript/TypeScript syntax exit: {node_static_code if node_static_code is not None else 'Not run'}",
            f"- JavaScript/TypeScript log: {'node-static.log' if node_static_code is not None else 'Not generated'}",
            "",
            message,
            "",
            "## Mandatory approval boundary",
            "This is a draft for human review only. AI-Worker did not claim the bounty, contact anyone, commit, push, open a pull request, or submit work.",
            "",
            "Review issue terms, ownership/licensing, acceptance criteria, changed files, test logs, and payout conditions before any external action.",
            "",
        ]
        (output_dir / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
        return result
    except (GitHubIssueError, WorkspaceError, OllamaError, PatchError, SandboxError) as exc:
        raise PipelineError(str(exc)) from exc
