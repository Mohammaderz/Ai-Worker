import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from ai_worker.workspace import WorkspaceError, clone_public_github_repo


def test_clone_uses_public_https_and_isolated_git_environment(monkeypatch, tmp_path):
    root = tmp_path / "scratch"
    workspace = root / "task-42"
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["env"] = kwargs["env"]
        workspace.joinpath(".git").mkdir()
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr("ai_worker.workspace.subprocess.run", fake_run)
    result = clone_public_github_repo(
        "acme/widget", workspace, scratch_root=root
    )

    assert result.repository == "acme/widget"
    assert result.path == str(workspace)
    assert ("https://" + "github.com/acme/widget.git") in captured["argv"]
    assert "--no-recurse-submodules" in captured["argv"]
    assert "--filter=blob:limit=1m" in captured["argv"]
    assert captured["env"]["GIT_TERMINAL_PROMPT"] == "0"
    assert captured["env"]["GIT_CONFIG_NOSYSTEM"] == "1"
    assert "GITHUB_TOKEN" not in captured["env"]


def test_rejects_noncanonical_repository_name(tmp_path):
    with pytest.raises(WorkspaceError):
        clone_public_github_repo("../evil", tmp_path / "task", scratch_root=tmp_path)


def test_rejects_workspace_outside_scratch_root(tmp_path):
    root = tmp_path / "scratch"
    root.mkdir()
    with pytest.raises(WorkspaceError):
        clone_public_github_repo("acme/widget", tmp_path / "outside", scratch_root=root)


def test_rejects_existing_workspace(tmp_path):
    root = tmp_path / "scratch"
    root.mkdir()
    workspace = root / "existing"
    workspace.mkdir()
    with pytest.raises(WorkspaceError):
        clone_public_github_repo("acme/widget", workspace, scratch_root=root)


def test_failed_clone_cleans_partial_workspace(monkeypatch, tmp_path):
    root = tmp_path / "scratch"
    workspace = root / "partial"

    def fake_run(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 128, "", "repository not found")

    monkeypatch.setattr("ai_worker.workspace.subprocess.run", fake_run)
    with pytest.raises(WorkspaceError):
        clone_public_github_repo("acme/missing", workspace, scratch_root=root)
    assert not workspace.exists()


def test_timeout_cleans_partial_workspace(monkeypatch, tmp_path):
    root = tmp_path / "scratch"
    workspace = root / "partial"

    def fake_run(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, 1)

    monkeypatch.setattr("ai_worker.workspace.subprocess.run", fake_run)

    with pytest.raises(WorkspaceError, match="timed out"):
        clone_public_github_repo("acme/widget", workspace, scratch_root=root)

    assert not workspace.exists()


def test_missing_git_cleans_partial_workspace(monkeypatch, tmp_path):
    root = tmp_path / "scratch"
    workspace = root / "partial"

    def fake_run(argv, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr("ai_worker.workspace.subprocess.run", fake_run)

    with pytest.raises(WorkspaceError, match="Git is not installed"):
        clone_public_github_repo("acme/widget", workspace, scratch_root=root)

    assert not workspace.exists()


def test_unexpected_error_cleans_partial_workspace(monkeypatch, tmp_path):
    root = tmp_path / "scratch"
    workspace = root / "partial"

    def fake_run(argv, **kwargs):
        raise RuntimeError("unexpected failure")

    monkeypatch.setattr("ai_worker.workspace.subprocess.run", fake_run)

    with pytest.raises(RuntimeError, match="unexpected failure"):
        clone_public_github_repo("acme/widget", workspace, scratch_root=root)

    assert not workspace.exists()


def test_success_without_git_metadata_raises_and_cleans(monkeypatch, tmp_path):
    root = tmp_path / "scratch"
    workspace = root / "missing"

    def fake_run(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr("ai_worker.workspace.subprocess.run", fake_run)

    with pytest.raises(WorkspaceError, match="Git metadata was not created"):
        clone_public_github_repo("acme/widget", workspace, scratch_root=root)

    assert not workspace.exists()


def test_cleanup_error_does_not_mask_original_clone_error(monkeypatch, tmp_path):
    root = tmp_path / "scratch"
    workspace = root / "partial"

    def fake_run(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 128, "", "original clone failure")

    original_rmtree = shutil.rmtree

    def fake_rmtree(path, *args, **kwargs):
        if Path(path).name == workspace.name:
            raise PermissionError("cleanup denied")
        return original_rmtree(path, *args, **kwargs)

    monkeypatch.setattr("ai_worker.workspace.subprocess.run", fake_run)
    monkeypatch.setattr("ai_worker.workspace.shutil.rmtree", fake_rmtree)

    with pytest.raises(WorkspaceError, match="original clone failure"):
        clone_public_github_repo("acme/widget", workspace, scratch_root=root)


def test_cleanup_does_not_follow_symlink_workspace(monkeypatch, tmp_path):
    root = tmp_path / "scratch"
    workspace = root / "partial"
    external = tmp_path / "external"
    external.mkdir()
    (external / "keep.txt").write_text("keep")

    def fake_run(argv, **kwargs):
        workspace.rmdir()
        workspace.symlink_to(external, target_is_directory=True)
        return subprocess.CompletedProcess(argv, 128, "", "clone failed")

    monkeypatch.setattr("ai_worker.workspace.subprocess.run", fake_run)

    with pytest.raises(WorkspaceError, match="clone failed"):
        clone_public_github_repo("acme/widget", workspace, scratch_root=root)

    assert workspace.is_symlink()
    assert (external / "keep.txt").read_text() == "keep"


def test_cleanup_does_not_remove_workspace_created_by_another_process(monkeypatch, tmp_path):
    root = tmp_path / "scratch"
    workspace = root / "partial"

    def fake_run(argv, **kwargs):
        workspace.rename(root / "displaced")
        workspace.mkdir()
        (workspace / "owned-by-other-process.txt").write_text("keep")
        return subprocess.CompletedProcess(argv, 128, "", "clone failed")

    monkeypatch.setattr("ai_worker.workspace.subprocess.run", fake_run)

    with pytest.raises(WorkspaceError, match="clone failed"):
        clone_public_github_repo("acme/widget", workspace, scratch_root=root)

    assert (workspace / "owned-by-other-process.txt").read_text() == "keep"



def test_scratch_root_permissions_are_restricted(monkeypatch, tmp_path):
    root = tmp_path / "scratch"
    root.mkdir()
    root.chmod(0o755)
    workspace = root / "task"

    def fake_run(argv, **kwargs):
        workspace.joinpath(".git").mkdir()
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr("ai_worker.workspace.subprocess.run", fake_run)

    clone_public_github_repo("acme/widget", workspace, scratch_root=root)

    assert stat.S_IMODE(root.stat().st_mode) == 0o700


def test_rejects_symlink_scratch_root(tmp_path):
    real_root = tmp_path / "real-scratch"
    real_root.mkdir()
    real_root.chmod(0o755)
    linked_root = tmp_path / "linked-scratch"
    linked_root.symlink_to(real_root, target_is_directory=True)

    with pytest.raises(WorkspaceError, match="Scratch root"):
        clone_public_github_repo(
            "acme/widget",
            linked_root / "task",
            scratch_root=linked_root,
        )

    assert stat.S_IMODE(real_root.stat().st_mode) == 0o755
