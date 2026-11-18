"""Conservative portfolio selection for concurrently reviewable opportunities."""
from __future__ import annotations

import math
from collections import Counter
from typing import TypeVar

T = TypeVar("T")


def select_portfolio(
    ranked: list[tuple[T, float, list[str]]],
    *,
    limit: int = 5,
    max_per_source: int = 2,
    active_count: int = 0,
    max_active: int = 5,
) -> list[tuple[T, float, list[str]]]:
    """Select a diversified shortlist within remaining active-work capacity.

    Input must already have passed all hard eligibility gates. Active tasks
    are claimed/in-progress/submitted/accepted records from the local ledger.
    This only prepares a shortlist; it never claims or submits work.
    """
    for name, value in (("limit", limit), ("max_per_source", max_per_source), ("max_active", max_active)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"{name} must be a positive integer")
    if isinstance(active_count, bool) or not isinstance(active_count, int) or active_count < 0:
        raise ValueError("active_count must be a non-negative integer")

    remaining = max(0, max_active - active_count)
    capacity = min(limit, remaining)
    if capacity == 0:
        return []

    selected: list[tuple[T, float, list[str]]] = []
    source_counts: Counter[str] = Counter()
    seen_ids: set[str] = set()

    for item, score, reasons in ranked:
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score):
            continue
        item_id = str(getattr(item, "id", "") or "")
        if not item_id or item_id in seen_ids:
            continue
        source = str(getattr(item, "source", "") or "unknown").strip().lower() or "unknown"
        if source_counts[source] >= max_per_source:
            continue
        selected.append((item, float(score), list(reasons)))
        seen_ids.add(item_id)
        source_counts[source] += 1
        if len(selected) >= capacity:
            break

    return selected
