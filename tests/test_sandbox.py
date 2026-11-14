import subprocess

import pytest

from ai_worker.sandbox import SandboxError, run_in_sandbox


def workspace_pair(tmp_path):
    root = tmp_path / "scratch"
    root.mkdir()
    work = root / "task-1"
    work.mkdir()
    return root, work


def test_sandbox_uses_networkless_hardened_docker(monkeypatch, tmp_path):
    root, work = workspace_pair(tmp_path)
    seen = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        seen["kwargs"] = kwargs
        return subprocess.CompletedProcess(argv, 0, "ok", "")

    monkeypatch.setattr("ai_worker.sandbox.subprocess.run", fake_run)
    result = run_in_sandbox(work, ["python", "-m", "pytest"], scratch_root=root)

    assert result.exit_code == 0
    assert "--network=none" in seen["argv"]
    assert "--read-only" in seen["argv"]
    assert "--cap-drop=ALL" in seen["argv"]
    assert "--memory=1g" in seen["argv"]
    assert any(arg.startswith("--user=") for arg in seen["argv"])
    assert seen["argv"][-3:] == ["python", "-m", "pytest"]
    assert seen["kwargs"]["timeout"] == 600


def test_rejects_workspace_outside_scratch_root(tmp_path):
    root, _ = workspace_pair(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    with pytest.raises(SandboxError):
        run_in_sandbox(outside, ["python", "-V"], scratch_root=root)


def test_rejects_empty_command(tmp_path):
    root, work = workspace_pair(tmp_path)
    with pytest.raises(SandboxError):
        run_in_sandbox(work, [], scratch_root=root)


def test_timeout_kills_and_removes_container(monkeypatch, tmp_path):
    root, work = workspace_pair(tmp_path)
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        if argv[0:2] == ["docker", "run"]:
            raise subprocess.TimeoutExpired(argv, 1, output="partial")
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr("ai_worker.sandbox.subprocess.run", fake_run)
    result = run_in_sandbox(work, ["python", "-V"], scratch_root=root, timeout_seconds=1)

    assert result.timed_out
    assert result.exit_code == 124
    assert calls[1][0:2] == ["docker", "kill"]
    assert calls[2][0:3] == ["docker", "rm", "-f"]
