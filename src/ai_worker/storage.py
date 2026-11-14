import json
import sqlite3
from pathlib import Path

from ai_worker.models import Gig


def connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.execute("""CREATE TABLE IF NOT EXISTS gigs (
        id TEXT PRIMARY KEY, title TEXT NOT NULL, url TEXT NOT NULL,
        source TEXT, currency TEXT, reward_amount REAL, payout_grade TEXT,
        payment_state TEXT, payment_rail TEXT,
        first_seen TEXT DEFAULT CURRENT_TIMESTAMP, last_seen TEXT DEFAULT CURRENT_TIMESTAMP,
        raw_json TEXT NOT NULL)""")
    # Additive migration for databases created by v0.1.
    columns = {row[1] for row in db.execute("PRAGMA table_info(gigs)")}
    if "payment_state" not in columns:
        db.execute("ALTER TABLE gigs ADD COLUMN payment_state TEXT")
    if "payment_rail" not in columns:
        db.execute("ALTER TABLE gigs ADD COLUMN payment_rail TEXT")
    db.commit()
    return db


def upsert_gigs(db: sqlite3.Connection, gigs: list[Gig]) -> None:
    for gig in gigs:
        db.execute("""INSERT INTO gigs(
            id,title,url,source,currency,reward_amount,payout_grade,payment_state,payment_rail,raw_json
        ) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
        title=excluded.title,url=excluded.url,source=excluded.source,currency=excluded.currency,
        reward_amount=excluded.reward_amount,payout_grade=excluded.payout_grade,
        payment_state=excluded.payment_state,payment_rail=excluded.payment_rail,
        last_seen=CURRENT_TIMESTAMP,raw_json=excluded.raw_json""",
        (
            gig.id, gig.title, gig.url, gig.source, gig.currency, gig.reward_amount,
            gig.payout_grade, gig.payment_state, gig.payment_rail,
            json.dumps(gig.raw, ensure_ascii=False),
        ))
    db.commit()
