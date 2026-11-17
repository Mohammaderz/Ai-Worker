import json

import pytest

from ai_worker.node_qa import NodeProjectError, inspect_node_project


def write_manifest(root, **values):
    manifest = {
        "name": "demo",
        "scripts": {
            "test": "node test.js",
            "build": "node build.js",
        },
        "dependencies": {"left-pad": "1.3.0"},
    }
    manifest.update(values)
    (root / "package.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )


def write_npm_lock(root):
    (root / "package-lock.json").write_text(
        json.dumps({
            "name": "demo",
            "lockfileVersion": 3,
            "packages": {},
        }),
        encoding="utf-8",
    )


def test_detects_locked_npm_project_and_scripts(tmp_path):
    write_manifest(
        tmp_path,
        packageManager="npm@10.8.2",
        engines={"node": ">=22"},
    )
    write_npm_lock(tmp_path)

    result = inspect_node_project(tmp_path)

    assert result.status == "ready"
    assert result.package_manager == "npm"
    assert result.lockfile == "package-lock.json"
    assert result.has_dependencies is True
    assert result.has_test_script is True
    assert result.has_build_script is True
    assert result.node_engine == ">=22"


def test_reports_missing_package_manifest(tmp_path):
    result = inspect_node_project(tmp_path)

    assert result.status == "not_detected"
    assert result.package_manager is None


def test_rejects_dependency_install_without_lockfile(tmp_path):
    write_manifest(tmp_path)

    result = inspect_node_project(tmp_path)

    assert result.status == "unsupported"
    assert result.package_manager == "npm"
    assert result.lockfile is None
    assert "no deterministic npm lockfile" in result.reason


def test_allows_dependency_free_npm_project_without_lockfile(tmp_path):
    write_manifest(
        tmp_path,
        dependencies={},
        devDependencies={},
        optionalDependencies={},
        peerDependencies={},
    )

    result = inspect_node_project(tmp_path)

    assert result.status == "ready"
    assert result.package_manager == "npm"
    assert result.has_dependencies is False
    assert result.reason == "No external dependencies are declared."


def test_detects_pnpm_but_does_not_claim_installer_support(tmp_path):
    write_manifest(
        tmp_path,
        packageManager="pnpm@9.0.0",
    )
    (tmp_path / "pnpm-lock.yaml").write_text(
        "lockfileVersion: '9.0'\n",
        encoding="utf-8",
    )

    result = inspect_node_project(tmp_path)

    assert result.status == "unsupported"
    assert result.package_manager == "pnpm"
    assert result.lockfile == "pnpm-lock.yaml"


def test_rejects_conflicting_package_manager_and_lockfile(tmp_path):
    write_manifest(
        tmp_path,
        packageManager="pnpm@9.0.0",
    )
    write_npm_lock(tmp_path)

    result = inspect_node_project(tmp_path)

    assert result.status == "unsupported"
    assert "conflicts" in result.reason


def test_rejects_multiple_lockfiles(tmp_path):
    write_manifest(tmp_path)
    write_npm_lock(tmp_path)
    (tmp_path / "yarn.lock").write_text(
        "# yarn lock\n",
        encoding="utf-8",
    )

    result = inspect_node_project(tmp_path)

    assert result.status == "unsupported"
    assert "Multiple package-manager lockfiles" in result.reason


def test_rejects_invalid_npm_lockfile_version(tmp_path):
    write_manifest(tmp_path)
    (tmp_path / "package-lock.json").write_text(
        json.dumps({"lockfileVersion": 99}),
        encoding="utf-8",
    )

    with pytest.raises(NodeProjectError, match="unsupported lockfileVersion"):
        inspect_node_project(tmp_path)


def test_rejects_symlink_package_manifest(tmp_path):
    target = tmp_path / "manifest.json"
    target.write_text('{"name":"demo"}', encoding="utf-8")
    (tmp_path / "package.json").symlink_to(target)

    with pytest.raises(NodeProjectError, match="symlink"):
        inspect_node_project(tmp_path)


def test_rejects_invalid_package_json(tmp_path):
    (tmp_path / "package.json").write_text(
        "{invalid",
        encoding="utf-8",
    )

    with pytest.raises(NodeProjectError, match="valid UTF-8 JSON"):
        inspect_node_project(tmp_path)


def test_rejects_malformed_scripts_field(tmp_path):
    write_manifest(tmp_path, scripts=[])

    with pytest.raises(NodeProjectError, match="scripts must be an object"):
        inspect_node_project(tmp_path)



def test_rejects_project_npmrc(tmp_path):
    write_manifest(tmp_path)
    write_npm_lock(tmp_path)
    (tmp_path / ".npmrc").write_text(
        "registry=https://evil.example\n",
        encoding="utf-8",
    )
    with pytest.raises(NodeProjectError, match="Project .npmrc"):
        inspect_node_project(tmp_path)


def test_rejects_non_registry_lockfile_url(tmp_path):
    write_manifest(tmp_path)
    (tmp_path / "package-lock.json").write_text(
        json.dumps({
            "lockfileVersion": 3,
            "packages": {
                "node_modules/evil": {
                    "resolved": "https://evil.example/package.tgz",
                    "integrity": "sha512-YWJjZA==",
                }
            },
        }),
        encoding="utf-8",
    )
    with pytest.raises(NodeProjectError, match="registry.npmjs.org"):
        inspect_node_project(tmp_path)


def test_rejects_registry_package_without_integrity(tmp_path):
    write_manifest(tmp_path)
    (tmp_path / "package-lock.json").write_text(
        json.dumps({
            "lockfileVersion": 3,
            "packages": {
                "node_modules/example": {
                    "resolved": "https://registry.npmjs.org/example/-/example-1.0.0.tgz",
                }
            },
        }),
        encoding="utf-8",
    )
    with pytest.raises(NodeProjectError, match="integrity"):
        inspect_node_project(tmp_path)


def test_accepts_integrity_pinned_official_registry_package(tmp_path):
    write_manifest(tmp_path)
    (tmp_path / "package-lock.json").write_text(
        json.dumps({
            "lockfileVersion": 3,
            "packages": {
                "node_modules/example": {
                    "version": "1.0.0",
                    "resolved": "https://registry.npmjs.org/example/-/example-1.0.0.tgz",
                    "integrity": "sha512-YWJjZA==",
                }
            },
        }),
        encoding="utf-8",
    )
    result = inspect_node_project(tmp_path)
    assert result.status == "ready"
    assert result.package_manager == "npm"


def test_rejects_workspaces_until_all_packages_are_inspected(tmp_path):
    write_manifest(
        tmp_path,
        dependencies={},
        devDependencies={},
        optionalDependencies={},
        peerDependencies={},
        workspaces=["packages/*"],
    )

    result = inspect_node_project(tmp_path)

    assert result.status == "unsupported"
    assert result.has_dependencies is False
    assert "workspaces are not supported" in result.reason
