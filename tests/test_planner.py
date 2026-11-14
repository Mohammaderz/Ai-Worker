import json

import pytest

from ai_worker.planner import OllamaError, plan_github_issue
from ai_worker.sources.github_issue import ResearchBrief


def brief():
    return ResearchBrief(
        url="https://github.com/acme/widget/issues/42",
        title="Fix API retry handling",
        repository="acme/widget",
        number=42,
        state="open",
        body="Add tests for retry backoff.",
        labels=["bug"],
        updated_at="2026-11-14T10:00:00Z",
    )


def valid_plan():
    return {
        "summary": "Implement bounded retry backoff for transient API errors.",
        "estimated_effort_hours": 3.5,
        "risk_level": "medium",
        "prerequisites": ["Confirm existing retry policy."],
        "implementation_steps": ["Inspect the API client.", "Implement bounded backoff."],
        "test_plan": ["Add deterministic retry tests."],
        "acceptance_checklist": ["All tests pass."],
        "blockers": [],
    }


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit):
        return json.dumps(self.payload).encode("utf-8")


def test_local_planner_returns_validated_structured_plan(monkeypatch):
    seen = {}

    class FakeOpener:
        def open(self, request, timeout):
            seen["url"] = request.full_url
            seen["body"] = json.loads(request.data.decode("utf-8"))
            seen["timeout"] = timeout
            return FakeResponse({"message": {"content": json.dumps(valid_plan())}})

    monkeypatch.setattr("ai_worker.planner.build_opener", lambda handler: FakeOpener())
    result = plan_github_issue(brief(), model="qwen2.5-coder:7b")

    assert result.estimated_effort_hours == 3.5
    assert result.risk_level == "medium"
    assert seen["url"] == "http://127.0.0.1:11434/api/chat"
    assert seen["body"]["stream"] is False
    assert "untrusted third-party data" in seen["body"]["messages"][0]["content"]
    assert seen["timeout"] == 300


def test_planner_rejects_remote_model_endpoint():
    with pytest.raises(OllamaError):
        plan_github_issue(brief(), host="https://remote.example")


def test_planner_rejects_invalid_model_output(monkeypatch):
    bad = valid_plan()
    bad["estimated_effort_hours"] = float("inf")
    class FakeOpener:
        def open(self, request, timeout):
            return FakeResponse({"message": {"content": json.dumps(bad)}})

    monkeypatch.setattr("ai_worker.planner.build_opener", lambda handler: FakeOpener())
    with pytest.raises(OllamaError):
        plan_github_issue(brief())


def test_planner_rejects_missing_required_steps(monkeypatch):
    bad = valid_plan()
    bad["implementation_steps"] = []
    monkeypatch.setattr(
        "ai_worker.planner.urlopen",
        lambda request, timeout: FakeResponse({"message": {"content": json.dumps(bad)}}),
    )
    with pytest.raises(OllamaError):
        plan_github_issue(brief())
