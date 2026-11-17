import io
import subprocess

import pytest

from ai_worker.sandbox import MAX_OUTPUT_BYTES, MAX_OUTPUT_CHARS, SandboxError, run_in_sandbox


@pytest.fixture(autouse=True)
def run_sandbox_tests_as_non_root(monkeypatch):
    # Production deliberately refuses root-owned host processes. Keep these
    # command-construction tests portable to root-based CI containers.
    monkeypatch.setattr("ai_worker.sandbox.os.getuid", lambda: 1000)
    monkeypatch.setattr("ai_worker.sandbox.os.getgid", lambda: 1000)


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


def test_sandbox_refuses_root_owned_host_process(monkeypatch, tmp_path):
    root, work = workspace_pair(tmp_path)
    monkeypatch.setattr("ai_worker.sandbox.os.getuid", lambda: 0)
    with pytest.raises(SandboxError, match="root-owned"):
        run_in_sandbox(work, ["python", "-V"], scratch_root=root)


def test_unexpected_error_after_docker_start_cleans_up_container(monkeypatch, tmp_path):
    root, work = workspace_pair(tmp_path)
    calls = []

    class RunningProcess:
        stdout = io.BytesIO()
        stderr = io.BytesIO()
        stopped = False

        def poll(self):
            return -9 if self.stopped else None

        def kill(self):
            self.stopped = True

        def wait(self, timeout=None):
            return -9

    process = RunningProcess()
    monkeypatch.setattr("ai_worker.sandbox.subprocess.Popen", lambda *a, **k: process)
    monkeypatch.setattr("ai_worker.sandbox.threading.Thread.start", lambda self: (_ for _ in ()).throw(RuntimeError("thread start failed")))

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr("ai_worker.sandbox.subprocess.run", fake_run)

    with pytest.raises(RuntimeError, match="thread start failed"):
        run_in_sandbox(work, ["python", "-V"], scratch_root=root)

    assert process.stopped
    assert calls[0][0:2] == ["docker", "kill"]
    assert calls[1][0:3] == ["docker", "rm", "-f"]


def test_host_process_stop_has_a_bounded_wait(monkeypatch, tmp_path):
    root, work = workspace_pair(tmp_path)
    calls = []

    class UnstoppableProcess:
        stdout = io.BytesIO()
        stderr = io.BytesIO()

        def poll(self):
            return None

        def kill(self):
            pass

        def wait(self, timeout=None):
            raise subprocess.TimeoutExpired("docker", timeout)

    monkeypatch.setattr("ai_worker.sandbox.subprocess.Popen", lambda *a, **k: UnstoppableProcess())
    clock = iter([0.0, 2.0])
    monkeypatch.setattr("ai_worker.sandbox.time.monotonic", lambda: next(clock))
    monkeypatch.setattr("ai_worker.sandbox.time.sleep", lambda _: None)

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr("ai_worker.sandbox.subprocess.run", fake_run)

    with pytest.raises(SandboxError, match="could not be stopped"):
        run_in_sandbox(work, ["python", "-V"], scratch_root=root, timeout_seconds=1)

    assert calls[0][0:2] == ["docker", "kill"]
    assert calls[1][0:3] == ["docker", "rm", "-f"]


def test_rejects_symlink_workspace(tmp_path):
    root, work = workspace_pair(tmp_path)
    linked = root / "linked-task"
    linked.symlink_to(work, target_is_directory=True)

    with pytest.raises(SandboxError):
        run_in_sandbox(linked, ["python", "-V"], scratch_root=root)


def test_container_cleanup_retries_when_container_is_not_yet_available(monkeypatch):
    from ai_worker.sandbox import _cleanup_container

    calls = []
    outcomes = iter([1, 1, 0])

    def fake_run(argv, **kwargs):
        calls.append(argv)
        if argv[1] == "rm":
            return subprocess.CompletedProcess(argv, next(outcomes), "", "")
        return subprocess.CompletedProcess(argv, 1, "", "")

    monkeypatch.setattr("ai_worker.sandbox.subprocess.run", fake_run)
    monkeypatch.setattr("ai_worker.sandbox.time.sleep", lambda _: None)

    _cleanup_container("ai-worker-task-test")

    assert [call[1] for call in calls] == ["kill", "rm", "kill", "rm", "kill", "rm"]



def test_container_cleanup_logs_when_all_retries_fail(monkeypatch, caplog):
    import logging
    from ai_worker.sandbox import _cleanup_container

    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 1, "", "still present")

    monkeypatch.setattr("ai_worker.sandbox.subprocess.run", fake_run)
    monkeypatch.setattr("ai_worker.sandbox.time.sleep", lambda _: None)

    with caplog.at_level(logging.ERROR, logger="ai_worker.sandbox"):
        _cleanup_container("ai-worker-task-stuck")

    assert sum(call[1] == "rm" for call in calls) == 3
    assert "Could not confirm removal" in caplog.text
    assert "ai-worker-task-stuck" in caplog.text



def test_sandbox_network_is_enabled_only_by_explicit_opt_in(monkeypatch, tmp_path):
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
        return FakeProcess()

    monkeypatch.setattr(
        "ai_worker.sandbox.subprocess.Popen",
        fake_popen,
    )

    result = run_in_sandbox(
        work,
        ["npm", "--version"],
        scratch_root=root,
        network_enabled=True,
    )

    assert result.exit_code == 0
    assert "--network=bridge" in seen["argv"]
    assert "--network=none" not in seen["argv"]
    assert "--read-only" in seen["argv"]
    assert "--cap-drop=ALL" in seen["argv"]
