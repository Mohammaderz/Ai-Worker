import json
from urllib.parse import parse_qs, urlsplit

import pytest

from ai_worker.sources.trybounty import BountyAPIError, fetch_open_bounties


class FakeResponse:
    def __init__(self, payload):
        self.raw = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, size=-1):
        return self.raw[:size]


def test_bounty_read_adapter_paginates_and_normalizes_without_bid_or_claim():
    calls = []
    pages = [
        {"bounties": [{
            "_id": "fixed-1", "title": "Fix an API bug", "description": "Fix the endpoint.",
            "verification": "Tests pass", "category": "software", "tags": ["python"],
            "currency": "usd", "flow": "claim", "status": "open", "version": 2,
            "payout_cents": 2500, "budget_cents": None, "created_at": 1000,
        }], "has_more": True, "next_cursor": "cursor-2"},
        {"bounties": [{
            "_id": "bid-1", "title": "Build a dashboard", "description": "Build UI.",
            "verification": "Demo", "category": "software", "tags": [],
            "currency": "usd", "flow": "bid", "status": "open", "version": 1,
            "payout_cents": None, "budget_cents": 10000, "created_at": 1001,
        }, {
            "_id": "test-1", "title": "Test bounty", "flow": "claim", "status": "open",
            "test": True, "currency": "usd", "version": 1, "payout_cents": 1000,
        }], "has_more": False, "next_cursor": ""},
    ]

    def fake_urlopen(request, timeout):
        calls.append((request, timeout))
        return FakeResponse(pages[len(calls) - 1])

    items = fetch_open_bounties("test-secret", limit=10, timeout=10, opener=fake_urlopen)
    assert len(items) == 2
    assert items[0].fixed_payout == 25.0
    assert items[0].flow == "claim"
    assert items[1].fixed_payout is None
    assert items[1].budget_guide == 100.0
    assert len(calls) == 2
    assert parse_qs(urlsplit(calls[1][0].full_url).query)["cursor"] == ["cursor-2"]
    assert calls[0][0].get_method() == "GET"
    assert calls[0][0].get_header("Authorization") == "Bearer test-secret"


def test_bounty_read_adapter_requires_key_and_bounds_limit():
    with pytest.raises(BountyAPIError, match="BOUNTY_AGENT_API_KEY"):
        fetch_open_bounties("")
    with pytest.raises(BountyAPIError, match="1 to 1000"):
        fetch_open_bounties("key", limit=1001)


def test_bounty_adapter_rejects_malformed_key_and_unhashable_flow():
    with pytest.raises(BountyAPIError, match="malformed"):
        fetch_open_bounties("bad\\nheader")

    calls = []

    def fake_urlopen(request, timeout):
        calls.append(request)
        return FakeResponse({
            "bounties": [
                {"_id": "bad-flow", "title": "Malformed", "flow": ["claim"], "status": "open"},
                {"_id": "good", "title": "Valid", "flow": "claim", "status": "open",
                 "currency": "usd", "payout_cents": 500, "version": 1},
            ],
            "has_more": False,
            "next_cursor": "",
        })

    items = fetch_open_bounties("test-secret", opener=fake_urlopen)
    assert [item.id for item in items] == ["good"]


def test_bounty_adapter_rejects_unexpected_response_shape():
    def fake_urlopen(request, timeout):
        return FakeResponse({"items": []})

    with pytest.raises(BountyAPIError, match="Unexpected"):
        fetch_open_bounties("test-secret", opener=fake_urlopen)


def test_bounty_cli_writes_read_only_report_without_printing_secret(tmp_path, monkeypatch, capsys):
    import sys

    from ai_worker import cli
    from ai_worker.sources.trybounty import BountyOpportunity

    secret = "local-secret-value"
    monkeypatch.setenv("BOUNTY_AGENT_API_KEY", secret)
    output = tmp_path / "nested" / "bounties.json"
    monkeypatch.setattr(
        cli,
        "fetch_open_bounties",
        lambda api_key, limit: [
            BountyOpportunity(
                id="bounty-1", title="Fix a bug", description="Repair endpoint",
                verification="Tests pass", category="software", tags=["python"],
                currency="USD", flow="claim", status="open", version=1,
                fixed_payout=25.0, budget_guide=None, expires_at=None, created_at=None,
            )
        ],
    )
    monkeypatch.setattr(
        sys, "argv",
        ["ai-worker", "bounty", "scan", "--limit", "5", "--output", str(output)],
    )

    assert cli.main() == 0
    captured = capsys.readouterr()
    assert "Open Bounties fetched: 1" in captured.out
    assert secret not in captured.out
    assert secret not in output.read_text(encoding="utf-8")
    assert '"fixed_payout": 25.0' in output.read_text(encoding="utf-8")
    assert "No bids, claims, messages, or submissions" in captured.out


def test_bounty_adapter_surfaces_rate_limit_retry_after():
    from email.message import Message
    from urllib.error import HTTPError

    def fake_urlopen(request, timeout):
        headers = Message()
        headers["Retry-After"] = "45"
        raise HTTPError(request.full_url, 429, "Too Many Requests", headers, None)

    with pytest.raises(BountyAPIError, match="retry after 45 seconds"):
        fetch_open_bounties("test-secret", opener=fake_urlopen)


def test_bounty_adapter_rejects_repeated_pagination_cursor():
    calls = 0

    def fake_urlopen(request, timeout):
        nonlocal calls
        calls += 1
        return FakeResponse({
            "bounties": [],
            "has_more": True,
            "next_cursor": "same-cursor",
        })

    with pytest.raises(BountyAPIError, match="missing or repeated"):
        fetch_open_bounties("test-secret", opener=fake_urlopen)
    assert calls == 2
