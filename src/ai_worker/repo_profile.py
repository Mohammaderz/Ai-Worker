"""Read-only repository intelligence: detect languages, manifests and safe QA guidance.

This profiler never executes repository scripts, package managers or build hooks.
All repository content is treated as untrusted input.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

MAX_FILES = 5000
MAX_MANIFEST_BYTES = 64 * 1024
SKIP_DIRS = {
    ".git", ".venv", "venv", "node_modules", "dist", "build", "target",
    "__pycache__", ".tox", ".mypy_cache", ".pytest_cache", ".next",
}
LANGUAGES = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript",
    ".mjs": "JavaScript", ".cjs": "JavaScript", ".ts": "TypeScript",
    ".tsx": "TypeScript", ".go": "Go", ".rs": "Rust", ".java": "Java",
    ".kt": "Kotlin", ".swift": "Swift", ".rb": "Ruby", ".php": "PHP",
    ".cs": "C#", ".cpp": "C++", ".cc": "C++", ".c": "C",
    ".h": "C/C++", ".hpp": "C++", ".ex": "Elixir", ".exs": "Elixir",
}
LOCKFILES = {
    "pnpm-lock.yaml": "pnpm",
    "yarn.lock": "yarn",
    "package-lock.json": "npm",
    "bun.lockb": "bun",
    "bun.lock": "bun",
    "poetry.lock": "poetry",
    "uv.lock": "uv",
    "Pipfile.lock": "pipenv",
    "Cargo.lock": "cargo",
    "go.sum": "go modules",
}
TEST_DIR_NAMES = {"test", "tests", "__tests__", "spec", "specs"}


def _inside_test_tree(path: Path) -> bool:
    return any(part.lower() in TEST_DIR_NAMES for part in path.parts[:-1])


def profile_repository(workspace: str | Path) -> dict:
    """Inspect a repository with bounded, symlink-safe reads; never run its code."""
    root = Path(workspace).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Repository workspace must be a directory")

    files: list[Path] = []
    truncated = False
    for path in root.rglob("*"):
        try:
            if path.is_symlink():
                continue
            if path.is_dir():
                continue
            relative = path.relative_to(root)
            if any(part in SKIP_DIRS for part in relative.parts[:-1]):
                continue
            if not path.is_file():
                continue
            files.append(relative)
            if len(files) >= MAX_FILES:
                truncated = True
                break
        except OSError:
            continue

    language_counts: Counter[str] = Counter()
    lockfiles: list[str] = []
    test_files: list[str] = []
    manifests: list[str] = []
    for relative in files:
        language = LANGUAGES.get(relative.suffix.lower())
        if language:
            language_counts[language] += 1
        if relative.name in LOCKFILES:
            lockfiles.append(relative.as_posix())
        if relative.name in {"pyproject.toml", "pytest.ini", "tox.ini", "setup.cfg",
                             "package.json", "go.mod", "Cargo.toml", "pom.xml",
                             "build.gradle", "build.gradle.kts"}:
            manifests.append(relative.as_posix())
        if (
            relative.name.startswith("test_")
            or relative.name.endswith(("_test.py", ".test.js", ".test.ts",
                                       ".spec.js", ".spec.ts", ".test.tsx", ".spec.tsx"))
            or _inside_test_tree(relative)
        ):
            test_files.append(relative.as_posix())

    package_scripts: dict[str, str] = {}
    package_manager = next(
        (LOCKFILES[Path(item).name] for item in sorted(lockfiles)
         if Path(item).name in LOCKFILES and LOCKFILES[Path(item).name] in {"pnpm", "yarn", "npm", "bun"}),
        None,
    )
    package_path = next((p for p in files if p.as_posix() == "package.json"), None)
    package_json_status = "not_present"
    if package_path:
        try:
            manifest_path = root / package_path
            if manifest_path.stat().st_size > MAX_MANIFEST_BYTES:
                package_json_status = "too_large_skipped"
            else:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    scripts = data.get("scripts", {})
                    if isinstance(scripts, dict):
                        package_scripts = {
                            str(key): str(value)[:300]
                            for key, value in scripts.items()
                            if isinstance(key, str) and isinstance(value, str)
                        }
                    package_json_status = "parsed"
                else:
                    package_json_status = "invalid_shape"
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            package_json_status = "invalid_or_unreadable"

    languages = [name for name, _ in language_counts.most_common()]
    qa: list[dict[str, str]] = []
    if "Python" in language_counts:
        qa.append({
            "kind": "python",
            "command": "python -m compileall -q .",
            "execution": "sandbox_only",
            "reason": "Python source files detected; syntax compilation does not require dependency installation.",
        })
        if test_files:
            qa.append({
                "kind": "python_tests",
                "command": "python -m pytest -q",
                "execution": "sandbox_only_if_dependencies_available",
                "reason": "Test-like files detected; missing dependencies must be reported, not fetched automatically.",
            })
    if "Go" in language_counts or any(Path(p).name == "go.mod" for p in manifests):
        qa.append({
            "kind": "go_tests",
            "command": "go test ./...",
            "execution": "manual_review_required",
            "reason": "Go project detected; module downloads and build steps are not run by the profiler.",
        })
    if "Rust" in language_counts or any(Path(p).name == "Cargo.toml" for p in manifests):
        qa.append({
            "kind": "rust_tests",
            "command": "cargo test --locked",
            "execution": "manual_review_required",
            "reason": "Rust project detected; Cargo build scripts and dependencies are not executed by the profiler.",
        })
    if package_scripts:
        for key in ("test", "lint", "typecheck", "check"):
            if key in package_scripts:
                qa.append({
                    "kind": f"node_{key}",
                    "command": f"{package_manager or 'npm'} run {key}",
                    "execution": "manual_review_required",
                    "reason": "Command was read from untrusted package.json and is never executed automatically.",
                })

    return {
        "schema_version": 1,
        "repository_root": str(root),
        "files_scanned": len(files),
        "scan_truncated": truncated,
        "languages": [{"name": name, "files": count} for name, count in language_counts.most_common()],
        "manifests": sorted(manifests),
        "lockfiles": sorted(lockfiles),
        "package_manager": package_manager,
        "package_json_status": package_json_status,
        "package_scripts": package_scripts,
        "test_file_count": len(test_files),
        "test_file_samples": sorted(test_files)[:30],
        "qa_recommendations": qa,
        "safety": {
            "repository_code_executed": False,
            "package_scripts_executed": False,
            "dependency_installation_attempted": False,
            "network_access_required": False,
        },
    }
