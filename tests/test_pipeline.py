import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_worker import pipeline
from ai_worker.models import Gig
from ai_worker.sources.github_issue import ResearchBrief


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
    assert (tmp_path / "proposals" / next((tmp_path / "proposals").iterdir()).name / "REPORT.md").exists()


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
            model="local", status="patch", diff="diff --git a/a.py b/a.py", changed_files=["a.py"],
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
    assert manifest["human_approval_required"] is True
    assert manifest["execution"]["external_actions"] == []
    assert manifest["execution"]["max_output_bytes"] == 1_000_000

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
            model="local", status="patch", diff="diff --git a/a.py b/a.py", changed_files=["a.py"],
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
            model="generator-model", status="patch", diff="diff --git a/a.py b/a.py",
            changed_files=["a.py"], questions=[], to_dict=lambda: {"diff": "draft"},
        ),
    )
    monkeypatch.setattr(
        pipeline, "review_patch",
        lambda *args, **kwargs: (_ for _ in ()).throw(ReviewerError("review model unavailable")),
    )
    monkeypatch.setattr(
        pipeline, "apply_patch_in_sandbox",
        lambda *args, **kwargs: pytest.fail("patch must not be applied without a successful review"),
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
            model="generator-model", status="patch", diff="diff --git a/a.py b/a.py",
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
        pipeline, "apply_patch_in_sandbox",
        lambda *args, **kwargs: pytest.fail("critical review finding must block patch application"),
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
            model="qwen2.5-coder:7b", status="patch", diff="diff --git a/a.py b/a.py",
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
