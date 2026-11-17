import json

import pytest

from ai_worker.planner import (
    OllamaError, _validate_plan, plan_github_issue,
    validate_serialized_task_plan,
)
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


def structured_steps():
    return [
        {
            "id": "add-tests",
            "implementation_step_index": 1,
            "depends_on": ["update-client"],
            "files": ["tests/test_client.py"],
        },
        {
            "id": "update-client",
            "implementation_step_index": 0,
            "depends_on": [],
            "files": ["src/client.py"],
        },
    ]


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
    assert result.steps == []  # Legacy model payloads remain accepted.
    assert result.to_dict()["implementation_steps"] == valid_plan()["implementation_steps"]
    assert "steps" not in result.to_dict()  # Legacy serialization remains unchanged.
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
    class FakeOpener:
        def open(self, request, timeout):
            return FakeResponse({"message": {"content": json.dumps(bad)}})

    monkeypatch.setattr("ai_worker.planner.build_opener", lambda handler: FakeOpener())
    with pytest.raises(OllamaError):
        plan_github_issue(brief())


def test_planner_includes_repository_snapshot_in_model_request(monkeypatch):
    seen = {}
    repository_context = [
        {
            "path": "src/client.py",
            "content": "class APIClient:\n    def request(self): pass\n",
        },
        {
            "path": "tests/test_client.py",
            "content": "def test_request(): pass\n",
        },
    ]

    class FakeOpener:
        def open(self, request, timeout):
            seen["body"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse({
                "message": {"content": json.dumps(valid_plan())}
            })

    monkeypatch.setattr(
        "ai_worker.planner.build_opener",
        lambda handler: FakeOpener(),
    )

    plan_github_issue(
        brief(),
        model="qwen2.5-coder:7b",
        repository_context=repository_context,
    )

    messages = seen["body"]["messages"]
    user_message = next(
        item["content"] for item in messages if item["role"] == "user"
    )
    payload_text = user_message.split("Return JSON only:\n", 1)[1]
    payload = json.loads(payload_text)

    assert payload["repository_files"] == repository_context
    assert "src/client.py" in user_message
    assert "tests/test_client.py" in user_message


def test_planner_validates_and_serializes_dependency_order(monkeypatch):
    payload = valid_plan()
    payload["steps"] = structured_steps()
    seen = {}

    class FakeOpener:
        def open(self, request, timeout):
            seen["body"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse({"message": {"content": json.dumps(payload)}})

    monkeypatch.setattr("ai_worker.planner.build_opener", lambda handler: FakeOpener())
    plan = plan_github_issue(brief())

    assert [step.id for step in plan.steps] == ["update-client", "add-tests"]
    serialized = plan.to_dict()
    assert serialized["steps"][0] == {
        "id": "update-client",
        "description": "Inspect the API client.",
        "depends_on": [],
        "files": ["src/client.py"],
    }
    prompt = seen["body"]["messages"][0]["content"]
    assert "Only declare a dependency when" in prompt
    assert "explicitly list any intended new-file path" in prompt
    validated = validate_serialized_task_plan(serialized)
    assert [step["id"] for step in validated["steps"]] == [
        "update-client", "add-tests"
    ]


def test_serialized_structured_plan_rejects_incomplete_step_mapping(monkeypatch):
    payload = valid_plan()
    payload["steps"] = structured_steps()
    class FakeOpener:
        def open(self, request, timeout):
            return FakeResponse({"message": {"content": json.dumps(payload)}})
    monkeypatch.setattr("ai_worker.planner.build_opener", lambda handler: FakeOpener())
    serialized = plan_github_issue(brief()).to_dict()
    serialized["steps"].pop()
    with pytest.raises(OllamaError, match="one-to-one"):
        validate_serialized_task_plan(serialized)


def test_serialized_structured_plan_reports_malformed_base_fields():
    payload = valid_plan()
    payload["steps"] = structured_steps()
    payload["implementation_steps"] = None
    with pytest.raises(OllamaError, match="implementation_steps must be a list"):
        validate_serialized_task_plan(payload)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda steps: steps.__setitem__(1, {**steps[1], "id": "add-tests"}), "Duplicate structured step id"),
        (lambda steps: steps[1].__setitem__("implementation_step_index", 1), "Duplicate implementation_step_index"),
        (lambda steps: steps[1].__setitem__("implementation_step_index", 3), "invalid implementation_step_index"),
        (lambda steps: steps[0].__setitem__("depends_on", ["missing"]), "unknown step id"),
        (lambda steps: steps[0].__setitem__("depends_on", ["add-tests"]), "cannot depend on itself"),
        (lambda steps: steps[1].__setitem__("depends_on", ["add-tests"]), "contain a cycle"),
    ],
)
def test_planner_rejects_invalid_dependency_graph(mutate, message):
    payload = valid_plan()
    payload["steps"] = structured_steps()
    mutate(payload["steps"])
    with pytest.raises(OllamaError, match=message):
        _validate_plan(payload)


def test_planner_rejects_unsafe_planned_file_path():
    payload = valid_plan()
    payload["steps"] = structured_steps()
    payload["steps"][1]["files"] = ["../outside.py"]
    with pytest.raises(OllamaError, match="unsafe file path"):
        _validate_plan(payload)


@pytest.mark.parametrize("path", ["/etc/passwd", "../outside.py", "C:/outside.py", "a/../b.py", "bad\u0001.py"])
def test_planner_rejects_absolute_traversal_and_unsafe_paths(path):
    payload = valid_plan()
    payload["steps"] = structured_steps()
    payload["steps"][1]["files"] = [path]
    with pytest.raises(OllamaError, match="unsafe file path"):
        _validate_plan(payload)
