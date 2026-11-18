from dataclasses import dataclass

import pytest

from ai_worker.portfolio import select_portfolio


@dataclass
class Candidate:
    id: str
    source: str


def row(task_id, source, score):
    return (Candidate(task_id, source), score, ["eligible"])


def test_selects_top_opportunities_within_capacity():
    ranked = [row("a", "x", 90), row("b", "y", 80), row("c", "z", 70)]
    selected = select_portfolio(ranked, limit=2)
    assert [item.id for item, _, _ in selected] == ["a", "b"]


def test_diversifies_sources_without_lowering_hard_eligibility():
    ranked = [
        row("a", "same", 100), row("b", "same", 95),
        row("c", "same", 90), row("d", "other", 85),
    ]
    selected = select_portfolio(ranked, limit=3, max_per_source=2)
    assert [item.id for item, _, _ in selected] == ["a", "b", "d"]


def test_skips_duplicate_ids_and_invalid_scores():
    ranked = [row("a", "x", 10), row("a", "y", 9), row("bad", "z", float("nan")), row("b", "z", 8)]
    selected = select_portfolio(ranked)
    assert [item.id for item, _, _ in selected] == ["a", "b"]


@pytest.mark.parametrize("kwargs", [
    {"limit": 0}, {"limit": -1}, {"limit": True},
    {"max_per_source": 0}, {"max_per_source": -1}, {"max_per_source": True},
    {"max_active": 0}, {"max_active": -1}, {"max_active": True},
])
def test_rejects_invalid_capacity_settings(kwargs):
    with pytest.raises(ValueError):
        select_portfolio([row("a", "x", 1)], **kwargs)


def test_empty_source_is_treated_as_unknown():
    selected = select_portfolio([row("a", "", 10), row("b", "", 9), row("c", "", 8)])
    assert [item.id for item, _, _ in selected] == ["a", "b"]


def test_active_work_reduces_new_opportunity_capacity():
    ranked = [row(str(i), "src" + str(i), 100-i) for i in range(5)]
    selected = select_portfolio(ranked, limit=5, max_active=4, active_count=3)
    assert len(selected) == 1


def test_at_active_work_limit_selects_nothing():
    assert select_portfolio([row("a", "x", 10)], active_count=5, max_active=5) == []


def test_invalid_active_count_is_rejected():
    with pytest.raises(ValueError):
        select_portfolio([row("a", "x", 10)], active_count=-1)
