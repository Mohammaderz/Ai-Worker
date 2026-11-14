import pytest

from ai_worker.models import Gig
from ai_worker.storage import connect, outcome_summary, record_outcome, upsert_gigs


def seed(db):
    upsert_gigs(db, [
        Gig(
            id="board:task-1",
            title="Fix Python bug",
            url="https://github.com/acme/project/issues/1",
            currency="USD",
            reward_amount=25,
            raw={},
        )
    ])


def test_only_actual_paid_amounts_count_as_earnings(tmp_path):
    db = connect(tmp_path / "ledger.sqlite3")
    seed(db)

    record_outcome(db, "board:task-1", "claimed")
    record_outcome(db, "board:task-1", "in_progress", actual_hours=1.5)
    record_outcome(db, "board:task-1", "submitted")
    before_payment = outcome_summary(db)
    assert before_payment["gross_received"] == 0
    assert before_payment["net_received"] == 0

    record_outcome(db, "board:task-1", "accepted")
    record_outcome(
        db, "board:task-1", "paid",
        gross_received=25, fees=1.5, actual_hours=2.0,
    )
    summary = outcome_summary(db)
    db.close()

    assert summary["paid_tasks"] == 1
    assert summary["gross_received"] == 25
    assert summary["fees"] == 1.5
    assert summary["net_received"] == 23.5
    assert summary["net_received_per_paid_hour"] == 11.75
    assert summary["acceptance_rate"] == 1.0
    assert summary["payout_latency_sample_size"] == 1
    assert summary["average_payout_latency_days"] is not None
    assert summary["median_payout_latency_days"] is not None


def test_outcome_requires_known_gig_and_valid_transition(tmp_path):
    db = connect(tmp_path / "ledger.sqlite3")
    seed(db)

    with pytest.raises(ValueError, match="does not exist"):
        record_outcome(db, "missing", "claimed")

    record_outcome(db, "board:task-1", "claimed")
    with pytest.raises(ValueError, match="Invalid outcome transition"):
        record_outcome(db, "board:task-1", "paid", gross_received=25)

    db.close()


def test_paid_status_requires_actual_gross_amount(tmp_path):
    db = connect(tmp_path / "ledger.sqlite3")
    seed(db)

    with pytest.raises(ValueError, match="actual gross amount"):
        record_outcome(db, "board:task-1", "paid")

    db.close()


def test_outcome_rejects_non_finite_amounts(tmp_path):
    db = connect(tmp_path / "ledger.sqlite3")
    seed(db)

    with pytest.raises(ValueError, match="finite"):
        record_outcome(db, "board:task-1", "claimed", actual_hours=float("nan"))

    db.close()



@pytest.mark.parametrize("initial_status", ["in_progress", "submitted", "accepted", "rejected", "paid"])
def test_outcome_must_start_at_claimed(tmp_path, initial_status):
    db = connect(tmp_path / "ledger.sqlite3")
    seed(db)

    with pytest.raises(ValueError, match="first outcome status must be claimed"):
        record_outcome(
            db, "board:task-1", initial_status,
            gross_received=25 if initial_status == "paid" else None,
        )

    row = db.execute(
        "SELECT status FROM task_outcomes WHERE gig_id=?",
        ("board:task-1",),
    ).fetchone()
    assert row is None
    db.close()


def test_pre_submission_rejection_does_not_count_as_submitted(tmp_path):
    db = connect(tmp_path / "ledger.sqlite3")
    seed(db)
    upsert_gigs(db, [
        Gig(
            id="board:task-2",
            title="Fix another Python bug",
            url="https://github.com/acme/project/issues/2",
            currency="USD",
            reward_amount=30,
            raw={},
        )
    ])

    record_outcome(db, "board:task-1", "claimed")
    record_outcome(db, "board:task-1", "rejected")
    record_outcome(db, "board:task-2", "claimed")
    record_outcome(db, "board:task-2", "in_progress")
    record_outcome(db, "board:task-2", "submitted")

    summary = outcome_summary(db)
    assert summary["by_status"]["rejected"] == 1
    assert summary["submitted_or_later"] == 1
    assert summary["acceptance_rate"] == 0.0
    db.close()


def test_post_submission_rejection_counts_in_acceptance_rate(tmp_path):
    db = connect(tmp_path / "ledger.sqlite3")
    seed(db)
    upsert_gigs(db, [
        Gig(
            id="board:task-2",
            title="Fix another Python bug",
            url="https://github.com/acme/project/issues/2",
            currency="USD",
            reward_amount=30,
            raw={},
        )
    ])

    record_outcome(db, "board:task-1", "claimed")
    record_outcome(db, "board:task-1", "in_progress")
    record_outcome(db, "board:task-1", "submitted")
    record_outcome(db, "board:task-1", "rejected")

    record_outcome(db, "board:task-2", "claimed")
    record_outcome(db, "board:task-2", "in_progress")
    record_outcome(db, "board:task-2", "submitted")
    record_outcome(db, "board:task-2", "accepted")

    summary = outcome_summary(db)
    assert summary["submitted_or_later"] == 2
    assert summary["accepted_or_paid"] == 1
    assert summary["acceptance_rate"] == 0.5
    db.close()


def test_source_economics_uses_only_realized_outcomes_and_requires_sample_size(tmp_path):
    db = connect(tmp_path / "ledger.sqlite3")
    upsert_gigs(db, [
        Gig(
            id=f"algora:{number}",
            title=f"Fix Python issue {number}",
            url=f"https://github.com/acme/project/issues/{number}",
            source="algora",
            currency="USD",
            reward_amount=25,
            raw={},
        )
        for number in (1, 2, 3)
    ])
    for gig_id, gross, fees, hours in (
        ("algora:1", 25, 1, 2),
        ("algora:2", 40, 2, 4),
    ):
        record_outcome(db, gig_id, "claimed")
        record_outcome(db, gig_id, "in_progress", actual_hours=hours)
        record_outcome(db, gig_id, "submitted")
        record_outcome(db, gig_id, "accepted")
        record_outcome(db, gig_id, "paid", gross_received=gross, fees=fees)
    record_outcome(db, "algora:3", "claimed")
    record_outcome(db, "algora:3", "in_progress", actual_hours=1)
    record_outcome(db, "algora:3", "submitted")
    record_outcome(db, "algora:3", "rejected")

    summary = outcome_summary(db)
    source = next(item for item in summary["by_source"] if item["source"] == "algora")
    db.close()

    assert source["tracked_tasks"] == 3
    assert source["submitted_tasks"] == 3
    assert source["accepted_tasks"] == 2
    assert source["paid_tasks"] == 2
    assert source["acceptance_rate"] == pytest.approx(2 / 3, abs=0.001)
    assert source["gross_received"] == 65
    assert source["fees"] == 3
    assert source["net_received"] == 62
    assert source["paid_task_hours"] == 6
    assert source["net_per_paid_hour"] == pytest.approx(62 / 6, abs=0.01)
    assert source["confidence"] == "usable"
