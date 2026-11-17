import json
from dataclasses import replace

import pytest

from ai_worker.developer import PatchError, collect_repo_context, draft_patch, repair_patch
from ai_worker.sources.github_issue import ResearchBrief


ISSUE = ResearchBrief(
    url="https://github.com/acme/widget/issues/42",
    title="Fix API retry handling",
    repository="acme/widget",
    number=42,
    state="open",
    body="Add tests for retry backoff.",
    labels=["bug"],
    updated_at="2026-11-14T10:00:00Z",
)

DIFF = """diff --git a/client.py b/client.py
index 1111111..2222222 100644
--- a/client.py
+++ b/client.py
@@ -1 +1 @@
-before
+after
"""


def _structured_scope_plan(file_path):
    description = "Update the client implementation"
    return {
        "summary": "Update the client implementation",
        "estimated_effort_hours": 1,
        "risk_level": "low",
        "prerequisites": [],
        "implementation_steps": [description],
        "test_plan": ["Run focused tests"],
        "acceptance_checklist": [],
        "blockers": [],
        "steps": [{
            "id": "client",
            "description": description,
            "depends_on": [],
            "files": [file_path],
        }],
    }


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit):
        return json.dumps(self.payload).encode("utf-8")


def test_context_excludes_git_and_environment_files(tmp_path):
    (tmp_path / "main.py").write_text("print('hello')", encoding="utf-8")
    (tmp_path / ".env").write_text("API_KEY=secret", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("secret config", encoding="utf-8")

    context = collect_repo_context(tmp_path)
    paths = [item["path"] for item in context]

    assert "main.py" in paths
    assert ".env" not in paths
    assert ".git/config" not in paths


def test_draft_patch_returns_validated_diff_without_writing_files(monkeypatch, tmp_path):
    (tmp_path / "client.py").write_text("before\n", encoding="utf-8")
    seen = {}

    response = {
        "message": {
            "content": json.dumps({
                "status": "patch",
                "summary": "Update retry handling.",
                "diff": DIFF,
                "assumptions": ["The existing client is the intended target."],
                "questions": [],
            })
        }
    }

    class FakeOpener:
        def open(self, request, timeout):
            seen["request"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse(response)

    monkeypatch.setattr("ai_worker.developer.build_opener", lambda handler: FakeOpener())
    proposal = draft_patch(ISSUE, tmp_path, model="qwen2.5-coder:7b")

    assert proposal.changed_files == ["client.py"]
    assert proposal.diff == DIFF
    user_content = next(item["content"] for item in seen["request"]["messages"] if item["role"] == "user")
    assert "client.py" in user_content
    assert ".env" not in user_content
    assert not (tmp_path / ".ai-worker-generated.patch").exists()


def test_draft_patch_rejects_sensitive_file_targets(monkeypatch, tmp_path):
    (tmp_path / "main.py").write_text("print('hello')", encoding="utf-8")
    bad_diff = DIFF.replace("client.py", ".env")
    response = {
        "message": {
            "content": json.dumps({
                "status": "patch",
                "summary": "Unsafe change.",
                "diff": bad_diff,
                "assumptions": [],
                "questions": [],
            })
        }
    }

    class FakeOpener:
        def open(self, request, timeout):
            return FakeResponse(response)

    monkeypatch.setattr("ai_worker.developer.build_opener", lambda handler: FakeOpener())
    import pytest
    with pytest.raises(PatchError):
        draft_patch(ISSUE, tmp_path)


def test_context_prioritizes_paths_related_to_issue(tmp_path):
    (tmp_path / "aaa.py").write_text("unrelated = True", encoding="utf-8")
    (tmp_path / "retry.py").write_text("retry = True", encoding="utf-8")

    context = collect_repo_context(tmp_path, brief=ISSUE)

    assert context[0]["path"] == "retry.py"

def test_context_prioritizes_relevant_file_contents(tmp_path):
    for index in range(65):
        (tmp_path / f"a_unrelated_{index:02}.py").write_text(
            "unrelated_value = True", encoding="utf-8"
        )

    (tmp_path / "z_relevant.py").write_text(
        "The retry backoff implementation handles the API response.",
        encoding="utf-8",
    )

    context = collect_repo_context(tmp_path, brief=ISSUE)

    assert context[0]["path"] == "z_relevant.py"


def test_draft_patch_returns_needs_information_without_diff(monkeypatch, tmp_path):
    (tmp_path / "client.py").write_text("before\n", encoding="utf-8")
    response = {
        "message": {
            "content": json.dumps({
                "status": "needs_information",
                "summary": "More information is needed.",
                "diff": "",
                "assumptions": [],
                "questions": ["What retry backoff behavior is expected?"],
            })
        }
    }

    class FakeOpener:
        def open(self, request, timeout):
            return FakeResponse(response)

    monkeypatch.setattr("ai_worker.developer.build_opener", lambda handler: FakeOpener())

    proposal = draft_patch(ISSUE, tmp_path)

    assert proposal.status == "needs_information"
    assert proposal.diff == ""
    assert proposal.changed_files == []
    assert proposal.questions == ["What retry backoff behavior is expected?"]


def test_draft_patch_rejects_needs_information_with_diff():
    import pytest
    from ai_worker.developer import _validate_patch_response

    with pytest.raises(PatchError):
        _validate_patch_response({
            "status": "needs_information",
            "summary": "Invalid response.",
            "diff": DIFF,
            "assumptions": [],
            "questions": ["What is missing?"],
        })


def test_draft_patch_fails_when_repair_response_is_invalid(monkeypatch, tmp_path):
    import pytest

    (tmp_path / "main.py").write_text("print('hello')", encoding="utf-8")
    bad_diff = DIFF.replace("client.py", ".env")

    def make_response(diff):
        return {
            "message": {
                "content": json.dumps({
                    "status": "patch",
                    "summary": "Unsafe patch.",
                    "diff": diff,
                    "assumptions": [],
                    "questions": [],
                })
            }
        }

    responses = [make_response(bad_diff), make_response(bad_diff)]

    class FakeOpener:
        def __init__(self):
            self.calls = 0

        def open(self, request, timeout):
            response = responses[self.calls]
            self.calls += 1
            return FakeResponse(response)

    opener = FakeOpener()
    monkeypatch.setattr("ai_worker.developer.build_opener", lambda handler: opener)

    with pytest.raises(PatchError):
        draft_patch(ISSUE, tmp_path)

    assert opener.calls == 2


def test_draft_patch_repairs_invalid_json_response(monkeypatch, tmp_path):
    import pytest

    (tmp_path / "client.py").write_text("before\n", encoding="utf-8")

    responses = [
        {"message": {"content": "not valid JSON"}},
        {"message": {"content": "still not valid JSON"}},
    ]

    class FakeOpener:
        def __init__(self):
            self.calls = 0

        def open(self, request, timeout):
            response = responses[self.calls]
            self.calls += 1
            return FakeResponse(response)

    opener = FakeOpener()
    monkeypatch.setattr(
        "ai_worker.developer.build_opener",
        lambda handler: opener,
    )

    with pytest.raises(PatchError):
        draft_patch(ISSUE, tmp_path)

    assert opener.calls == 2


def test_context_scan_has_a_hard_candidate_limit(monkeypatch, tmp_path):
    for index in range(8):
        (tmp_path / f"file_{index:02}.py").write_text(
            f"value = {index}", encoding="utf-8"
        )
    monkeypatch.setattr("ai_worker.developer.MAX_CONTEXT_SCAN_FILES", 3)

    context = collect_repo_context(tmp_path)

    assert [item["path"] for item in context] == [
        "file_00.py", "file_01.py", "file_02.py"
    ]


def test_context_scan_has_a_hard_byte_budget(monkeypatch, tmp_path):
    (tmp_path / "a.py").write_text("12345678", encoding="utf-8")
    (tmp_path / "b.py").write_text("abcdefgh", encoding="utf-8")
    monkeypatch.setattr("ai_worker.developer.MAX_CONTEXT_SCAN_BYTES", 10)

    context = collect_repo_context(tmp_path)

    assert [item["path"] for item in context] == ["a.py"]


def test_question_relevance_requires_two_task_specific_terms():
    import pytest
    from ai_worker.developer import _validate_question_relevance

    proposal = {
        "status": "needs_information",
        "questions": ["What retry backoff behavior is expected?"],
    }
    _validate_question_relevance(proposal, ISSUE)

    unrelated = {
        "status": "needs_information",
        "questions": ["What retry configuration is required for deployment?"],
    }
    with pytest.raises(PatchError, match="not grounded"):
        _validate_question_relevance(unrelated, ISSUE)


def test_draft_patch_includes_task_plan_in_model_request(monkeypatch, tmp_path):
    (tmp_path / "client.py").write_text("before\n", encoding="utf-8")
    seen = {}
    response = {
        "message": {
            "content": json.dumps({
                "status": "patch",
                "summary": "Update retry handling.",
                "diff": DIFF,
                "assumptions": [],
                "questions": [],
            })
        }
    }

    class FakeOpener:
        def open(self, request, timeout):
            seen["request"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse(response)

    monkeypatch.setattr(
        "ai_worker.developer.build_opener",
        lambda handler: FakeOpener(),
    )
    plan = {
        "summary": "Improve retry backoff handling",
        "acceptance_checklist": ["Retry backoff is covered by tests"],
    }
    draft_patch(ISSUE, tmp_path, plan=plan)

    user_message = next(
        item["content"]
        for item in seen["request"]["messages"]
        if item["role"] == "user"
    )
    payload = json.loads(user_message.split("Return JSON only:\n", 1)[1])
    assert payload["task_plan"] == plan


def test_draft_patch_rejects_files_outside_structured_plan_scope(monkeypatch, tmp_path):
    import pytest

    (tmp_path / "client.py").write_text("before\n", encoding="utf-8")
    outside_diff = DIFF.replace("client.py", "unplanned.py")
    response = {
        "message": {
            "content": json.dumps({
                "status": "patch",
                "summary": "Modify an unplanned file.",
                "diff": outside_diff,
                "assumptions": [],
                "questions": [],
            })
        }
    }

    class FakeOpener:
        def open(self, request, timeout):
            return FakeResponse(response)

    monkeypatch.setattr("ai_worker.developer.build_opener", lambda handler: FakeOpener())
    plan = _structured_scope_plan("client.py")

    with pytest.raises(PatchError, match="outside structured plan scope"):
        draft_patch(ISSUE, tmp_path, plan=plan)


def test_draft_patch_allows_an_explicitly_planned_new_file(monkeypatch, tmp_path):
    (tmp_path / "client.py").write_text("before\n", encoding="utf-8")
    new_file_diff = """diff --git a/new_client.py b/new_client.py
new file mode 100644
--- /dev/null
+++ b/new_client.py
@@ -0,0 +1 @@
+value = 1
"""
    response = {
        "message": {
            "content": json.dumps({
                "status": "patch",
                "summary": "Add the planned module.",
                "diff": new_file_diff,
                "assumptions": [],
                "questions": [],
            })
        }
    }

    class FakeOpener:
        def open(self, request, timeout):
            return FakeResponse(response)

    monkeypatch.setattr("ai_worker.developer.build_opener", lambda handler: FakeOpener())
    plan = _structured_scope_plan("new_client.py")

    proposal = draft_patch(ISSUE, tmp_path, plan=plan)
    assert proposal.changed_files == ["new_client.py"]


def test_draft_prompt_allows_planned_new_file_missing_from_context(monkeypatch, tmp_path):
    captured = {}
    responses = [
      {"message": {"content": json.dumps({
        "status": "needs_information",
        "summary": "Clarification required.",
        "diff": "",
        "assumptions": [],
        "questions": ["Should the requested client module be created as new_client.py?"],
      })}},
      {"message": {"content": json.dumps({
        "status": "patch",
        "summary": "Add the explicitly requested planned module.",
        "diff": """diff --git a/new_client.py b/new_client.py
new file mode 100644
--- /dev/null
+++ b/new_client.py
@@ -0,0 +1 @@
+class Client: pass
""",
        "assumptions": [],
        "questions": [],
      })}},
    ]

    class FakeOpener:
        def open(self, request, timeout):
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse(responses.pop(0))

    monkeypatch.setattr("ai_worker.developer.build_opener", lambda handler: FakeOpener())
    plan = _structured_scope_plan("new_client.py")
    brief = replace(
        ISSUE,
        title="Create requested client module",
        body="Create the requested client module named new_client.py.",
    )
    proposal = draft_patch(
        brief,
        tmp_path,
        plan=plan,
        repository_context=[{"path": "client.py", "content": "class Client: pass\n"}],
    )
    system_prompt = captured["body"]["messages"][0]["content"]
    assert proposal.status == "patch"
    assert proposal.changed_files == ["new_client.py"]
    assert "A planned new-file path may be absent from context" in system_prompt
    assert "Do NOT ask for permission or propose an alternative solely because" in system_prompt


def test_relevance_check_does_not_treat_negated_file_creation_as_authorization():
    from ai_worker.developer import _validate_question_relevance

    brief = replace(
        ISSUE,
        title="Do not add the config module",
        body="Do not add src/config.py; keep the timeout behavior in worker.py.",
    )
    plan = _structured_scope_plan("src/config.py")
    proposal = {
        "status": "needs_information",
        "questions": ["Should src/config.py be created instead?"],
    }

    _validate_question_relevance(proposal, brief, plan)


def test_draft_patch_rejects_malformed_structured_plan_before_model_call(monkeypatch, tmp_path):
    (tmp_path / "client.py").write_text("before\n", encoding="utf-8")
    monkeypatch.setattr(
        "ai_worker.developer.build_opener",
        lambda handler: (_ for _ in ()).throw(AssertionError("model called")),
    )
    with pytest.raises(PatchError, match="Invalid structured task plan"):
        draft_patch(ISSUE, tmp_path, plan={"steps": [{"id": "one", "files": ["client.py"]}]})


def test_structured_plan_with_empty_scope_fails_closed_for_changed_file():
    from ai_worker.developer import _validate_patch_plan_scope

    plan = _structured_scope_plan("client.py")
    plan["steps"][0]["files"] = []
    with pytest.raises(PatchError, match="outside structured plan scope"):
        _validate_patch_plan_scope(["client.py"], plan)


def test_plan_scope_rejects_case_normalization_aliases():
    from ai_worker.developer import _validate_patch_plan_scope

    plan = _structured_scope_plan("Client.py")
    with pytest.raises(PatchError, match="outside structured plan scope"):
        _validate_patch_plan_scope(["client.py"], plan)


@pytest.mark.parametrize("path", ["/tmp/file.py", "../file.py", "C:/file.py", "folder/../file.py"])
def test_patch_path_rejects_absolute_and_traversal(path):
    from ai_worker.developer import _safe_patch_path

    with pytest.raises(PatchError, match="Unsafe path"):
        _safe_patch_path(path)


def test_context_prioritizes_explicit_paths_from_issue(tmp_path):
    target = tmp_path / ".agents" / "install.py"
    target.parent.mkdir(parents=True)
    target.write_text("def uninstall(): pass", encoding="utf-8")

    (tmp_path / "aaa.py").write_text(
        "uninstall manifest hash force", encoding="utf-8"
    )

    brief = replace(
        ISSUE,
        title="Add uninstall",
        body="Update `.agents/install.py` to add --uninstall.",
    )

    context = collect_repo_context(tmp_path, brief=brief)

    assert context[0]["path"] == ".agents/install.py"

def test_context_preserves_case_in_explicit_issue_paths(tmp_path):
    target = tmp_path / "src" / "MyModule" / "Install.py"
    target.parent.mkdir(parents=True)
    target.write_text("def install(): pass", encoding="utf-8")

    brief = replace(
        ISSUE,
        title="Update install module",
        body="Update `src/MyModule/Install.py` to add uninstall.",
    )

    context = collect_repo_context(tmp_path, brief=brief)

    assert context[0]["path"] == "src/MyModule/Install.py"


def test_question_relevance_accepts_question_grounded_in_plan():
    import pytest
    from ai_worker.developer import _validate_question_relevance

    brief = replace(
        ISSUE,
        title="Fix application startup",
        body="The application fails during startup.",
    )
    plan = {
        "summary": "Improve retry backoff handling",
        "implementation_steps": [
            "Configure exponential retry backoff with jitter",
        ],
    }
    proposal = {
        "status": "needs_information",
        "questions": ["Should retry backoff include jitter?"],
    }

    _validate_question_relevance(proposal, brief, plan)


def test_context_prioritizes_plain_paths_from_plan(tmp_path):
    (tmp_path / "mkdocs.yml").write_text("site_name: Example", encoding="utf-8")
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "prepare-mkdocs.py").write_text(
        "def prepare(): pass", encoding="utf-8"
    )
    (tmp_path / "aaa.py").write_text("unrelated = True", encoding="utf-8")

    plan = {
        "implementation_steps": [
            "Update mkdocs.yml and scripts/prepare-mkdocs.py"
        ]
    }
    context = collect_repo_context(tmp_path, brief=ISSUE, plan=plan)
    paths = [item["path"] for item in context]

    assert "mkdocs.yml" in paths
    assert "scripts/prepare-mkdocs.py" in paths
    assert paths.index("mkdocs.yml") < paths.index("aaa.py")
    assert paths.index("scripts/prepare-mkdocs.py") < paths.index("aaa.py")


def test_context_ignores_unsafe_paths_from_plan(tmp_path):
    (tmp_path / "safe.py").write_text("value = 1", encoding="utf-8")
    plan = {
        "implementation_steps": [
            "Read `../outside.py` and `https://example.com/secret.py`"
        ]
    }
    context = collect_repo_context(tmp_path, brief=ISSUE, plan=plan)
    paths = [item["path"] for item in context]

    assert "safe.py" in paths
    assert "../outside.py" not in paths
    assert "https://example.com/secret.py" not in paths


def test_context_diagnostics_track_unquoted_and_missing_explicit_paths(tmp_path):
    from dataclasses import replace

    target = tmp_path / "src" / "MyModule" / "Install.py"
    target.parent.mkdir(parents=True)
    target.write_text("def install(): pass", encoding="utf-8")

    brief = replace(
        ISSUE,
        title="Update installer",
        body=(
            "Update src/MyModule/Install.py and "
            "src/Missing/Deploy.py to support installation."
        ),
    )
    diagnostics = {}
    context = collect_repo_context(
        tmp_path, brief=brief, diagnostics=diagnostics
    )

    assert "src/MyModule/Install.py" in [item["path"] for item in context]
    assert "src/MyModule/Install.py" in diagnostics["explicit_paths_found"]
    assert "src/Missing/Deploy.py" in diagnostics["explicit_paths_missing"]
    assert "explicit_path" in diagnostics["selected_files"][0]["reasons"]
    assert all(
        "content" not in item
        for item in diagnostics["selected_files"]
    )
    assert "content" not in diagnostics
    assert all(
        "content" not in item
        for item in diagnostics["inspected_files"]
    )



def test_context_diagnostics_find_python_definitions_and_cross_file_references(
    tmp_path,
):
    (tmp_path / "helpers.py").write_text(
        "def install_helper():\n    return True\n",
        encoding="utf-8",
    )
    (tmp_path / "consumer.py").write_text(
        "from helpers import install_helper\n"
        "def run_install():\n"
        "    return install_helper()\n",
        encoding="utf-8",
    )
    brief = replace(
        ISSUE,
        title="Fix install helper",
        body="The install helper is not being called correctly.",
    )
    diagnostics = {}
    collect_repo_context(tmp_path, brief=brief, diagnostics=diagnostics)

    analysis = diagnostics["symbol_analysis"]
    assert analysis["files_analyzed"] == 2
    assert any(
        item["name"] == "install_helper" and item["path"] == "helpers.py"
        for item in analysis["definitions"]
    )
    assert any(
        item["name"] == "install_helper"
        and item["reference_path"] == "consumer.py"
        and item["definition_path"] == "helpers.py"
        for item in analysis["cross_file_references"]
    )
    assert "symbol_definition_match" in next(
        item["reasons"]
        for item in diagnostics["selected_files"]
        if item["path"] == "helpers.py"
    )


def test_context_symbol_analysis_skips_non_python_files_without_partial_status(tmp_path):
    (tmp_path / "app.ts").write_text(
        "export function installApp() { return true; }",
        encoding="utf-8",
    )
    diagnostics = {}
    collect_repo_context(tmp_path, diagnostics=diagnostics)

    analysis = diagnostics["symbol_analysis"]
    assert analysis["unsupported_files"] == 1
    assert analysis["status"] == "completed"


def test_context_diagnostics_report_scan_byte_budget_truncation(
    monkeypatch, tmp_path
):
    (tmp_path / "a.py").write_text("12345678", encoding="utf-8")
    (tmp_path / "b.py").write_text("abcdefgh", encoding="utf-8")
    monkeypatch.setattr("ai_worker.developer.MAX_CONTEXT_SCAN_BYTES", 10)

    diagnostics = {}
    collect_repo_context(tmp_path, diagnostics=diagnostics)

    assert diagnostics["scan"]["truncated"] is True
    assert "scan_byte_budget" in diagnostics["scan"]["truncation_reasons"]
    assert diagnostics["skipped_counts"]["scan_byte_budget"] >= 1
    assert diagnostics["status"] == "truncated"


def test_context_status_prioritizes_truncation_when_no_files_are_selected(
    monkeypatch, tmp_path
):
    (tmp_path / "a.py").write_text("x = 1", encoding="utf-8")
    monkeypatch.setattr("ai_worker.developer.MAX_CONTEXT_SCAN_BYTES", 1)

    diagnostics = {}
    context = collect_repo_context(tmp_path, diagnostics=diagnostics)

    assert context == []
    assert diagnostics["context_files_sent"] == 0
    assert diagnostics["scan"]["truncated"] is True
    assert "scan_byte_budget" in diagnostics["scan"]["truncation_reasons"]
    assert diagnostics["status"] == "truncated"


def test_context_prioritizes_python_project_structure(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        "[project]\\nname = 'sample'\\n", encoding="utf-8"
    )
    (tmp_path / "app.py").write_text(
        "def run(): pass\\n", encoding="utf-8"
    )
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_app.py").write_text(
        "def test_run(): pass\\n", encoding="utf-8"
    )
    (tmp_path / "aaa.py").write_text(
        "unrelated_value = True\\n", encoding="utf-8"
    )

    diagnostics = {}
    context = collect_repo_context(tmp_path, diagnostics=diagnostics)
    paths = [item["path"] for item in context]
    selected = {item["path"]: item for item in diagnostics["selected_files"]}

    assert paths.index("pyproject.toml") < paths.index("aaa.py")
    assert paths.index("app.py") < paths.index("aaa.py")
    assert paths.index("tests/test_app.py") < paths.index("aaa.py")
    assert "project_manifest" in selected["pyproject.toml"]["reasons"]
    assert "application_entrypoint" in selected["app.py"]["reasons"]
    assert "test_file" in selected["tests/test_app.py"]["reasons"]


def test_context_prioritizes_javascript_project_structure(tmp_path):
    (tmp_path / "package.json").write_text(
        '{"name": "sample", "scripts": {"test": "vitest"}}',
        encoding="utf-8",
    )
    src = tmp_path / "src"
    src.mkdir()
    (src / "index.ts").write_text(
        "export function start() {}\\n", encoding="utf-8"
    )
    tests_dir = tmp_path / "__tests__"
    tests_dir.mkdir()
    (tests_dir / "app.test.ts").write_text(
        "test('app', () => {});\\n", encoding="utf-8"
    )
    (tmp_path / "aaa.ts").write_text(
        "const unrelated = true;\\n", encoding="utf-8"
    )

    diagnostics = {}
    context = collect_repo_context(tmp_path, diagnostics=diagnostics)
    paths = [item["path"] for item in context]
    selected = {item["path"]: item for item in diagnostics["selected_files"]}

    assert paths.index("package.json") < paths.index("aaa.ts")
    assert paths.index("src/index.ts") < paths.index("aaa.ts")
    assert paths.index("__tests__/app.test.ts") < paths.index("aaa.ts")
    assert "project_manifest" in selected["package.json"]["reasons"]
    assert "application_entrypoint" in selected["src/index.ts"]["reasons"]
    assert "test_file" in selected["__tests__/app.test.ts"]["reasons"]


def test_context_symbol_analysis_resolves_relative_import(tmp_path):
    package = tmp_path / "sample"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "helpers.py").write_text(
        "def install_helper():\n    return True\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text(
        "from .helpers import install_helper as install\n"
        "def run():\n    return install()\n",
        encoding="utf-8",
    )

    brief = replace(
        ISSUE,
        title="Fix install helper",
        body="The install helper is not being called correctly.",
    )
    diagnostics = {}
    collect_repo_context(tmp_path, brief=brief, diagnostics=diagnostics)

    assert any(
        item["name"] == "install_helper"
        and item["local_name"] == "install"
        and item["reference_path"] == "sample/consumer.py"
        and item["definition_path"] == "sample/helpers.py"
        for item in diagnostics["symbol_analysis"]["cross_file_references"]
    )


def test_context_symbol_analysis_resolves_relative_module_attribute(tmp_path):
    package = tmp_path / "sample"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "helpers.py").write_text(
        "def install_helper():\n    return True\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text(
        "from . import helpers as helper_module\n"
        "def run():\n    return helper_module.install_helper()\n",
        encoding="utf-8",
    )

    brief = replace(
        ISSUE,
        title="Fix install helper",
        body="The install helper is not being called correctly.",
    )
    diagnostics = {}
    collect_repo_context(tmp_path, brief=brief, diagnostics=diagnostics)

    assert any(
        item["name"] == "install_helper"
        and item["local_name"] == "helper_module"
        and item["reference_path"] == "sample/consumer.py"
        and item["definition_path"] == "sample/helpers.py"
        for item in diagnostics["symbol_analysis"]["cross_file_references"]
    )


def test_context_symbol_analysis_resolves_relative_package_symbol(tmp_path):
    package = tmp_path / "sample"
    package.mkdir()
    (package / "__init__.py").write_text(
        "def install_helper():\n    return True\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text(
        "from . import install_helper as install\n"
        "def run():\n    return install()\n",
        encoding="utf-8",
    )

    brief = replace(
        ISSUE,
        title="Fix install helper",
        body="The install helper is not being called correctly.",
    )
    diagnostics = {}
    collect_repo_context(tmp_path, brief=brief, diagnostics=diagnostics)

    assert any(
        item["name"] == "install_helper"
        and item["local_name"] == "install"
        and item["reference_path"] == "sample/consumer.py"
        and item["definition_path"] == "sample/__init__.py"
        for item in diagnostics["symbol_analysis"]["cross_file_references"]
    )

def test_context_symbol_analysis_reports_ambiguous_import_targets(tmp_path):
    package_dir = tmp_path / "helpers"
    package_dir.mkdir()

    (tmp_path / "helpers.py").write_text(
        """def install_helper():
    return 'module'
""",
        encoding="utf-8",
    )
    (package_dir / "__init__.py").write_text(
        """def install_helper():
    return 'package'
""",
        encoding="utf-8",
    )
    (tmp_path / "consumer.py").write_text(
        """from helpers import install_helper

def run():
    return install_helper()
""",
        encoding="utf-8",
    )

    brief = replace(
        ISSUE,
        title="Fix install helper",
        body="The install helper is not being called correctly.",
    )
    diagnostics = {}
    collect_repo_context(tmp_path, brief=brief, diagnostics=diagnostics)

    analysis = diagnostics["symbol_analysis"]
    assert not any(
        item["reference_path"] == "consumer.py"
        and item["name"] == "install_helper"
        for item in analysis["cross_file_references"]
    )

    ambiguous = [
        item for item in analysis["ambiguous_references"]
        if item["reference_path"] == "consumer.py"
        and item["name"] == "install_helper"
    ]
    assert len(ambiguous) == 1
    assert ambiguous[0]["local_name"] == "install_helper"
    assert ambiguous[0]["candidate_definition_paths"] == [
        "helpers.py",
        "helpers/__init__.py",
    ]
    assert ambiguous[0]["candidate_definition_count"] == 2
    assert ambiguous[0]["reason"] == "multiple_matching_definitions"


def test_context_symbol_analysis_caps_ambiguous_reference_reports(tmp_path):
    package_dir = tmp_path / "helpers"
    package_dir.mkdir()

    names = [f"install_helper_{index:03d}" for index in range(101)]
    definitions = []
    for index, symbol in enumerate(names):
        definitions.extend([
            f"def {symbol}():",
            f"    return {index}",
            "",
        ])

    module_source = "\n".join(definitions)
    (tmp_path / "helpers.py").write_text(module_source, encoding="utf-8")
    (package_dir / "__init__.py").write_text(
        module_source, encoding="utf-8"
    )

    consumer_lines = [
        "from helpers import (",
        *[f"    {symbol}," for symbol in names],
        ")",
        "",
        "def run():",
        *[f"    {symbol}()" for symbol in names],
    ]
    (tmp_path / "consumer.py").write_text(
        "\n".join(consumer_lines) + "\n",
        encoding="utf-8",
    )

    brief = replace(
        ISSUE,
        title="Fix install helper functions",
        body="The install helper functions are not being called correctly.",
    )
    diagnostics = {}
    collect_repo_context(tmp_path, brief=brief, diagnostics=diagnostics)

    analysis = diagnostics["symbol_analysis"]
    assert len(analysis["ambiguous_references"]) == 100
    assert analysis["truncated"] is True
    assert "ambiguity_report_limit" in analysis["truncation_reasons"]
    assert analysis["status"] == "truncated"

def test_context_symbol_analysis_keeps_unique_reference_when_another_is_ambiguous(tmp_path):
    package_dir = tmp_path / "helpers"
    package_dir.mkdir()

    (tmp_path / "helpers.py").write_text(
        """def install_helper():
    return 'module'

def unique_helper():
    return 'unique'
""",
        encoding="utf-8",
    )
    (package_dir / "__init__.py").write_text(
        """def install_helper():
    return 'package'
""",
        encoding="utf-8",
    )
    (tmp_path / "consumer.py").write_text(
        """from helpers import install_helper, unique_helper

def run():
    install_helper()
    return unique_helper()
""",
        encoding="utf-8",
    )

    brief = replace(
        ISSUE,
        title="Fix install helper and unique helper",
        body="The install helper and unique helper calls are incorrect.",
    )
    diagnostics = {}
    collect_repo_context(tmp_path, brief=brief, diagnostics=diagnostics)

    analysis = diagnostics["symbol_analysis"]

    assert any(
        item["reference_path"] == "consumer.py"
        and item["name"] == "install_helper"
        for item in analysis["ambiguous_references"]
    )
    assert any(
        item["reference_path"] == "consumer.py"
        and item["name"] == "unique_helper"
        and item["definition_path"] == "helpers.py"
        for item in analysis["cross_file_references"]
    )


def test_context_symbol_analysis_caps_cross_file_reference_reports(tmp_path):
    package_dir = tmp_path / "helpers"
    package_dir.mkdir()

    names = [f"install_helper_{index:03d}" for index in range(201)]
    definitions = []
    for index, symbol in enumerate(names):
        definitions.extend([
            f"def {symbol}():",
            f"    return {index}",
            "",
        ])

    (tmp_path / "helpers.py").write_text(
        "\n".join(definitions),
        encoding="utf-8",
    )
    (package_dir / "__init__.py").write_text("", encoding="utf-8")

    consumer_lines = [
        "from helpers import (",
        *[f"    {symbol}," for symbol in names],
        ")",
        "",
        "def run():",
        *[f"    {symbol}()" for symbol in names],
    ]
    (tmp_path / "consumer.py").write_text(
        "\n".join(consumer_lines) + "\n",
        encoding="utf-8",
    )

    brief = replace(
        ISSUE,
        title="Fix install helper functions",
        body="The install helper functions are not being called correctly.",
    )
    diagnostics = {}
    collect_repo_context(tmp_path, brief=brief, diagnostics=diagnostics)

    analysis = diagnostics["symbol_analysis"]
    assert len(analysis["cross_file_references"]) == 200
    assert analysis["truncated"] is True
    assert "reference_report_limit" in analysis["truncation_reasons"]
    assert analysis["status"] == "truncated"

def test_context_symbol_analysis_reports_duplicate_definitions_with_line_numbers(tmp_path):
    (tmp_path / "helpers.py").write_text(
        """def install_helper():
    return 'first'

def install_helper():
    return 'second'
""",
        encoding="utf-8",
    )
    (tmp_path / "consumer.py").write_text(
        """from helpers import install_helper

def run():
    return install_helper()
""",
        encoding="utf-8",
    )

    brief = replace(
        ISSUE,
        title="Fix install helper",
        body="The install helper is not being called correctly.",
    )
    diagnostics = {}
    collect_repo_context(tmp_path, brief=brief, diagnostics=diagnostics)

    analysis = diagnostics["symbol_analysis"]
    ambiguous = [
        item for item in analysis["ambiguous_references"]
        if item["reference_path"] == "consumer.py"
        and item["name"] == "install_helper"
    ]

    assert len(ambiguous) == 1
    report = ambiguous[0]
    assert report["candidate_definition_paths"] == ["helpers.py"]
    assert report["candidate_definition_count"] == 2
    assert report["candidate_definitions"] == [
        {"path": "helpers.py", "line": 1, "kind": "FunctionDef"},
        {"path": "helpers.py", "line": 4, "kind": "FunctionDef"},
    ]

def test_context_symbol_analysis_does_not_promote_function_local_imports(
    tmp_path,
):
    (tmp_path / "helpers.py").write_text(
        "def install_helper():\\n    return True\\n",
        encoding="utf-8",
    )
    (tmp_path / "consumer.py").write_text(
        "def local_runner():\\n"
        "    from helpers import install_helper\\n"
        "    return install_helper()\\n"
        "\\n"
        "install_helper()\\n",
        encoding="utf-8",
    )

    brief = replace(
        ISSUE,
        title="Fix install helper",
        body="The install helper is not being called correctly.",
    )
    diagnostics = {}
    collect_repo_context(tmp_path, brief=brief, diagnostics=diagnostics)

    analysis = diagnostics["symbol_analysis"]
    assert not any(
        item["reference_path"] == "consumer.py"
        and item["name"] == "install_helper"
        for item in analysis["cross_file_references"]
    )
    assert not any(
        item["reference_path"] == "consumer.py"
        and item["name"] == "install_helper"
        for item in analysis["ambiguous_references"]
    )

def test_context_symbol_analysis_ignores_function_local_shadowed_imports(
    tmp_path,
):
    (tmp_path / "helpers.py").write_text(
        "def install_helper():\n    return 'module'\n",
        encoding="utf-8",
    )
    (tmp_path / "other_helpers.py").write_text(
        "def install_helper():\n    return 'local'\n",
        encoding="utf-8",
    )
    (tmp_path / "consumer.py").write_text(
        "from helpers import install_helper\n"
        "\n"
        "def local_runner():\n"
        "    from other_helpers import install_helper\n"
        "    return install_helper()\n",
        encoding="utf-8",
    )

    brief = replace(
        ISSUE,
        title="Fix install helper",
        body="The install helper is not being called correctly.",
    )
    diagnostics = {}
    collect_repo_context(tmp_path, brief=brief, diagnostics=diagnostics)

    analysis = diagnostics["symbol_analysis"]
    assert not any(
        item["reference_path"] == "consumer.py"
        and item["name"] == "install_helper"
        for item in analysis["cross_file_references"]
    )
    assert not any(
        item["reference_path"] == "consumer.py"
        and item["name"] == "install_helper"
        for item in analysis["ambiguous_references"]
    )

def test_context_symbol_analysis_scopes_local_imports_per_function(tmp_path):
    (tmp_path / "helpers.py").write_text(
        "def install_helper():\n    return 'module'\n",
        encoding="utf-8",
    )
    (tmp_path / "other_helpers.py").write_text(
        "def install_helper():\n    return 'local'\n",
        encoding="utf-8",
    )
    (tmp_path / "consumer.py").write_text(
        "from helpers import install_helper\n"
        "\n"
        "def local_runner():\n"
        "    from other_helpers import install_helper\n"
        "    return install_helper()\n"
        "\n"
        "def module_runner():\n"
        "    return install_helper()\n"
        "\n"
        "def outer_runner():\n"
        "    from other_helpers import install_helper\n"
        "    def inner_runner():\n"
        "        return install_helper()\n"
        "    return inner_runner()\n",
        encoding="utf-8",
    )

    brief = replace(
        ISSUE,
        title="Fix install helper",
        body="The install helper is not being called correctly.",
    )
    diagnostics = {}
    collect_repo_context(tmp_path, brief=brief, diagnostics=diagnostics)

    references = diagnostics["symbol_analysis"]["cross_file_references"]
    consumer_refs = [
        item for item in references
        if item["reference_path"] == "consumer.py"
        and item["name"] == "install_helper"
    ]

    assert any(
        item["definition_path"] == "helpers.py"
        for item in consumer_refs
    )
    assert not any(
        item["definition_path"] == "other_helpers.py"
        for item in consumer_refs
    )


def test_repair_patch_returns_validated_in_scope_diff(monkeypatch, tmp_path):
    (tmp_path / "client.py").write_text("before\n", encoding="utf-8")
    repaired_diff = DIFF.replace("+after", "+fixed")

    response = {
        "message": {
            "content": json.dumps({
                "status": "patch",
                "summary": "Address the review finding.",
                "diff": repaired_diff,
                "assumptions": [],
                "questions": [],
            })
        }
    }
    seen = {}

    class FakeOpener:
        def open(self, request, timeout):
            seen["request"] = json.loads(request.data.decode("utf-8"))
            seen["timeout"] = timeout
            return FakeResponse(response)

    monkeypatch.setattr(
        "ai_worker.developer.build_opener",
        lambda handler: FakeOpener(),
    )

    finding = {
        "severity": "medium",
        "file": "client.py",
        "line": 1,
        "title": "Incorrect retry behavior",
        "evidence": "The current implementation does not preserve the retry delay.",
        "recommendation": "Preserve the configured retry delay.",
    }

    proposal = repair_patch(
        ISSUE,
        tmp_path,
        model="qwen2.5-coder:7b",
        current_diff=DIFF,
        findings=[finding],
        allowed_files=["client.py"],
    )

    assert proposal.diff == repaired_diff
    assert proposal.changed_files == ["client.py"]
    assert proposal.status == "patch"
    assert proposal.questions == []
    assert (tmp_path / "client.py").read_text(encoding="utf-8") == "before\n"

    user_message = next(
        item["content"]
        for item in seen["request"]["messages"]
        if item["role"] == "user"
    )
    payload = json.loads(user_message.split("Return JSON only:\n", 1)[1])
    assert payload["authorized_files"] == ["client.py"]
    assert payload["review_findings"][0]["title"] == finding["title"]
    assert seen["request"]["model"] == "qwen2.5-coder:7b"


def test_repair_patch_rejects_files_outside_original_boundary(monkeypatch, tmp_path):
    (tmp_path / "client.py").write_text("before\n", encoding="utf-8")
    outside_diff = DIFF.replace("client.py", "other.py")

    response = {
        "message": {
            "content": json.dumps({
                "status": "patch",
                "summary": "Modify another file.",
                "diff": outside_diff,
                "assumptions": [],
                "questions": [],
            })
        }
    }

    class FakeOpener:
        def open(self, request, timeout):
            return FakeResponse(response)

    monkeypatch.setattr(
        "ai_worker.developer.build_opener",
        lambda handler: FakeOpener(),
    )

    finding = {
        "severity": "medium",
        "file": "client.py",
        "line": 1,
        "title": "Retry defect",
        "evidence": "Retry behavior is incorrect.",
        "recommendation": "Fix the retry behavior.",
    }

    import pytest

    with pytest.raises(PatchError, match="outside the original patch"):
        repair_patch(
            ISSUE,
            tmp_path,
            model="qwen2.5-coder:7b",
            current_diff=DIFF,
            findings=[finding],
            allowed_files=["client.py"],
        )


def test_repair_patch_cannot_exceed_structured_plan_scope(monkeypatch, tmp_path):
    import pytest

    (tmp_path / "client.py").write_text("before\n", encoding="utf-8")
    outside_diff = DIFF.replace("client.py", "other.py")
    response = {
        "message": {
            "content": json.dumps({
                "status": "patch",
                "summary": "Modify a file outside the plan.",
                "diff": outside_diff,
                "assumptions": [],
                "questions": [],
            })
        }
    }

    class FakeOpener:
        def open(self, request, timeout):
            return FakeResponse(response)

    monkeypatch.setattr("ai_worker.developer.build_opener", lambda handler: FakeOpener())
    finding = {
        "severity": "medium",
        "file": "client.py",
        "line": 1,
        "title": "Retry defect",
        "evidence": "Retry behavior is incorrect.",
        "recommendation": "Fix the retry behavior.",
    }
    plan = _structured_scope_plan("client.py")

    with pytest.raises(PatchError, match="outside structured plan scope"):
        repair_patch(
            ISSUE,
            tmp_path,
            model="qwen2.5-coder:7b",
            current_diff=DIFF,
            findings=[finding],
            allowed_files=["client.py", "other.py"],
            plan=plan,
        )


def test_repair_patch_rejects_unchanged_diff(monkeypatch, tmp_path):
    (tmp_path / "client.py").write_text("before\n", encoding="utf-8")

    response = {
        "message": {
            "content": json.dumps({
                "status": "patch",
                "summary": "Attempted repair.",
                "diff": DIFF,
                "assumptions": [],
                "questions": [],
            })
        }
    }

    class FakeOpener:
        def open(self, request, timeout):
            return FakeResponse(response)

    monkeypatch.setattr(
        "ai_worker.developer.build_opener",
        lambda handler: FakeOpener(),
    )

    finding = {
        "severity": "medium",
        "file": "client.py",
        "line": 1,
        "title": "Retry defect",
        "evidence": "Retry behavior is incorrect.",
        "recommendation": "Fix the retry behavior.",
    }

    import pytest

    with pytest.raises(PatchError, match="unchanged patch"):
        repair_patch(
            ISSUE,
            tmp_path,
            model="qwen2.5-coder:7b",
            current_diff=DIFF,
            findings=[finding],
            allowed_files=["client.py"],
        )


def test_draft_patch_uses_supplied_repository_snapshot_without_rescanning(
    monkeypatch, tmp_path
):
    import pytest

    repository_context = [
        {
            "path": "client.py",
            "content": "class APIClient:\n    pass\n",
        }
    ]
    seen = {}

    class FakeOpener:
        def open(self, request, timeout):
            seen["request"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse({
                "message": {
                    "content": json.dumps({
                        "status": "needs_information",
                        "summary": "Clarification required.",
                        "diff": "",
                        "assumptions": [],
                        "questions": ["What retry backoff policy is expected?"],
                    })
                }
            })

    monkeypatch.setattr(
        "ai_worker.developer.collect_repo_context",
        lambda *args, **kwargs: pytest.fail(
            "Repository context must not be collected twice"
        ),
    )
    monkeypatch.setattr(
        "ai_worker.developer.build_opener",
        lambda handler: FakeOpener(),
    )

    proposal = draft_patch(
        ISSUE,
        tmp_path,
        repository_context=repository_context,
    )

    user_message = next(
        item["content"]
        for item in seen["request"]["messages"]
        if item["role"] == "user"
    )

    assert proposal.status == "needs_information"
    assert "client.py" in user_message
    assert "class APIClient" in user_message
