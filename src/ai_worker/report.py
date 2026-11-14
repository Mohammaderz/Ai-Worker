from datetime import datetime, timezone
from pathlib import Path

from ai_worker.models import Gig


def write_report(
    rows: list[tuple[Gig, float, list[str]]],
    output: str | Path,
    source_history: list[dict] | None = None,
) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# AI-Worker opportunity shortlist",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "> Listed rewards are not earnings. Verify original-board terms before starting.",
        "> Only tasks with escrowed USD/USDC rewards and B-grade-or-better payout evidence pass the current gate.",
        "",
        "## Realized source economics",
        "",
        "This section uses only manually recorded submissions and actual payments. It does not treat advertised rewards as income.",
        "",
    ]
    if not source_history:
        lines += ["No completed source history yet. Record task outcomes and actual payments to build evidence.", ""]
    else:
        for item in source_history:
            acceptance = (
                f"{item['acceptance_rate']:.0%}"
                if item["acceptance_rate"] is not None else "n/a"
            )
            net_hour = (
                f"${item['net_per_paid_hour']:.2f}/paid hour"
                if item["net_per_paid_hour"] is not None else "n/a"
            )
            lines += [
                f"### {item['source']}",
                "",
                f"- Tracked / submitted / accepted / paid: {item['tracked_tasks']} / {item['submitted_tasks']} / {item['accepted_tasks']} / {item['paid_tasks']}",
                f"- Observed acceptance rate: {acceptance}",
                f"- Actual net received: ${item['net_received']:.2f}",
                f"- Realized net per paid-task hour: {net_hour}",
                f"- Average payout delay: {item['average_payout_days'] if item['average_payout_days'] is not None else 'n/a'} days",
                f"- Evidence confidence: {item['confidence']}",
                f"- Guidance: {item['guidance']}",
                "",
            ]
    lines += ["## Current opportunities", ""]
    if not rows:
        lines += ["No gigs passed the current conservative filters.", ""]
    for i, (gig, score, reasons) in enumerate(rows, 1):
        lines += [
            f"### {i}. {gig.title}",
            "",
            f"- Gig ID: {gig.id}",
            f"- Score: {score}",
            f"- Reward: {gig.reward_amount:g} {gig.currency}",
            f"- Board: {gig.source or 'Not specified'}",
            f"- Payment state: {gig.payment_state or 'Not disclosed'}",
            f"- Payment rail: {gig.payment_rail or 'Not disclosed'}",
            f"- Acceptance type: {gig.acceptance_type or 'Not disclosed'}",
            f"- Acceptance criteria: {' '.join(gig.acceptance.split()) or 'Not disclosed'}",
            f"- Claims open: {'yes' if gig.claims_open is True else 'no/unknown'}",
            f"- Expiry: {gig.expires or 'Not disclosed'}",
            f"- Payout evidence: {gig.payout_grade}",
            f"- Original listing: {gig.url}",
            "- Reasons: " + "; ".join(reasons),
            "",
        ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
