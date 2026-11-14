"""Marketplace source registry for Jobbi-indexed boards and manual-only platforms.

The registry distinguishes a real feed integration from a link that still
requires human access. It never scrapes login-protected marketplaces.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from typing import Iterable

from ai_worker.models import Gig
from ai_worker.sources.github_issue import GitHubIssueError, parse_github_issue_url


@dataclass(frozen=True, slots=True)
class SourceInfo:
    key: str
    name: str
    mode: str
    status: str
    note: str
    url: str = ""


# These keys are source identifiers from Jobbi normalized public feed.
INDEXED_SOURCES: dict[str, SourceInfo] = {
    "algora": SourceInfo("algora", "Algora", "jobbi_feed", "active", "Indexed through Jobbi read-only agent feed.", "https://algora.io/bounties"),
    "issuehunt": SourceInfo("issuehunt", "IssueHunt", "jobbi_feed", "active", "Indexed through Jobbi read-only agent feed.", "https://oss.issuehunt.io/"),
    "bountybook": SourceInfo("bountybook", "BountyBook", "jobbi_feed", "active", "Indexed through Jobbi feed; verify x402 payment conditions."),
    "bountyhub": SourceInfo("bountyhub", "BountyHub", "jobbi_feed", "active", "Indexed through Jobbi read-only agent feed."),
    "agent-bounties": SourceInfo("agent-bounties", "Agent Bounties", "jobbi_feed", "active", "Verify Base network and fees."),
    "openwork": SourceInfo("openwork", "OpenWork", "jobbi_feed", "active", "Token-denominated rewards are excluded by default."),
    "opentask": SourceInfo("opentask", "OpenTask", "jobbi_feed", "active", "Indexed through Jobbi read-only agent feed."),
    "basedagents": SourceInfo("basedagents", "BasedAgents", "jobbi_feed", "active", "Verify Base network and fees."),
    "opire": SourceInfo("opire", "Opire", "jobbi_feed", "active", "Indexed through Jobbi read-only agent feed."),
    "frantic": SourceInfo("frantic", "Frantic", "jobbi_feed", "active", "Indexed through Jobbi read-only agent feed."),
    "olas": SourceInfo("olas", "Olas Mech Marketplace", "jobbi_feed", "active", "On-chain settlement needs manual review."),
    "rentahuman": SourceInfo("rentahuman", "RentAHuman", "jobbi_feed", "active", "Human-work lane only; excluded from autonomous execution."),
}

MANUAL_ONLY_SOURCES: dict[str, SourceInfo] = {
    "gitcoin": SourceInfo("gitcoin", "Gitcoin", "manual_link", "manual_only", "Legacy cGrants bounty program sunset in 2023; Buidlbox is the successor route for hackathons and bounties.", "https://gitcoin.co/"),
    "buidlbox": SourceInfo("buidlbox", "Buidlbox", "manual_link", "manual_only", "No verified contributor search API adapter configured."),
    "upwork": SourceInfo("upwork", "Upwork", "approved_api_only", "manual_only", "Requires approved API access; unauthorized automation risks account suspension.", "https://www.upwork.com/developer"),
    "contra": SourceInfo("contra", "Contra", "manual_link", "manual_only", "No automated scraping or outreach; review manually under platform terms.", "https://contra.com/"),
    "hackerone": SourceInfo("hackerone", "HackerOne", "program_scope_review", "manual_only", "Researcher participation requires in-scope manual validation.", "https://www.hackerone.com/"),
    "immunefi": SourceInfo("immunefi", "Immunefi", "program_scope_review", "manual_only", "Security opportunities require strict scope and human review.", "https://immunefi.com/"),
    "freelancer": SourceInfo("freelancer", "Freelancer.com", "manual_link", "manual_only", "No verified approved job-search adapter configured.", "https://www.freelancer.com/"),
    "fiverr": SourceInfo("fiverr", "Fiverr", "manual_link", "manual_only", "Use manually managed service listings and orders, not scraping.", "https://www.fiverr.com/"),
    "codementor": SourceInfo("codementor", "Codementor", "manual_link", "manual_only", "Mentoring is human-led; no automated job-search adapter configured.", "https://www.codementor.io/"),
}


def _has_github_issue_adapter(gig: Gig) -> bool:
    """Return true only for the URL shape accepted by the current coding pipeline."""
    try:
        parse_github_issue_url(gig.url)
        return True
    except GitHubIssueError:
        return False


def source_report(gigs: Iterable[Gig]) -> dict:
    """Report observed feed coverage and actual URL-level execution compatibility."""
    items = list(gigs)
    counts = Counter((gig.source or "unknown").strip().lower() for gig in items)
    execution = defaultdict(lambda: {"github_issue_pipeline_ready": 0, "adapter_required": 0})
    for gig in items:
        key = (gig.source or "unknown").strip().lower()
        field = "github_issue_pipeline_ready" if _has_github_issue_adapter(gig) else "adapter_required"
        execution[key][field] += 1

    indexed = []
    for key, count in sorted(counts.items()):
        info = INDEXED_SOURCES.get(key)
        indexed.append({
            "key": key,
            "name": info.name if info else key,
            "count": count,
            "integration": "jobbi_feed",
            "status": "active" if info else "observed_unclassified",
            "url": info.url if info else "",
            "execution": {
                "mode": "github_issue_only",
                **execution[key],
                "other_urls_note": "Visible in discovery, but not executable until a dedicated adapter exists.",
            },
        })
    manual = [asdict(item) for item in MANUAL_ONLY_SOURCES.values()]
    return {
        "aggregator": {
            "name": "Jobbi",
            "mode": "public_read_only_feed",
            "url": "https://jobbi.org/gigs",
            "note": "One feed request indexes multiple boards; Jobbi is an index, not the payer.",
        },
        "indexed_sources_observed": indexed,
        "manual_only_sources": manual,
        "total_indexed_gigs": len(items),
        "execution_boundary": "Only canonical public github.com/OWNER/REPO/issues/NUMBER URLs are supported by the current coding pipeline. This is a URL capability, not a promise that a task will be accepted or paid.",
    }


def filter_sources(gigs: Iterable[Gig], selected: Iterable[str] | None = None) -> list[Gig]:
    """Filter normalized gigs by their original marketplace source."""
    items = list(gigs)
    if not selected:
        return items
    wanted = {value.strip().lower() for value in selected if value.strip()}
    if not wanted or "all" in wanted:
        return items
    return [gig for gig in items if (gig.source or "").strip().lower() in wanted]
