"""Conservative ranking feedback based only on realized payout history."""
from __future__ import annotations

import math
from statistics import median


def source_priority_adjustments(source_history: list[dict]) -> dict[str, float]:
    """Return small ranking-only adjustments for sources with enough real outcomes.

    Hard eligibility gates are evaluated separately and can never be overridden.
    A source needs at least 3 submissions and 2 actual payments before it can
    influence ranking. No history means no adjustment.
    """
    usable = [
        item for item in source_history
        if item.get("confidence") == "usable"
        and item.get("submitted_tasks", 0) >= 3
        and item.get("paid_tasks", 0) >= 2
        and item.get("hours_coverage") == 1.0
        and isinstance(item.get("net_per_tracked_hour"), (int, float))
        and math.isfinite(item["net_per_tracked_hour"])
        and item["net_per_tracked_hour"] > 0
    ]
    if not usable:
        return {}

    baseline = median(item["net_per_tracked_hour"] for item in usable)
    adjustments: dict[str, float] = {}
    for item in usable:
        acceptance = item.get("acceptance_rate")
        acceptance_points = (
            (max(0.0, min(1.0, acceptance)) - 0.5) * 8
            if isinstance(acceptance, (int, float)) and math.isfinite(acceptance)
            else 0.0
        )
        hourly_ratio = (item["net_per_tracked_hour"] + 1) / (baseline + 1)
        hourly_points = max(-4.0, min(4.0, 2 * math.log2(hourly_ratio)))
        delay = item.get("average_payout_days")
        delay_points = (
            -2 * min(max(float(delay), 0.0), 30.0) / 30.0
            if isinstance(delay, (int, float)) and math.isfinite(delay)
            else 0.0
        )
        adjustments[item["source"]] = round(
            max(-8.0, min(8.0, acceptance_points + hourly_points + delay_points)),
            1,
        )
    return adjustments
