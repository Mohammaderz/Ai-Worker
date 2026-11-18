"""End-to-end local bounty workflow with explicit human approval boundaries."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from ai_worker.developer import (
    PatchError,
    _validate_patch_plan_scope,
    apply_patch_in_sandbox,
    collect_repo_context,
    draft_patch,
    repair_patch,
    validate_patch_text,
)
from ai_worker.planner import OllamaError, plan_github_issue
from ai_worker.model_router import resolve_model_route
from ai_worker.reviewer import DEFAULT_REVIEWER_MODEL, ReviewerError, review_patch
from ai_worker.sandbox import DEFAULT_IMAGE, DEFAULT_NODE_IMAGE, MAX_OUTPUT_BYTES, SandboxError, run_in_sandbox
from ai_worker.sources.github_issue import GitHubIssueError, inspect_github_issue
from ai_worker.workspace import WorkspaceError, clone_public_github_repo
from ai_worker.storage import connect, create_task_run, advance_task_run
from ai_worker.node_qa import NodeProjectError, inspect_node_project


class PipelineError(RuntimeError):
    pass


MAX_REPAIR_ATTEMPTS = 2


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
    reviewer_verdict: str
    reviewer_summary: str
    reviewer_findings: list[dict]
    message: str
    node_project: dict | None = None
    node_test_exit_code: int | None = None
    node_build_exit_code: int | None = None
    node_test_log: str = ""
    node_build_log: str = ""
    node_check_reason: str | None = None

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


def _model_usage_summary(records: list[dict]) -> dict:
    complete_token_records = [
        item for item in records
        if item.get("prompt_tokens") is not None
        and item.get("completion_tokens") is not None
    ]
    return {
        "call_count": len(records),
        "accepted_response_count": sum(
            item.get("outcome") in {"accepted", "schema_valid", "schema_validated"}
            for item in records
        ),
        "failed_or_rejected_response_count": sum(
            item.get("outcome") in {"request_failed", "response_rejected", "rejected"}
            for item in records
        ),
        "prompt_tokens": (
            sum(item["prompt_tokens"] for item in complete_token_records)
            if complete_token_records else None
        ),
        "completion_tokens": (
            sum(item["completion_tokens"] for item in complete_token_records)
            if complete_token_records else None
        ),
        "total_tokens": (
            sum(item["prompt_tokens"] + item["completion_tokens"]
                for item in complete_token_records)
            if complete_token_records else None
        ),
        "calls_with_token_counts": len(complete_token_records),
        "cost_usd": None,
        "token_source": "Ollama response metadata; null means unavailable",
    }



def _git_commit(workspace: Path) -> str | None:
    """Read the cloned source revision without running repository code or hooks."""
    try:
        completed = subprocess.run(
            ["git", "-c", "core.hooksPath=/dev/null", "-C", str(workspace), "rev-parse", "--verify", "HEAD"],
            capture_output=True, text=True, timeout=10, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    value = completed.stdout.strip()
    return value if completed.returncode == 0 and len(value) == 40 else None


def _sha256_file(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None

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


def _run_candidate_verification(
    diff: str,
    changed_files: list[str],
    workspace: Path,
    plan: object,
    *,
    scratch: Path,
    image: str,
    timeout: int,
) -> dict:
    """Apply and run Python checks on an isolated copy before review/acceptance."""
    evidence = {"schema_version": 1, "checks": [], "patch_applied": False}
    actual_paths = validate_patch_text(diff)
    if set(actual_paths) != set(changed_files):
        evidence["patch_error"] = "Proposal changed-file list does not match its unified diff"
        evidence["passed"] = False
        return evidence
    _validate_patch_plan_scope(actual_paths, plan, require_complete=True)
    with tempfile.TemporaryDirectory(prefix="ai-worker-verify-", dir=scratch) as temp:
        candidate = Path(temp) / "workspace"
        shutil.copytree(workspace, candidate, symlinks=True)
        applied = apply_patch_in_sandbox(
            diff, candidate, scratch_root=scratch, image=image,
            timeout_seconds=min(timeout, 300),
        )
        if not applied.applied:
            evidence["patch_error"] = applied.message
            evidence["patch_apply_stdout"] = (applied.stdout or "")[-8000:]
            evidence["patch_apply_stderr"] = (applied.stderr or "")[-8000:]
            evidence["passed"] = False
            return evidence
        evidence["patch_applied"] = True
        checks = evidence["checks"]
        commands = []
        if _has_python_files(candidate):
            commands.append(("python_compile", ["python", "-m", "compileall", "-q", "."]))
            if _has_python_tests(candidate):
                commands.append(("pytest", ["python", "-m", "pytest", "-q"]))
        for check_name, command in commands:
            try:
                result = run_in_sandbox(
                    candidate, command, scratch_root=scratch, image=image,
                    timeout_seconds=min(timeout, 600),
                )
                checks.append({
                    "name": check_name,
                    "command": command,
                    "required": True,
                    "ran": result.exit_code is not None,
                    "exit_code": result.exit_code,
                    "timed_out": bool(getattr(result, "timed_out", False)),
                    "stdout": (result.stdout or "")[-8000:],
                    "stderr": (result.stderr or "")[-8000:],
                })
            except SandboxError as exc:
                checks.append({
                    "name": check_name, "command": command, "required": True,
                    "ran": False, "exit_code": None, "timed_out": False,
                    "error": str(exc)[:2000],
                })
    evidence["changed_files"] = list(changed_files)
    evidence["passed"] = _verification_gate(evidence)
    return evidence


def _verification_gate(evidence: dict) -> bool:
    """Return true only when every required check has complete passing evidence."""
    if not isinstance(evidence, dict) or evidence.get("patch_applied") is not True:
        return False
    checks = evidence.get("checks")
    if (
        not isinstance(checks, list)
        or any(
            not isinstance(item, dict)
            or type(item.get("required")) is not bool
            for item in checks
        )
    ):
        return False
    required = [item for item in checks if isinstance(item, dict) and item.get("required") is True]
    return bool(required) and all(
        item.get("ran") is True
        and item.get("timed_out") is False
        and type(item.get("exit_code")) is int
        and item.get("exit_code") == 0
        for item in required
    )


def _has_required_checks(evidence: dict) -> bool:
    return bool(
        isinstance(evidence, dict)
        and isinstance(evidence.get("checks"), list)
        and any(
            isinstance(item, dict) and item.get("required") is True
            for item in evidence["checks"]
        )
    )


def _verification_findings(evidence: dict, changed_files: list[str]) -> list[dict]:
    """Convert executed failed checks into reproducible bounded-repair findings."""
    if not changed_files:
        return []
    findings = []
    if evidence.get("patch_applied") is not True:
        diagnostic = {
            "error": evidence.get("patch_error", "Sandbox did not apply the candidate patch"),
            "stdout": evidence.get("patch_apply_stdout", ""),
            "stderr": evidence.get("patch_apply_stderr", ""),
        }
        findings.append({
            "severity": "high",
            "file": changed_files[0],
            "line": 1,
            "title": "Candidate patch failed sandbox application",
            "evidence": json.dumps(diagnostic, ensure_ascii=False)[:1900],
            "recommendation": (
                "Return a valid patch against the unchanged repository workspace that "
                "passes the recorded sandbox git apply check."
            ),
        })
        return findings
    for check in evidence.get("checks", []):
        if not isinstance(check, dict) or check.get("required") is not True:
            continue
        if check.get("ran") is True and check.get("timed_out") is False and check.get("exit_code") == 0:
            continue
        if check.get("ran") is not True or check.get("timed_out") is True:
            continue
        details = json.dumps({
            "command": check.get("command"),
            "exit_code": check.get("exit_code"),
            "stdout": check.get("stdout", ""),
            "stderr": check.get("stderr", ""),
        }, ensure_ascii=False)
        findings.append({
            "severity": "high",
            "file": changed_files[0],
            "line": 1,
            "title": f"Required {check.get('name', 'verification')} check failed",
            "evidence": details[:1900],
            "recommendation": "Correct the patch so the recorded command passes without weakening the test or check.",
        })
    return findings


def _run_pipeline_impl(
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
    reviewer_model: str | None = None,
    _run_id: str,
    _stage_callback=None,
) -> PipelineResult:
    """Internal pipeline implementation; lifecycle is managed by run_pipeline."""
    if not isinstance(timeout, int) or not 30 <= timeout <= 1800:
        raise PipelineError("Pipeline timeout must be between 30 and 1800 seconds")

    scratch = Path(scratch_root).expanduser().resolve()
    output_base = Path(output_root).expanduser().resolve()
    scratch.mkdir(parents=True, exist_ok=True)
    output_base.mkdir(parents=True, exist_ok=True)

    started_at = datetime.now(timezone.utc).isoformat()
    try:
        brief = inspect_github_issue(issue_url)
        if _stage_callback:
            _stage_callback("inspect", {
                "repository": brief.repository,
                "issue_number": brief.number,
                "issue_url": brief.url,
            })
        if brief.state.lower() != "open":
            raise PipelineError("Only currently open GitHub issues can enter the work pipeline")
        run_id = _run_id
        workspace = scratch / f"task-{brief.repository.replace('/', '-')}-{brief.number}-{run_id}"
        output_dir = output_base / f"{brief.repository.replace('/', '-')}-{brief.number}-{run_id}"
        output_dir.mkdir(parents=True, exist_ok=False)

        planning_route = resolve_model_route("planning", override=model)
        drafting_route = resolve_model_route("drafting", override=model)
        reviewer_route = resolve_model_route("review", override=reviewer_model)
        repair_route = resolve_model_route("repair", override=drafting_route.model)
        model_routes = {
            "planning": planning_route.to_dict(),
            "drafting": drafting_route.to_dict(),
            "repair": repair_route.to_dict(),
            "review": reviewer_route.to_dict(),
        }
        model_usage: list[dict] = []
        _write_json(output_dir / "model-routing.json", model_routes)

        _write_json(output_dir / "issue.json", brief.to_dict())
        if _stage_callback:
            _stage_callback(
                'clone',
                {"repository": brief.repository, "issue_number": brief.number},
            )
        clone_public_github_repo(
            brief.repository,
            workspace,
            scratch_root=scratch,
            timeout_seconds=min(timeout, 900),
        )

        context_diagnostics: dict = {}
        try:
            repository_context = collect_repo_context(
                workspace,
                brief=brief,
                diagnostics=context_diagnostics,
            )
        except Exception:
            if not context_diagnostics:
                context_diagnostics = {
                    "schema_version": 1,
                    "status": "unavailable",
                    "reason": "context_collection_failed",
                }
            elif context_diagnostics.get("status") == "in_progress":
                context_diagnostics["status"] = "interrupted"
                context_diagnostics["reason"] = "context_collection_interrupted"
            _write_json(output_dir / "context-report.json", context_diagnostics)
            raise

        _write_json(output_dir / "context-report.json", context_diagnostics)

        if _stage_callback:
            _stage_callback('plan')
        try:
            task_plan = plan_github_issue(
                brief,
                repository_context=repository_context,
                model=planning_route.model,
                timeout=min(timeout, 900),
                usage_sink=model_usage,
            )
        finally:
            _write_json(output_dir / "model-usage.json", {
                "summary": _model_usage_summary(model_usage), "calls": model_usage,
            })
        _write_json(output_dir / "plan.json", task_plan.to_dict())
        estimated_effort = float(task_plan.estimated_effort_hours)
        estimated_gross_per_hour = (
            round(reward_amount / estimated_effort, 2)
            if reward_amount is not None and estimated_effort > 0
            else None
        )

        if _stage_callback:
            _stage_callback('draft')
        try:
            proposal = draft_patch(
                brief,
                workspace,
                model=drafting_route.model,
                timeout=min(timeout, 900),
                plan=task_plan,
                repository_context=repository_context,
                context_diagnostics=context_diagnostics,
                usage_sink=model_usage,
            )
        except Exception as exc:
            # Preserve whatever repository-intelligence diagnostics were
            # collected, even when drafting cannot produce a proposal.
            if not context_diagnostics:
                context_diagnostics = {
                    "schema_version": 1,
                    "status": "unavailable",
                    "reason": "context_collection_diagnostics_not_returned",
                }
            elif context_diagnostics.get("status") == "in_progress":
                context_diagnostics["status"] = "interrupted"
                context_diagnostics["reason"] = "context_collection_interrupted"

            _write_json(output_dir / "context-report.json", context_diagnostics)
            finished_at = datetime.now(timezone.utc).isoformat()
            failure_manifest = {
                "schema_version": 1,
                "run_id": run_id,
                "started_at": started_at,
                "finished_at": finished_at,
                "task": {
                    "issue_url": brief.url,
                    "issue_title": brief.title,
                    "repository": brief.repository,
                    "issue_snapshot_sha256": _sha256_file(output_dir / "issue.json"),
                    "source_commit_sha": _git_commit(workspace),
                },
                "agent": {
                    "model": model or os.getenv("AI_WORKER_MODEL") or "unavailable",
                    "patch_schema": "patch-schema-v1",
                    "policy_version": "2026-11-15",
                    "reviewer_stage": "not_run",
                    "reviewer_model": None,
                    "reviewer_findings": [],
                },
                "execution": {
                    "python_image": image,
                    "node_image": node_image,
                    "timeout_seconds": timeout,
                    "max_output_bytes": MAX_OUTPUT_BYTES,
                    "network_access": "disabled_in_task_containers",
                    "external_actions": [],
                },
                "model_routing": model_routes,
                "model_usage": {
                    "summary": _model_usage_summary(model_usage), "calls": model_usage,
                },
                "escalation": {
                    "required": True,
                    "performed": False,
                    "target": "human_or_separately_authorized_higher_tier",
                    "reason": "Local patch drafting failed; no remote provider or Codex bridge is configured.",
                },
                "assessment": {
                    "risk_level": task_plan.risk_level,
                    "blockers": task_plan.blockers,
                    "acceptance_checklist": task_plan.acceptance_checklist,
                    "estimated_effort_hours": estimated_effort,
                },
                "proposal": {
                    "status": "unavailable",
                    "changed_files": [],
                    "patch_sha256": None,
                    "no_patch_reason": "draft_generation_failed",
                    "context_report": "context-report.json",
                },
                "checks": {
                    "python_compile": {"ran": False, "exit_code": None},
                    "pytest": {"detected": False, "ran": False, "exit_code": None},
                    "javascript_typescript_syntax": {"ran": False, "exit_code": None},
                    "dependency_aware_node_tests": {
                        "ran": False,
                        "reason": "Draft generation failed before QA execution.",
                    },
                },
                "outcome": {
                    "status": "draft_failed",
                    "error_type": type(exc).__name__,
                    "failed_stage": "draft",
                },
                "human_approval_required": True,
            }
            _write_json(output_dir / "run-manifest.json", failure_manifest)
            raise
        _write_json(output_dir / "model-usage.json", {
            "summary": _model_usage_summary(model_usage), "calls": model_usage,
        })
        context_diagnostics = (
            getattr(proposal, "context_diagnostics", None) or context_diagnostics
        )
        if not context_diagnostics:
            context_diagnostics = {
                "schema_version": 1,
                "status": "unavailable",
                "reason": "context_collection_diagnostics_not_returned",
            }
        _write_json(output_dir / "context-report.json", context_diagnostics)
        _write_json(output_dir / "proposal.json", proposal.to_dict())
        if proposal.status == "patch":
            (output_dir / "proposal.patch").write_text(proposal.diff, encoding="utf-8")

        reviewer_verdict = "not_run"
        reviewer_summary = "No patch was available for review."
        reviewer_findings: list[dict] = []
        reviewer_error = ""
        repair_error = ""
        review_history: list[dict] = []
        repair_history: list[dict] = []

        effective_reviewer_model = reviewer_route.model

        # Keep the original file authorization boundary for every repair.
        authorized_repair_files = list(proposal.changed_files)
        current_diff = proposal.diff
        current_changed_files = list(proposal.changed_files)
        current_summary = getattr(proposal, "summary", "")
        verification_evidence = {
            "schema_version": 1,
            "patch_applied": False,
            "checks": [],
            "passed": False,
            "status": "not_run",
        }
        verification_attempts: list[dict] = []

        verification_eligible = (
            proposal.status == "patch"
            and not proposal.questions
            and not task_plan.blockers
            and bool(task_plan.acceptance_checklist)
            and task_plan.risk_level != "high"
            and not (reward_amount is not None and reward_amount > 500)
            and effective_reviewer_model != proposal.model
            and (
                _has_python_files(workspace)
                or any(Path(path).suffix.lower() == ".py" for path in proposal.changed_files)
            )
        )
        if verification_eligible:
            for verification_attempt in range(MAX_REPAIR_ATTEMPTS + 1):
                if _stage_callback:
                    _stage_callback(
                        "verify",
                        {"phase": "pre-review", "attempt": verification_attempt},
                    )
                verification_evidence = _run_candidate_verification(
                    current_diff,
                    current_changed_files,
                    workspace,
                    task_plan,
                    scratch=scratch,
                    image=image,
                    timeout=timeout,
                )
                verification_evidence["status"] = (
                    "passed" if verification_evidence.get("passed")
                    else "failed_or_incomplete"
                )
                verification_attempts.append(
                    json.loads(json.dumps(verification_evidence, ensure_ascii=False))
                )
                if _verification_gate(verification_evidence):
                    break

                qa_findings = _verification_findings(
                    verification_evidence, authorized_repair_files
                )
                if (
                    verification_evidence.get("patch_applied") is True
                    and not _has_required_checks(verification_evidence)
                ):
                    break
                if (
                    not qa_findings
                    or len(repair_history) >= MAX_REPAIR_ATTEMPTS
                ):
                    break

                try:
                    repaired = repair_patch(
                        brief,
                        str(workspace),
                        model=proposal.model,
                        current_diff=current_diff,
                        findings=qa_findings,
                        allowed_files=authorized_repair_files,
                        plan=task_plan,
                        repository_context=repository_context,
                        timeout=min(timeout, 900),
                        usage_sink=model_usage,
                    )
                    repaired_diff = getattr(repaired, "diff", None)
                    repaired_files = getattr(repaired, "changed_files", None)
                    if (
                        getattr(repaired, "status", None) != "patch"
                        or not isinstance(repaired_diff, str)
                        or not repaired_diff.strip()
                        or not isinstance(repaired_files, list)
                        or not repaired_files
                        or set(repaired_files) - set(authorized_repair_files)
                        or repaired_diff.strip() == current_diff.strip()
                    ):
                        raise PatchError(
                            "Test-feedback repair was invalid, unchanged, or outside the original file scope"
                        )
                    current_diff = repaired_diff
                    current_changed_files = list(repaired_files)
                    current_summary = getattr(repaired, "summary", "")
                    verification_evidence = _run_candidate_verification(
                        current_diff, current_changed_files, workspace,
                        task_plan,
                        scratch=scratch, image=image, timeout=timeout,
                    )
                    verification_evidence["status"] = (
                        "passed" if verification_evidence.get("passed")
                        else "failed_or_incomplete"
                    )
                    verification_attempts.append(
                        json.loads(json.dumps(verification_evidence, ensure_ascii=False))
                    )
                    repair_history.append({
                        "attempt": verification_attempt + 1,
                        "status": "repaired_after_verification_failure",
                        "summary": getattr(repaired, "summary", "Repaired after failed verification."),
                        "changed_files": current_changed_files,
                        "findings": qa_findings,
                    })
                except PatchError as exc:
                    repair_error = str(exc)
                    repair_history.append({
                        "attempt": verification_attempt + 1,
                        "status": "failed",
                        "error": repair_error,
                        "findings": qa_findings,
                    })
                    break

        verification_with_history = {
            **verification_evidence,
            "attempts": verification_attempts,
        }
        _write_json(output_dir / "verification.json", {
            "pre_review": verification_with_history,
        })

        if _stage_callback:
            _stage_callback("review")

        if proposal.status == "patch":
            if effective_reviewer_model == proposal.model:
                reviewer_verdict = "unavailable"
                reviewer_summary = "Independent review could not be completed."
                reviewer_error = (
                    "Reviewer model must differ from the patch generator model"
                )
                unavailable_review = {
                    "verdict": "unavailable",
                    "summary": reviewer_summary,
                    "error": reviewer_error,
                    "findings": [],
                }
                review_history.append({
                    "review_number": 1,
                    **unavailable_review,
                })
                _write_json(output_dir / "review.json", unavailable_review)
            else:
                for review_index in range(MAX_REPAIR_ATTEMPTS + 1):
                    if review_index and _stage_callback:
                        _stage_callback(
                            "review",
                            {
                                "phase": "re-review",
                                "attempt": review_index,
                            },
                        )

                    try:
                        review_verification_evidence = {
                            **verification_evidence,
                            "attempts": verification_attempts,
                        }
                        review = review_patch(
                            brief,
                            str(workspace),
                            current_diff,
                            model=effective_reviewer_model,
                            repository_context=repository_context,
                            task_plan=task_plan.to_dict(),
                            verification_evidence=review_verification_evidence,
                            timeout=min(timeout, 900),
                            usage_sink=model_usage,
                        )
                    except ReviewerError as exc:
                        reviewer_verdict = "unavailable"
                        reviewer_summary = (
                            "Independent review could not be completed."
                        )
                        reviewer_error = str(exc)
                        unavailable_review = {
                            "verdict": "unavailable",
                            "summary": reviewer_summary,
                            "error": reviewer_error,
                            "findings": [],
                        }
                        review_history.append({
                            "review_number": review_index + 1,
                            **unavailable_review,
                        })
                        _write_json(
                            output_dir / "review.json",
                            unavailable_review,
                        )
                        break

                    review_payload = review.to_dict()
                    review_history.append({
                        "review_number": review_index + 1,
                        **review_payload,
                    })
                    _write_json(
                        output_dir / f"review-{review_index + 1}.json",
                        review_payload,
                    )
                    _write_json(output_dir / "review.json", review_payload)

                    reviewer_verdict = review.verdict
                    reviewer_summary = review.summary
                    reviewer_findings = [
                        {
                            "severity": item.severity,
                            "file": item.file,
                            "line": item.line,
                            "title": item.title,
                            "evidence": item.evidence,
                            "recommendation": item.recommendation,
                        }
                        for item in review.findings
                    ]

                    if reviewer_verdict == "pass":
                        break

                    if reviewer_verdict not in {"needs_changes", "blocked"}:
                        reviewer_verdict = "unavailable"
                        reviewer_error = "Reviewer returned an unsupported verdict."
                        reviewer_summary = (
                            "Independent review returned an invalid verdict."
                        )
                        break

                    if len(repair_history) >= MAX_REPAIR_ATTEMPTS:
                        repair_error = (
                            f"Maximum bounded repair attempts "
                            f"({MAX_REPAIR_ATTEMPTS}) exhausted."
                        )
                        break

                    if not review.findings:
                        repair_error = (
                            "Reviewer reported unresolved changes without findings."
                        )
                        break

                    repair_number = review_index + 1

                    if _stage_callback:
                        _stage_callback(
                            "review",
                            {
                                "phase": "repair",
                                "attempt": repair_number,
                            },
                        )

                    findings_payload = [
                        {
                            "severity": item.severity,
                            "file": item.file,
                            "line": item.line,
                            "title": item.title,
                            "evidence": item.evidence,
                            "recommendation": item.recommendation,
                        }
                        for item in review.findings
                    ]

                    try:
                        repaired = repair_patch(
                            brief,
                            str(workspace),
                            model=proposal.model,
                            current_diff=current_diff,
                            findings=findings_payload,
                            allowed_files=authorized_repair_files,
                            plan=task_plan,
                            repository_context=repository_context,
                            timeout=min(timeout, 900),
                            usage_sink=model_usage,
                        )

                        if getattr(repaired, "status", None) != "patch":
                            raise PatchError(
                                "Repair did not return a valid patch proposal"
                            )

                        repaired_diff = getattr(repaired, "diff", None)
                        repaired_files = getattr(repaired, "changed_files", None)

                        if (
                            not isinstance(repaired_diff, str)
                            or not repaired_diff.strip()
                        ):
                            raise PatchError(
                                "Repair returned an empty or invalid diff"
                            )

                        if (
                            not isinstance(repaired_files, list)
                            or not repaired_files
                            or any(
                                not isinstance(path, str) or not path
                                for path in repaired_files
                            )
                        ):
                            raise PatchError(
                                "Repair returned an invalid changed-file list"
                            )

                        unexpected_files = (
                            set(repaired_files) - set(authorized_repair_files)
                        )
                        if unexpected_files:
                            raise PatchError(
                                "Repair attempted to modify files outside "
                                "the original patch: "
                                + ", ".join(sorted(unexpected_files))
                            )

                        if repaired_diff.strip() == current_diff.strip():
                            raise PatchError(
                                "Repair returned the unchanged patch"
                            )

                        current_diff = repaired_diff
                        current_changed_files = list(repaired_files)
                        current_summary = repaired.summary
                        verification_evidence = _run_candidate_verification(
                            current_diff, current_changed_files, workspace,
                            task_plan,
                            scratch=scratch, image=image, timeout=timeout,
                        )
                        verification_evidence["status"] = (
                            "passed" if verification_evidence.get("passed")
                            else "failed_or_incomplete"
                        )
                        verification_attempts.append(
                            json.loads(json.dumps(verification_evidence, ensure_ascii=False))
                        )

                        repair_history.append({
                            "attempt": repair_number,
                            "status": "repaired",
                            "summary": repaired.summary,
                            "changed_files": current_changed_files,
                        })

                    except PatchError as exc:
                        repair_error = str(exc)
                        repair_history.append({
                            "attempt": repair_number,
                            "status": "failed",
                            "error": repair_error,
                        })
                        break

        # Persist the final candidate, not merely the original draft.
        proposal.diff = current_diff
        proposal.changed_files = current_changed_files
        proposal.summary = current_summary

        _write_json(output_dir / "proposal.json", proposal.to_dict())

        if proposal.status == "patch":
            (output_dir / "proposal.patch").write_text(
                current_diff,
                encoding="utf-8",
            )

        _write_json(
            output_dir / "review-history.json",
            {"reviews": review_history},
        )
        _write_json(
            output_dir / "repair-history.json",
            {"attempts": repair_history},
        )

        node_static_code = None
        node_static_log = ""
        node_project_info = None
        node_project_error = ""
        node_test_code = None
        node_build_code = None
        node_test_log = ""
        node_build_log = ""
        node_check_reason = None
        node_changed_files: list[str] = []
        if reviewer_verdict == "unavailable":
            status = "reviewer_unavailable_blocked"
            message = "Independent review was unavailable or invalid; fail-closed policy prevented patch application. " + reviewer_error
            compile_code = tests_code = None
            tests_detected = False
            compile_log = tests_log = ""
        elif reviewer_verdict in {"needs_changes", "blocked"}:
            status = "review_blocked"
            message = "Independent reviewer found unresolved issues; patch was not applied. " + reviewer_summary
            if repair_error:
                message += " Bounded repair stopped: " + repair_error
            compile_code = tests_code = None
            tests_detected = False
            compile_log = tests_log = ""
        elif proposal.status == "needs_information":
            status = "needs_human_clarification"
            message = "The model did not produce a safe diff. Review the plan and questions; no patch was applied."
            compile_code = tests_code = None
            tests_detected = False
            compile_log = tests_log = ""
        elif (
            proposal.status == "patch"
            and _has_required_checks(verification_evidence)
            and not _verification_gate(verification_evidence)
        ):
            status = "verification_failed"
            message = (
                "Required pre-review verification failed or was incomplete; "
                "the reviewer verdict cannot authorize patch application."
            )
            if repair_error:
                message += " Bounded test-feedback repair stopped: " + repair_error
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
            if _stage_callback:
                _stage_callback('apply')
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
                if _stage_callback:
                    _stage_callback('verify')
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
                    if Path(path).suffix.lower() in {
                        ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"
                    }
                ]

                node_metadata_names = {
                    "package.json",
                    "package-lock.json",
                    "npm-shrinkwrap.json",
                    "pnpm-lock.yaml",
                    "yarn.lock",
                    "bun.lock",
                    "bun.lockb",
                }
                node_related_changes = bool(node_changed_files) or any(
                    Path(path).name in node_metadata_names
                    for path in proposal.changed_files
                )

                if node_related_changes:
                    try:
                        node_project_info = inspect_node_project(workspace)
                        _write_json(
                            output_dir / "node-project.json",
                            node_project_info.to_dict(),
                        )
                    except NodeProjectError as exc:
                        node_project_error = str(exc)
                        _write_json(
                            output_dir / "node-project.json",
                            {
                                "status": "invalid",
                                "reason": node_project_error,
                            },
                        )

                if node_changed_files:
                    node_result = run_in_sandbox(
                        workspace,
                        ["esbuild", *node_changed_files, "--outdir=/tmp/ai-worker-check"],
                        scratch_root=scratch,
                        image=node_image,
                        timeout_seconds=min(timeout, 300),
                    )
                    node_static_code = node_result.exit_code
                    node_static_log = (
                        node_result.stdout + "\n" + node_result.stderr
                    ).strip()
                    (output_dir / "node-static.log").write_text(
                        node_static_log,
                        encoding="utf-8",
                    )
                if node_project_error:
                    status = "node_project_invalid"
                    message = (
                        "Node project metadata failed safe inspection. "
                        "No dependency installation or Node test/build was attempted. "
                        + node_project_error
                    )
                elif (
                    (compile_code is not None and compile_code != 0)
                    or (node_static_code is not None and node_static_code != 0)
                ):
                    status = "compile_failed"
                    message = "An isolated syntax/static check failed. Review the relevant sandbox logs before proceeding."
                else:
                    # Python tests run first. Node QA is eligible only after
                    # Python checks have passed (or when no Python tests exist).
                    if tests_detected:
                        test_result = run_in_sandbox(
                            workspace,
                            ["python", "-m", "pytest", "-q"],
                            scratch_root=scratch,
                            image=image,
                            timeout_seconds=min(timeout, 600),
                        )
                        tests_code = test_result.exit_code
                        tests_log = (
                            test_result.stdout + "\\n" + test_result.stderr
                        ).strip()
                        (output_dir / "pytest.log").write_text(
                            tests_log, encoding="utf-8"
                        )

                    if tests_code is not None and tests_code != 0:
                        status = "tests_failed"
                        message = (
                            "The patch was applied, but the isolated pytest run "
                            "failed. Node test/build checks were not attempted."
                        )
                    else:
                        node_scripts_detected = bool(
                            node_project_info
                            and (
                                node_project_info.has_test_script
                                or node_project_info.has_build_script
                            )
                        )

                        if node_scripts_detected:
                            if node_project_info.status != "ready":
                                node_check_reason = (
                                    "Node project metadata is not supported for "
                                    "automated test/build execution: "
                                    + (node_project_info.reason or node_project_info.status)
                                )
                            elif node_project_info.has_dependencies:
                                node_check_reason = (
                                    "External Node dependencies are declared. "
                                    "Dependency installation is disabled and "
                                    "Node test/build scripts were not executed."
                                )
                            else:
                                node_check_reason = (
                                    "No external dependencies are declared; "
                                    "Node scripts are executed offline in the sandbox."
                                )

                                if node_project_info.has_test_script:
                                    node_result = run_in_sandbox(
                                        workspace,
                                        ["node", "--run", "test"],
                                        scratch_root=scratch,
                                        image=node_image,
                                        timeout_seconds=min(timeout, 600),
                                        network_enabled=False,
                                    )
                                    node_test_code = node_result.exit_code
                                    node_test_log = (
                                        node_result.stdout + "\n"
                                        + node_result.stderr
                                    ).strip()
                                    (output_dir / "node-test.log").write_text(
                                        node_test_log, encoding="utf-8"
                                    )

                                if (
                                    node_test_code is None
                                    or node_test_code == 0
                                ):
                                    if node_project_info.has_build_script:
                                        node_result = run_in_sandbox(
                                            workspace,
                                            ["node", "--run", "build"],
                                            scratch_root=scratch,
                                            image=node_image,
                                            timeout_seconds=min(timeout, 600),
                                            network_enabled=False,
                                        )
                                        node_build_code = node_result.exit_code
                                        node_build_log = (
                                            node_result.stdout + "\n"
                                            + node_result.stderr
                                        ).strip()
                                        (output_dir / "node-build.log").write_text(
                                            node_build_log, encoding="utf-8"
                                        )

                            if (
                                node_project_info.status != "ready"
                                or node_project_info.has_dependencies
                            ):
                                status = "node_checks_not_run"
                                message = (
                                    "Node test/build scripts were detected but "
                                    "could not be executed under the current "
                                    "offline dependency policy. Human review is required. "
                                    + node_check_reason
                                )
                            elif node_test_code is not None and node_test_code != 0:
                                status = "node_tests_failed"
                                message = (
                                    "The Node test script failed in the isolated "
                                    "network-disabled sandbox. The build was skipped."
                                )
                            elif node_build_code is not None and node_build_code != 0:
                                status = "node_build_failed"
                                message = (
                                    "The Node test checks passed or were absent, "
                                    "but the Node build script failed in the isolated "
                                    "network-disabled sandbox."
                                )
                            else:
                                status = "ready_for_human_review"
                                message = (
                                    "Available Python checks and eligible "
                                    "dependency-free Node test/build checks passed "
                                    "in isolated sandboxes. No submission was made."
                                )
                        elif tests_detected:
                            status = "ready_for_human_review"
                            message = (
                                "Patch applied in the disposable sandbox; "
                                "detected pytest suite passed. No submission was made."
                            )

                        elif compile_code is None and node_static_code is None:
                            status = "no_automated_tests_detected"
                            message = (
                                "No supported source files or automated test "
                                "scripts were detected. Human review is required."
                            )
                        else:
                            status = "static_check_passed_no_tests"
                            checks = []
                            if compile_code == 0:
                                checks.append("Python syntax check passed")
                            if node_static_code == 0:
                                checks.append(
                                    "JavaScript/TypeScript syntax transpilation "
                                    "passed with esbuild"
                                )
                            message = (
                                "; ".join(checks)
                                + ". No automated test suite was detected. "
                                "Human review is required."
                            )

        final_checks = []
        if _has_python_files(workspace):
            final_checks.append({
                "name": "python_compile", "required": True,
                "ran": compile_code is not None, "exit_code": compile_code,
                "timed_out": False,
            })
        if tests_detected:
            final_checks.append({
                "name": "pytest", "required": True,
                "ran": tests_code is not None, "exit_code": tests_code,
                "timed_out": False,
            })
        if node_changed_files:
            final_checks.append({
                "name": "javascript_typescript_syntax", "required": True,
                "ran": node_static_code is not None, "exit_code": node_static_code,
                "timed_out": False,
            })
        if node_project_info and node_project_info.has_test_script:
            final_checks.append({
                "name": "node_test", "required": True,
                "ran": node_test_code is not None, "exit_code": node_test_code,
                "timed_out": False,
            })
        if node_project_info and node_project_info.has_build_script:
            final_checks.append({
                "name": "node_build", "required": True,
                "ran": node_build_code is not None, "exit_code": node_build_code,
                "timed_out": False,
            })
        if reviewer_verdict == "pass":
            final_checks.append({
                "name": "independent_review", "required": True,
                "ran": True, "exit_code": 0, "timed_out": False,
            })
        final_verification = {
            "schema_version": 1,
            "patch_applied": status in {
                "ready_for_human_review", "tests_failed", "compile_failed",
                "node_project_invalid", "node_checks_not_run", "node_tests_failed",
                "node_build_failed", "no_automated_tests_detected",
                "static_check_passed_no_tests",
            },
            "checks": final_checks,
        }
        final_verification["passed"] = _verification_gate(final_verification)
        verification_evidence["final"] = final_verification
        verification_with_history = {
            **verification_evidence,
            "attempts": verification_attempts,
        }
        _write_json(output_dir / "verification.json", {
            "pre_review": verification_with_history,
            "final": final_verification,
        })
        if status == "ready_for_human_review" and not final_verification["passed"]:
            status = "verification_incomplete"
            message = (
                "The candidate lacks complete passing evidence for every required "
                "automated and independent-review check; it is not eligible for handoff."
            )

        model_usage_summary = _model_usage_summary(model_usage)
        _write_json(output_dir / "model-usage.json", {
            "summary": model_usage_summary, "calls": model_usage,
        })

        if _stage_callback:
            _stage_callback('finalize')
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
            reviewer_verdict=reviewer_verdict,
            reviewer_summary=reviewer_summary,
            reviewer_findings=reviewer_findings,
            message=message,
            node_project=(
                node_project_info.to_dict()
                if node_project_info is not None
                else (
                    {"status": "invalid", "reason": node_project_error}
                    if node_project_error
                    else None
                )
            ),
            node_test_exit_code=node_test_code,
            node_build_exit_code=node_build_code,
            node_test_log=node_test_log,
            node_build_log=node_build_log,
            node_check_reason=node_check_reason,
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
            f"- Independent reviewer model: {effective_reviewer_model}",
            f"- Independent reviewer verdict: {reviewer_verdict}",
            f"- Independent reviewer summary: {reviewer_summary}",
            f"- Bounded repair attempts: {len(repair_history)} / {MAX_REPAIR_ATTEMPTS}",
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
            f"- Node project status: {node_project_info.status if node_project_info else ('invalid' if node_project_error else 'not checked')}",
            f"- Node package manager: {node_project_info.package_manager if node_project_info else 'Unknown'}",
            f"- Node lockfile: {node_project_info.lockfile if node_project_info else 'Unknown'}",
            f"- Node test script detected: {'yes' if node_project_info and node_project_info.has_test_script else 'no'}",
            f"- Node build script detected: {'yes' if node_project_info and node_project_info.has_build_script else 'no'}",
            "- Node test exit: " + (str(node_test_code) if node_test_code is not None else "Not run"),
            "- Node test log: " + ("node-test.log" if node_test_code is not None else "Not generated"),
            "- Node build exit: " + (str(node_build_code) if node_build_code is not None else "Not run"),
            "- Node build log: " + ("node-build.log" if node_build_code is not None else "Not generated"),
            "- Node QA reason: " + (node_check_reason or "No Node test/build scripts required execution"),
            "- Node dependency installation: Not performed; network access remains disabled",
            "",
            message,
            "",
            "## Mandatory approval boundary",
            "This is a draft for human review only. AI-Worker did not claim the bounty, contact anyone, commit, push, open a pull request, or submit work.",
            "",
            "Review issue terms, ownership/licensing, acceptance criteria, changed files, test logs, and payout conditions before any external action.",
            "",
        ]

        if review_history:
            lines.extend(["## Review history", ""])
            for item in review_history:
                lines.append(
                    f"- Review {item['review_number']}: "
                    f"**{item['verdict']}** — {item['summary']}"
                )
            lines.append("")

        if repair_history:
            lines.extend(["## Bounded repair history", ""])
            for item in repair_history:
                if item["status"].startswith("repaired"):
                    lines.append(
                        f"- Attempt {item['attempt']}: "
                        f"repaired `{', '.join(item['changed_files'])}` — "
                        f"{item['summary']}"
                    )
                else:
                    lines.append(
                        f"- Attempt {item['attempt']}: failed — {item['error']}"
                    )
            lines.append("")

        if reviewer_findings:
            lines.extend(["## Independent review findings", ""])
            for finding in reviewer_findings:
                lines.extend([
                    f"- **{finding['severity'].upper()}** — `{finding['file']}:{finding['line']}`: {finding['title']}",
                    f"  - Evidence: {finding['evidence']}",
                    f"  - Recommendation: {finding['recommendation']}",
                ])
            lines.append("")
        (output_dir / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
        finished_at = datetime.now(timezone.utc).isoformat()
        issue_snapshot = output_dir / "issue.json"
        proposal_file = output_dir / "proposal.patch"
        manifest = {
            "schema_version": 1,
            "run_id": run_id,
            "started_at": started_at,
            "finished_at": finished_at,
            "task": {
                "issue_url": brief.url,
                "issue_title": brief.title,
                "repository": brief.repository,
                "issue_snapshot_sha256": _sha256_file(issue_snapshot),
                "source_commit_sha": _git_commit(workspace),
            },
            "agent": {
                "model": proposal.model,
                "patch_schema": "patch-schema-v1",
                "policy_version": "2026-11-15",
                "reviewer_stage": reviewer_verdict,
                "reviewer_model": effective_reviewer_model,
                "reviewer_findings": reviewer_findings,
                "repair_attempt_count": len(repair_history),
                "review_history_path": "review-history.json",
                "repair_history_path": "repair-history.json",
            },
            "execution": {
                "python_image": image,
                "node_image": node_image,
                "timeout_seconds": timeout,
                "max_output_bytes": MAX_OUTPUT_BYTES,
                "network_access": "disabled_in_task_containers",
                "external_actions": [],
            },
            "model_routing": model_routes,
            "model_usage": {
                "summary": model_usage_summary,
                "calls": model_usage,
                "artifact": "model-usage.json",
            },
            "escalation": {
                "required": status not in {"ready_for_human_review"},
                "performed": False,
                "target": "human_or_separately_authorized_higher_tier",
                "reason": (
                    "No remote provider or Codex bridge is configured;"
                    " no escalation request was sent."
                ),
            },
            "assessment": {
                "risk_level": task_plan.risk_level,
                "blockers": task_plan.blockers,
                "acceptance_checklist": task_plan.acceptance_checklist,
                "estimated_effort_hours": estimated_effort,
            },
            "proposal": {
                "status": proposal.status,
                "summary": getattr(proposal, "summary", ""),
                "changed_files": proposal.changed_files,
                "patch_sha256": _sha256_file(proposal_file),
                "no_patch_reason": (
                    "model_requested_clarification"
                    if proposal.status == "needs_information"
                    else None
                ),
                "context_report": "context-report.json",
            },
            "checks": {
                "pre_review_verification": verification_with_history,
                "final_verification": final_verification,
                "python_compile": {"ran": compile_code is not None, "exit_code": compile_code},
                "pytest": {"detected": tests_detected, "ran": tests_code is not None, "exit_code": tests_code},
                "javascript_typescript_syntax": {"ran": node_static_code is not None, "exit_code": node_static_code},
                "node_project": (
                    node_project_info.to_dict()
                    if node_project_info is not None
                    else (
                        {"status": "invalid", "reason": node_project_error}
                        if node_project_error
                        else {"status": "not_checked"}
                    )
                ),
                "dependency_aware_node_tests": {
                    "detected": bool(
                        node_project_info
                        and node_project_info.has_test_script
                    ),
                    "ran": node_test_code is not None,
                    "exit_code": node_test_code,
                    "package_manager": (
                        node_project_info.package_manager
                        if node_project_info else None
                    ),
                    "lockfile": (
                        node_project_info.lockfile
                        if node_project_info else None
                    ),
                    "log": "node-test.log" if node_test_code is not None else None,
                    "reason": (
                        node_check_reason
                        or ("Node test script passed." if node_test_code == 0 else "No Node test script was detected.")
                    ),
                },
                "node_build": {
                    "detected": bool(
                        node_project_info
                        and node_project_info.has_build_script
                    ),
                    "ran": node_build_code is not None,
                    "exit_code": node_build_code,
                    "log": "node-build.log" if node_build_code is not None else None,
                    "reason": (
                        node_check_reason
                        or ("Node build script passed." if node_build_code == 0 else "No Node build script was detected.")
                    ),
                },
            },
            "outcome": {"status": status, "message": message},
            "human_approval_required": True,
        }
        _write_json(output_dir / "run-manifest.json", manifest)
        return result
    except (GitHubIssueError, WorkspaceError, OllamaError, PatchError, SandboxError) as exc:
        raise PipelineError(str(exc)) from exc


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
    reviewer_model: str | None = None,
    db_path: str | Path | None = None,
) -> PipelineResult:
    """Run the pipeline and optionally persist its execution lifecycle."""
    run_id = uuid.uuid4().hex
    if db_path is None:
        return _run_pipeline_impl(
            issue_url,
            scratch_root=scratch_root,
            output_root=output_root,
            image=image,
            node_image=node_image,
            model=model,
            reward_amount=reward_amount,
            currency=currency,
            timeout=timeout,
            reviewer_model=reviewer_model,
            _run_id=run_id,
        )

    db = connect(db_path)
    try:
        create_task_run(db, run_id, issue_url)

        def record_stage(stage: str, metadata: dict | None = None) -> None:
            metadata = metadata or {}
            advance_task_run(
                db,
                run_id,
                stage,
                details=metadata,
                repository=metadata.get("repository"),
                issue_number=metadata.get("issue_number"),
            )

        try:
            result = _run_pipeline_impl(
                issue_url,
                scratch_root=scratch_root,
                output_root=output_root,
                image=image,
                node_image=node_image,
                model=model,
                reward_amount=reward_amount,
                currency=currency,
                timeout=timeout,
                reviewer_model=reviewer_model,
                _run_id=run_id,
                _stage_callback=record_stage,
            )
        except Exception as exc:
            try:
                advance_task_run(
                    db, run_id, "failed",
                    status="failed",
                    details={"error": str(exc)},
                    error=str(exc),
                    finished=True,
                )
            except Exception as persistence_error:
                exc.add_note(
                    "Additionally, persisting the failed task lifecycle "
                    f"state failed: {persistence_error}"
                )
            raise

        advance_task_run(
            db, run_id, "complete",
            status="completed",
            details={"result": result.to_dict()},
            output_dir=result.output_dir,
            result_json=json.dumps(result.to_dict(), ensure_ascii=False),
            result_status=result.status,
            finished=True,
        )
        return result
    finally:
        db.close()
