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
    assert not (workspace / ".ai-worker-generated.patch").exists()


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


def test_validate_new_file_patch():
    patch = """diff --git a/new.txt b/new.txt
new file mode 100644
--- /dev/null
+++ b/new.txt
@@ -0,0 +1 @@
+hello
"""
    assert validate_patch_text(patch) == ["new.txt"]


def test_validate_deleted_file_patch():
    patch = """diff --git a/old.txt b/old.txt
deleted file mode 100644
--- a/old.txt
+++ /dev/null
@@ -1 +0,0 @@
-goodbye
"""
    assert validate_patch_text(patch) == ["old.txt"]


def test_validate_multiple_file_patch():
    patch = VALID_DIFF + VALID_DIFF.replace("hello.txt", "second.txt")
    assert validate_patch_text(patch) == ["hello.txt", "second.txt"]


def test_reject_hunk_with_incorrect_declared_line_counts():
    patch = VALID_DIFF.replace("@@ -1 +1 @@", "@@ -1,2 +1 @@")
    with pytest.raises(PatchError, match="incorrect line counts"):
        validate_patch_text(patch)


def test_reject_quoted_git_paths_until_supported():
    patch = VALID_DIFF.replace("a/hello.txt b/hello.txt", '"a/hello world.txt" "b/hello world.txt"')
    with pytest.raises(PatchError, match="quoted Git diff path"):
        validate_patch_text(patch)


def test_accept_executable_bit_change_with_content_hunk():
    patch = VALID_DIFF.replace("index 1111111..2222222 100644", "old mode 100644\nnew mode 100755")
    assert validate_patch_text(patch) == ["hello.txt"]


def test_validate_source_lines_that_look_like_file_headers():
    patch = VALID_DIFF.replace("-before", "--- this is source text").replace("+after", "+++ this is new source text")
    assert validate_patch_text(patch) == ["hello.txt"]


def test_reject_submodule_index_mode():
    patch = VALID_DIFF.replace("100644", "160000")
    with pytest.raises(PatchError, match="Submodule changes"):
        validate_patch_text(patch)


def test_patch_file_is_cleaned_when_sandbox_raises(monkeypatch, tmp_path):
    root = tmp_path / "scratch"
    root.mkdir()
    workspace = root / "repo"
    workspace.mkdir()

    def failing_runner(*args, **kwargs):
        from ai_worker.sandbox import SandboxError
        raise SandboxError("docker unavailable")

    monkeypatch.setattr("ai_worker.developer.run_in_sandbox", failing_runner)
    from ai_worker.sandbox import SandboxError
    with pytest.raises(SandboxError, match="docker unavailable"):
        apply_patch_in_sandbox(VALID_DIFF, workspace, scratch_root=root)

    assert not (workspace / ".ai-worker-generated.patch").exists()


def test_patch_apply_refuses_preexisting_patch_path(monkeypatch, tmp_path):
    root = tmp_path / "scratch"
    root.mkdir()
    workspace = root / "repo"
    workspace.mkdir()
    patch_file = workspace / ".ai-worker-generated.patch"
    patch_file.write_text("do not overwrite", encoding="utf-8")

    def unexpected_runner(*args, **kwargs):
        pytest.fail("sandbox must not run when the patch path already exists")

    monkeypatch.setattr("ai_worker.developer.run_in_sandbox", unexpected_runner)
    with pytest.raises(PatchError, match="already exists"):
        apply_patch_in_sandbox(VALID_DIFF, workspace, scratch_root=root)

    assert patch_file.read_text(encoding="utf-8") == "do not overwrite"


def test_patch_cleanup_error_does_not_mask_sandbox_error(monkeypatch, tmp_path):
    root = tmp_path / "scratch"
    root.mkdir()
    workspace = root / "repo"
    workspace.mkdir()

    patch_file = workspace / ".ai-worker-generated.patch"

    def failing_runner(*args, **kwargs):
        from ai_worker.sandbox import SandboxError
        raise SandboxError("original sandbox failure")

    original_unlink = type(patch_file).unlink

    def failing_unlink(path, *args, **kwargs):
        if path.name == ".ai-worker-generated.patch":
            raise PermissionError("cleanup denied")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr("ai_worker.developer.run_in_sandbox", failing_runner)
    monkeypatch.setattr("ai_worker.developer.Path.unlink", failing_unlink)

    from ai_worker.sandbox import SandboxError

    with pytest.raises(SandboxError, match="original sandbox failure"):
        apply_patch_in_sandbox(VALID_DIFF, workspace, scratch_root=root)
