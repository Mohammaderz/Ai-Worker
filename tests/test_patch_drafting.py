import json

from ai_worker.developer import PatchError, collect_repo_context, draft_patch
from ai_worker.sources.github_issue import ResearchBrief


ISSUE = ResearchBrief(
    url="https://github.com/acme/widget/issues/42",
    title="Fix API retry handling",
    repository="acme/widget",
    number=42,
    state="open",
    body="Add tests for retry backoff.",
    labels=["bug"],
    updated_at="2026-11-14T10:00:00Z",
)

DIFF = """diff --git a/client.py b/client.py
index 1111111..2222222 100644
--- a/client.py
+++ b/client.py
@@ -1 +1 @@
-before
+after
"""


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit):
        return json.dumps(self.payload).encode("utf-8")


def test_context_excludes_git_and_environment_files(tmp_path):
    (tmp_path / "main.py").write_text("print('hello')", encoding="utf-8")
    (tmp_path / ".env").write_text("API_KEY=secret", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("secret config", encoding="utf-8")

    context = collect_repo_context(tmp_path)
    paths = [item["path"] for item in context]

    assert "main.py" in paths
    assert ".env" not in paths
    assert ".git/config" not in paths


def test_draft_patch_returns_validated_diff_without_writing_files(monkeypatch, tmp_path):
    (tmp_path / "client.py").write_text("before\n", encoding="utf-8")
    seen = {}

    response = {
        "message": {
            "content": json.dumps({
                "status": "patch",
                "summary": "Update retry handling.",
                "diff": DIFF,
                "assumptions": ["The existing client is the intended target."],
                "questions": [],
            })
        }
    }

    class FakeOpener:
        def open(self, request, timeout):
            seen["request"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse(response)

    monkeypatch.setattr("ai_worker.developer.build_opener", lambda handler: FakeOpener())
    proposal = draft_patch(ISSUE, tmp_path, model="qwen2.5-coder:7b")

    assert proposal.changed_files == ["client.py"]
    assert proposal.diff == DIFF
    user_content = next(item["content"] for item in seen["request"]["messages"] if item["role"] == "user")
    assert "client.py" in user_content
    assert ".env" not in user_content
    assert not (tmp_path / ".ai-worker-generated.patch").exists()


def test_draft_patch_rejects_sensitive_file_targets(monkeypatch, tmp_path):
    (tmp_path / "main.py").write_text("print('hello')", encoding="utf-8")
    bad_diff = DIFF.replace("client.py", ".env")
    response = {
        "message": {
            "content": json.dumps({
                "status": "patch",
                "summary": "Unsafe change.",
                "diff": bad_diff,
                "assumptions": [],
                "questions": [],
            })
        }
    }

    class FakeOpener:
        def open(self, request, timeout):
            return FakeResponse(response)

    monkeypatch.setattr("ai_worker.developer.build_opener", lambda handler: FakeOpener())
    import pytest
    with pytest.raises(PatchError):
        draft_patch(ISSUE, tmp_path)


def test_context_prioritizes_paths_related_to_issue(tmp_path):
    (tmp_path / "aaa.py").write_text("unrelated = True", encoding="utf-8")
    (tmp_path / "retry.py").write_text("retry = True", encoding="utf-8")

    context = collect_repo_context(tmp_path, brief=ISSUE)

    assert context[0]["path"] == "retry.py"

def test_context_prioritizes_relevant_file_contents(tmp_path):
    for index in range(65):
        (tmp_path / f"a_unrelated_{index:02}.py").write_text(
            "unrelated_value = True", encoding="utf-8"
        )

    (tmp_path / "z_relevant.py").write_text(
        "The retry backoff implementation handles the API response.",
        encoding="utf-8",
    )

    context = collect_repo_context(tmp_path, brief=ISSUE)

    assert context[0]["path"] == "z_relevant.py"


def test_draft_patch_returns_needs_information_without_diff(monkeypatch, tmp_path):
    (tmp_path / "client.py").write_text("before\n", encoding="utf-8")
    response = {
        "message": {
            "content": json.dumps({
                "status": "needs_information",
                "summary": "More information is needed.",
                "diff": "",
                "assumptions": [],
                "questions": ["What retry backoff behavior is expected?"],
            })
        }
    }

    class FakeOpener:
        def open(self, request, timeout):
            return FakeResponse(response)

    monkeypatch.setattr("ai_worker.developer.build_opener", lambda handler: FakeOpener())

    proposal = draft_patch(ISSUE, tmp_path)

    assert proposal.status == "needs_information"
    assert proposal.diff == ""
    assert proposal.changed_files == []
    assert proposal.questions == ["What retry backoff behavior is expected?"]


def test_draft_patch_rejects_needs_information_with_diff():
    import pytest
    from ai_worker.developer import _validate_patch_response

    with pytest.raises(PatchError):
        _validate_patch_response({
            "status": "needs_information",
            "summary": "Invalid response.",
            "diff": DIFF,
            "assumptions": [],
            "questions": ["What is missing?"],
        })


def test_draft_patch_fails_when_repair_response_is_invalid(monkeypatch, tmp_path):
    import pytest

    (tmp_path / "main.py").write_text("print('hello')", encoding="utf-8")
    bad_diff = DIFF.replace("client.py", ".env")

    def make_response(diff):
        return {
            "message": {
                "content": json.dumps({
                    "status": "patch",
                    "summary": "Unsafe patch.",
                    "diff": diff,
                    "assumptions": [],
                    "questions": [],
                })
            }
        }

    responses = [make_response(bad_diff), make_response(bad_diff)]

    class FakeOpener:
        def __init__(self):
            self.calls = 0

        def open(self, request, timeout):
            response = responses[self.calls]
            self.calls += 1
            return FakeResponse(response)

    opener = FakeOpener()
    monkeypatch.setattr("ai_worker.developer.build_opener", lambda handler: opener)

    with pytest.raises(PatchError):
        draft_patch(ISSUE, tmp_path)

    assert opener.calls == 2


def test_draft_patch_repairs_invalid_json_response(monkeypatch, tmp_path):
    import pytest

    (tmp_path / "client.py").write_text("before\n", encoding="utf-8")

    responses = [
        {"message": {"content": "not valid JSON"}},
        {"message": {"content": "still not valid JSON"}},
    ]

    class FakeOpener:
        def __init__(self):
            self.calls = 0

        def open(self, request, timeout):
            response = responses[self.calls]
            self.calls += 1
            return FakeResponse(response)

    opener = FakeOpener()
    monkeypatch.setattr(
        "ai_worker.developer.build_opener",
        lambda handler: opener,
    )

    with pytest.raises(PatchError):
        draft_patch(ISSUE, tmp_path)

    assert opener.calls == 2


def test_context_scan_has_a_hard_candidate_limit(monkeypatch, tmp_path):
    for index in range(8):
        (tmp_path / f"file_{index:02}.py").write_text(
            f"value = {index}", encoding="utf-8"
        )
    monkeypatch.setattr("ai_worker.developer.MAX_CONTEXT_SCAN_FILES", 3)

    context = collect_repo_context(tmp_path)

    assert [item["path"] for item in context] == [
        "file_00.py", "file_01.py", "file_02.py"
    ]


def test_context_scan_has_a_hard_byte_budget(monkeypatch, tmp_path):
    (tmp_path / "a.py").write_text("12345678", encoding="utf-8")
    (tmp_path / "b.py").write_text("abcdefgh", encoding="utf-8")
    monkeypatch.setattr("ai_worker.developer.MAX_CONTEXT_SCAN_BYTES", 10)

    context = collect_repo_context(tmp_path)

    assert [item["path"] for item in context] == ["a.py"]
