"""Conservative portfolio selection for concurrently reviewable opportunities.

This module selects a small, diversified shortlist. It does not claim tasks,
contact maintainers, or bypass the independent eligibility/security gates.
"""
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
) -> list[tuple[T, float, list[str]]]:
    """Select the highest-ranked unique opportunities with source diversification.

    Input must already have passed all hard eligibility gates. Ranking scores
    are preserved; this function only chooses a bounded shortlist.
    """
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("limit must be a positive integer")
    if (
        isinstance(max_per_source, bool)
        or not isinstance(max_per_source, int)
        or max_per_source < 1
    ):
        raise ValueError("max_per_source must be a positive integer")

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
        if len(selected) >= limit:
            break

    return selected
