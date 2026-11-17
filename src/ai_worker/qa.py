"""Deterministic, serializable QA check results; this module executes no commands."""
from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass
from pathlib import PurePosixPath
from typing import Any


QA_SCHEMA_VERSION = 1
CHECK_STATUSES = frozenset({"passed", "failed", "skipped", "unavailable", "not_run"})


class QAContractError(ValueError):
    """Raised when a QA result is inconsistent or malformed."""


def _is_finite_number(value: int | float) -> bool:
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _safe_relative_path(value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > 500:
        raise QAContractError("evidence_path must be a non-empty relative path")
    if value.startswith("/") or "\\" in value or "\x00" in value:
        raise QAContractError("evidence_path must use safe relative POSIX syntax")
    parts = value.split("/")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in parts)
        or ".git" in path.parts
    ):
        raise QAContractError("evidence_path contains an unsafe path component")
    return path.as_posix()


@dataclass(slots=True)
class QACheck:
    check_id: str
    name: str
    status: str
    summary: str
    required: bool = True
    command: list[str] | None = None
    exit_code: int | None = None
    duration_seconds: float | None = None
    evidence_path: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.check_id, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}", self.check_id):
            raise QAContractError("check_id has an invalid format")
        if not isinstance(self.name, str) or not self.name.strip() or len(self.name) > 160:
            raise QAContractError("name must be non-empty text up to 160 characters")
        if not isinstance(self.status, str) or self.status not in CHECK_STATUSES:
            raise QAContractError("check status is not supported")
        if not isinstance(self.summary, str) or not self.summary.strip() or len(self.summary) > 2000 or "\x00" in self.summary:
            raise QAContractError("summary must be non-empty text up to 2000 characters")
        if not isinstance(self.required, bool):
            raise QAContractError("required must be a boolean")
        if self.command is not None:
            if (
                not isinstance(self.command, list)
                or not self.command
                or len(self.command) > 20
                or any(not isinstance(part, str) or not part or len(part) > 500 or "\x00" in part for part in self.command)
            ):
                raise QAContractError("command must be a bounded argv list or null")
        if self.exit_code is not None and (
            isinstance(self.exit_code, bool) or not isinstance(self.exit_code, int)
        ):
            raise QAContractError("exit_code must be an integer or null")
        if self.status == "passed" and self.exit_code != 0:
            raise QAContractError("a passed check requires exit_code 0")
        if self.status == "failed" and (self.exit_code is None or self.exit_code == 0):
            raise QAContractError("a failed check requires a non-zero exit_code")
        if self.status in {"skipped", "unavailable", "not_run"} and self.exit_code is not None:
            raise QAContractError(f"a {self.status} check must not have an exit_code")
        if self.duration_seconds is not None and (
            isinstance(self.duration_seconds, bool)
            or not isinstance(self.duration_seconds, (int, float))
            or not _is_finite_number(self.duration_seconds)
            or self.duration_seconds < 0
        ):
            raise QAContractError("duration_seconds must be finite and non-negative")
        if self.status in {"unavailable", "not_run"} and self.duration_seconds is not None:
            raise QAContractError(f"a {self.status} check must not have a duration")
        if self.evidence_path is not None:
            self.evidence_path = _safe_relative_path(self.evidence_path)


@dataclass(slots=True)
class QAResult:
    checks: list[QACheck]
    schema_version: int = QA_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or not isinstance(self.schema_version, int) or self.schema_version != QA_SCHEMA_VERSION:
            raise QAContractError("unsupported QA schema version")
        if not isinstance(self.checks, list) or len(self.checks) > 100:
            raise QAContractError("checks must be a list of at most 100 items")
        if any(not isinstance(item, QACheck) for item in self.checks):
            raise QAContractError("every check must be a validated QACheck")
        identifiers = [item.check_id for item in self.checks]
        if len(identifiers) != len(set(identifiers)):
            raise QAContractError("check_id values must be unique")

    @property
    def overall_status(self) -> str:
        required = [check for check in self.checks if check.required]
        if not required:
            return "incomplete"
        if any(check.status == "failed" for check in required):
            return "failed"
        if any(check.status != "passed" for check in required):
            return "incomplete"
        return "passed"

    @property
    def warning_check_ids(self) -> list[str]:
        return [
            check.check_id for check in self.checks
            if not check.required and check.status != "passed"
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "overall_status": self.overall_status,
            "checks": [asdict(item) for item in self.checks],
        }

    @classmethod
    def from_dict(cls, payload: object) -> "QAResult":
        if not isinstance(payload, dict) or set(payload) != {
            "schema_version", "overall_status", "checks"
        }:
            raise QAContractError("QA result has missing or unexpected fields")
        checks_data = payload["checks"]
        if not isinstance(checks_data, list) or len(checks_data) > 100:
            raise QAContractError("checks must be a list of at most 100 items")
        check_fields = {
            "check_id", "name", "status", "summary", "required", "command",
            "exit_code", "duration_seconds", "evidence_path",
        }
        checks: list[QACheck] = []
        for item in checks_data:
            if not isinstance(item, dict) or set(item) != check_fields:
                raise QAContractError("a check has missing or unexpected fields")
            try:
                checks.append(QACheck(**item))
            except TypeError as exc:
                raise QAContractError("a check has invalid field types") from exc
        try:
            result = cls(checks=checks, schema_version=payload["schema_version"])
        except TypeError as exc:
            raise QAContractError("QA result has invalid field types") from exc
        if payload["overall_status"] != result.overall_status:
            raise QAContractError("overall_status does not match the individual check results")
        return result
