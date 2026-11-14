from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_worker import pipeline
from ai_worker.models import Gig
from ai_worker.sources.github_issue import ResearchBrief


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
            model="local", diff="diff --git a/a.py b/a.py", changed_files=["a.py"],
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
    assert result.status == "blocked_for_human_review"
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
            model="local", diff="diff --git a/a.py b/a.py", changed_files=["a.py"],
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
