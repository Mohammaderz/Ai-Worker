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
    assert "main.py" in user_content
    assert ".env" not in user_content
    assert not (tmp_path / ".ai-worker-generated.patch").exists()


def test_draft_patch_rejects_sensitive_file_targets(monkeypatch, tmp_path):
    (tmp_path / "main.py").write_text("print('hello')", encoding="utf-8")
    bad_diff = DIFF.replace("client.py", ".env")
    response = {
        "message": {
            "content": json.dumps({
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
