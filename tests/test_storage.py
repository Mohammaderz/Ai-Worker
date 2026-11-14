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
