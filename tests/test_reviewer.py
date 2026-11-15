import json

import pytest

from ai_worker.reviewer import (
    _detect_static_security_findings,
    ReviewerError,
    _detect_static_security_findings,
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
