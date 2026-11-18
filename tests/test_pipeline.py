import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_worker import pipeline
from ai_worker.models import Gig
from ai_worker.sources.github_issue import ResearchBrief

SIMPLE_DIFF = """diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -1 +1 @@
-before
+after
"""


def _allow_preflight_only(diff, workspace, **kwargs):
    if "ai-worker-verify-" in str(workspace):
        return SimpleNamespace(applied=True, message="pre-review candidate verified")
    pytest.fail("patch must not be applied to the task workspace")


@pytest.fixture(autouse=True)
def allow_pipeline_tests_to_stub_independent_review(monkeypatch):
    monkeypatch.setattr(
        pipeline,
        "review_patch",
        lambda *args, **kwargs: SimpleNamespace(
            verdict="pass", summary="No actionable findings.", findings=[],
            to_dict=lambda: {"verdict": "pass", "summary": "No actionable findings.", "findings": []},
        ),
    )


def eligible_gig(**changes):
    data = dict(
        id="algora:42",
        title="Fix Python API tests",
        url="https://github.com/acme/widget/issues/42",
        summary="Fix backend bug and add tests",
        tags=["python", "api"],
        lane="agent",
        reward_amount=25,
        currency="USD",
        payout_grade="B",
        payment_state="escrowed",
        payment_rail="stripe",
        acceptance="PR merged with tests passing",
        acceptance_type="human-review",
        claims_open=True,
    )
    data.update(changes)
    return Gig(**data)


def brief(state="open"):
    return ResearchBrief(
        url="https://github.com/acme/widget/issues/42",
        title="Fix Python API tests",
        repository="acme/widget",
        number=42,
        state=state,
        body="Add tests for the API.",
        labels=["bug"],
        updated_at="2026-11-14T00:00:00Z",
    )


def test_resolve_eligible_gig_requires_current_eligible_record():
    gig = eligible_gig()
    assert pipeline.resolve_eligible_gig(gig.id, [gig]).url == gig.url


def test_resolve_eligible_gig_rejects_missing_or_filtered_records():
    with pytest.raises(pipeline.PipelineError, match="not found"):
        pipeline.resolve_eligible_gig("missing", [eligible_gig()])
    with pytest.raises(pipeline.PipelineError, match="safety filters"):
        pipeline.resolve_eligible_gig("algora:42", [eligible_gig(payment_state="promised")])


def test_model_usage_summary_keeps_incomplete_token_totals_unknown():
    summary = pipeline._model_usage_summary([
        {"outcome": "accepted", "prompt_tokens": 10, "completion_tokens": 3},
        {"outcome": "request_failed", "prompt_tokens": 5, "completion_tokens": None},
    ])

    assert summary["call_count"] == 2
    assert summary["accepted_response_count"] == 1
    assert summary["failed_or_rejected_response_count"] == 1
    assert summary["calls_with_token_counts"] == 1
    assert summary["prompt_tokens"] == 10
    assert summary["completion_tokens"] == 3
    assert summary["total_tokens"] == 13
    assert summary["cost_usd"] is None


def test_pipeline_stops_for_closed_issue(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, "inspect_github_issue", lambda url: brief(state="closed"))
    with pytest.raises(pipeline.PipelineError, match="open GitHub issues"):
        pipeline.run_pipeline(
            brief().url,
            scratch_root=tmp_path / "scratch",
            output_root=tmp_path / "proposals",
        )


def test_pipeline_blocks_unresolved_questions_without_applying_patch(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, "inspect_github_issue", lambda url: brief())

    def fake_clone(repository, workspace, **kwargs):
        workspace.mkdir(parents=True)
        return SimpleNamespace(path=str(workspace))

    monkeypatch.setattr(pipeline, "clone_public_github_repo", fake_clone)
    monkeypatch.setattr(
        pipeline, "plan_github_issue",
        lambda *args, **kwargs: SimpleNamespace(
            risk_level="low", blockers=[], acceptance_checklist=["Acceptance verified"], estimated_effort_hours=2.0, to_dict=lambda: {"risk_level": "low"}
        ),
    )
    monkeypatch.setattr(
        pipeline, "draft_patch",
        lambda *args, **kwargs: SimpleNamespace(
            model="local", status="needs_information", diff="", changed_files=[],
            questions=["Need clarify API contract"], to_dict=lambda: {"diff": "draft"}
        ),
    )
    monkeypatch.setattr(
        pipeline, "apply_patch_in_sandbox",
        lambda *args, **kwargs: pytest.fail("patch must not be applied when questions remain"),
    )

    result = pipeline.run_pipeline(
        brief().url,
        scratch_root=tmp_path / "scratch",
        output_root=tmp_path / "proposals",
    )
    assert result.status == "needs_human_clarification"
    assert (tmp_path / "proposals").exists()
    output_dir = tmp_path / "proposals" / next((tmp_path / "proposals").iterdir()).name
    assert (output_dir / "REPORT.md").exists()
    context_report = json.loads((output_dir / "context-report.json").read_text())
    manifest = json.loads((output_dir / "run-manifest.json").read_text())
    assert context_report["status"] == "no_eligible_files"
    assert manifest["proposal"]["no_patch_reason"] == "model_requested_clarification"
    assert manifest["proposal"]["context_report"] == "context-report.json"


def test_pipeline_serializes_and_passes_structured_plan_to_drafter(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, "inspect_github_issue", lambda url: brief())

    def fake_clone(repository, workspace, **kwargs):
        workspace.mkdir(parents=True)
        (workspace / "client.py").write_text("class Client: pass\n", encoding="utf-8")
        return SimpleNamespace(path=str(workspace))

    monkeypatch.setattr(pipeline, "clone_public_github_repo", fake_clone)
    plan_data = {
        "summary": "Update client and cover it with tests.",
        "implementation_steps": ["Update the client", "Add client tests"],
        "steps": [
            {
                "id": "client",
                "description": "Update the client",
                "depends_on": [],
                "files": ["client.py"],
            },
            {
                "id": "tests",
                "description": "Add client tests",
                "depends_on": ["client"],
                "files": ["tests/test_client.py"],
            },
        ],
        "risk_level": "low",
        "blockers": [],
        "acceptance_checklist": ["Acceptance verified"],
        "estimated_effort_hours": 1.0,
    }
    task_plan = SimpleNamespace(
        risk_level="low",
        blockers=[],
        acceptance_checklist=["Acceptance verified"],
        estimated_effort_hours=1.0,
        to_dict=lambda: plan_data,
    )
    monkeypatch.setattr(pipeline, "plan_github_issue", lambda *args, **kwargs: task_plan)
    captured = {}

    def fake_draft(*args, **kwargs):
        captured["plan"] = kwargs["plan"]
        return SimpleNamespace(
            model="local",
            status="needs_information",
            diff="",
            changed_files=[],
            questions=["Need clarify API contract"],
            summary="Clarification needed.",
            to_dict=lambda: {"status": "needs_information", "diff": ""},
        )

    monkeypatch.setattr(pipeline, "draft_patch", fake_draft)
    result = pipeline.run_pipeline(
        brief().url,
        scratch_root=tmp_path / "scratch",
        output_root=tmp_path / "proposals",
    )

    assert result.status == "needs_human_clarification"
    assert captured["plan"] is task_plan
    output_plan = json.loads((Path(result.output_dir) / "plan.json").read_text())
    assert output_plan["steps"] == plan_data["steps"]


def test_pipeline_runs_compile_and_tests_in_sandbox(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, "inspect_github_issue", lambda url: brief())

    def fake_clone(repository, workspace, **kwargs):
        workspace.mkdir(parents=True)
        (workspace / "tests").mkdir()
        (workspace / "tests" / "test_smoke.py").write_text("def test_ok(): assert True")
        return SimpleNamespace(path=str(workspace))

    monkeypatch.setattr(pipeline, "clone_public_github_repo", fake_clone)
    monkeypatch.setattr(
        pipeline, "plan_github_issue",
        lambda *args, **kwargs: SimpleNamespace(
            risk_level="low", blockers=[], acceptance_checklist=["Acceptance verified"], estimated_effort_hours=2.0, to_dict=lambda: {"risk_level": "low"}
        ),
    )
    monkeypatch.setattr(
        pipeline, "draft_patch",
        lambda *args, **kwargs: SimpleNamespace(
            model="local", status="patch", diff=SIMPLE_DIFF, changed_files=["a.py"],
            questions=[], to_dict=lambda: {"diff": "draft"}
        ),
    )
    monkeypatch.setattr(
        pipeline, "apply_patch_in_sandbox",
        lambda *args, **kwargs: SimpleNamespace(applied=True, message="applied"),
    )
    calls = []

    def fake_run(workspace, command, **kwargs):
        calls.append(command)
        return SimpleNamespace(exit_code=0, stdout="checks passed", stderr="")

    monkeypatch.setattr(pipeline, "run_in_sandbox", fake_run)

    result = pipeline.run_pipeline(
        brief().url,
        scratch_root=tmp_path / "scratch",
        output_root=tmp_path / "proposals",
        reward_amount=25,
        currency="USD",
    )
    assert result.status == "ready_for_human_review"
    assert result.compile_exit_code == 0
    assert result.tests_exit_code == 0
    assert result.estimated_gross_per_hour == 12.5
    assert result.currency == "USD"
    assert calls == [
        ["python", "-m", "compileall", "-q", "."],
        ["python", "-m", "pytest", "-q"],
        ["python", "-m", "compileall", "-q", "."],
        ["python", "-m", "pytest", "-q"],
    ]
    assert "did not claim the bounty" in (
        (tmp_path / "proposals" / Path(result.output_dir).name / "REPORT.md").read_text()
    )

    manifest = json.loads((Path(result.output_dir) / "run-manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    assert manifest["task"]["repository"] == "acme/widget"
    assert manifest["agent"]["model"] == "local"
    assert manifest["agent"]["reviewer_stage"] == "pass"
    assert manifest["checks"]["python_compile"] == {"ran": True, "exit_code": 0}
    assert manifest["checks"]["pytest"] == {"detected": True, "ran": True, "exit_code": 0}
    assert manifest["checks"]["pre_review_verification"]["passed"] is True
    assert manifest["checks"]["final_verification"]["passed"] is True
    assert manifest["human_approval_required"] is True
    assert manifest["execution"]["external_actions"] == []
    assert manifest["execution"]["max_output_bytes"] == 1_000_000
    assert manifest["model_routing"]["planning"]["provider"] == "ollama_loopback"
    assert manifest["model_routing"]["review"]["provider"] == "ollama_loopback"
    assert manifest["model_usage"]["summary"]["call_count"] == 0
    assert manifest["model_usage"]["summary"]["cost_usd"] is None
    assert manifest["model_usage"]["artifact"] == "model-usage.json"
    assert manifest["escalation"]["performed"] is False
    assert (Path(result.output_dir) / "model-routing.json").exists()
    assert (Path(result.output_dir) / "model-usage.json").exists()

    manifest_path = Path(result.output_dir) / "run-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    assert manifest["task"]["repository"] == "acme/widget"
    assert manifest["agent"]["model"] == "local"
    assert manifest["checks"]["python_compile"] == {"ran": True, "exit_code": 0}
    assert manifest["checks"]["pytest"] == {"detected": True, "ran": True, "exit_code": 0}
    assert manifest["human_approval_required"] is True
    assert manifest["execution"]["external_actions"] == []



def test_pipeline_holds_high_value_bounties_for_manual_verification(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, "inspect_github_issue", lambda url: brief())

    def fake_clone(repository, workspace, **kwargs):
        workspace.mkdir(parents=True)
        return SimpleNamespace(path=str(workspace))

    monkeypatch.setattr(pipeline, "clone_public_github_repo", fake_clone)
    monkeypatch.setattr(
        pipeline, "plan_github_issue",
        lambda *args, **kwargs: SimpleNamespace(
            risk_level="low", blockers=[], acceptance_checklist=["Acceptance verified"],
            estimated_effort_hours=10.0, to_dict=lambda: {"risk_level": "low"}
        ),
    )
    monkeypatch.setattr(
        pipeline, "draft_patch",
        lambda *args, **kwargs: SimpleNamespace(
            model="local", status="patch", diff=SIMPLE_DIFF, changed_files=["a.py"],
            questions=[], to_dict=lambda: {"diff": "draft"}
        ),
    )
    monkeypatch.setattr(
        pipeline, "apply_patch_in_sandbox",
        lambda *args, **kwargs: pytest.fail("high-value task must wait for human verification"),
    )

    result = pipeline.run_pipeline(
        brief().url,
        scratch_root=tmp_path / "scratch",
        output_root=tmp_path / "proposals",
        reward_amount=1000,
        currency="USD",
    )
    assert result.status == "blocked_for_human_review"
    assert "above $500" in result.message



def test_pipeline_runs_node_syntax_check_in_node_sandbox(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, "inspect_github_issue", lambda url: brief())

    def fake_clone(repository, workspace, **kwargs):
        workspace.mkdir(parents=True)
        return SimpleNamespace(path=str(workspace))

    monkeypatch.setattr(pipeline, "clone_public_github_repo", fake_clone)
    monkeypatch.setattr(
        pipeline, "plan_github_issue",
        lambda *args, **kwargs: SimpleNamespace(
            risk_level="low", blockers=[], acceptance_checklist=["Acceptance verified"],
            estimated_effort_hours=1.0, to_dict=lambda: {"risk_level": "low"}
        ),
    )
    monkeypatch.setattr(
        pipeline, "draft_patch",
        lambda *args, **kwargs: SimpleNamespace(
            model="local", status="patch", diff="diff --git a/src/index.ts b/src/index.ts",
            changed_files=["src/index.ts"], questions=[], to_dict=lambda: {"diff": "draft"}
        ),
    )
    monkeypatch.setattr(
        pipeline, "apply_patch_in_sandbox",
        lambda *args, **kwargs: SimpleNamespace(applied=True, message="applied"),
    )
    captured = {}

    def fake_run(workspace, command, **kwargs):
        captured["command"] = command
        captured["image"] = kwargs["image"]
        return SimpleNamespace(exit_code=0, stdout="esbuild ok", stderr="")

    monkeypatch.setattr(pipeline, "run_in_sandbox", fake_run)
    result = pipeline.run_pipeline(
        brief().url,
        scratch_root=tmp_path / "scratch",
        output_root=tmp_path / "proposals",
        node_image="ai-worker-sandbox:node22-test",
    )

    assert result.status == "static_check_passed_no_tests"
    assert result.node_static_exit_code == 0
    assert captured["image"] == "ai-worker-sandbox:node22-test"
    assert captured["command"] == [
        "esbuild", "src/index.ts", "--outdir=/tmp/ai-worker-check"
    ]



def test_pipeline_fails_closed_when_independent_reviewer_is_unavailable(monkeypatch, tmp_path):
    from ai_worker.reviewer import ReviewerError

    monkeypatch.setattr(pipeline, "inspect_github_issue", lambda url: brief())

    def fake_clone(repository, workspace, **kwargs):
        workspace.mkdir(parents=True)
        return SimpleNamespace(path=str(workspace))

    monkeypatch.setattr(pipeline, "clone_public_github_repo", fake_clone)
    monkeypatch.setattr(
        pipeline, "plan_github_issue",
        lambda *args, **kwargs: SimpleNamespace(
            risk_level="low", blockers=[], acceptance_checklist=["Acceptance verified"],
            estimated_effort_hours=2.0, to_dict=lambda: {"risk_level": "low"},
        ),
    )
    monkeypatch.setattr(
        pipeline, "draft_patch",
        lambda *args, **kwargs: SimpleNamespace(
            model="generator-model", status="patch", diff=SIMPLE_DIFF,
            changed_files=["a.py"], questions=[], to_dict=lambda: {"diff": "draft"},
        ),
    )
    monkeypatch.setattr(
        pipeline, "review_patch",
        lambda *args, **kwargs: (_ for _ in ()).throw(ReviewerError("review model unavailable")),
    )
    monkeypatch.setattr(
        pipeline, "apply_patch_in_sandbox",
        _allow_preflight_only,
    )

    result = pipeline.run_pipeline(
        brief().url,
        scratch_root=tmp_path / "scratch",
        output_root=tmp_path / "proposals",
    )

    assert result.status == "reviewer_unavailable_blocked"
    assert result.reviewer_verdict == "unavailable"
    manifest = json.loads((Path(result.output_dir) / "run-manifest.json").read_text())
    assert manifest["agent"]["reviewer_stage"] == "unavailable"
    assert manifest["agent"]["reviewer_findings"] == []
    review = json.loads((Path(result.output_dir) / "review.json").read_text())
    assert review["verdict"] == "unavailable"



def test_pipeline_blocks_patch_when_reviewer_finds_critical_issue(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, "inspect_github_issue", lambda url: brief())

    def fake_clone(repository, workspace, **kwargs):
        workspace.mkdir(parents=True)
        return SimpleNamespace(path=str(workspace))

    monkeypatch.setattr(pipeline, "clone_public_github_repo", fake_clone)
    monkeypatch.setattr(
        pipeline, "plan_github_issue",
        lambda *args, **kwargs: SimpleNamespace(
            risk_level="low", blockers=[], acceptance_checklist=["Acceptance verified"],
            estimated_effort_hours=2.0, to_dict=lambda: {"risk_level": "low"},
        ),
    )
    monkeypatch.setattr(
        pipeline, "draft_patch",
        lambda *args, **kwargs: SimpleNamespace(
            model="generator-model", status="patch", diff=SIMPLE_DIFF,
            changed_files=["a.py"], questions=[], to_dict=lambda: {"diff": "draft"},
        ),
    )
    finding = SimpleNamespace(
        severity="critical", file="a.py", line=1, title="Unsafe behavior",
        evidence="Sensitive data is exposed.", recommendation="Remove the exposure.",
    )
    monkeypatch.setattr(
        pipeline, "review_patch",
        lambda *args, **kwargs: SimpleNamespace(
            verdict="blocked", summary="Critical security issue.", findings=[finding],
            to_dict=lambda: {"verdict": "blocked", "summary": "Critical security issue.", "findings": []},
        ),
    )
    monkeypatch.setattr(
        pipeline, "repair_patch",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            pipeline.PatchError("repair intentionally unavailable in this test")
        ),
    )
    monkeypatch.setattr(
        pipeline, "apply_patch_in_sandbox",
        _allow_preflight_only,
    )

    result = pipeline.run_pipeline(
        brief().url,
        scratch_root=tmp_path / "scratch",
        output_root=tmp_path / "proposals",
        model="generator-model",
        reviewer_model="reviewer-model",
    )

    assert result.status == "review_blocked"
    assert result.reviewer_verdict == "blocked"
    assert result.reviewer_findings[0]["severity"] == "critical"
    report = (Path(result.output_dir) / "REPORT.md").read_text()
    assert "Independent review findings" in report
    assert "a.py:1" in report
    assert "Sensitive data is exposed." in report


def test_pipeline_rejects_same_generator_and_reviewer_model(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, "inspect_github_issue", lambda url: brief())

    def fake_clone(repository, workspace, **kwargs):
        workspace.mkdir(parents=True)
        return SimpleNamespace(path=str(workspace))

    monkeypatch.setattr(pipeline, "clone_public_github_repo", fake_clone)
    monkeypatch.setattr(
        pipeline, "plan_github_issue",
        lambda *args, **kwargs: SimpleNamespace(
            risk_level="low", blockers=[], acceptance_checklist=["Acceptance verified"],
            estimated_effort_hours=2.0, to_dict=lambda: {"risk_level": "low"},
        ),
    )
    monkeypatch.setattr(
        pipeline, "draft_patch",
        lambda *args, **kwargs: SimpleNamespace(
            model="qwen2.5-coder:7b", status="patch", diff=SIMPLE_DIFF,
            changed_files=["a.py"], questions=[], to_dict=lambda: {"diff": "draft"},
        ),
    )
    monkeypatch.setattr(
        pipeline, "review_patch",
        lambda *args, **kwargs: pytest.fail("identical reviewer model must be rejected before inference"),
    )
    monkeypatch.setattr(
        pipeline, "apply_patch_in_sandbox",
        lambda *args, **kwargs: pytest.fail("patch must remain unapplied"),
    )

    result = pipeline.run_pipeline(
        brief().url,
        scratch_root=tmp_path / "scratch",
        output_root=tmp_path / "proposals",
        reviewer_model="qwen2.5-coder:7b",
    )

    assert result.status == "reviewer_unavailable_blocked"
    assert result.reviewer_verdict == "unavailable"
    assert "must differ" in result.message


def test_pipeline_shares_one_repository_snapshot_with_planner_and_drafter(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        pipeline, "inspect_github_issue", lambda url: brief()
    )

    def fake_clone(repository, workspace, **kwargs):
        workspace.mkdir(parents=True)
        return SimpleNamespace(path=str(workspace))

    monkeypatch.setattr(
        pipeline, "clone_public_github_repo", fake_clone
    )

    repository_context = [
        {
            "path": "src/client.py",
            "content": "class APIClient:\\n    pass\\n",
        }
    ]
    diagnostics = {
        "schema_version": 1,
        "status": "completed",
        "selected_files": ["src/client.py"],
        "context_files_sent": 1,
        "context_bytes_sent": 32,
    }
    collector_calls = []
    planner_calls = []
    drafter_calls = []

    def fake_collect(workspace, *, brief, diagnostics):
        collector_calls.append(workspace)
        diagnostics.update({
            "schema_version": 1,
            "status": "completed",
            "selected_files": ["src/client.py"],
            "context_files_sent": 1,
            "context_bytes_sent": 32,
        })
        return repository_context

    monkeypatch.setattr(
        pipeline, "collect_repo_context", fake_collect
    )

    generated_plan = SimpleNamespace(
        risk_level="low",
        blockers=[],
        acceptance_checklist=["Verify API retry behavior"],
        estimated_effort_hours=2.0,
        to_dict=lambda: {
            "risk_level": "low",
            "acceptance_checklist": ["Verify API retry behavior"],
        },
    )

    def fake_planner(brief_arg, **kwargs):
        planner_calls.append(kwargs)
        return generated_plan

    monkeypatch.setattr(
        pipeline, "plan_github_issue", fake_planner
    )

    def fake_draft(brief_arg, workspace, **kwargs):
        drafter_calls.append(kwargs)
        return SimpleNamespace(
            model="local",
            status="needs_information",
            diff="",
            changed_files=[],
            questions=["What retry backoff behavior is expected?"],
            to_dict=lambda: {"status": "needs_information"},
        )

    monkeypatch.setattr(pipeline, "draft_patch", fake_draft)

    result = pipeline.run_pipeline(
        brief().url,
        scratch_root=tmp_path / "scratch",
        output_root=tmp_path / "proposals",
    )

    assert result.status == "needs_human_clarification"
    assert len(collector_calls) == 1
    assert len(planner_calls) == 1
    assert len(drafter_calls) == 1

    assert planner_calls[0]["repository_context"] is repository_context
    assert drafter_calls[0]["repository_context"] is repository_context
    assert drafter_calls[0]["context_diagnostics"]["status"] == "completed"
    assert drafter_calls[0]["plan"] is generated_plan

def test_pipeline_preserves_context_report_and_failure_manifest_when_draft_fails(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(pipeline, "inspect_github_issue", lambda url: brief())

    def fake_clone(repository, workspace, **kwargs):
        workspace.mkdir(parents=True)
        return SimpleNamespace(path=str(workspace))

    monkeypatch.setattr(pipeline, "clone_public_github_repo", fake_clone)
    monkeypatch.setattr(
        pipeline, "plan_github_issue",
        lambda *args, **kwargs: SimpleNamespace(
            risk_level="low",
            blockers=[],
            acceptance_checklist=["Acceptance verified"],
            estimated_effort_hours=2.0,
            to_dict=lambda: {"risk_level": "low"},
        ),
    )

    def failing_draft(*args, **kwargs):
        kwargs["context_diagnostics"].update({
            "schema_version": 1,
            "status": "completed",
            "context_files_sent": 3,
            "context_bytes_sent": 1200,
        })
        raise pipeline.PatchError("draft could not produce a valid proposal")

    monkeypatch.setattr(pipeline, "draft_patch", failing_draft)

    with pytest.raises(pipeline.PipelineError, match="draft could not produce"):
        pipeline.run_pipeline(
            brief().url,
            scratch_root=tmp_path / "scratch",
            output_root=tmp_path / "proposals",
        )

    output_dir = tmp_path / "proposals" / next((tmp_path / "proposals").iterdir()).name
    context_report = json.loads((output_dir / "context-report.json").read_text())
    manifest = json.loads((output_dir / "run-manifest.json").read_text())

    assert context_report["status"] == "completed"
    assert context_report["context_files_sent"] == 3
    assert manifest["proposal"]["status"] == "unavailable"
    assert manifest["proposal"]["no_patch_reason"] == "draft_generation_failed"
    assert manifest["outcome"]["status"] == "draft_failed"
    assert manifest["outcome"]["failed_stage"] == "draft"
    assert manifest["outcome"]["error_type"] == "PatchError"
    assert not (output_dir / "proposal.patch").exists()

    # Draft-failure manifests must preserve the same top-level contract
    # as successful runs, with execution and QA accurately marked.
    assert {
        "schema_version", "run_id", "started_at", "finished_at",
        "task", "agent", "execution", "assessment", "proposal",
        "checks", "outcome", "human_approval_required",
    } <= manifest.keys()
    assert manifest["agent"]["reviewer_stage"] == "not_run"
    assert manifest["agent"]["reviewer_findings"] == []
    assert manifest["execution"]["external_actions"] == []
    assert manifest["execution"]["network_access"] == "disabled_in_task_containers"
    assert manifest["assessment"]["risk_level"] == "low"
    assert manifest["assessment"]["acceptance_checklist"] == ["Acceptance verified"]
    assert manifest["checks"]["python_compile"] == {
        "ran": False, "exit_code": None
    }
    assert manifest["checks"]["pytest"] == {
        "detected": False, "ran": False, "exit_code": None
    }
    assert manifest["checks"]["javascript_typescript_syntax"] == {
        "ran": False, "exit_code": None
    }
    assert manifest["checks"]["dependency_aware_node_tests"]["ran"] is False


def _configure_bounded_repair_pipeline(
    monkeypatch,
    tmp_path,
    review_callback,
    repair_callback,
):
    initial_diff = """diff --git a/client.py b/client.py
--- a/client.py
+++ b/client.py
@@ -1 +1 @@
-before
+after
"""

    def fake_clone(repository, workspace, **kwargs):
        workspace.mkdir(parents=True)
        (workspace / "client.py").write_text("before\n", encoding="utf-8")
        (workspace / "tests").mkdir()
        (workspace / "tests" / "test_smoke.py").write_text(
            "def test_smoke():\n    assert True\n",
            encoding="utf-8",
        )
        return SimpleNamespace(path=str(workspace))

    monkeypatch.setattr(
        pipeline, "inspect_github_issue", lambda url: brief()
    )
    monkeypatch.setattr(
        pipeline, "clone_public_github_repo", fake_clone
    )
    monkeypatch.setattr(
        pipeline, "plan_github_issue",
        lambda *args, **kwargs: SimpleNamespace(
            risk_level="low",
            blockers=[],
            acceptance_checklist=["Acceptance verified"],
            estimated_effort_hours=2.0,
            to_dict=lambda: {"risk_level": "low"},
        ),
    )
    monkeypatch.setattr(
        pipeline, "draft_patch",
        lambda *args, **kwargs: SimpleNamespace(
            model="generator-model",
            status="patch",
            diff=initial_diff,
            summary="Initial patch.",
            changed_files=["client.py"],
            questions=[],
            to_dict=lambda: {
                "status": "patch",
                "diff": initial_diff,
                "summary": "Initial patch.",
            },
        ),
    )
    monkeypatch.setattr(
        pipeline, "review_patch", review_callback
    )
    monkeypatch.setattr(
        pipeline, "repair_patch", repair_callback
    )

    applied_diffs = []

    def fake_apply(diff, workspace, **kwargs):
        if "ai-worker-verify-" not in str(workspace):
            applied_diffs.append(diff)
        return SimpleNamespace(
            applied=True,
            message="applied",
        )

    monkeypatch.setattr(
        pipeline, "apply_patch_in_sandbox", fake_apply
    )
    monkeypatch.setattr(
        pipeline, "run_in_sandbox",
        lambda *args, **kwargs: SimpleNamespace(
            exit_code=0,
            stdout="checks passed",
            stderr="",
        ),
    )

    return applied_diffs


def _fake_review_result(verdict, summary, findings=None):
    findings = findings or []
    payload = {
        "verdict": verdict,
        "summary": summary,
        "findings": [
            {
                "severity": item.severity,
                "file": item.file,
                "line": item.line,
                "title": item.title,
                "evidence": item.evidence,
                "recommendation": item.recommendation,
            }
            for item in findings
        ],
        "model": "reviewer-model",
    }
    return SimpleNamespace(
        verdict=verdict,
        summary=summary,
        findings=findings,
        to_dict=lambda: payload,
    )


def test_pipeline_repairs_and_re_reviews_before_applying(monkeypatch, tmp_path):
    finding = SimpleNamespace(
        severity="medium",
        file="client.py",
        line=1,
        title="Retry behavior is incomplete",
        evidence="The retry path does not preserve the previous behavior.",
        recommendation="Preserve the existing retry behavior.",
    )

    review_calls = []
    review_contexts = []
    repair_contexts = []
    collector_calls = []

    repository_context = [
        {
            "path": "client.py",
            "content": "class APIClient:\\n    pass\\n",
        }
    ]

    def fake_collect(workspace, *, brief, diagnostics):
        collector_calls.append(workspace)
        diagnostics.update({
            "schema_version": 1,
            "status": "completed",
            "selected_files": ["client.py"],
            "context_files_sent": 1,
            "context_bytes_sent": 32,
        })
        return repository_context

    monkeypatch.setattr(
        pipeline, "collect_repo_context", fake_collect
    )

    def fake_review(brief_arg, workspace, diff, **kwargs):
        review_calls.append(diff)
        review_contexts.append(kwargs.get("repository_context"))
        if len(review_calls) == 1:
            return _fake_review_result(
                "needs_changes",
                "One medium issue needs correction.",
                [finding],
            )
        return _fake_review_result(
            "pass",
            "The repaired patch has no actionable findings.",
        )

    repaired_diff = """diff --git a/client.py b/client.py
--- a/client.py
+++ b/client.py
@@ -1 +1 @@
-before
+fixed
"""

    repair_calls = []

    def fake_repair(brief_arg, workspace, **kwargs):
        repair_calls.append(kwargs)
        repair_contexts.append(kwargs.get("repository_context"))
        return SimpleNamespace(
            status="patch",
            diff=repaired_diff,
            changed_files=["client.py"],
            summary="Preserved retry behavior.",
            questions=[],
        )

    applied = _configure_bounded_repair_pipeline(
        monkeypatch,
        tmp_path,
        fake_review,
        fake_repair,
    )

    result = pipeline.run_pipeline(
        brief().url,
        scratch_root=tmp_path / "scratch",
        output_root=tmp_path / "proposals",
        model="generator-model",
        reviewer_model="reviewer-model",
    )

    assert result.status == "ready_for_human_review"
    assert len(review_calls) == 2
    assert len(repair_calls) == 1
    assert len(collector_calls) == 1

    assert len(review_contexts) == 2
    assert all(context is repository_context for context in review_contexts)
    assert repair_contexts == [repository_context]
    assert repair_calls[0]["repository_context"] is repository_context
    assert repair_calls[0]["allowed_files"] == ["client.py"]
    assert applied == [repaired_diff]

    output_dir = Path(result.output_dir)
    assert (output_dir / "proposal.patch").read_text() == repaired_diff

    manifest = json.loads(
        (output_dir / "run-manifest.json").read_text()
    )
    assert manifest["agent"]["repair_attempt_count"] == 1
    assert manifest["agent"]["review_history_path"] == "review-history.json"

    review_history = json.loads(
        (output_dir / "review-history.json").read_text()
    )
    repair_history = json.loads(
        (output_dir / "repair-history.json").read_text()
    )
    assert len(review_history["reviews"]) == 2
    assert len(repair_history["attempts"]) == 1


def test_pipeline_never_applies_when_repair_fails(monkeypatch, tmp_path):
    finding = SimpleNamespace(
        severity="high",
        file="client.py",
        line=1,
        title="Unsafe retry handling",
        evidence="The new code can retry indefinitely.",
        recommendation="Bound the retry count.",
    )

    def fake_review(*args, **kwargs):
        return _fake_review_result(
            "blocked",
            "A high-severity issue remains.",
            [finding],
        )

    def failing_repair(*args, **kwargs):
        raise pipeline.PatchError("repair response was invalid")

    applied = _configure_bounded_repair_pipeline(
        monkeypatch,
        tmp_path,
        fake_review,
        failing_repair,
    )

    result = pipeline.run_pipeline(
        brief().url,
        scratch_root=tmp_path / "scratch",
        output_root=tmp_path / "proposals",
        model="generator-model",
        reviewer_model="reviewer-model",
    )

    assert result.status == "review_blocked"
    assert applied == []
    assert "repair response was invalid" in result.message

    history = json.loads(
        (Path(result.output_dir) / "repair-history.json").read_text()
    )
    assert len(history["attempts"]) == 1
    assert history["attempts"][0]["status"] == "failed"


def test_pipeline_stops_after_two_unsuccessful_repair_attempts(
    monkeypatch, tmp_path
):
    finding = SimpleNamespace(
        severity="medium",
        file="client.py",
        line=1,
        title="Retry behavior remains incomplete",
        evidence="The retry behavior is still incorrect.",
        recommendation="Correct the retry behavior.",
    )

    review_calls = []

    def fake_review(*args, **kwargs):
        review_calls.append(kwargs)
        return _fake_review_result(
            "needs_changes",
            "The issue remains unresolved.",
            [finding],
        )

    repair_calls = []

    def fake_repair(*args, **kwargs):
        repair_calls.append(kwargs)
        replacement = f"repair{len(repair_calls)}"
        return SimpleNamespace(
            status="patch",
            diff=(
                "diff --git a/client.py b/client.py\n"
                "--- a/client.py\n+++ b/client.py\n"
                "@@ -1 +1 @@\n-before\n+" + replacement + "\n"
            ),
            changed_files=["client.py"],
            summary="Attempted a bounded correction.",
            questions=[],
        )

    applied = _configure_bounded_repair_pipeline(
        monkeypatch,
        tmp_path,
        fake_review,
        fake_repair,
    )

    result = pipeline.run_pipeline(
        brief().url,
        scratch_root=tmp_path / "scratch",
        output_root=tmp_path / "proposals",
        model="generator-model",
        reviewer_model="reviewer-model",
    )

    assert result.status == "review_blocked"
    assert len(review_calls) == 3
    assert len(repair_calls) == 2
    assert applied == []
    assert "Maximum bounded repair attempts (2) exhausted" in result.message

    history = json.loads(
        (Path(result.output_dir) / "repair-history.json").read_text()
    )
    assert len(history["attempts"]) == 2


def test_failed_required_test_is_sent_to_bounded_repair_before_review(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(pipeline, "inspect_github_issue", lambda url: brief())

    def fake_clone(repository, workspace, **kwargs):
        workspace.mkdir(parents=True)
        (workspace / "worker.py").write_text("def create_worker(options): return options\n")
        (workspace / "tests").mkdir()
        (workspace / "tests" / "test_worker.py").write_text("def test_existing(): assert True\n")
        return SimpleNamespace(path=str(workspace))

    monkeypatch.setattr(pipeline, "clone_public_github_repo", fake_clone)
    plan = SimpleNamespace(
        risk_level="low", blockers=[], acceptance_checklist=["Existing behavior remains valid"],
        estimated_effort_hours=1.0, to_dict=lambda: {"test_plan": ["pytest -q"]},
    )
    monkeypatch.setattr(pipeline, "plan_github_issue", lambda *args, **kwargs: plan)
    initial_diff = """diff --git a/worker.py b/worker.py
--- a/worker.py
+++ b/worker.py
@@ -1 +1 @@
-def create_worker(options): return options
+def create_worker(options): return options
"""
    repaired_diff = initial_diff.replace("return options", "return dict(options)")
    monkeypatch.setattr(
        pipeline, "draft_patch",
        lambda *args, **kwargs: SimpleNamespace(
            model="generator-model", status="patch", diff=initial_diff,
            changed_files=["worker.py"], questions=[], summary="initial",
            to_dict=lambda: {"status": "patch", "diff": initial_diff},
        ),
    )
    monkeypatch.setattr(
        pipeline, "apply_patch_in_sandbox",
        lambda *args, **kwargs: SimpleNamespace(applied=True, message="applied in candidate"),
    )

    runs = []

    def fake_run(workspace, command, **kwargs):
        runs.append(command)
        is_pytest = command[-2:] == ["pytest", "-q"]
        failed = is_pytest and runs.count(command) == 1
        return SimpleNamespace(
            exit_code=1 if failed else 0,
            stdout="FAILED test_timeout_zero" if failed else "checks passed",
            stderr="",
            timed_out=False,
        )

    monkeypatch.setattr(pipeline, "run_in_sandbox", fake_run)
    repair_requests = []

    def fake_repair(brief_arg, workspace, **kwargs):
        repair_requests.append(kwargs)
        return SimpleNamespace(
            status="patch", diff=repaired_diff, changed_files=["worker.py"],
            summary="repaired based on the failing pytest output", questions=[],
        )

    monkeypatch.setattr(pipeline, "repair_patch", fake_repair)
    reviews = []

    def fake_review(*args, **kwargs):
        reviews.append(kwargs)
        return _fake_review_result("pass", "Reviewer passed despite prior test failure.")

    monkeypatch.setattr(pipeline, "review_patch", fake_review)

    result = pipeline.run_pipeline(
        brief().url,
        scratch_root=tmp_path / "scratch",
        output_root=tmp_path / "proposals",
        model="generator-model",
        reviewer_model="reviewer-model",
    )

    assert result.status == "ready_for_human_review"
    assert len(repair_requests) == 1
    finding = repair_requests[0]["findings"][0]
    assert finding["file"] == "worker.py"
    assert "FAILED test_timeout_zero" in finding["evidence"]
    assert repair_requests[0]["allowed_files"] == ["worker.py"]
    assert reviews[0]["verification_evidence"]["passed"] is True
    assert reviews[0]["task_plan"] == {"test_plan": ["pytest -q"]}
    verification_attempts = reviews[0]["verification_evidence"]["attempts"]
    assert any(
        check["name"] == "pytest" and check["exit_code"] == 1
        and "FAILED test_timeout_zero" in check["stdout"]
        for attempt in verification_attempts for check in attempt["checks"]
    )
    assert any(
        check["name"] == "pytest" and check["exit_code"] == 0
        for attempt in verification_attempts for check in attempt["checks"]
    )
    manifest = json.loads((Path(result.output_dir) / "run-manifest.json").read_text())
    assert manifest["checks"]["pre_review_verification"]["passed"] is True
    assert manifest["checks"]["final_verification"]["passed"] is True


def test_sandbox_patch_check_failure_becomes_bounded_repair_finding():
    findings = pipeline._verification_findings(
        {
            "patch_applied": False,
            "patch_error": "Patch failed git apply --check",
            "patch_apply_stderr": "error: patch failed: tests/test_worker.py:9",
            "checks": [],
        },
        ["src/worker.py", "tests/test_worker.py"],
    )
    assert len(findings) == 1
    assert findings[0]["file"] == "src/worker.py"
    assert findings[0]["title"] == "Candidate patch failed sandbox application"
    assert "tests/test_worker.py:9" in findings[0]["evidence"]
    assert "unchanged repository workspace" in findings[0]["recommendation"]


def test_sandbox_patch_check_failure_is_repaired_before_review(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, "inspect_github_issue", lambda url: brief())

    def fake_clone(repository, workspace, **kwargs):
        workspace.mkdir(parents=True)
        (workspace / "a.py").write_text("before\n")
        (workspace / "tests").mkdir()
        (workspace / "tests" / "test_a.py").write_text("def test_ok(): assert True\n")
        return SimpleNamespace(path=str(workspace))

    monkeypatch.setattr(pipeline, "clone_public_github_repo", fake_clone)
    monkeypatch.setattr(
        pipeline, "plan_github_issue",
        lambda *args, **kwargs: SimpleNamespace(
            risk_level="low", blockers=[], acceptance_checklist=["verify"],
            estimated_effort_hours=1.0, to_dict=lambda: {"test_plan": ["pytest"]},
        ),
    )
    initial = SIMPLE_DIFF
    repaired = SIMPLE_DIFF.replace("+after", "+fixed")
    monkeypatch.setattr(
        pipeline, "draft_patch",
        lambda *args, **kwargs: SimpleNamespace(
            model="generator-model", status="patch", diff=initial,
            changed_files=["a.py"], questions=[], summary="initial",
            to_dict=lambda: {"status": "patch", "diff": initial},
        ),
    )

    apply_calls = []

    def fake_apply(diff, workspace, **kwargs):
        apply_calls.append((diff, workspace))
        if len(apply_calls) == 1:
            return SimpleNamespace(
                applied=False, message="git apply --check failed",
                stdout="", stderr="error: patch does not apply",
            )
        return SimpleNamespace(applied=True, message="applied in candidate")

    monkeypatch.setattr(pipeline, "apply_patch_in_sandbox", fake_apply)
    monkeypatch.setattr(
        pipeline, "run_in_sandbox",
        lambda *args, **kwargs: SimpleNamespace(
            exit_code=0, stdout="checks passed", stderr="", timed_out=False,
        ),
    )
    repair_calls = []

    def fake_repair(*args, **kwargs):
        repair_calls.append(kwargs)
        return SimpleNamespace(
            status="patch", diff=repaired, changed_files=["a.py"],
            summary="repaired after exact sandbox diagnostic", questions=[],
        )

    monkeypatch.setattr(pipeline, "repair_patch", fake_repair)
    review_calls = []
    monkeypatch.setattr(
        pipeline, "review_patch",
        lambda *args, **kwargs: (
            review_calls.append(kwargs)
            or _fake_review_result("pass", "Reviewed the repaired candidate.")
        ),
    )

    result = pipeline.run_pipeline(
        brief().url, scratch_root=tmp_path / "scratch",
        output_root=tmp_path / "proposals", model="generator-model",
        reviewer_model="reviewer-model",
    )

    assert result.status == "ready_for_human_review"
    assert len(repair_calls) == 1
    finding = repair_calls[0]["findings"][0]
    assert finding["title"] == "Candidate patch failed sandbox application"
    assert "patch does not apply" in finding["evidence"]
    assert len(review_calls) == 1
    assert review_calls[0]["verification_evidence"]["passed"] is True
    first_attempt = review_calls[0]["verification_evidence"]["attempts"][0]
    assert first_attempt["patch_applied"] is False
    assert first_attempt["patch_apply_stderr"] == "error: patch does not apply"


def test_incomplete_verification_cannot_be_overridden_by_reviewer_pass(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(pipeline, "inspect_github_issue", lambda url: brief())

    def fake_clone(repository, workspace, **kwargs):
        workspace.mkdir(parents=True)
        (workspace / "worker.py").write_text("pass\n")
        (workspace / "tests").mkdir()
        (workspace / "tests" / "test_worker.py").write_text("def test_example(): assert True\n")
        return SimpleNamespace(path=str(workspace))

    monkeypatch.setattr(pipeline, "clone_public_github_repo", fake_clone)
    monkeypatch.setattr(
        pipeline, "plan_github_issue",
        lambda *args, **kwargs: SimpleNamespace(
            risk_level="low", blockers=[], acceptance_checklist=["verify"],
            estimated_effort_hours=1.0, to_dict=lambda: {"test_plan": ["pytest"]},
        ),
    )
    diff = initial_diff = """diff --git a/worker.py b/worker.py
--- a/worker.py
+++ b/worker.py
@@ -1 +1 @@
-pass
+pass
"""
    monkeypatch.setattr(
        pipeline, "draft_patch",
        lambda *args, **kwargs: SimpleNamespace(
            model="generator-model", status="patch", diff=diff,
            changed_files=["worker.py"], questions=[], to_dict=lambda: {"diff": diff},
        ),
    )
    monkeypatch.setattr(
        pipeline, "run_in_sandbox",
        lambda *args, **kwargs: SimpleNamespace(
            exit_code=None, stdout="", stderr="", timed_out=True,
        ),
    )
    monkeypatch.setattr(
        pipeline, "review_patch",
        lambda *args, **kwargs: _fake_review_result("pass", "Misleading model pass."),
    )
    monkeypatch.setattr(
        pipeline, "repair_patch",
        lambda *args, **kwargs: pytest.fail("timeouts are incomplete verification, not repair findings"),
    )
    monkeypatch.setattr(
        pipeline, "apply_patch_in_sandbox",
        lambda diff, workspace, **kwargs: (
            SimpleNamespace(applied=True, message="candidate")
            if "ai-worker-verify-" in str(workspace)
            else pytest.fail("incomplete verification must prevent task-workspace application")
        ),
    )

    result = pipeline.run_pipeline(
        brief().url, scratch_root=tmp_path / "scratch",
        output_root=tmp_path / "proposals", model="generator-model",
        reviewer_model="reviewer-model",
    )
    assert result.status == "verification_failed"
    assert result.reviewer_verdict == "pass"
    assert "cannot authorize patch application" in result.message


@pytest.mark.parametrize(
    "check",
    [
        {"required": True, "ran": False, "exit_code": None, "timed_out": False},
        {"required": True, "ran": True, "exit_code": None, "timed_out": True},
        {"required": True, "ran": True, "exit_code": 1, "timed_out": False},
        {"required": True, "ran": True, "exit_code": False, "timed_out": False},
    ],
)
def test_deterministic_gate_rejects_missing_failed_timeout_and_boolean_exit(check):
    evidence = {"patch_applied": True, "checks": [check]}
    assert pipeline._verification_gate(evidence) is False


def test_deterministic_gate_requires_at_least_one_required_check():
    assert pipeline._verification_gate({
        "patch_applied": True,
        "checks": [{"required": False, "ran": True, "exit_code": 0, "timed_out": False}],
    }) is False


def test_pipeline_records_node_project_without_installing_dependencies(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        pipeline, "inspect_github_issue", lambda url: brief()
    )

    def fake_clone(repository, workspace, **kwargs):
        workspace.mkdir(parents=True)
        (workspace / "src").mkdir()
        (workspace / "src" / "index.ts").write_text(
            "export const value: number = 1;\n",
            encoding="utf-8",
        )
        (workspace / "package.json").write_text(
            json.dumps({
                "name": "node-demo",
                "packageManager": "npm@10.8.2",
                "scripts": {
                    "test": "node test.js",
                    "build": "node build.js",
                },
                "dependencies": {},
            }),
            encoding="utf-8",
        )
        (workspace / "package-lock.json").write_text(
            json.dumps({
                "name": "node-demo",
                "lockfileVersion": 3,
                "packages": {},
            }),
            encoding="utf-8",
        )
        return SimpleNamespace(path=str(workspace))

    monkeypatch.setattr(
        pipeline, "clone_public_github_repo", fake_clone
    )
    monkeypatch.setattr(
        pipeline, "plan_github_issue",
        lambda *args, **kwargs: SimpleNamespace(
            risk_level="low",
            blockers=[],
            acceptance_checklist=["Acceptance verified"],
            estimated_effort_hours=1.0,
            to_dict=lambda: {"risk_level": "low"},
        ),
    )
    monkeypatch.setattr(
        pipeline, "draft_patch",
        lambda *args, **kwargs: SimpleNamespace(
            model="generator-model",
            status="patch",
            diff="diff --git a/src/index.ts b/src/index.ts",
            changed_files=["src/index.ts"],
            questions=[],
            summary="Update TypeScript.",
            to_dict=lambda: {
                "status": "patch",
                "summary": "Update TypeScript.",
                "changed_files": ["src/index.ts"],
            },
        ),
    )
    monkeypatch.setattr(
        pipeline, "apply_patch_in_sandbox",
        lambda *args, **kwargs: SimpleNamespace(
            applied=True,
            message="applied",
        ),
    )

    commands = []
    network_settings = []

    def fake_run(workspace, command, **kwargs):
        commands.append(command)
        network_settings.append(kwargs.get('network_enabled', False))
        return SimpleNamespace(
            exit_code=0,
            stdout="static check passed",
            stderr="",
        )

    monkeypatch.setattr(pipeline, "run_in_sandbox", fake_run)

    result = pipeline.run_pipeline(
        brief().url,
        scratch_root=tmp_path / "scratch",
        output_root=tmp_path / "proposals",
        model="generator-model",
        reviewer_model="reviewer-model",
    )

    assert result.status == "ready_for_human_review"
    assert result.node_project["status"] == "ready"
    assert result.node_project["package_manager"] == "npm"
    assert result.node_project["lockfile"] == "package-lock.json"
    assert result.node_project["has_test_script"] is True
    assert result.node_project["has_build_script"] is True

    assert commands[0][0] == "esbuild"
    # The hardened Node image intentionally ships without npm/npx; scripts are
    # executed with the Node built-in runner available in Node 22.23.5.
    assert commands[1] == ["node", "--run", "test"]
    assert commands[2] == ["node", "--run", "build"]
    assert all(command[0] != "npm" for command in commands)
    assert network_settings == [False, False, False]
    assert result.node_test_exit_code == 0
    assert result.node_build_exit_code == 0
    assert result.node_test_log == "static check passed"
    assert result.node_build_log == "static check passed"

    output_dir = Path(result.output_dir)
    node_report = json.loads(
        (output_dir / "node-project.json").read_text()
    )
    manifest = json.loads(
        (output_dir / "run-manifest.json").read_text()
    )

    assert node_report["status"] == "ready"
    assert manifest["checks"]["dependency_aware_node_tests"]["ran"] is True
    assert manifest["checks"]["dependency_aware_node_tests"]["detected"] is True
    assert manifest["checks"]["dependency_aware_node_tests"]["exit_code"] == 0
    assert manifest["checks"]["node_build"]["ran"] is True
    assert manifest["checks"]["node_build"]["detected"] is True
    assert manifest["checks"]["node_build"]["exit_code"] == 0
    assert (output_dir / "node-test.log").exists()
    assert (output_dir / "node-build.log").exists()


def test_pipeline_preserves_context_report_when_planner_fails(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        pipeline, "inspect_github_issue", lambda url: brief()
    )

    def fake_clone(repository, workspace, **kwargs):
        workspace.mkdir(parents=True)
        return SimpleNamespace(path=str(workspace))

    monkeypatch.setattr(
        pipeline, "clone_public_github_repo", fake_clone
    )

    repository_context = [
        {"path": "src/client.py", "content": "class APIClient:\n    pass\n"}
    ]

    def fake_collect(workspace, *, brief, diagnostics):
        diagnostics.update({
            "schema_version": 1,
            "status": "completed",
            "selected_files": ["src/client.py"],
            "context_files_sent": 1,
            "context_bytes_sent": 32,
        })
        return repository_context

    monkeypatch.setattr(
        pipeline, "collect_repo_context", fake_collect
    )

    def failing_planner(brief_arg, **kwargs):
        assert kwargs["repository_context"] is repository_context
        raise pipeline.OllamaError("simulated planner failure")

    monkeypatch.setattr(
        pipeline, "plan_github_issue", failing_planner
    )

    with pytest.raises(
        pipeline.PipelineError, match="simulated planner failure"
    ):
        pipeline.run_pipeline(
            brief().url,
            scratch_root=tmp_path / "scratch",
            output_root=tmp_path / "proposals",
        )

    output_dirs = list((tmp_path / "proposals").iterdir())
    assert len(output_dirs) == 1

    report = json.loads(
        (output_dirs[0] / "context-report.json").read_text(
            encoding="utf-8"
        )
    )

    assert report["status"] == "completed"
    assert report["selected_files"] == ["src/client.py"]
    assert report["context_files_sent"] == 1
