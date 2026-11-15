import io
import subprocess

import pytest

from ai_worker.sandbox import MAX_OUTPUT_BYTES, MAX_OUTPUT_CHARS, SandboxError, run_in_sandbox


def workspace_pair(tmp_path):
    root = tmp_path / "scratch"
    root.mkdir()
    work = root / "task-1"
    work.mkdir()
    return root, work


def test_sandbox_uses_networkless_hardened_docker(monkeypatch, tmp_path):
    root, work = workspace_pair(tmp_path)
    seen = {}

    class FakeProcess:
        stdout = io.BytesIO(b"ok")
        stderr = io.BytesIO(b"")

        def poll(self):
            return 0

        def wait(self, timeout=None):
            return 0

    def fake_popen(argv, **kwargs):
        seen["argv"] = argv
        seen["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setattr("ai_worker.sandbox.subprocess.Popen", fake_popen)
    result = run_in_sandbox(work, ["python", "-m", "pytest"], scratch_root=root)

    assert result.exit_code == 0
    assert result.stdout == "ok"
    assert "stdout" in seen["kwargs"] and "stderr" in seen["kwargs"]
    assert "--network=none" in seen["argv"]
    assert "--read-only" in seen["argv"]
    assert "--cap-drop=ALL" in seen["argv"]
    assert "--memory=1g" in seen["argv"]
    assert any(arg.startswith("--user=") for arg in seen["argv"])
    assert seen["argv"][-3:] == ["python", "-m", "pytest"]


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

    class HangingProcess:
        stdout = io.BytesIO()
        stderr = io.BytesIO()
        running = True

        def poll(self):
            return None if self.running else -9

        def kill(self):
            self.running = False

        def wait(self, timeout=None):
            return -9

    monkeypatch.setattr("ai_worker.sandbox.subprocess.Popen", lambda *a, **k: HangingProcess())
    clock = iter([0.0, 2.0])
    monkeypatch.setattr("ai_worker.sandbox.time.monotonic", lambda: next(clock))
    monkeypatch.setattr("ai_worker.sandbox.time.sleep", lambda _: None)

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr("ai_worker.sandbox.subprocess.run", fake_run)
    result = run_in_sandbox(work, ["python", "-V"], scratch_root=root, timeout_seconds=1)

    assert result.timed_out
    assert result.exit_code == 124
    assert calls[0][0:2] == ["docker", "kill"]
    assert calls[1][0:3] == ["docker", "rm", "-f"]


def test_sandbox_stops_process_after_bounded_output(monkeypatch, tmp_path):
    root, work = workspace_pair(tmp_path)
    calls = []

    class NoisyProcess:
        stdout = io.BytesIO(b"x" * (MAX_OUTPUT_BYTES + 1))
        stderr = io.BytesIO()

        def poll(self):
            return 0

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr("ai_worker.sandbox.subprocess.Popen", lambda *a, **k: NoisyProcess())

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr("ai_worker.sandbox.subprocess.run", fake_run)
    result = run_in_sandbox(work, ["python", "-V"], scratch_root=root)

    assert result.exit_code == 125
    assert not result.timed_out
    assert "output exceeded" in result.stderr
    assert len(result.stdout) <= MAX_OUTPUT_CHARS
    assert calls[0][0:2] == ["docker", "kill"]
    assert calls[1][0:3] == ["docker", "rm", "-f"]
