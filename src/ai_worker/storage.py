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
    db.execute("""CREATE TABLE IF NOT EXISTS task_runs (
        run_id TEXT PRIMARY KEY,
        issue_url TEXT NOT NULL,
        repository TEXT,
        issue_number INTEGER,
        status TEXT NOT NULL,
        current_stage TEXT NOT NULL,
        output_dir TEXT,
        result_json TEXT,
        error TEXT,
        started_at TEXT NOT NULL,
        finished_at TEXT,
        updated_at TEXT NOT NULL
    )""")
    task_run_columns = {
        row[1] for row in db.execute("PRAGMA table_info(task_runs)")
    }
    for column, definition in (
        ("repository", "TEXT"),
        ("issue_number", "INTEGER"),
        ("result_json", "TEXT"),
        ("result_status", "TEXT"),
    ):
        if column not in task_run_columns:
            db.execute(f"ALTER TABLE task_runs ADD COLUMN {column} {definition}")

    db.execute("""
        UPDATE task_runs
        SET result_status = status, status = 'completed'
        WHERE status NOT IN ('running', 'completed', 'failed')
          AND result_status IS NULL
    """)
    db.execute("""CREATE TABLE IF NOT EXISTS task_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        stage TEXT NOT NULL,
        status TEXT,
        details_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        FOREIGN KEY(run_id) REFERENCES task_runs(run_id)
    )""")
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_task_events_run_id "
        "ON task_events(run_id, id)"
    )
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
    fees: float = 0.0,
    notes: str = "",
) -> None:
    import math

    if status not in OUTCOME_TRANSITIONS:
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
            fees=excluded.fees,
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
    submitted = counts["submitted"] + counts["accepted"] + counts["paid"] + counts["rejected"]
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
        "note": "Only amounts manually recorded as paid count as earnings; advertised bounty values are excluded.",
    }


def create_task_run(
    db: sqlite3.Connection,
    run_id: str,
    issue_url: str,
    *,
    output_dir: str | None = None,
) -> None:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    with db:
        db.execute(
            """INSERT INTO task_runs(
                run_id, issue_url, status, current_stage, output_dir,
                started_at, updated_at
            ) VALUES(?, ?, 'running', 'inspect', ?, ?, ?)""",
            (run_id, issue_url, output_dir, now, now),
        )
        db.execute(
            """INSERT INTO task_events(
                run_id, event_type, stage, status, details_json, created_at
            ) VALUES(?, 'run_started', 'inspect', 'running', '{}', ?)""",
            (run_id, now),
        )


def advance_task_run(
    db: sqlite3.Connection,
    run_id: str,
    stage: str,
    *,
    status: str = "running",
    details: dict | None = None,
    output_dir: str | None = None,
    error: str | None = None,
    finished: bool = False,
    repository: str | None = None,
    issue_number: int | None = None,
    result_json: str | None = None,
    result_status: str | None = None,
) -> None:
    from datetime import datetime, timezone

    allowed_statuses = {"running", "completed", "failed"}
    if status not in allowed_statuses:
        raise ValueError(f"Unknown task lifecycle status: {status}")

    allowed_stages = (
        "inspect", "clone", "plan", "draft", "review",
        "apply", "verify", "finalize", "complete", "failed",
    )
    if stage not in allowed_stages:
        raise ValueError(f"Unknown task lifecycle stage: {stage}")

    if not isinstance(finished, bool):
        raise ValueError("finished must be a boolean")
    if stage == "failed":
        if status != "failed" or not finished:
            raise ValueError("The failed stage requires failed status and finished=True")
    elif stage == "complete":
        if status != "completed" or not finished:
            raise ValueError("The complete stage requires completed status and finished=True")
    elif status != "running" or finished:
        raise ValueError("Non-terminal stages require running status and finished=False")

    if details is not None and not isinstance(details, dict):
        raise ValueError("Task event details must be a dictionary")

    now = datetime.now(timezone.utc).isoformat()
    finished_at = now if finished else None
    payload = json.dumps(details or {}, ensure_ascii=False)
    stage_order = {name: index for index, name in enumerate(allowed_stages)}

    # Acquire the SQLite write lock before reading state. This makes the
    # read/validate/update/event sequence one serialized transaction.
    with db:
        db.execute("BEGIN IMMEDIATE")
        current = db.execute(
            "SELECT status, current_stage FROM task_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        if current is None:
            raise ValueError(f"Unknown task run: {run_id}")

        current_status, current_stage = current
        if current_status != "running":
            raise ValueError(f"Cannot advance terminal task run: {run_id}")
        if current_stage not in stage_order:
            raise ValueError(
                f"Stored task run has an unknown current stage: {current_stage}"
            )

        if stage != "failed" and stage_order[stage] < stage_order[current_stage]:
            raise ValueError(
                f"Task stage cannot move backwards: {current_stage} -> {stage}"
            )

        cursor = db.execute(
            """UPDATE task_runs
               SET status=?, current_stage=?,
                   output_dir=COALESCE(?, output_dir),
                   error=COALESCE(?, error),
                   repository=COALESCE(?, repository),
                   issue_number=COALESCE(?, issue_number),
                   result_json=COALESCE(?, result_json),
                   result_status=COALESCE(?, result_status),
                   updated_at=?,
                   finished_at=CASE WHEN ? THEN ? ELSE finished_at END
               WHERE run_id=? AND status='running' AND current_stage=?""",
            (
                status, stage, output_dir, error, repository, issue_number,
                result_json, result_status, now, int(finished), finished_at,
                run_id, current_stage,
            ),
        )
        if cursor.rowcount != 1:
            raise ValueError(
                f"Task run changed while advancing; transition rejected: {run_id}"
            )

        db.execute(
            """INSERT INTO task_events(
                run_id, event_type, stage, status, details_json, created_at
            ) VALUES(?, 'stage_update', ?, ?, ?, ?)""",
            (run_id, stage, status, payload, now),
        )


def _rows_as_dicts(cursor: sqlite3.Cursor) -> list[dict]:
    columns = [item[0] for item in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def list_task_runs(
    db: sqlite3.Connection,
    *,
    limit: int = 20,
    status: str | None = None,
    stale_minutes: int | None = None,
) -> list[dict]:
    from datetime import datetime, timedelta, timezone

    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1 or limit > 1000:
        raise ValueError("Run limit must be between 1 and 1000")
    if status is not None and status not in {"running", "completed", "failed"}:
        raise ValueError(f"Unknown task lifecycle status: {status}")
    if stale_minutes is not None:
        if (
            not isinstance(stale_minutes, int)
            or isinstance(stale_minutes, bool)
            or stale_minutes < 1
        ):
            raise ValueError("Stale minutes must be a positive integer")
        if status not in (None, "running"):
            raise ValueError("Stale-run filtering only supports status='running'")

    query = "SELECT * FROM task_runs"
    conditions = []
    params = []

    if status is not None:
        conditions.append("status = ?")
        params.append(status)

    if stale_minutes is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=stale_minutes)
        conditions.append("status = 'running'")
        conditions.append("julianday(updated_at) <= julianday(?)")
        params.append(cutoff.isoformat())

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY started_at DESC LIMIT ?"
    params.append(limit)

    return _rows_as_dicts(db.execute(query, params))


def get_task_run(
    db: sqlite3.Connection,
    run_id: str,
) -> dict | None:
    cursor = db.execute(
        "SELECT * FROM task_runs WHERE run_id = ?",
        (run_id,),
    )
    rows = _rows_as_dicts(cursor)
    return rows[0] if rows else None


def list_task_run_events(
    db: sqlite3.Connection,
    run_id: str,
) -> list[dict]:
    return _rows_as_dicts(
        db.execute(
            """SELECT id, event_type, stage, status, details_json, created_at
               FROM task_events
               WHERE run_id = ?
               ORDER BY id ASC""",
            (run_id,),
        )
    )
