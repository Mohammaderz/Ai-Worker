import json

import pytest

from ai_worker.reviewer import (
    ReviewerError,
    _detect_static_security_findings,
    _read_changed_python_sources,
    _validate_finding_locations,
    _validate_review,
    review_patch,
)
from ai_worker.sources.github_issue import ResearchBrief


def brief():
    return ResearchBrief(
        url="https://github.com/acme/widget/issues/42",
        title="Fix retry handling",
        repository="acme/widget",
        number=42,
        state="open",
        body="Handle transient API failures safely.",
        labels=["bug"],
        updated_at="2026-11-14T10:00:00Z",
    )


def valid_review():
    return {
        "verdict": "pass",
        "summary": "No actionable defects were found in the proposed change.",
        "findings": [],
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


def test_reviewer_returns_validated_review_and_untrusted_context(monkeypatch, tmp_path):
    (tmp_path / "client.py").write_text("def request():\n    return True\n", encoding="utf-8")
    seen = {}

    class FakeOpener:
        def open(self, request, timeout):
            seen["url"] = request.full_url
            seen["body"] = json.loads(request.data.decode("utf-8"))
            seen["timeout"] = timeout
            return FakeResponse({"message": {"content": json.dumps(valid_review())}})

    monkeypatch.setattr("ai_worker.reviewer.build_opener", lambda handler: FakeOpener())
    result = review_patch(
        brief(), str(tmp_path), "diff --git a/client.py b/client.py\n",
        model="review-model",
    )

    assert result.verdict == "pass"
    assert result.findings == []
    assert seen["url"] == "http://127.0.0.1:11434/api/chat"
    assert seen["body"]["model"] == "review-model"
    assert "untrusted data" in seen["body"]["messages"][0]["content"]
    assert seen["body"]["messages"][1]["content"].find("client.py") >= 0
    assert seen["timeout"] == 300


def test_reviewer_accepts_blocking_finding_with_file_and_line():
    data = {
        "verdict": "blocked",
        "summary": "The patch introduces an unsafe authorization bypass.",
        "findings": [{
            "severity": "critical",
            "file": "client.py",
            "line": 12,
            "title": "Authorization is skipped",
            "evidence": "The new handler returns data before checking the caller.",
            "recommendation": "Perform authorization before returning the resource.",
        }],
    }
    assert _validate_review(data)["verdict"] == "blocked"


def test_reviewer_rejects_pass_with_findings():
    data = valid_review()
    data["findings"] = [{
        "severity": "low",
        "file": "client.py",
        "line": 1,
        "title": "Minor concern",
        "evidence": "A concrete issue.",
        "recommendation": "Consider changing it.",
    }]
    with pytest.raises(ReviewerError, match="cannot contain unresolved findings"):
        _validate_review(data)


def test_reviewer_rejects_high_severity_marked_needs_changes():
    data = {
        "verdict": "needs_changes",
        "summary": "A high-severity issue was found.",
        "findings": [{
            "severity": "high",
            "file": "client.py",
            "line": 4,
            "title": "Unsafe behavior",
            "evidence": "Sensitive data is exposed.",
            "recommendation": "Remove the exposure.",
        }],
    }
    with pytest.raises(ReviewerError, match="must block"):
        _validate_review(data)


def test_reviewer_rejects_remote_endpoint():
    with pytest.raises(ReviewerError, match="Invalid reviewer endpoint"):
        review_patch(brief(), ".", "diff --git a/a b/a", host="https://remote.example")



def test_reviewer_rejects_malformed_unhashable_verdict():
    data = valid_review()
    data["verdict"] = ["pass"]
    with pytest.raises(ReviewerError, match="verdict is invalid"):
        _validate_review(data)


def test_reviewer_rejects_malformed_unhashable_severity():
    data = {
        "verdict": "blocked",
        "summary": "Malformed severity must never pass validation.",
        "findings": [{
            "severity": ["critical"],
            "file": "client.py",
            "line": 4,
            "title": "Unsafe behavior",
            "evidence": "Sensitive data is exposed.",
            "recommendation": "Remove the exposure.",
        }],
    }
    with pytest.raises(ReviewerError, match="severity is invalid"):
        _validate_review(data)




def test_static_security_finding_overrides_model_pass(monkeypatch, tmp_path):
    (tmp_path / "sample.py").write_text(
        "def calculate(expression):\n    return 0\n", encoding="utf-8"
    )

    class FakeOpener:
        def open(self, request, timeout):
            return FakeResponse({"message": {"content": json.dumps(valid_review())}})

    monkeypatch.setattr("ai_worker.reviewer.build_opener", lambda handler: FakeOpener())
    diff = """diff --git a/sample.py b/sample.py
--- a/sample.py
+++ b/sample.py
@@ -1,2 +1,2 @@
 def calculate(expression):
-    return 0
+    return eval(expression)
"""
    result = review_patch(brief(), str(tmp_path), diff, model="review-model")

    assert result.verdict == "blocked"
    assert len(result.findings) == 1
    assert result.findings[0].severity == "critical"
    assert result.findings[0].file == "sample.py"
    assert result.findings[0].line == 2
    assert "eval()/exec()" in result.findings[0].evidence


def test_static_security_scanner_ignores_removed_eval_lines():
    from ai_worker.reviewer import _detect_static_security_findings

    diff = """diff --git a/sample.py b/sample.py
--- a/sample.py
+++ b/sample.py
@@ -1 +1 @@
-return eval(expression)
+return 0
"""
    assert _detect_static_security_findings(diff) == []



def test_reviewer_finding_location_must_be_inside_new_side_hunk():
    diff = """diff --git a/sample.py b/sample.py
--- a/sample.py
+++ b/sample.py
@@ -1,2 +1,2 @@
 def calculate(expression):
-    return 0
+    return eval(expression)
"""
    data = {
        "findings": [{
            "file": "sample.py",
            "line": 2,
        }]
    }
    _validate_finding_locations(data, diff)


def test_reviewer_rejects_finding_line_outside_changed_hunk():
    diff = """diff --git a/sample.py b/sample.py
--- a/sample.py
+++ b/sample.py
@@ -1,2 +1,2 @@
 def calculate(expression):
-    return 0
+    return eval(expression)
"""
    data = {
        "findings": [{
            "file": "sample.py",
            "line": 3,
        }]
    }
    with pytest.raises(ReviewerError, match="outside the changed hunks"):
        _validate_finding_locations(data, diff)


def test_reviewer_rejects_finding_for_file_not_in_patch():
    diff = """diff --git a/sample.py b/sample.py
--- a/sample.py
+++ b/sample.py
@@ -1 +1 @@
-old()
+new()
"""
    data = {
        "findings": [{
            "file": "other.py",
            "line": 1,
        }]
    }
    with pytest.raises(ReviewerError, match="outside the patch"):
        _validate_finding_locations(data, diff)



def test_ast_security_scanner_ignores_comments_and_string_literals():
    diff = """diff --git a/sample.py b/sample.py
--- a/sample.py
+++ b/sample.py
@@ -0,0 +1,2 @@
+# eval(user_input) is mentioned in a comment
+message = "exec(user_input)"
"""
    assert _detect_static_security_findings(diff) == []


def test_ast_security_scanner_detects_builtins_dynamic_execution():
    diff = """diff --git a/sample.py b/sample.py
--- a/sample.py
+++ b/sample.py
@@ -0,0 +1 @@
+return builtins.eval(expression)
"""
    findings = _detect_static_security_findings(diff)
    assert len(findings) == 1
    assert findings[0]["line"] == 1
    assert findings[0]["severity"] == "critical"


def test_ast_security_scanner_ignores_non_python_files():
    diff = """diff --git a/example.js b/example.js
--- a/example.js
+++ b/example.js
@@ -0,0 +1 @@
+eval(expression)
"""
    assert _detect_static_security_findings(diff) == []



def test_ast_security_scanner_detects_multiline_eval_call():
    diff = """diff --git a/sample.py b/sample.py
--- a/sample.py
+++ b/sample.py
@@ -0,0 +1,3 @@
+    return eval(
+        expression
+    )
"""
    findings = _detect_static_security_findings(diff)
    assert len(findings) == 1
    assert findings[0]["file"] == "sample.py"
    assert findings[0]["line"] == 1
    assert findings[0]["severity"] == "critical"


def test_ast_security_scanner_detects_multiline_builtins_exec():
    diff = """diff --git a/sample.py b/sample.py
--- a/sample.py
+++ b/sample.py
@@ -0,0 +1,3 @@
+    builtins.exec(
+        untrusted_source
+    )
"""
    findings = _detect_static_security_findings(diff)
    assert len(findings) == 1
    assert findings[0]["line"] == 1



def test_ast_security_scanner_detects_imported_eval_alias():
    diff = """diff --git a/sample.py b/sample.py
--- a/sample.py
+++ b/sample.py
@@ -0,0 +1,2 @@
+from builtins import eval as run_code
+result = run_code(user_input)
"""
    findings = _detect_static_security_findings(diff)
    assert len(findings) == 1
    assert findings[0]["line"] == 2
    assert findings[0]["severity"] == "critical"


def test_ast_security_scanner_detects_aliased_builtins_module():
    diff = """diff --git a/sample.py b/sample.py
--- a/sample.py
+++ b/sample.py
@@ -0,0 +1,2 @@
+import builtins as core
+result = core.exec(untrusted_source)
"""
    findings = _detect_static_security_findings(diff)
    assert len(findings) == 1
    assert findings[0]["line"] == 2
    assert findings[0]["severity"] == "critical"



def test_ast_security_scanner_resolves_eval_alias_across_hunks():
    diff = """diff --git a/sample.py b/sample.py
--- a/sample.py
+++ b/sample.py
@@ -0,0 +1 @@
+from builtins import eval as run_code
@@ -99,0 +100,1 @@
+result = run_code(user_input)
"""
    findings = _detect_static_security_findings(diff)
    assert len(findings) == 1
    assert findings[0]["line"] == 100
    assert findings[0]["severity"] == "critical"


def test_ast_security_scanner_resolves_module_alias_across_hunks():
    diff = """diff --git a/sample.py b/sample.py
--- a/sample.py
+++ b/sample.py
@@ -0,0 +1 @@
+import builtins as core
@@ -99,0 +100,1 @@
+core.exec(untrusted_source)
"""
    findings = _detect_static_security_findings(diff)
    assert len(findings) == 1
    assert findings[0]["line"] == 100


def test_ast_security_scanner_does_not_flag_unrelated_run_function():
    diff = """diff --git a/sample.py b/sample.py
--- a/sample.py
+++ b/sample.py
@@ -0,0 +1,2 @@
+def run_code(value):
+    return value
+result = run_code(user_input)
"""
    assert _detect_static_security_findings(diff) == []



def test_ast_security_scanner_resolves_alias_from_unchanged_file_context():
    diff = """diff --git a/sample.py b/sample.py
--- a/sample.py
+++ b/sample.py
@@ -49,0 +50,1 @@
+result = run_code(user_input)
"""
    existing_source = "from builtins import eval as run_code\n"
    findings = _detect_static_security_findings(
        diff, {"sample.py": existing_source + "result = run_code(user_input)\n"}
    )
    assert len(findings) == 1
    assert findings[0]["line"] == 50
    assert findings[0]["severity"] == "critical"


def test_ast_security_scanner_resolves_existing_builtins_module_alias():
    diff = """diff --git a/sample.py b/sample.py
--- a/sample.py
+++ b/sample.py
@@ -49,0 +50,1 @@
+core.exec(untrusted_source)
"""
    findings = _detect_static_security_findings(
        diff, {"sample.py": "import builtins as core\n"}
    )
    assert len(findings) == 1
    assert findings[0]["line"] == 50


def test_read_changed_python_sources_reads_only_safe_changed_files(tmp_path):
    package = tmp_path / "src"
    package.mkdir()
    source = package / "sample.py"
    source.write_text("from builtins import eval as run_code\n", encoding="utf-8")
    diff = """diff --git a/src/sample.py b/src/sample.py
--- a/src/sample.py
+++ b/src/sample.py
@@ -1 +1,2 @@
 from builtins import eval as run_code
+result = run_code(user_input)
"""
    assert _read_changed_python_sources(str(tmp_path), diff) == {
        "src/sample.py": "from builtins import eval as run_code\n"
    }


def test_read_changed_python_sources_rejects_symlink(tmp_path):
    outside = tmp_path.parent / "outside-security-source.py"
    outside.write_text("import builtins as core\n", encoding="utf-8")
    link = tmp_path / "linked.py"
    link.symlink_to(outside)
    diff = """diff --git a/linked.py b/linked.py
--- a/linked.py
+++ b/linked.py
@@ -1 +1,2 @@
 import builtins as core
+core.eval(user_input)
"""
    with pytest.raises(ReviewerError, match="symlink"):
        _read_changed_python_sources(str(tmp_path), diff)



def test_ast_security_scanner_detects_eval_assignment_alias():
    diff = """diff --git a/sample.py b/sample.py
--- a/sample.py
+++ b/sample.py
@@ -0,0 +1,2 @@
+run_code = eval
+result = run_code(user_input)
"""
    findings = _detect_static_security_findings(diff)
    assert len(findings) == 1
    assert findings[0]["line"] == 2
    assert findings[0]["severity"] == "critical"


def test_ast_security_scanner_detects_builtins_exec_assignment_alias():
    diff = """diff --git a/sample.py b/sample.py
--- a/sample.py
+++ b/sample.py
@@ -0,0 +1,3 @@
+import builtins as core
+execute = core.exec
+execute(untrusted_source)
"""
    findings = _detect_static_security_findings(diff)
    assert len(findings) == 1
    assert findings[0]["line"] == 3


def test_ast_security_scanner_detects_assignment_alias_from_unchanged_source():
    diff = """diff --git a/sample.py b/sample.py
--- a/sample.py
+++ b/sample.py
@@ -19,0 +20,1 @@
+run_code(user_input)
"""
    findings = _detect_static_security_findings(
        diff, {"sample.py": "run_code = eval\n"}
    )
    assert len(findings) == 1
    assert findings[0]["line"] == 20


def test_ast_security_scanner_ignores_assignment_to_ordinary_callable():
    diff = """diff --git a/sample.py b/sample.py
--- a/sample.py
+++ b/sample.py
@@ -0,0 +1,2 @@
+run_code = safe_function
+run_code(user_input)
"""
    assert _detect_static_security_findings(diff) == []



def test_ast_security_scanner_drops_eval_alias_after_safe_rebinding():
    diff = """diff --git a/sample.py b/sample.py
--- a/sample.py
+++ b/sample.py
@@ -0,0 +1,3 @@
+run_code = eval
+run_code = safe_function
+run_code(user_input)
"""
    assert _detect_static_security_findings(diff) == []


def test_ast_security_scanner_drops_builtins_module_alias_after_rebinding():
    diff = """diff --git a/sample.py b/sample.py
--- a/sample.py
+++ b/sample.py
@@ -0,0 +1,3 @@
+import builtins as core
+core = safe_module
+core.exec(untrusted_source)
"""
    assert _detect_static_security_findings(diff) == []


def test_ast_security_scanner_detects_alias_after_safe_rebinding_then_eval():
    diff = """diff --git a/sample.py b/sample.py
--- a/sample.py
+++ b/sample.py
@@ -0,0 +1,3 @@
+run_code = safe_function
+run_code = eval
+run_code(user_input)
"""
    findings = _detect_static_security_findings(diff)
    assert len(findings) == 1
    assert findings[0]["line"] == 3


def test_ast_security_scanner_uses_alias_state_at_each_call():
    diff = """diff --git a/sample.py b/sample.py
--- a/sample.py
+++ b/sample.py
@@ -0,0 +1,3 @@
+run_code(user_input)
+run_code = safe_function
+run_code(user_input)
"""
    assert _detect_static_security_findings(diff) == []


def test_ast_security_scanner_detects_call_before_alias_is_rebound_safe():
    diff = """diff --git a/sample.py b/sample.py
--- a/sample.py
+++ b/sample.py
@@ -0,0 +1,3 @@
+run_code = eval
+run_code(user_input)
+run_code = safe_function
"""
    findings = _detect_static_security_findings(diff)
    assert len(findings) == 1
    assert findings[0]["line"] == 2


def test_ast_security_scanner_does_not_use_future_alias_from_full_source():
    diff = """diff --git a/sample.py b/sample.py
--- a/sample.py
+++ b/sample.py
@@ -0,0 +1 @@
+run_code(user_input)
"""
    findings = _detect_static_security_findings(
        diff, {"sample.py": "run_code(user_input)\nrun_code = eval\n"}
    )
    assert findings == []


def test_ast_security_scanner_uses_prior_full_source_alias_before_changed_call():
    diff = """diff --git a/sample.py b/sample.py
--- a/sample.py
+++ b/sample.py
@@ -1,2 +1,2 @@
 from builtins import eval as run_code
-result = 0
+result = run_code(user_input)
"""
    findings = _detect_static_security_findings(
        diff,
        {"sample.py": "from builtins import eval as run_code\nresult = run_code(user_input)\n"},
    )
    assert len(findings) == 1
    assert findings[0]["line"] == 2


def test_ast_security_scanner_respects_safe_rebinding_in_full_source():
    diff = """diff --git a/sample.py b/sample.py
--- a/sample.py
+++ b/sample.py
@@ -1,3 +1,3 @@
 import builtins as core
-core.exec(user_input)
+core = safe_module
+core.exec(user_input)
"""
    findings = _detect_static_security_findings(
        diff,
        {"sample.py": "import builtins as core\ncore = safe_module\ncore.exec(user_input)\n"},
    )
    assert findings == []


def test_ast_security_scanner_detects_eval_alias_inside_if_branch():
    diff = """diff --git a/sample.py b/sample.py
--- a/sample.py
+++ b/sample.py
@@ -0,0 +1,3 @@
+if condition:
+    run_code = eval
+    run_code(user_input)
"""
    findings = _detect_static_security_findings(diff)
    assert len(findings) == 1
    assert findings[0]["line"] == 3


def test_ast_security_scanner_tracks_possible_alias_after_if_branch():
    diff = """diff --git a/sample.py b/sample.py
--- a/sample.py
+++ b/sample.py
@@ -0,0 +1,5 @@
+if condition:
+    run_code = eval
+else:
+    run_code = safe_function
+run_code(user_input)
"""
    findings = _detect_static_security_findings(diff)
    assert len(findings) == 1
    assert findings[0]["line"] == 5


def test_ast_security_scanner_does_not_flag_safe_alias_inside_if_branch():
    diff = """diff --git a/sample.py b/sample.py
--- a/sample.py
+++ b/sample.py
@@ -0,0 +1,3 @@
+if condition:
+    run_code = safe_function
+    run_code(user_input)
"""
    assert _detect_static_security_findings(diff) == []



def test_ast_security_scanner_detects_eval_alias_inside_for_loop():
    diff = """diff --git a/sample.py b/sample.py
--- a/sample.py
+++ b/sample.py
@@ -0,0 +1,3 @@
+for item in items:
+    run_code = eval
+    run_code(user_input)
"""
    findings = _detect_static_security_findings(diff)
    assert len(findings) == 1
    assert findings[0]["line"] == 3


def test_ast_security_scanner_tracks_possible_alias_after_while_loop():
    diff = """diff --git a/sample.py b/sample.py
--- a/sample.py
+++ b/sample.py
@@ -0,0 +1,3 @@
+while condition:
+    run_code = eval
+run_code(user_input)
"""
    findings = _detect_static_security_findings(diff)
    assert len(findings) == 1
    assert findings[0]["line"] == 3


def test_ast_security_scanner_detects_eval_alias_inside_with_block():
    diff = """diff --git a/sample.py b/sample.py
--- a/sample.py
+++ b/sample.py
@@ -0,0 +1,3 @@
+with manager:
+    run_code = eval
+    run_code(user_input)
"""
    findings = _detect_static_security_findings(diff)
    assert len(findings) == 1
    assert findings[0]["line"] == 3


def test_ast_security_scanner_detects_eval_alias_inside_try_block():
    diff = """diff --git a/sample.py b/sample.py
--- a/sample.py
+++ b/sample.py
@@ -0,0 +1,3 @@
+try:
+    run_code = eval
+    run_code(user_input)
"""
    findings = _detect_static_security_findings(diff)
    assert len(findings) == 1
    assert findings[0]["line"] == 3


def test_ast_security_scanner_detects_eval_alias_inside_match_case():
    diff = """diff --git a/sample.py b/sample.py
--- a/sample.py
+++ b/sample.py
@@ -0,0 +1,3 @@
+match value:
+    case 1:
+        eval(user_input)
"""
    findings = _detect_static_security_findings(diff)
    assert len(findings) == 1
    assert findings[0]["line"] == 3


def test_ast_security_scanner_keeps_safe_aliases_in_loop_body_unflagged():
    diff = """diff --git a/sample.py b/sample.py
--- a/sample.py
+++ b/sample.py
@@ -0,0 +1,3 @@
+for item in items:
+    run_code = safe_function
+    run_code(user_input)
"""
    assert _detect_static_security_findings(diff) == []



def test_ast_security_scanner_drops_alias_shadowed_by_loop_target():
    diff = """diff --git a/sample.py b/sample.py
--- a/sample.py
+++ b/sample.py
@@ -0,0 +1,3 @@
+run_code = eval
+for run_code in safe_functions:
+    run_code(user_input)
"""
    assert _detect_static_security_findings(diff) == []


def test_ast_security_scanner_drops_alias_shadowed_by_with_target():
    diff = """diff --git a/sample.py b/sample.py
--- a/sample.py
+++ b/sample.py
@@ -0,0 +1,3 @@
+run_code = eval
+with manager as run_code:
+    run_code(user_input)
"""
    assert _detect_static_security_findings(diff) == []



def test_ast_security_scanner_detects_direct_eval_inside_nested_function():
    diff = """diff --git a/sample.py b/sample.py
--- a/sample.py
+++ b/sample.py
@@ -0,0 +1,3 @@
+def calculate(value):
+    return eval(value)
+result = calculate(user_input)
"""
    findings = _detect_static_security_findings(diff)
    assert len(findings) == 1
    assert findings[0]["line"] == 2


def test_ast_security_scanner_detects_eval_alias_inside_function_scope():
    diff = """diff --git a/sample.py b/sample.py
--- a/sample.py
+++ b/sample.py
@@ -0,0 +1,3 @@
+def calculate(value):
+    run_code = eval
+    return run_code(value)
"""
    findings = _detect_static_security_findings(diff)
    assert len(findings) == 1
    assert findings[0]["line"] == 3


def test_ast_security_scanner_does_not_flag_eval_parameter_shadowing_builtin():
    diff = """diff --git a/sample.py b/sample.py
--- a/sample.py
+++ b/sample.py
@@ -0,0 +1,2 @@
+def calculate(eval):
+    return eval(user_input)
"""
    assert _detect_static_security_findings(diff) == []


def test_ast_security_scanner_does_not_flag_function_local_eval_rebinding():
    diff = """diff --git a/sample.py b/sample.py
--- a/sample.py
+++ b/sample.py
@@ -0,0 +1,3 @@
+def calculate(value):
+    eval = safe_function
+    return eval(value)
"""
    assert _detect_static_security_findings(diff) == []


def test_ast_security_scanner_does_not_leak_function_aliases_to_module_scope():
    diff = """diff --git a/sample.py b/sample.py
--- a/sample.py
+++ b/sample.py
@@ -0,0 +1,4 @@
+def calculate(value):
+    run_code = eval
+    run_code(value)
+run_code(user_input)
"""
    findings = _detect_static_security_findings(diff)
    assert len(findings) == 1
    assert findings[0]["line"] == 3


def test_ast_security_scanner_inherits_module_aliases_inside_function_scope():
    diff = """diff --git a/sample.py b/sample.py
--- a/sample.py
+++ b/sample.py
@@ -0,0 +1,3 @@
+run_code = eval
+def calculate(value):
+    return run_code(value)
"""
    findings = _detect_static_security_findings(diff)
    assert len(findings) == 1
    assert findings[0]["line"] == 3


def test_ast_security_scanner_does_not_use_class_attributes_as_method_globals():
    diff = """diff --git a/sample.py b/sample.py
--- a/sample.py
+++ b/sample.py
@@ -0,0 +1,4 @@
+class Calculator:
+    run_code = safe_function
+    def calculate(self, value):
+        return run_code(value)
"""
    assert _detect_static_security_findings(diff) == []
