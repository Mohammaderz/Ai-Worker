"""Disposable, network-isolated Docker runner for untrusted task workspaces.

The caller must create a disposable workspace under the configured scratch root.
No host credentials or environment variables are forwarded into the container.
"""
from __future__ import annotations

import os
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path


DEFAULT_IMAGE = "ai-worker-sandbox:py311"
DEFAULT_NODE_IMAGE = "ai-worker-sandbox:node22"
MAX_OUTPUT_CHARS = 20_000


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


def run_in_sandbox(
    workspace: str | Path,
    command: list[str],
    *,
    scratch_root: str | Path,
    image: str = DEFAULT_IMAGE,
    timeout_seconds: int = 600,
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

    uid, gid = os.getuid(), os.getgid()
    if uid == 0:
        raise SandboxError("Refusing to run task containers from a root-owned host process")
    container_name = f"ai-worker-task-{uuid.uuid4().hex[:16]}"
    mount = f"type=bind,src={target},dst=/workspace"
    argv = [
        "docker", "run", "--rm", "--pull=never", "--name", container_name,
        "--network=none", "--read-only", "--cap-drop=ALL",
        "--security-opt=no-new-privileges:true", "--pids-limit=128",
        "--memory=1g", "--cpus=1", f"--user={uid}:{gid}",
        "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=256m",
        "--env", "HOME=/tmp",
        "--mount", mount, "--workdir", "/workspace",
        image, *command,
    ]
    try:
        completed = subprocess.run(
            argv, capture_output=True, text=True, timeout=timeout_seconds, check=False
        )
        return SandboxResult(
            exit_code=completed.returncode,
            stdout=_text(completed.stdout)[-MAX_OUTPUT_CHARS:],
            stderr=_text(completed.stderr)[-MAX_OUTPUT_CHARS:],
        )
    except subprocess.TimeoutExpired as exc:
        # A killed Docker client can leave the container running; explicitly stop it.
        for cleanup_argv in (
            ["docker", "kill", container_name],
            ["docker", "rm", "-f", container_name],
        ):
            try:
                subprocess.run(cleanup_argv, capture_output=True, timeout=10, check=False)
            except (OSError, subprocess.TimeoutExpired):
                pass
        return SandboxResult(
            exit_code=124,
            stdout=_text(exc.stdout)[-MAX_OUTPUT_CHARS:],
            stderr=(_text(exc.stderr) + f"\nSandbox timed out after {timeout_seconds}s.")[-MAX_OUTPUT_CHARS:],
            timed_out=True,
        )
    except FileNotFoundError as exc:
        raise SandboxError("Docker CLI is not installed or is not available in PATH") from exc
