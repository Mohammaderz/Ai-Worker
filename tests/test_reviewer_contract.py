import json

import pytest

from ai_worker.reviewer import ReviewContractError, parse_review_response


def finding(**changes):
    value = {
        "finding_id": "R-1",
        "severity": "medium",
        "title": "Missing retry assertion",
        "description": "The changed branch is not covered by a regression test.",
        "file_path": "tests/test_client.py",
        "line_start": 10,
        "line_end": 12,
        "evidence": "The diff changes retry behavior but adds no assertion for the second attempt.",
        "acceptance_criterion": "Retry behavior is covered by tests.",
        "recommendation": "Add a test that verifies the retry count and backoff.",
        "confidence": 0.9,
        "verified": True,
    }
    value.update(changes)
    return value


def response(decision="request_changes", findings=None, **changes):
    value = {
        "schema_version": 1,
        "decision": decision,
        "summary": "The patch needs one test improvement.",
        "findings": [finding()] if findings is None and decision == "request_changes" else (findings or []),
    }
    value.update(changes)
    return value


def test_parser_accepts_valid_review_and_round_trips():
    result = parse_review_response(json.dumps(response()))
    assert result.decision == "request_changes"
    assert result.findings[0].file_path == "tests/test_client.py"
    assert parse_review_response(result.to_dict()).to_dict() == result.to_dict()


def test_approve_is_rejected_when_critical_or_high_finding_exists():
    with pytest.raises(ReviewContractError, match="approve is forbidden"):
        parse_review_response(response(
            decision="approve",
            findings=[finding(severity="high")],
        ))


def test_request_changes_requires_at_least_one_finding():
    with pytest.raises(ReviewContractError, match="requires at least one finding"):
        parse_review_response(response(decision="request_changes", findings=[]))


def test_inconclusive_without_findings_is_valid():
    result = parse_review_response(response(decision="inconclusive", findings=[]))
    assert result.decision == "inconclusive"
    assert result.findings == []


@pytest.mark.parametrize("path", ["../secret.txt", "/etc/passwd", ".git/config", "src\\main.py", "src//main.py"])
def test_rejects_unsafe_finding_paths(path):
    with pytest.raises(ReviewContractError):
        parse_review_response(response(findings=[finding(file_path=path)]))


def test_rejects_line_numbers_without_a_file_path():
    with pytest.raises(ReviewContractError, match="line numbers require file_path"):
        parse_review_response(response(findings=[finding(file_path=None)]))


def test_rejects_duplicate_finding_ids():
    with pytest.raises(ReviewContractError, match="must be unique"):
        parse_review_response(response(findings=[finding(), finding()]))


@pytest.mark.parametrize("confidence", [True, float("nan"), float("inf"), -0.1, 1.1])
def test_rejects_invalid_confidence(confidence):
    with pytest.raises(ReviewContractError, match="confidence"):
        parse_review_response(response(findings=[finding(confidence=confidence)]))


def test_rejects_unknown_fields_and_oversized_json():
    extra = response()
    extra["chain_of_thought"] = "must not be accepted"
    with pytest.raises(ReviewContractError, match="unexpected fields"):
        parse_review_response(extra)
    with pytest.raises(ReviewContractError, match="100 KiB"):
        parse_review_response(" " * 100_001)


def test_rejects_invalid_json_and_unsupported_schema_version():
    with pytest.raises(ReviewContractError, match="valid JSON"):
        parse_review_response("{")
    with pytest.raises(ReviewContractError, match="schema version"):
        parse_review_response(response(schema_version=2))
