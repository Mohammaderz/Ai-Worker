"""Strict, fail-closed contract for independent patch-review results.

This module validates reviewer output only. It does not call a model or approve
external submissions; callers must treat a validation error as a blocked review.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass
from pathlib import PurePosixPath
from typing import Any


REVIEW_SCHEMA_VERSION = 1
MAX_REVIEW_BYTES = 100_000
MAX_FINDINGS = 50
DECISIONS = frozenset({"approve", "request_changes", "inconclusive"})
SEVERITIES = frozenset({"critical", "high", "medium", "low", "info"})
BLOCKING_SEVERITIES = frozenset({"critical", "high"})

REVIEW_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "schema_version": {"type": "integer", "const": REVIEW_SCHEMA_VERSION},
        "decision": {"type": "string", "enum": sorted(DECISIONS)},
        "summary": {"type": "string", "minLength": 1, "maxLength": 2000},
        "findings": {
            "type": "array",
            "maxItems": MAX_FINDINGS,
            "items": {
                "type": "object",
                "properties": {
                    "finding_id": {"type": "string", "minLength": 1, "maxLength": 64},
                    "severity": {"type": "string", "enum": sorted(SEVERITIES)},
                    "title": {"type": "string", "minLength": 1, "maxLength": 200},
                    "description": {"type": "string", "minLength": 1, "maxLength": 2000},
                    "file_path": {"type": ["string", "null"], "maxLength": 500},
                    "line_start": {"type": ["integer", "null"], "minimum": 1},
                    "line_end": {"type": ["integer", "null"], "minimum": 1},
                    "evidence": {"type": "string", "minLength": 1, "maxLength": 2000},
                    "acceptance_criterion": {"type": ["string", "null"], "maxLength": 500},
                    "recommendation": {"type": "string", "minLength": 1, "maxLength": 1000},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "verified": {"type": "boolean"},
                },
                "required": [
                    "finding_id", "severity", "title", "description", "file_path",
                    "line_start", "line_end", "evidence", "acceptance_criterion",
                    "recommendation", "confidence", "verified",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["schema_version", "decision", "summary", "findings"],
    "additionalProperties": False,
}


class ReviewContractError(ValueError):
    """Raised when reviewer output is malformed or unsafe to rely on."""


def _text(value: object, field: str, limit: int, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or len(value) > limit or "\x00" in value:
        raise ReviewContractError(f"{field} must be text up to {limit} characters")
    if not allow_empty and not value.strip():
        raise ReviewContractError(f"{field} must not be empty")
    return value


def _safe_relative_path(value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > 500:
        raise ReviewContractError("file_path must be a non-empty relative path")
    if value.startswith("/") or "\\" in value or "\x00" in value:
        raise ReviewContractError("file_path must use safe relative POSIX syntax")
    parts = value.split("/")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in parts)
        or ".git" in path.parts
    ):
        raise ReviewContractError("file_path contains an unsafe path component")
    return path.as_posix()


def _is_finite_number(value: int | float) -> bool:
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _optional_line(value: object, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ReviewContractError(f"{field} must be a positive integer or null")
    return value


@dataclass(slots=True)
class ReviewFinding:
    finding_id: str
    severity: str
    title: str
    description: str
    evidence: str
    recommendation: str
    confidence: float
    verified: bool
    file_path: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    acceptance_criterion: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.finding_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", self.finding_id):
            raise ReviewContractError("finding_id has an invalid format")
        if not isinstance(self.severity, str) or self.severity not in SEVERITIES:
            raise ReviewContractError("finding severity is not supported")
        _text(self.title, "title", 200)
        _text(self.description, "description", 2000)
        _text(self.evidence, "evidence", 2000)
        _text(self.recommendation, "recommendation", 1000)
        if self.file_path is not None:
            self.file_path = _safe_relative_path(self.file_path)
        self.line_start = _optional_line(self.line_start, "line_start")
        self.line_end = _optional_line(self.line_end, "line_end")
        if self.line_end is not None and self.line_start is None:
            raise ReviewContractError("line_end requires line_start")
        if self.line_start is not None and self.file_path is None:
            raise ReviewContractError("line numbers require file_path")
        if self.line_start is not None and self.line_end is not None and self.line_end < self.line_start:
            raise ReviewContractError("line_end must not precede line_start")
        if self.acceptance_criterion is not None:
            _text(self.acceptance_criterion, "acceptance_criterion", 500)
        if (
            isinstance(self.confidence, bool)
            or not isinstance(self.confidence, (int, float))
            or not _is_finite_number(self.confidence)
            or not 0 <= self.confidence <= 1
        ):
            raise ReviewContractError("confidence must be a finite number from 0 to 1")
        if not isinstance(self.verified, bool):
            raise ReviewContractError("verified must be a boolean")


@dataclass(slots=True)
class ReviewResult:
    decision: str
    summary: str
    findings: list[ReviewFinding]
    schema_version: int = REVIEW_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or not isinstance(self.schema_version, int) or self.schema_version != REVIEW_SCHEMA_VERSION:
            raise ReviewContractError("unsupported reviewer schema version")
        if not isinstance(self.decision, str) or self.decision not in DECISIONS:
            raise ReviewContractError("review decision is not supported")
        _text(self.summary, "summary", 2000)
        if not isinstance(self.findings, list) or len(self.findings) > MAX_FINDINGS:
            raise ReviewContractError(f"findings must be a list of at most {MAX_FINDINGS} items")
        if any(not isinstance(item, ReviewFinding) for item in self.findings):
            raise ReviewContractError("every finding must be a validated ReviewFinding")
        identifiers = [item.finding_id for item in self.findings]
        if len(identifiers) != len(set(identifiers)):
            raise ReviewContractError("finding_id values must be unique")
        if self.decision == "request_changes" and not self.findings:
            raise ReviewContractError("request_changes requires at least one finding")
        if self.decision == "approve" and any(
            item.severity in BLOCKING_SEVERITIES for item in self.findings
        ):
            raise ReviewContractError("approve is forbidden while critical or high findings exist")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "decision": self.decision,
            "summary": self.summary,
            "findings": [asdict(item) for item in self.findings],
        }


def parse_review_response(payload: object) -> ReviewResult:
    """Parse and validate JSON or a decoded object; never fail open."""
    if isinstance(payload, str):
        if len(payload.encode("utf-8")) > MAX_REVIEW_BYTES:
            raise ReviewContractError("review response exceeds the 100 KiB limit")
        try:
            payload = json.loads(payload)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ReviewContractError("review response is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ReviewContractError("review response must be a JSON object")
    if set(payload) != {"schema_version", "decision", "summary", "findings"}:
        raise ReviewContractError("review response has missing or unexpected fields")
    findings_data = payload["findings"]
    if not isinstance(findings_data, list) or len(findings_data) > MAX_FINDINGS:
        raise ReviewContractError(f"findings must be a list of at most {MAX_FINDINGS} items")

    finding_fields = {
        "finding_id", "severity", "title", "description", "file_path",
        "line_start", "line_end", "evidence", "acceptance_criterion",
        "recommendation", "confidence", "verified",
    }
    findings: list[ReviewFinding] = []
    for item in findings_data:
        if not isinstance(item, dict) or set(item) != finding_fields:
            raise ReviewContractError("a finding has missing or unexpected fields")
        try:
            findings.append(ReviewFinding(**item))
        except TypeError as exc:
            raise ReviewContractError("a finding has invalid field types") from exc
    try:
        return ReviewResult(
            schema_version=payload["schema_version"],
            decision=payload["decision"],
            summary=payload["summary"],
            findings=findings,
        )
    except TypeError as exc:
        raise ReviewContractError("review response has invalid field types") from exc
