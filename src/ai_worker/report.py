from datetime import datetime, timezone
from pathlib import Path
from ai_worker.models import Gig

def write_report(rows: list[tuple[Gig, float, list[str]]], output: str | Path) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# AI-Worker opportunity shortlist", "", f"Generated: {datetime.now(timezone.utc).isoformat()}", "", "> Listed rewards are not earnings. Verify original-board terms before starting.", ""]
    if not rows:
        lines += ["No gigs passed the current conservative filters.", ""]
    for i, (gig, score, reasons) in enumerate(rows, 1):
        lines += [f"## {i}. {gig.title}", "", f"- Score: {score}", f"- Reward: {gig.reward_amount:g} {gig.currency}", f"- Board: {gig.source or 'Not specified'}", f"- Payout evidence: {gig.payout_grade}", f"- Original listing: {gig.url}", "- Reasons: " + "; ".join(reasons), ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
