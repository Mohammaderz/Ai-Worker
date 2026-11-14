from ai_worker.models import Gig
from ai_worker.storage import connect, upsert_gigs


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


def test_acceptance_rate_excludes_rejections_before_submission(tmp_path):
    from ai_worker.storage import outcome_summary, record_outcome

    db = connect(tmp_path / "outcomes.sqlite3")
    gigs = [
        Gig(id="rejected-early", title="Early rejection", url="https://example.com/1"),
        Gig(id="rejected-late", title="Late rejection", url="https://example.com/2"),
        Gig(id="accepted", title="Accepted task", url="https://example.com/3"),
    ]
    upsert_gigs(db, gigs)

    record_outcome(db, "rejected-early", "claimed")
    record_outcome(db, "rejected-early", "rejected")

    record_outcome(db, "rejected-late", "claimed")
    record_outcome(db, "rejected-late", "in_progress")
    record_outcome(db, "rejected-late", "submitted")
    record_outcome(db, "rejected-late", "rejected")

    record_outcome(db, "accepted", "claimed")
    record_outcome(db, "accepted", "in_progress")
    record_outcome(db, "accepted", "submitted")
    record_outcome(db, "accepted", "accepted")

    summary = outcome_summary(db)
    db.close()

    assert summary["submitted_or_later"] == 2
    assert summary["accepted_or_paid"] == 1
    assert summary["acceptance_rate"] == 0.5
    assert summary["by_status"]["rejected"] == 2
