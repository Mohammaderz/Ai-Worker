"""Safe, read-only inspection of Node.js project manifests and lockfiles."""
from __future__ import annotations

import json
import re
import stat
from urllib.parse import urlsplit
from dataclasses import asdict, dataclass
from pathlib import Path


MAX_PACKAGE_JSON_BYTES = 256 * 1024
MAX_LOCKFILE_BYTES = 20 * 1024 * 1024

LOCKFILES = {
    "package-lock.json": "npm",
    "npm-shrinkwrap.json": "npm",
    "pnpm-lock.yaml": "pnpm",
    "yarn.lock": "yarn",
    "bun.lock": "bun",
    "bun.lockb": "bun",
}

SUPPORTED_INSTALLERS = {"npm"}
DEPENDENCY_FIELDS = (
    "dependencies",
    "devDependencies",
    "optionalDependencies",
    "peerDependencies",
)


class NodeProjectError(ValueError):
    """Raised when a Node project manifest cannot be inspected safely."""


@dataclass(slots=True)
class NodeProjectInfo:
    status: str
    package_manager: str | None
    lockfile: str | None
    package_name: str | None
    has_dependencies: bool
    has_test_script: bool
    has_build_script: bool
    node_engine: str | None
    reason: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _read_regular_file(
    root: Path,
    relative_name: str,
    *,
    max_bytes: int,
) -> bytes | None:
    path = root / relative_name

    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise NodeProjectError(
            f"Could not inspect {relative_name}: {exc}"
        ) from exc

    if stat.S_ISLNK(metadata.st_mode):
        raise NodeProjectError(
            f"Refusing symlink in Node project metadata: {relative_name}"
        )

    if not stat.S_ISREG(metadata.st_mode):
        raise NodeProjectError(
            f"Node project metadata must be a regular file: {relative_name}"
        )

    if metadata.st_size > max_bytes:
        raise NodeProjectError(
            f"Node project metadata exceeds the size limit: {relative_name}"
        )

    try:
        data = path.read_bytes()
    except OSError as exc:
        raise NodeProjectError(
            f"Could not read {relative_name}: {exc}"
        ) from exc

    if len(data) > max_bytes:
        raise NodeProjectError(
            f"Node project metadata exceeds the size limit: {relative_name}"
        )

    return data


def _declared_package_manager(value: object) -> str | None:
    if value is None:
        return None

    if not isinstance(value, str) or len(value) > 160:
        raise NodeProjectError("packageManager must be a short manager@version string")

    manager, separator, version = value.partition("@")

    if (
        not separator
        or manager not in {"npm", "pnpm", "yarn", "bun"}
        or not version
        or any(char.isspace() for char in version)
    ):
        raise NodeProjectError("packageManager declaration is invalid")

    return manager



def _validate_npm_lockfile(lock_data: dict) -> None:
    """Accept only integrity-pinned packages from the official HTTPS npm registry."""
    version = lock_data.get("lockfileVersion")
    if isinstance(version, bool) or version not in {2, 3}:
        raise NodeProjectError("npm lockfile has unsupported lockfileVersion; supported versions are 2 or 3")

    packages = lock_data.get("packages")
    if not isinstance(packages, dict) or len(packages) > 50_000:
        raise NodeProjectError("npm lockfile packages section is invalid")

    seen = 0

    def inspect_record(record: object, location: str, depth: int = 0) -> None:
        nonlocal seen
        seen += 1
        if seen > 50_000 or depth > 100:
            raise NodeProjectError("npm lockfile dependency tree exceeds safety limits")
        if not isinstance(record, dict):
            raise NodeProjectError(f"Invalid npm lockfile entry: {location}")

        resolved = record.get("resolved")
        if resolved is not None:
            if not isinstance(resolved, str) or len(resolved) > 4096:
                raise NodeProjectError(f"Invalid resolved URL in npm lockfile: {location}")
            try:
                url = urlsplit(resolved)
                port = url.port
            except ValueError as exc:
                raise NodeProjectError("Invalid npm lockfile URL") from exc

            if (
                url.scheme != "https"
                or url.hostname != "registry.npmjs.org"
                or port not in (None, 443)
                or url.username is not None
                or url.password is not None
                or not url.path.startswith("/")
                or url.query
                or url.fragment
            ):
                raise NodeProjectError(
                    "Only HTTPS packages from registry.npmjs.org are supported"
                )

            integrity = record.get("integrity")
            if (
                not isinstance(integrity, str)
                or not re.fullmatch(
                    r"(?:sha1|sha256|sha384|sha512)-[A-Za-z0-9+/]+={0,2}",
                    integrity,
                )
            ):
                raise NodeProjectError(
                    f"Registry package lacks valid integrity metadata: {location}"
                )

        dependencies = record.get("dependencies", {})
        if not isinstance(dependencies, dict):
            raise NodeProjectError(
                f"Invalid nested dependencies in npm lockfile: {location}"
            )
        for name, child in dependencies.items():
            if not isinstance(name, str):
                raise NodeProjectError("Invalid dependency name in npm lockfile")
            inspect_record(child, f"{location}/{name}", depth + 1)

    for name, record in packages.items():
        if not isinstance(name, str):
            raise NodeProjectError("Invalid package path in npm lockfile")
        inspect_record(record, name)

    dependencies = lock_data.get("dependencies", {})
    if not isinstance(dependencies, dict):
        raise NodeProjectError("Invalid npm lockfile dependencies section")
    for name, record in dependencies.items():
        if not isinstance(name, str):
            raise NodeProjectError("Invalid dependency name in npm lockfile")
        inspect_record(record, name)


def _unsupported(
    *,
    manager: str | None,
    lockfile: str | None,
    package_name: str | None,
    has_dependencies: bool,
    has_test_script: bool,
    has_build_script: bool,
    node_engine: str | None,
    reason: str,
) -> NodeProjectInfo:
    return NodeProjectInfo(
        status="unsupported",
        package_manager=manager,
        lockfile=lockfile,
        package_name=package_name,
        has_dependencies=has_dependencies,
        has_test_script=has_test_script,
        has_build_script=has_build_script,
        node_engine=node_engine,
        reason=reason,
    )


def inspect_node_project(workspace: str | Path) -> NodeProjectInfo:
    """Inspect root package.json and lockfiles without executing project code."""
    candidate = Path(workspace)

    try:
        if candidate.is_symlink():
            raise NodeProjectError("Node workspace cannot be a symbolic link")

        root = candidate.resolve(strict=True)
    except OSError as exc:
        raise NodeProjectError(
            f"Node workspace could not be resolved: {exc}"
        ) from exc

    if not root.is_dir():
        raise NodeProjectError("Node workspace must be a directory")

    npmrc = _read_regular_file(root, ".npmrc", max_bytes=64 * 1024)
    if npmrc is not None:
        raise NodeProjectError(
            "Project .npmrc is not allowed for automated dependency installation"
        )

    raw_manifest = _read_regular_file(
        root,
        "package.json",
        max_bytes=MAX_PACKAGE_JSON_BYTES,
    )

    if raw_manifest is None:
        return NodeProjectInfo(
            status="not_detected",
            package_manager=None,
            lockfile=None,
            package_name=None,
            has_dependencies=False,
            has_test_script=False,
            has_build_script=False,
            node_engine=None,
            reason="Root package.json was not found.",
        )

    try:
        manifest = json.loads(raw_manifest.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NodeProjectError("package.json is not valid UTF-8 JSON") from exc

    if not isinstance(manifest, dict):
        raise NodeProjectError("package.json must contain a JSON object")

    package_name = manifest.get("name")
    if package_name is not None and (
        not isinstance(package_name, str) or len(package_name) > 300
    ):
        raise NodeProjectError("package.json name is invalid")

    scripts = manifest.get("scripts", {})
    if not isinstance(scripts, dict):
        raise NodeProjectError("package.json scripts must be an object")

    for script_name in ("test", "build"):
        if script_name in scripts and (
            not isinstance(scripts[script_name], str)
            or len(scripts[script_name]) > 2000
        ):
            raise NodeProjectError(
                f"package.json scripts.{script_name} is invalid"
            )

    has_test_script = bool(
        isinstance(scripts.get("test"), str)
        and scripts["test"].strip()
    )
    has_build_script = bool(
        isinstance(scripts.get("build"), str)
        and scripts["build"].strip()
    )

    has_dependencies = False
    for field in DEPENDENCY_FIELDS:
        value = manifest.get(field, {})
        if not isinstance(value, dict):
            raise NodeProjectError(
                f"package.json {field} must be an object"
            )
        if len(value) > 5000:
            raise NodeProjectError(
                f"package.json {field} contains too many entries"
            )
        has_dependencies = has_dependencies or bool(value)

    engines = manifest.get("engines", {})
    if not isinstance(engines, dict):
        raise NodeProjectError("package.json engines must be an object")

    node_engine = engines.get("node")
    if node_engine is not None and (
        not isinstance(node_engine, str) or len(node_engine) > 200
    ):
        raise NodeProjectError("package.json engines.node is invalid")

    declared_manager = _declared_package_manager(
        manifest.get("packageManager")
    )

    detected_lockfiles = []
    for filename, manager in LOCKFILES.items():
        contents = _read_regular_file(
            root,
            filename,
            max_bytes=MAX_LOCKFILE_BYTES,
        )
        if contents is not None:
            detected_lockfiles.append((filename, manager, contents))

    if len(detected_lockfiles) > 1:
        names = ", ".join(item[0] for item in detected_lockfiles)
        return _unsupported(
            manager=declared_manager,
            lockfile=None,
            package_name=package_name,
            has_dependencies=has_dependencies,
            has_test_script=has_test_script,
            has_build_script=has_build_script,
            node_engine=node_engine,
            reason=f"Multiple package-manager lockfiles are present: {names}",
        )

    lockfile = None
    lock_manager = None
    lock_contents = None

    if detected_lockfiles:
        lockfile, lock_manager, lock_contents = detected_lockfiles[0]

    if (
        declared_manager is not None
        and lock_manager is not None
        and declared_manager != lock_manager
    ):
        return _unsupported(
            manager=declared_manager,
            lockfile=lockfile,
            package_name=package_name,
            has_dependencies=has_dependencies,
            has_test_script=has_test_script,
            has_build_script=has_build_script,
            node_engine=node_engine,
            reason=(
                "packageManager declaration conflicts with the detected lockfile."
            ),
        )

    manager = lock_manager or declared_manager or "npm"
    if "workspaces" in manifest:
        return _unsupported(
            manager=manager,
            lockfile=lockfile,
            package_name=package_name,
            has_dependencies=has_dependencies,
            has_test_script=has_test_script,
            has_build_script=has_build_script,
            node_engine=node_engine,
            reason=(
                "npm workspaces are not supported by the current root-only "
                "dependency inspection. Automated Node checks were skipped."
            ),
        )

    if manager not in SUPPORTED_INSTALLERS:
        return _unsupported(
            manager=manager,
            lockfile=lockfile,
            package_name=package_name,
            has_dependencies=has_dependencies,
            has_test_script=has_test_script,
            has_build_script=has_build_script,
            node_engine=node_engine,
            reason=(
                f"{manager} was detected but its dependency installer "
                "is not enabled in this QA version."
            ),
        )

    if has_dependencies and lockfile is None:
        return _unsupported(
            manager=manager,
            lockfile=None,
            package_name=package_name,
            has_dependencies=has_dependencies,
            has_test_script=has_test_script,
            has_build_script=has_build_script,
            node_engine=node_engine,
            reason=(
                "External dependencies are declared but no deterministic "
                "npm lockfile is present."
            ),
        )

    if lockfile in {"package-lock.json", "npm-shrinkwrap.json"}:
        try:
            lock_data = json.loads(lock_contents.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise NodeProjectError(
                f"{lockfile} is not valid UTF-8 JSON"
            ) from exc

        if not isinstance(lock_data, dict):
            raise NodeProjectError(
                f"{lockfile} must contain a JSON object"
            )
        _validate_npm_lockfile(lock_data)

        version = lock_data.get("lockfileVersion")
        if (
            isinstance(version, bool)
            or not isinstance(version, int)
            or version not in {1, 2, 3}
        ):
            raise NodeProjectError(
                f"{lockfile} has an unsupported lockfileVersion"
            )

    reason = None
    if not has_dependencies:
        reason = "No external dependencies are declared."

    return NodeProjectInfo(
        status="ready",
        package_manager=manager,
        lockfile=lockfile,
        package_name=package_name,
        has_dependencies=has_dependencies,
        has_test_script=has_test_script,
        has_build_script=has_build_script,
        node_engine=node_engine,
        reason=reason,
    )
