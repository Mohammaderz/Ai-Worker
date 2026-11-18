from ai_worker.report import write_report


def test_report_discloses_incomplete_all_task_hours_and_paid_task_rate(tmp_path):
    source_history = [{
        "source": "board",
        "acceptance_rate": 0.5,
        "submitted_tasks": 2,
        "accepted_tasks": 1,
        "paid_tasks": 1,
        "net_received": 20.0,
        "net_per_tracked_hour": None,
        "net_per_paid_hour": 12.0,
        "hours_recorded_tasks": 2,
        "tracked_tasks": 3,
        "hours_coverage": 2 / 3,
        "average_payout_days": 3.0,
        "confidence": "incomplete_time_data",
        "guidance": "Record hours for every tracked task.",
    }]

    path = write_report([], tmp_path / "shortlist.md", source_history)
    report = path.read_text(encoding="utf-8")

    assert "Hours recorded: 2/3 tasks (67%)" in report
    assert (
        "Realized net per tracked task hour (includes unpaid/rejected attempts): "
        "n/a (incomplete hours or zero total hours)"
    ) in report
    assert "Conditional net per paid-task hour: USD 12.00/paid-task hour" in report
