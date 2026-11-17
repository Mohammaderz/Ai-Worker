import pytest

from ai_worker.qa import QAContractError, QACheck, QAResult


def check(check_id="pytest", status="passed", **changes):
    value = {
        "check_id": check_id,
        "name": "Python test suite",
        "status": status,
        "summary": "pytest completed",
        "required": True,
        "command": ["python", "-m", "pytest", "-q"],
        "exit_code": 0 if status == "passed" else None,
        "duration_seconds": 1.25 if status in {"passed", "failed", "skipped"} else None,
        "evidence_path": "logs/pytest.txt",
    }
    if status == "failed":
        value["exit_code"] = 1
    value.update(changes)
    return QACheck(**value)


def test_all_required_checks_pass_and_round_trip():
    result = QAResult([check(), check("compileall", summary="compileall completed")])
    assert result.overall_status == "passed"
    assert QAResult.from_dict(result.to_dict()).to_dict() == result.to_dict()


def test_required_failure_makes_overall_failed():
    result = QAResult([check(), check("lint", status="failed", summary="ruff found errors", exit_code=2)])
    assert result.overall_status == "failed"


@pytest.mark.parametrize("status", ["skipped", "unavailable", "not_run"])
def test_required_non_passed_check_makes_result_incomplete(status):
    result = QAResult([check("pytest", status=status)])
    assert result.overall_status == "incomplete"


def test_optional_failed_check_is_visible_without_blocking_required_passes():
    result = QAResult([
        check(),
        check("typecheck", status="failed", required=False, summary="mypy is not configured", exit_code=1),
    ])
    assert result.overall_status == "passed"
    assert result.warning_check_ids == ["typecheck"]


def test_no_required_checks_is_incomplete_not_passed():
    result = QAResult([check(required=False)])
    assert result.overall_status == "incomplete"


def test_rejects_exit_code_inconsistent_with_status():
    with pytest.raises(QAContractError, match="passed check requires"):
        check(exit_code=1)
    with pytest.raises(QAContractError, match="failed check requires"):
        check(status="failed", exit_code=0)


def test_rejects_exit_code_for_not_run_checks():
    with pytest.raises(QAContractError, match="must not have an exit_code"):
        check(status="not_run", exit_code=0)


def test_rejects_non_finite_or_negative_duration():
    with pytest.raises(QAContractError, match="duration_seconds"):
        check(duration_seconds=float("nan"))
    with pytest.raises(QAContractError, match="duration_seconds"):
        check(duration_seconds=-1)


@pytest.mark.parametrize("path", ["../private.log", "/tmp/log.txt", ".git/config", "logs\\secret.txt"])
def test_rejects_unsafe_evidence_paths(path):
    with pytest.raises(QAContractError, match="evidence_path"):
        check(evidence_path=path)


def test_rejects_duplicate_ids_and_tampered_overall_status():
    with pytest.raises(QAContractError, match="must be unique"):
        QAResult([check(), check()])
    payload = QAResult([check()]).to_dict()
    payload["overall_status"] = "incomplete"
    with pytest.raises(QAContractError, match="does not match"):
        QAResult.from_dict(payload)


def test_rejects_unknown_check_status():
    with pytest.raises(QAContractError, match="not supported"):
        check(status="success")
