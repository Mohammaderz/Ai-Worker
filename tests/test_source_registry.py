from ai_worker.models import Gig
from ai_worker.sources.registry import filter_sources, source_report


def gig(source, identifier):
    return Gig(
        id=identifier, title="Fix a TypeScript API bug",
        url="https://github.com/example/project/issues/1",
        summary="Fix the API bug and add meaningful automated tests.",
        lane="agent", source=source,
    )


def test_source_report_counts_only_observed_jobbi_sources():
    result = source_report([gig("algora", "a"), gig("issuehunt", "i"), gig("algora", "b")])
    assert result["total_indexed_gigs"] == 3
    assert {row["key"]: row["count"] for row in result["indexed_sources_observed"]} == {
        "algora": 2, "issuehunt": 1
    }
    assert result["aggregator"]["name"] == "Jobbi"
    assert any(row["key"] == "upwork" and row["status"] == "manual_only"
               for row in result["manual_only_sources"])


def test_filter_sources_selects_marketplace_without_losing_all_mode():
    items = [gig("algora", "a"), gig("issuehunt", "i"), gig("bountyhub", "b")]
    assert [x.id for x in filter_sources(items, ["algora", "bountyhub"])] == ["a", "b"]
    assert len(filter_sources(items, ["all"])) == 3
    assert len(filter_sources(items)) == 3
