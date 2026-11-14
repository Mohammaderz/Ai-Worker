"""Validate and apply model-proposed unified diffs only inside disposable sandboxes."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from ai_worker.sandbox import SandboxError, run_in_sandbox


MAX_PATCH_BYTES = 100_000
MAX_PATCH_FILES = 25
BLOCKED_NAMES = {
    ".env", ".npmrc", ".netrc", ".pypirc", "id_rsa", "id_ed25519",
    "credentials", "credentials.json", "secrets", "secrets.json",
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
    path = PurePosixPath(value)
    if (
        not value
        or value.startswith("/")
        or "\\" in value
        or any(part in {"", ".", ".."} for part in path.parts)
        or path.parts[0] == ".git"
    ):
        raise PatchError(f"Unsafe path in patch: {value!r}")
    basename = path.name.lower()
    if basename in BLOCKED_NAMES or basename.endswith((".pem", ".key", ".p12", ".pfx")):
        raise PatchError(f"Patch may not modify a credential-like path: {value!r}")
    if basename.startswith(".env"):
        raise PatchError("Patch may not create or modify environment files")
    return str(path)


def validate_patch_text(diff: str) -> list[str]:
    if not isinstance(diff, str) or not diff or len(diff.encode("utf-8")) > MAX_PATCH_BYTES:
        raise PatchError("Patch is empty or exceeds the 100 KiB limit")
    if "\x00" in diff or "GIT binary patch" in diff or "Binary files " in diff:
        raise PatchError("Binary or NUL-containing patches are not supported")

    paths: list[str] = []
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            parts = line[len("diff --git "):].split(" ")
            if len(parts) != 2 or not parts[0].startswith("a/") or not parts[1].startswith("b/"):
                raise PatchError("Patch contains an unsupported Git diff header")
            old_path = _safe_patch_path(parts[0][2:])
            new_path = _safe_patch_path(parts[1][2:])
            if old_path != new_path:
                raise PatchError("Renames and copies are not supported in the first patch runner")
            paths.append(new_path)
        elif line.startswith("new file mode 120000") or line.startswith("old mode 120000") or line.startswith("new mode 120000"):
            raise PatchError("Symlink changes are not allowed")
        elif line.startswith("new file mode 160000") or line.startswith("old mode 160000") or line.startswith("new mode 160000"):
            raise PatchError("Submodule changes are not allowed")

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
