"""Prepare isolated workspaces from public GitHub issue repositories."""

from __future__ import annotations

import os
import re
import shutil
import stat
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
    """Shallow-clone a public GitHub repo in a private disposable workspace."""
    match = re.fullmatch(r"([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)", repository or "")
    if not match:
        raise WorkspaceError("Only canonical owner/repository names are supported")

    owner, name = match.groups()
    if owner in {".", ".."} or name in {".", ".."}:
        raise WorkspaceError("Invalid GitHub owner or repository name")

    if not isinstance(timeout_seconds, int) or not 1 <= timeout_seconds <= 900:
        raise WorkspaceError("Clone timeout must be between 1 and 900 seconds")

    raw_root = Path(scratch_root).expanduser()
    raw_root.mkdir(parents=True, exist_ok=True)

    root_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        root_fd = os.open(raw_root, root_flags)
    except OSError as exc:
        raise WorkspaceError("Scratch root must be a real directory, not a symlink") from exc

    try:
        root_stat = os.fstat(root_fd)
        if not stat.S_ISDIR(root_stat.st_mode):
            raise WorkspaceError("Scratch root must be a real directory")
        if root_stat.st_uid != os.geteuid():
            raise WorkspaceError("Scratch root must be owned by the current user")

        root = raw_root.resolve()
        try:
            path_stat = os.stat(root, follow_symlinks=False)
        except OSError as exc:
            raise WorkspaceError("Could not verify scratch root") from exc

        if not os.path.samestat(root_stat, path_stat):
            raise WorkspaceError("Scratch root changed during validation")

        os.fchmod(root_fd, 0o700)
    finally:
        os.close(root_fd)

    raw_target = Path(workspace).expanduser()
    if raw_target.is_symlink():
        raise WorkspaceError("Workspace path may not be a symlink")

    target_parent = raw_target.parent.resolve()
    target = target_parent / raw_target.name

    if target_parent != root and root not in target_parent.parents:
        raise WorkspaceError("Workspace must be a child of the dedicated scratch root")
    if not raw_target.name or raw_target.name in {".", ".."}:
        raise WorkspaceError("Invalid workspace directory name")
    if "," in str(target):
        raise WorkspaceError("Workspace path cannot contain commas")

    target_parent.mkdir(parents=True, exist_ok=True)
    target_parent = target_parent.resolve()

    if target_parent != root and root not in target_parent.parents:
        raise WorkspaceError("Workspace parent escaped the dedicated scratch root")

    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        parent_fd = os.open(target_parent, directory_flags)
    except OSError as exc:
        raise WorkspaceError("Could not securely open workspace parent") from exc

    owned_identity = None
    try:
        parent_stat = os.fstat(parent_fd)
        if not os.path.samestat(parent_stat, os.stat(target_parent)):
            raise WorkspaceError("Workspace parent changed during validation")

        try:
            os.mkdir(target.name, mode=0o700, dir_fd=parent_fd)
        except FileExistsError as exc:
            raise WorkspaceError("Workspace path must not already exist") from exc

        try:
            owned_fd = os.open(target.name, directory_flags, dir_fd=parent_fd)
            try:
                owned_stat = os.fstat(owned_fd)
                if not os.path.samestat(
                    owned_stat,
                    os.stat(target.name, dir_fd=parent_fd, follow_symlinks=False),
                ):
                    raise WorkspaceError("Workspace changed during reservation")
                owned_identity = (owned_stat.st_dev, owned_stat.st_ino)
            finally:
                os.close(owned_fd)
        except OSError as exc:
            # Without a verified identity, do not risk deleting an unrelated path.
            raise WorkspaceError("Could not verify workspace ownership") from exc

        repo_url = "https://" + f"github.com/{owner}/{name}.git"
        argv = [
            "git",
            "-c", "core.hooksPath=/dev/null",
            "-c", "filter.lfs.smudge=cat",
            "-c", "filter.lfs.required=false",
            "clone", "--depth=1", "--single-branch", "--no-recurse-submodules",
            "--filter=blob:limit=1m", repo_url, str(target),
        ]

        def cleanup_partial_workspace() -> None:
            """Best-effort removal, anchored to the already-open parent directory."""
            if owned_identity is None:
                return
            try:
                current = os.stat(
                    target.name, dir_fd=parent_fd, follow_symlinks=False
                )
                if (current.st_dev, current.st_ino) != owned_identity:
                    return
                if not stat.S_ISDIR(current.st_mode):
                    return

                check_fd = os.open(target.name, directory_flags, dir_fd=parent_fd)
                try:
                    checked = os.fstat(check_fd)
                    if (checked.st_dev, checked.st_ino) != owned_identity:
                        return
                finally:
                    os.close(check_fd)

                shutil.rmtree(target.name, dir_fd=parent_fd)
            except OSError:
                # Preserve the original clone failure; cleanup is best-effort.
                pass

        try:
            with tempfile.TemporaryDirectory(
                prefix=".ai-worker-git-home-", dir=root
            ) as home:
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
                message = (
                    completed.stderr or completed.stdout or "git clone failed"
                )[-4000:]
                raise WorkspaceError(message)

            current = os.stat(
                target.name, dir_fd=parent_fd, follow_symlinks=False
            )
            if (current.st_dev, current.st_ino) != owned_identity:
                raise WorkspaceError("Workspace changed during Git clone")
            if not stat.S_ISDIR(current.st_mode):
                raise WorkspaceError("Git clone did not create a real directory")

            git_metadata = target / ".git"
            if not git_metadata.is_dir() or git_metadata.is_symlink():
                raise WorkspaceError(
                    "Git clone reported success but Git metadata was not created"
                )

            return WorkspaceResult(
                path=str(target),
                repository=f"{owner}/{name}",
                message="Public repository cloned into a disposable workspace.",
            )

        except subprocess.TimeoutExpired as exc:
            cleanup_partial_workspace()
            raise WorkspaceError(
                f"Git clone timed out after {timeout_seconds} seconds"
            ) from exc
        except FileNotFoundError as exc:
            cleanup_partial_workspace()
            raise WorkspaceError(
                "Git is not installed or is not available in PATH"
            ) from exc
        except Exception:
            cleanup_partial_workspace()
            raise

    finally:
        os.close(parent_fd)
