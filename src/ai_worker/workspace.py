"""Prepare isolated workspaces from public GitHub issue repositories."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


class WorkspaceError(RuntimeError):
    pass


@dataclass(slots=True)
class WorkspaceResult:
    path: str
    repository: str
    message: str


def clone_public_github_repo(
    repository: str,
    workspace: str | Path,
    *,
    scratch_root: str | Path,
    timeout_seconds: int = 300,
) -> WorkspaceResult:
    """Shallow-clone a public GitHub repo without using host Git credentials or hooks."""
    match = re.fullmatch(r"([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)", repository or "")
    if not match:
        raise WorkspaceError("Only canonical owner/repository names are supported")
    owner, name = match.groups()

    root = Path(scratch_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    target = Path(workspace).absolute()
    target_parent = target.parent.resolve()
    if target_parent != root and root not in target_parent.parents:
        raise WorkspaceError("Workspace must be a child of the dedicated scratch root")
    if "," in str(target):
        raise WorkspaceError("Workspace path cannot contain commas")
    if target.exists() or target.is_symlink():
        raise WorkspaceError("Workspace path must not already exist")
    target.parent.mkdir(parents=True, exist_ok=True)

    repo_url = f"https://github.com/{owner}/{name}.git"
    argv = [
        "git",
        "-c", "core.hooksPath=/dev/null",
        "-c", "filter.lfs.smudge=cat",
        "-c", "filter.lfs.required=false",
        "clone", "--depth=1", "--single-branch", "--no-recurse-submodules",
        "--filter=blob:limit=1m", repo_url, str(target),
    ]
    try:
        with tempfile.TemporaryDirectory(prefix=".ai-worker-git-home-", dir=root) as home:
            env = {
                "PATH": os.environ.get("PATH", ""),
                "HOME": home,
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_LFS_SKIP_SMUDGE": "1",
            }
            completed = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
                env=env,
            )
        if completed.returncode != 0:
            if target.exists() and not target.is_symlink():
                shutil.rmtree(target)
            message = (completed.stderr or completed.stdout or "git clone failed")[-4000:]
            raise WorkspaceError(message)
        if not target.is_dir() or target.is_symlink():
            raise WorkspaceError("Git clone reported success but the workspace was not created")
        return WorkspaceResult(
            path=str(target),
            repository=f"{owner}/{name}",
            message="Public repository cloned into a disposable workspace.",
        )
    except subprocess.TimeoutExpired as exc:
        if target.exists() and not target.is_symlink():
            shutil.rmtree(target)
        raise WorkspaceError(f"Git clone timed out after {timeout_seconds} seconds") from exc
    except FileNotFoundError as exc:
        raise WorkspaceError("Git is not installed or is not available in PATH") from exc
