from ai_worker.economics import source_priority_adjustments


def sample(source, *, acceptance, net_hour, delay=5):
    return {
        "source": source,
        "submitted_tasks": 3,
        "paid_tasks": 2,
        "confidence": "usable",
        "acceptance_rate": acceptance,
        "net_per_paid_hour": net_hour,
        "average_payout_days": delay,
    }


def test_no_source_history_means_no_adaptive_bonus():
    assert source_priority_adjustments([]) == {}


def test_small_samples_never_change_opportunity_ranking():
    history = [sample("new-board", acceptance=1.0, net_hour=100)]
    history[0]["submitted_tasks"] = 2
    assert source_priority_adjustments(history) == {}


def test_realized_economics_adjust_ranking_without_becoming_a_gate():
    history = [
        sample("reliable", acceptance=1.0, net_hour=30, delay=2),
        sample("slow", acceptance=0.33, net_hour=8, delay=30),
    ]
    adjustments = source_priority_adjustments(history)
    assert adjustments["reliable"] > adjustments["slow"]
    assert all(-8 <= value <= 8 for value in adjustments.values())


def test_zero_or_invalid_realized_hourly_rate_is_ignored():
    history = [sample("bad-data", acceptance=1.0, net_hour=0)]
    assert source_priority_adjustments(history) == {}
