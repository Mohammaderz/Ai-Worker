from ai_worker.models import Gig
from ai_worker.storage import (
    connect, upsert_gigs, create_task_run, advance_task_run,
    list_task_runs, get_task_run, list_task_run_events,
)


def test_ledger_persists_payment_state_and_rail(tmp_path):
    db = connect(tmp_path / "ledger.sqlite3")
    gig = Gig(
        id="escrowed-1",
        title="Fix Python bug",
        url="https://example.com/task",
        source="algora",
        currency="USD",
        reward_amount=25,
        payout_grade="B",
        payment_state="escrowed",
        payment_rail="stripe",
        acceptance_type="human-review",
        raw={"_jobbi": {"payment_state": "escrowed"}},
    )
    upsert_gigs(db, [gig])
    row = db.execute(
        "SELECT payment_state, payment_rail, acceptance_type FROM gigs WHERE id=?",
        (gig.id,),
    ).fetchone()
    db.close()
    assert row == ("escrowed", "stripe", "human-review")


def test_ledger_migrates_existing_v01_database(tmp_path):
    import sqlite3

    path = tmp_path / "old.sqlite3"
    old = sqlite3.connect(path)
    old.execute("""CREATE TABLE gigs (
        id TEXT PRIMARY KEY, title TEXT NOT NULL, url TEXT NOT NULL,
        source TEXT, currency TEXT, reward_amount REAL, payout_grade TEXT,
        first_seen TEXT DEFAULT CURRENT_TIMESTAMP, last_seen TEXT DEFAULT CURRENT_TIMESTAMP,
        raw_json TEXT NOT NULL)""")
    old.commit()
    old.close()

    db = connect(path)
    columns = {row[1] for row in db.execute("PRAGMA table_info(gigs)")}
    db.close()
    assert {"payment_state", "payment_rail", "acceptance_type"}.issubset(columns)



def test_task_run_history_lists_filters_and_reads_events(tmp_path):
    db = connect(tmp_path / "runs.sqlite3")
    create_task_run(db, "run-success", "https://github.com/acme/app/issues/1")
    advance_task_run(
        db,
        "run-success",
        "complete",
        status="completed",
        repository="acme/app",
        issue_number=1,
        result_status="ready_for_human_review",
        finished=True,
    )
    create_task_run(db, "run-failed", "https://github.com/acme/app/issues/2")
    advance_task_run(
        db,
        "run-failed",
        "failed",
        status="failed",
        error="inspection failed",
        finished=True,
    )

    runs = list_task_runs(db, limit=10)
    failed = list_task_runs(db, status="failed")
    run = get_task_run(db, "run-success")
    events = list_task_run_events(db, "run-success")
    db.close()

    assert {item["run_id"] for item in runs} == {"run-success", "run-failed"}
    assert [item["run_id"] for item in failed] == ["run-failed"]
    assert run["repository"] == "acme/app"
    assert run["issue_number"] == 1
    assert run["status"] == "completed"
    assert run["result_status"] == "ready_for_human_review"
    assert [event["stage"] for event in events] == ["inspect", "complete"]


def test_task_run_history_validates_filters_and_limits(tmp_path):
    import pytest

    db = connect(tmp_path / "runs.sqlite3")
    with pytest.raises(ValueError):
        list_task_runs(db, limit=0)
    with pytest.raises(ValueError):
        list_task_runs(db, status="unknown")
    db.close()



def test_task_run_history_filters_stale_running_tasks(tmp_path):
    from datetime import datetime, timedelta, timezone

    db = connect(tmp_path / "stale-runs.sqlite3")

    create_task_run(db, "run-stale", "https://github.com/acme/app/issues/10")
    create_task_run(db, "run-fresh", "https://github.com/acme/app/issues/11")

    old_time = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    db.execute(
        "UPDATE task_runs SET updated_at = ? WHERE run_id = ?",
        (old_time, "run-stale"),
    )
    db.commit()

    stale = list_task_runs(db, stale_minutes=30)
    all_running = list_task_runs(db, status="running")
    db.close()

    assert [run["run_id"] for run in stale] == ["run-stale"]
    assert {run["run_id"] for run in all_running} == {"run-stale", "run-fresh"}


def test_task_run_history_validates_stale_minutes(tmp_path):
    import pytest

    db = connect(tmp_path / "stale-validation.sqlite3")
    with pytest.raises(ValueError):
        list_task_runs(db, stale_minutes=0)
    with pytest.raises(ValueError):
        list_task_runs(db, status="failed", stale_minutes=30)
    db.close()

def test_task_run_lifecycle_rejects_invalid_transitions(tmp_path):
    import pytest

    db = connect(tmp_path / "lifecycle-validation.sqlite3")
    create_task_run(db, "run-guarded", "https://github.com/acme/app/issues/20")

    with pytest.raises(ValueError, match="Unknown task lifecycle stage"):
        advance_task_run(db, "run-guarded", "invented-stage")

    with pytest.raises(ValueError, match="Non-terminal stages"):
        advance_task_run(
            db, "run-guarded", "plan", status="completed", finished=True
        )

    advance_task_run(db, "run-guarded", "plan")

    with pytest.raises(ValueError, match="cannot move backwards"):
        advance_task_run(db, "run-guarded", "clone")

    advance_task_run(
        db, "run-guarded", "complete",
        status="completed", finished=True,
    )

    with pytest.raises(ValueError, match="terminal task run"):
        advance_task_run(db, "run-guarded", "failed", status="failed", finished=True)

    run = get_task_run(db, "run-guarded")
    assert run["status"] == "completed"
    assert run["current_stage"] == "complete"
    db.close()


def test_task_run_failed_transition_is_allowed_from_any_running_stage(tmp_path):
    db = connect(tmp_path / "lifecycle-failure.sqlite3")
    create_task_run(db, "run-failure", "https://github.com/acme/app/issues/21")
    advance_task_run(db, "run-failure", "clone")
    advance_task_run(
        db, "run-failure", "failed",
        status="failed", error="clone failed", finished=True,
    )

    run = get_task_run(db, "run-failure")
    assert run["status"] == "failed"
    assert run["current_stage"] == "failed"
    assert run["error"] == "clone failed"
    db.close()


def test_task_run_transition_rolls_back_when_event_insert_fails(tmp_path):
    import sqlite3
    import pytest

    db = connect(tmp_path / "lifecycle-atomicity.sqlite3")
    create_task_run(
        db,
        "run-atomic",
        "https://github.com/acme/app/issues/30",
    )

    db.execute("""
        CREATE TRIGGER reject_stage_event
        BEFORE INSERT ON task_events
        WHEN NEW.event_type = 'stage_update'
        BEGIN
            SELECT RAISE(ABORT, 'event persistence blocked');
        END
    """)
    db.commit()

    with pytest.raises(sqlite3.IntegrityError, match="event persistence blocked"):
        advance_task_run(db, "run-atomic", "plan")

    run = get_task_run(db, "run-atomic")
    events = list_task_run_events(db, "run-atomic")

    assert run["status"] == "running"
    assert run["current_stage"] == "inspect"
    assert [event["stage"] for event in events] == ["inspect"]

    db.close()
