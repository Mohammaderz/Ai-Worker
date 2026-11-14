import json

import pytest

from ai_worker.models import Gig
from ai_worker.report import write_report
from ai_worker.sources import jobbi


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size=-1):
        return self.payload[:size]


def feed_item():
    return {
        "id": "algora:owner/repo#42",
        "title": "Fix Python API bug",
        "url": "https://github.com/owner/repo/issues/42",
        "content_text": "Fix bug and add tests",
        "tags": ["python", "api"],
        "_jobbi": {
            "lane": "agent",
            "reward": {"amount": 25, "currency": "USD", "rail": "stripe"},
            "acceptance": "Merged PR with tests passing",
            "acceptance_type": "human-review",
            "payment_state": "escrowed",
            "payout_grade": "B",
            "claims_open": True,
            "source": "algora",
        },
    }


def test_fetch_gigs_parses_jobbi_normalized_feed(monkeypatch):
    payload = json.dumps({"items": [feed_item()]}).encode()

    monkeypatch.setattr(jobbi, "urlopen", lambda request, timeout: FakeResponse(payload))
    gigs = jobbi.fetch_gigs(limit=1000)

    assert len(gigs) == 1
    assert gigs[0].id == "algora:owner/repo#42"
    assert gigs[0].reward_amount == 25
    assert gigs[0].currency == "USD"
    assert gigs[0].payment_state == "escrowed"
    assert gigs[0].claims_open is True


def test_fetch_gigs_rejects_oversized_feed(monkeypatch):
    payload = b"x" * (jobbi.MAX_FEED_BYTES + 1)
    monkeypatch.setattr(jobbi, "urlopen", lambda request, timeout: FakeResponse(payload))

    with pytest.raises(jobbi.FeedError, match="5 MiB"):
        jobbi.fetch_gigs()


def test_report_includes_gig_id_acceptance_and_original_url(tmp_path):
    gig = Gig.from_feed_item(feed_item())
    report = write_report([(gig, 50.0, ["Escrow confirmed"])], tmp_path / "report.md")
    content = report.read_text(encoding="utf-8")

    assert gig.id in content
    assert gig.acceptance in content
    assert gig.url in content
