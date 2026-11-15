import pytest

from ai_worker.developer import (
    PatchError,
    apply_patch_in_sandbox,
    validate_patch_text,
)
from ai_worker.sandbox import SandboxResult


VALID_DIFF = """diff --git a/hello.txt b/hello.txt
index 1111111..2222222 100644
--- a/hello.txt
+++ b/hello.txt
@@ -1 +1 @@
-before
+after
"""


def test_validate_normal_text_patch():
    assert validate_patch_text(VALID_DIFF) == ["hello.txt"]


@pytest.mark.parametrize(
    "patch",
    [
        VALID_DIFF.replace("a/hello.txt b/hello.txt", "a/../secret b/../secret"),
        VALID_DIFF.replace("a/hello.txt b/hello.txt", "a/.env b/.env"),
        VALID_DIFF.replace("+++ b/hello.txt", "+++ b/other.txt"),
        VALID_DIFF + "GIT binary patch\n",
        VALID_DIFF.replace("100644", "120000"),
    ],
)
def test_reject_unsafe_patch(patch):
    with pytest.raises(PatchError):
        validate_patch_text(patch)


def test_apply_patch_checks_before_applying(monkeypatch, tmp_path):
    root = tmp_path / "scratch"
    root.mkdir()
    workspace = root / "repo"
    workspace.mkdir()
    calls = []

    def fake_runner(workspace_arg, command, **kwargs):
        calls.append(command)
        return SandboxResult(0, "", "")

    monkeypatch.setattr("ai_worker.developer.run_in_sandbox", fake_runner)
    result = apply_patch_in_sandbox(VALID_DIFF, workspace, scratch_root=root)

    assert result.applied
    assert result.changed_files == ["hello.txt"]
    assert calls[0][1:3] == ["apply", "--check"]
    assert calls[1][1] == "apply"
    assert not (workspace / ".ai-worker-generated.patch").exists()


def test_failed_patch_check_never_applies(monkeypatch, tmp_path):
    root = tmp_path / "scratch"
    root.mkdir()
    workspace = root / "repo"
    workspace.mkdir()
    calls = []

    def fake_runner(workspace_arg, command, **kwargs):
        calls.append(command)
        return SandboxResult(1, "", "patch does not apply")

    monkeypatch.setattr("ai_worker.developer.run_in_sandbox", fake_runner)
    result = apply_patch_in_sandbox(VALID_DIFF, workspace, scratch_root=root)

    assert not result.applied
    assert len(calls) == 1
    assert (workspace / ".ai-worker-generated.patch").exists()


@pytest.mark.parametrize(
    "patch",
    [
        "diff --git a/hello.txt b/hello.txt\n",
        "diff --git a/hello.txt b/hello.txt\n--- a/hello.txt\n+++ b/hello.txt\n",
        "diff --git a/hello.txt b/hello.txt\n--- a/hello.txt\n+++ b/hello.txt\n@@ malformed @@\n-before\n+after\n",
        "diff --git a/hello.txt b/hello.txt\n+++ b/hello.txt\n@@ -1 +1 @@\n-before\n+after\n",
    ],
)
def test_reject_patch_without_complete_unified_diff_structure(patch):
    with pytest.raises(PatchError):
        validate_patch_text(patch)
