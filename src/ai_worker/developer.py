"""Validate and apply model-proposed unified diffs only inside disposable sandboxes."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from ai_worker.sandbox import SandboxError, run_in_sandbox


MAX_PATCH_BYTES = 100_000
MAX_PATCH_FILES = 25
BLOCKED_NAMES = {
    ".env", ".npmrc", ".netrc", ".pypirc", "id_rsa", "id_ed25519",
}


class PatchError(RuntimeError):
    pass


@dataclass(slots=True)
class PatchApplyResult:
    applied: bool
    message: str
    changed_files: list[str]
    stdout: str = ""
    stderr: str = ""


def _safe_patch_path(value: str) -> str:
    parts = value.split("/")
    path = PurePosixPath(value)
    basename = path.name.lower()
    if (
        not value
        or value.startswith("/")
        or "\\" in value
        or not parts
        or any(part in {"", ".", ".."} for part in parts)
        or not path.parts
        or ".git" in path.parts
    ):
        raise PatchError(f"Unsafe path in patch: {value!r}")
    if (
        basename in BLOCKED_NAMES
        or basename.startswith(("credentials", "secrets"))
        or basename.endswith((".pem", ".key", ".p12", ".pfx"))
        or basename.startswith(".env")
    ):
        raise PatchError(f"Patch may not modify a credential or environment path: {value!r}")
    return str(path)


def validate_patch_text(diff: str) -> list[str]:
    if not isinstance(diff, str) or not diff or len(diff.encode("utf-8")) > MAX_PATCH_BYTES:
        raise PatchError("Patch is empty or exceeds the 100 KiB limit")
    if "\x00" in diff or "GIT binary patch" in diff or "Binary files " in diff:
        raise PatchError("Binary or NUL-containing patches are not supported")

    paths: list[str] = []
    current_path: str | None = None
    in_hunk = False
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            parts = line[len("diff --git "):].split(" ")
            if len(parts) != 2 or not parts[0].startswith("a/") or not parts[1].startswith("b/"):
                raise PatchError("Patch contains an unsupported Git diff header")
            old_path = _safe_patch_path(parts[0][2:])
            new_path = _safe_patch_path(parts[1][2:])
            if old_path != new_path:
                raise PatchError("Renames and copies are not supported in the first patch runner")
            current_path = new_path
            in_hunk = False
            paths.append(new_path)
        elif line.startswith("@@"):
            in_hunk = True
        elif not in_hunk and (line.startswith("--- ") or line.startswith("+++ ")):
            if current_path is None:
                raise PatchError("Patch file headers appeared before a Git diff header")
            value = line[4:].split("\t", 1)[0]
            if value == "/dev/null":
                continue
            expected_prefix = "a/" if line.startswith("--- ") else "b/"
            if not value.startswith(expected_prefix):
                raise PatchError("Patch contains an absolute or unsupported file header")
            if _safe_patch_path(value[2:]) != current_path:
                raise PatchError("Patch file header does not match its Git diff header")
        elif line in {"new file mode 120000", "old mode 120000", "new mode 120000"}:
            raise PatchError("Symlink changes are not allowed")
        elif line in {"new file mode 160000", "old mode 160000", "new mode 160000"}:
            raise PatchError("Submodule changes are not allowed")
        elif re.fullmatch(r"index [0-9a-f]+\.\.[0-9a-f]+ 120000", line):
            raise PatchError("Symlink changes are not allowed")

    if not paths:
        raise PatchError("No Git file changes were found in the patch")
    if len(paths) > MAX_PATCH_FILES:
        raise PatchError(f"Patch touches more than {MAX_PATCH_FILES} files")
    if len(set(paths)) != len(paths):
        raise PatchError("Patch contains duplicate file sections")
    return paths


def _workspace_path(workspace: str | Path, scratch_root: str | Path) -> Path:
    root = Path(scratch_root).resolve(strict=True)
    target = Path(workspace).resolve(strict=True)
    if not root.is_dir() or not target.is_dir() or target == root:
        raise PatchError("Workspace must be a child directory of the scratch root")
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise PatchError("Workspace must be inside the dedicated scratch root") from exc
    return target


def apply_patch_in_sandbox(
    diff: str,
    workspace: str | Path,
    *,
    scratch_root: str | Path,
    image: str = "ai-worker-sandbox:py311",
    timeout_seconds: int = 120,
) -> PatchApplyResult:
    """Check, then apply a text patch in a disposable workspace using isolated Docker."""
    paths = validate_patch_text(diff)
    target = _workspace_path(workspace, scratch_root)
    patch_file = target / ".ai-worker-generated.patch"
    if patch_file.exists() or patch_file.is_symlink():
        raise PatchError("A generated patch file already exists in this workspace")
    patch_file.write_text(diff, encoding="utf-8")

    try:
        check = run_in_sandbox(
            target,
            ["git", "apply", "--check", "--whitespace=error", patch_file.name],
            scratch_root=scratch_root,
            image=image,
            timeout_seconds=timeout_seconds,
        )
        if check.exit_code != 0:
            return PatchApplyResult(
                False, "Patch failed git apply --check; workspace was not modified.",
                paths, check.stdout, check.stderr,
            )
        applied = run_in_sandbox(
            target,
            ["git", "apply", "--whitespace=error", patch_file.name],
            scratch_root=scratch_root,
            image=image,
            timeout_seconds=timeout_seconds,
        )
        if applied.exit_code != 0:
            return PatchApplyResult(
                False, "Patch validation passed but application failed.",
                paths, applied.stdout, applied.stderr,
            )
        patch_file.unlink(missing_ok=True)
        return PatchApplyResult(True, "Patch applied inside the disposable workspace.", paths, applied.stdout, applied.stderr)
    except SandboxError:
        raise
