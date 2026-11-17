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
        payment_state TEXT, payment_rail TEXT, acceptance_type TEXT,
        first_seen TEXT DEFAULT CURRENT_TIMESTAMP, last_seen TEXT DEFAULT CURRENT_TIMESTAMP,
        raw_json TEXT NOT NULL)""")
    # Additive migration for databases created by v0.1.
    columns = {row[1] for row in db.execute("PRAGMA table_info(gigs)")}
    if "payment_state" not in columns:
        db.execute("ALTER TABLE gigs ADD COLUMN payment_state TEXT")
    if "payment_rail" not in columns:
        db.execute("ALTER TABLE gigs ADD COLUMN payment_rail TEXT")
    if "acceptance_type" not in columns:
        db.execute("ALTER TABLE gigs ADD COLUMN acceptance_type TEXT")
    db.execute("""CREATE TABLE IF NOT EXISTS task_outcomes (
        gig_id TEXT PRIMARY KEY,
        status TEXT NOT NULL,
        actual_hours REAL,
        gross_received REAL,
        fees REAL DEFAULT 0,
        submitted_at TEXT,
        accepted_at TEXT,
        paid_at TEXT,
        notes TEXT DEFAULT '',
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(gig_id) REFERENCES gigs(id)
    )""")
    db.commit()
    return db


def upsert_gigs(db: sqlite3.Connection, gigs: list[Gig]) -> None:
    for gig in gigs:
        db.execute("""INSERT INTO gigs(
            id,title,url,source,currency,reward_amount,payout_grade,payment_state,payment_rail,acceptance_type,raw_json
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
        title=excluded.title,url=excluded.url,source=excluded.source,currency=excluded.currency,
        reward_amount=excluded.reward_amount,payout_grade=excluded.payout_grade,
        payment_state=excluded.payment_state,payment_rail=excluded.payment_rail,
        acceptance_type=excluded.acceptance_type,
        last_seen=CURRENT_TIMESTAMP,raw_json=excluded.raw_json""",
        (
            gig.id, gig.title, gig.url, gig.source, gig.currency, gig.reward_amount,
            gig.payout_grade, gig.payment_state, gig.payment_rail, gig.acceptance_type,
            json.dumps(gig.raw, ensure_ascii=False),
        ))
    db.commit()



OUTCOME_TRANSITIONS = {
    "claimed": {"in_progress", "rejected"},
    "in_progress": {"submitted", "rejected"},
    "submitted": {"accepted", "rejected"},
    "accepted": {"paid"},
    "paid": set(),
    "rejected": set(),
}


def record_outcome(
    db: sqlite3.Connection,
    gig_id: str,
    status: str,
    *,
    actual_hours: float | None = None,
    gross_received: float | None = None,
    fees: float | None = None,
    notes: str = "",
) -> None:
    import math

    if not isinstance(status, str) or status not in OUTCOME_TRANSITIONS:
        raise ValueError("Unknown outcome status")
    for label, value, allow_zero in (
        ("actual_hours", actual_hours, False),
        ("gross_received", gross_received, True),
        ("fees", fees, True),
    ):
        if value is not None and (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or (value < 0 if allow_zero else value <= 0)
        ):
            raise ValueError(f"{label} must be a finite {'non-negative' if allow_zero else 'positive'} number")
    if status == "paid" and gross_received is None:
        existing = db.execute(
            "SELECT gross_received FROM task_outcomes WHERE gig_id=?", (gig_id,)
        ).fetchone()
        if not existing or existing[0] is None:
            raise ValueError("A paid outcome requires the actual gross amount received")
    if not isinstance(notes, str) or len(notes) > 4000:
        raise ValueError("Notes must be text up to 4000 characters")
    if not db.execute("SELECT 1 FROM gigs WHERE id=?", (gig_id,)).fetchone():
        raise ValueError("Gig ID does not exist in the local opportunity ledger")

    existing = db.execute(
        "SELECT status FROM task_outcomes WHERE gig_id=?", (gig_id,)
    ).fetchone()
    if not existing and status != "claimed":
        raise ValueError("The first outcome status must be claimed")
    if existing and status != existing[0] and status not in OUTCOME_TRANSITIONS[existing[0]]:
        raise ValueError(f"Invalid outcome transition: {existing[0]} -> {status}")

    db.execute(
        """INSERT INTO task_outcomes(
            gig_id,status,actual_hours,gross_received,fees,submitted_at,accepted_at,paid_at,notes
        ) VALUES(
            ?,?,?,?,?, 
            CASE WHEN ? IN ('submitted','accepted','paid') THEN CURRENT_TIMESTAMP END,
            CASE WHEN ? IN ('accepted','paid') THEN CURRENT_TIMESTAMP END,
            CASE WHEN ?='paid' THEN CURRENT_TIMESTAMP END,
            ?
        )
        ON CONFLICT(gig_id) DO UPDATE SET
            status=excluded.status,
            actual_hours=COALESCE(excluded.actual_hours,task_outcomes.actual_hours),
            gross_received=COALESCE(excluded.gross_received,task_outcomes.gross_received),
            fees=COALESCE(excluded.fees,task_outcomes.fees),
            submitted_at=COALESCE(task_outcomes.submitted_at,excluded.submitted_at),
            accepted_at=COALESCE(task_outcomes.accepted_at,excluded.accepted_at),
            paid_at=COALESCE(task_outcomes.paid_at,excluded.paid_at),
            notes=excluded.notes,
            updated_at=CURRENT_TIMESTAMP""",
        (
            gig_id, status, actual_hours, gross_received, fees,
            status, status, status, notes,
        ),
    )
    db.commit()


def source_performance(db: sqlite3.Connection) -> list[dict]:
    """Summarize realized outcomes by source; never treat listed rewards as income."""
    from datetime import datetime
    from collections import defaultdict

    rows = db.execute(
        """SELECT COALESCE(NULLIF(g.source, ''), 'unknown') AS source,
                  o.status, o.actual_hours, o.gross_received, o.fees,
                  o.submitted_at, o.accepted_at, o.paid_at
           FROM task_outcomes AS o
           JOIN gigs AS g ON g.id = o.gig_id
           ORDER BY source"""
    ).fetchall()
    grouped: dict[str, list[tuple]] = defaultdict(list)
    for row in rows:
        grouped[row[0]].append(row[1:])

    results = []
    for source, items in grouped.items():
        submitted = [r for r in items if r[4] is not None]
        accepted = [r for r in items if r[5] is not None]
        paid = [r for r in items if r[0] == "paid"]
        gross = sum(float(r[2] or 0) for r in paid)
        fees = sum(float(r[3] or 0) for r in paid)
        paid_hours = sum(float(r[1] or 0) for r in paid)
        latencies = []
        for row in paid:
            if row[4] and row[6]:
                try:
                    start = datetime.fromisoformat(str(row[4]))
                    end = datetime.fromisoformat(str(row[6]))
                    latencies.append(max(0.0, (end - start).total_seconds() / 86400))
                except ValueError:
                    pass
        acceptance_rate = len(accepted) / len(submitted) if submitted else None
        net = gross - fees
        # Do not infer a source preference from tiny samples.
        if len(submitted) < 3 or len(paid) < 2:
            confidence = "insufficient_data"
            guidance = "Collect at least 3 submissions and 2 actual payments before adapting source priority."
        elif acceptance_rate is not None and acceptance_rate >= 0.6 and net > 0:
            confidence = "usable"
            guidance = "Positive observed results; keep monitoring before increasing exposure."
        else:
            confidence = "usable"
            guidance = "Observed results are weak or mixed; inspect rejection reasons and payout friction."
        results.append({
            "source": source,
            "tracked_tasks": len(items),
            "submitted_tasks": len(submitted),
            "accepted_tasks": len(accepted),
            "paid_tasks": len(paid),
            "acceptance_rate": round(acceptance_rate, 3) if acceptance_rate is not None else None,
            "gross_received": round(gross, 2),
            "fees": round(fees, 2),
            "net_received": round(net, 2),
            "paid_task_hours": round(paid_hours, 2),
            "net_per_paid_hour": round(net / paid_hours, 2) if paid_hours else None,
            "average_payout_days": round(sum(latencies) / len(latencies), 2) if latencies else None,
            "confidence": confidence,
            "guidance": guidance,
        })
    return sorted(
        results,
        key=lambda item: (
            item["confidence"] == "usable",
            item["net_per_paid_hour"] if item["net_per_paid_hour"] is not None else -1,
            item["net_received"],
        ),
        reverse=True,
    )


def outcome_summary(db: sqlite3.Connection) -> dict:
    from datetime import datetime
    from statistics import median

    rows = db.execute(
        """SELECT status,actual_hours,gross_received,fees,submitted_at,paid_at
           FROM task_outcomes"""
    ).fetchall()
    counts = {status: 0 for status in OUTCOME_TRANSITIONS}
    for row in rows:
        status = row[0]
        counts[status] = counts.get(status, 0) + 1
    paid = [row for row in rows if row[0] == "paid"]
    gross = sum(float(row[2] or 0) for row in paid)
    fees = sum(float(row[3] or 0) for row in paid)
    hours = sum(float(row[1] or 0) for row in rows)
    paid_hours = sum(float(row[1] or 0) for row in paid)
    payout_latencies = []
    for row in paid:
        if row[4] and row[5]:
            try:
                submitted_at = datetime.fromisoformat(str(row[4]))
                paid_at = datetime.fromisoformat(str(row[5]))
                payout_latencies.append(max(0.0, (paid_at - submitted_at).total_seconds() / 86400))
            except ValueError:
                continue
    # A task rejected before submission has no submitted_at timestamp and must
    # not dilute the acceptance rate. Rejections after submission retain it.
    submitted = sum(1 for row in rows if row[4] is not None)
    accepted = counts["accepted"] + counts["paid"]
    return {
        "tasks": len(rows),
        "by_status": counts,
        "submitted_or_later": submitted,
        "accepted_or_paid": accepted,
        "acceptance_rate": round(accepted / submitted, 3) if submitted else None,
        "paid_tasks": len(paid),
        "gross_received": round(gross, 2),
        "fees": round(fees, 2),
        "net_received": round(gross - fees, 2),
        "tracked_hours_all_tasks": round(hours, 2),
        "paid_task_hours": round(paid_hours, 2),
        "net_received_per_paid_hour": round((gross - fees) / paid_hours, 2) if paid_hours else None,
        "payout_latency_sample_size": len(payout_latencies),
        "average_payout_latency_days": round(sum(payout_latencies) / len(payout_latencies), 2) if payout_latencies else None,
        "median_payout_latency_days": round(median(payout_latencies), 2) if payout_latencies else None,
        "by_source": source_performance(db),
        "note": "Only amounts manually recorded as paid count as earnings; advertised bounty values are excluded.",
    }
