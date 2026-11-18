import json

from ai_worker.repo_profile import profile_repository


def test_profile_detects_languages_manifests_tests_and_safe_commands(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('ok')", encoding="utf-8")
    (tmp_path / "tests" / "test_main.py").write_text("def test_ok(): pass", encoding="utf-8")
    (tmp_path / "package.json").write_text(json.dumps({
        "scripts": {"test": "echo DO_NOT_RUN", "build": "echo build"}
    }), encoding="utf-8")
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'", encoding="utf-8")

    result = profile_repository(tmp_path)

    assert result["package_manager"] == "pnpm"
    assert result["test_file_count"] == 1
    assert {item["name"] for item in result["languages"]} == {"Python"}
    assert any(item["command"] == "python -m pytest -q" for item in result["qa_recommendations"])
    node_test = next(item for item in result["qa_recommendations"] if item["kind"] == "node_test")
    assert node_test["command"] == "pnpm run test"
    assert node_test["execution"] == "manual_review_required"
    assert result["safety"]["package_scripts_executed"] is False


def test_profile_skips_symlinks_and_dependency_directories(tmp_path):
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "hidden.js").write_text("bad", encoding="utf-8")
    (tmp_path / "visible.ts").write_text("export const ok = true", encoding="utf-8")
    outside = tmp_path.parent / "outside-secret.py"
    outside.write_text("secret", encoding="utf-8")
    try:
        (tmp_path / "linked.py").symlink_to(outside)
    except OSError:
        pass

    result = profile_repository(tmp_path)

    assert result["files_scanned"] == 1
    assert result["languages"] == [{"name": "TypeScript", "files": 1}]


def test_profile_handles_invalid_or_oversized_package_json(tmp_path):
    (tmp_path / "package.json").write_text("{invalid", encoding="utf-8")
    result = profile_repository(tmp_path)
    assert result["package_json_status"] == "invalid_or_unreadable"
    assert result["package_scripts"] == {}
    assert result["safety"]["repository_code_executed"] is False
