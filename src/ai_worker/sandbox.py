"""Disposable, network-isolated Docker runner for untrusted task workspaces.

The caller must create a disposable workspace under the configured scratch root.
No host credentials or environment variables are forwarded into the container.
"""
from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path


DEFAULT_IMAGE = "ai-worker-sandbox:py311"
DEFAULT_NODE_IMAGE = "ai-worker-sandbox:node22"
MAX_OUTPUT_CHARS = 20_000
MAX_OUTPUT_BYTES = 1_000_000

logger = logging.getLogger(__name__)


class SandboxError(RuntimeError):
    """Raised when a sandbox cannot be safely prepared or started."""


@dataclass(slots=True)
class SandboxResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False


def _text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _validate_workspace(workspace: str | Path, scratch_root: str | Path) -> Path:
    try:
        if Path(workspace).is_symlink():
            raise SandboxError("Workspace cannot be a symbolic link")
        root = Path(scratch_root).resolve(strict=True)
        target = Path(workspace).resolve(strict=True)
    except OSError as exc:
        raise SandboxError(f"Workspace path could not be resolved: {exc}") from exc
    if not root.is_dir() or not target.is_dir():
        raise SandboxError("Scratch root and workspace must both be directories")
    if target == root:
        raise SandboxError("The scratch root itself cannot be mounted as a task workspace")
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise SandboxError("Workspace must be inside the dedicated scratch root") from exc
    if "," in str(target):
        raise SandboxError("Workspace path cannot contain commas")
    return target


def _stop_host_process(process: subprocess.Popen) -> None:
    """Stop the Docker CLI without waiting forever for an unresponsive process."""
    if process.poll() is None:
        try:
            process.kill()
        except OSError:
            pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except OSError:
            pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired as exc:
            raise SandboxError("Docker CLI could not be stopped after termination") from exc


def _cleanup_container(container_name: str) -> None:
    """Retry bounded container cleanup in case Docker is still processing creation."""
    for attempt in range(3):
        try:
            subprocess.run(
                ["docker", "kill", container_name],
                capture_output=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass

        try:
            result = subprocess.run(
                ["docker", "rm", "-f", container_name],
                capture_output=True,
                timeout=5,
                check=False,
            )
            if result.returncode == 0:
                return
        except (OSError, subprocess.TimeoutExpired):
            pass

        if attempt < 2:
            time.sleep(0.2)

    logger.error("Could not confirm removal of Docker sandbox container %s after 3 attempts", container_name)


def run_in_sandbox(
    workspace: str | Path,
    command: list[str],
    *,
    scratch_root: str | Path,
    image: str = DEFAULT_IMAGE,
    timeout_seconds: int = 600,
    network_enabled: bool = False,
) -> SandboxResult:
    """Run an argv command in Docker with no network, no capabilities and bounded resources.

    The command is passed as argv after the image; no host shell is involved.
    The workspace is the only writable host mount and must be disposable.
    """
    target = _validate_workspace(workspace, scratch_root)
    if not isinstance(command, list) or not command or any(not isinstance(part, str) or "\x00" in part for part in command):
        raise SandboxError("Command must be a non-empty list of text arguments")
    if not isinstance(image, str) or not image or image.startswith("-") or any(ch.isspace() for ch in image):
        raise SandboxError("Invalid sandbox image name")
    if not isinstance(timeout_seconds, int) or not 1 <= timeout_seconds <= 3600:
        raise SandboxError("Timeout must be between 1 and 3600 seconds")
    if not isinstance(network_enabled, bool):
        raise SandboxError("network_enabled must be a boolean")

    uid, gid = os.getuid(), os.getgid()
    if uid == 0:
        raise SandboxError("Refusing to run task containers from a root-owned host process")
    container_name = f"ai-worker-task-{uuid.uuid4().hex[:16]}"
    mount = f"type=bind,src={target},dst=/workspace"
    argv = [
        "docker", "run", "--rm", "--pull=never", "--name", container_name,
        f"--network={'bridge' if network_enabled else 'none'}", "--read-only", "--cap-drop=ALL",
        "--security-opt=no-new-privileges:true", "--pids-limit=128",
        "--memory=1g", "--cpus=1", f"--user={uid}:{gid}",
        "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=256m",
        "--env", "HOME=/tmp",
        "--mount", mount, "--workdir", "/workspace",
        image, *command,
    ]
    process = None
    completed_normally = False
    process_stopped = False
    try:
        process = subprocess.Popen(
            argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        stdout_tail = bytearray()
        stderr_tail = bytearray()
        output_bytes = 0
        output_lock = threading.Lock()
        output_limit_hit = threading.Event()

        def drain(stream, tail: bytearray) -> None:
            nonlocal output_bytes
            if stream is None:
                return
            try:
                while True:
                    chunk = stream.read(8192)
                    if not chunk:
                        break
                    with output_lock:
                        output_bytes += len(chunk)
                        tail.extend(chunk)
                        if len(tail) > MAX_OUTPUT_CHARS:
                            del tail[:-MAX_OUTPUT_CHARS]
                        if output_bytes > MAX_OUTPUT_BYTES:
                            output_limit_hit.set()
            except OSError:
                return

        readers = [
            threading.Thread(target=drain, args=(process.stdout, stdout_tail), daemon=True),
            threading.Thread(target=drain, args=(process.stderr, stderr_tail), daemon=True),
        ]
        for reader in readers:
            reader.start()

        deadline = time.monotonic() + timeout_seconds
        stop_reason = None
        while process.poll() is None:
            if output_limit_hit.is_set():
                stop_reason = "output"
                break
            if time.monotonic() >= deadline:
                stop_reason = "timeout"
                break
            time.sleep(0.05)

        if stop_reason is not None:
            _stop_host_process(process)
            process_stopped = True
        else:
            try:
                exit_code = process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                _stop_host_process(process)
                process_stopped = True
                raise SandboxError("Docker CLI did not exit after reporting completion")

        for reader in readers:
            reader.join(timeout=5)
        if any(reader.is_alive() for reader in readers):
            raise SandboxError("Sandbox output reader threads did not stop")

        if output_limit_hit.is_set() and stop_reason is None:
            stop_reason = "output"

        stdout = _text(bytes(stdout_tail))
        stderr = _text(bytes(stderr_tail))
        if stop_reason is not None:
            if stop_reason == "timeout":
                stderr = (stderr + f"\nSandbox timed out after {timeout_seconds}s.")[-MAX_OUTPUT_CHARS:]
                return SandboxResult(124, stdout, stderr, timed_out=True)
            stderr = (stderr + f"\nSandbox output exceeded {MAX_OUTPUT_BYTES} bytes; execution was stopped.")[-MAX_OUTPUT_CHARS:]
            return SandboxResult(125, stdout, stderr, timed_out=False)

        completed_normally = True
        return SandboxResult(exit_code=exit_code, stdout=stdout, stderr=stderr)

    except FileNotFoundError as exc:
        raise SandboxError("Docker CLI is not installed or is not available in PATH") from exc
    finally:
        if process is not None and not completed_normally:
            if not process_stopped:
                try:
                    _stop_host_process(process)
                except Exception:
                    # Container cleanup must continue if process stopping fails.
                    logger.exception("Failed to stop Docker CLI for container %s", container_name)
            _cleanup_container(container_name)
