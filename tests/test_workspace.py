import subprocess

import pytest

from ai_worker.workspace import WorkspaceError, clone_public_github_repo


def test_clone_uses_public_https_and_isolated_git_environment(monkeypatch, tmp_path):
    root = tmp_path / "scratch"
    workspace = root / "task-42"
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["env"] = kwargs["env"]
        workspace.mkdir(parents=True)
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr("ai_worker.workspace.subprocess.run", fake_run)
    result = clone_public_github_repo(
        "acme/widget", workspace, scratch_root=root
    )

    assert result.repository == "acme/widget"
    assert result.path == str(workspace)
    assert "https://github.com/acme/widget.git" in captured["argv"]
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
        workspace.mkdir(parents=True)
        return subprocess.CompletedProcess(argv, 128, "", "repository not found")

    monkeypatch.setattr("ai_worker.workspace.subprocess.run", fake_run)
    with pytest.raises(WorkspaceError):
        clone_public_github_repo("acme/missing", workspace, scratch_root=root)
    assert not workspace.exists()
