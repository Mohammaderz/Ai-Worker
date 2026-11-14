"""Marketplace source registry for Jobbi-indexed boards and manual-only platforms.

The registry distinguishes a real feed integration from a link that still
requires human access. It never scrapes login-protected marketplaces.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from typing import Iterable

from ai_worker.models import Gig


@dataclass(frozen=True, slots=True)
class SourceInfo:
    key: str
    name: str
    mode: str
    status: str
    note: str
    url: str = ""


# These keys are source identifiers from Jobbi's normalized public feed.
INDEXED_SOURCES: dict[str, SourceInfo] = {
    "algora": SourceInfo("algora", "Algora", "jobbi_feed", "active", "Indexed through Jobbi's read-only agent feed.", "https://algora.io/bounties"),
    "issuehunt": SourceInfo("issuehunt", "IssueHunt", "jobbi_feed", "active", "Indexed through Jobbi's read-only agent feed.", "https://oss.issuehunt.io/"),
    "bountybook": SourceInfo("bountybook", "BountyBook", "jobbi_feed", "active", "Indexed through Jobbi's read-only agent feed; verify x402 payment conditions.", "https://jobbi.org/gigs"),
    "bountyhub": SourceInfo("bountyhub", "BountyHub", "jobbi_feed", "active", "Indexed through Jobbi's read-only agent feed.", "https://bountyhub.dev/"),
    "agent-bounties": SourceInfo("agent-bounties", "Agent Bounties", "jobbi_feed", "active", "Indexed through Jobbi's read-only agent feed; verify Base network and fees.", "https://jobbi.org/gigs"),
    "openwork": SourceInfo("openwork", "OpenWork", "jobbi_feed", "active", "Indexed through Jobbi's feed; token-denominated rewards are excluded by default.", "https://openwork.bot/"),
    "opentask": SourceInfo("opentask", "OpenTask", "jobbi_feed", "active", "Indexed through Jobbi's read-only agent feed.", "https://jobbi.org/gigs"),
    "basedagents": SourceInfo("basedagents", "BasedAgents", "jobbi_feed", "active", "Indexed through Jobbi's read-only agent feed; verify Base network and fees.", "https://jobbi.org/gigs"),
    "opire": SourceInfo("opire", "Opire", "jobbi_feed", "active", "Indexed through Jobbi's read-only agent feed.", "https://opire.dev/"),
    "frantic": SourceInfo("frantic", "Frantic", "jobbi_feed", "active", "Indexed through Jobbi's read-only agent feed.", "https://jobbi.org/gigs"),
    "olas": SourceInfo("olas", "Olas Mech Marketplace", "jobbi_feed", "active", "Indexed through Jobbi's read-only agent feed; on-chain settlement needs manual review.", "https://olas.network/"),
    "rentahuman": SourceInfo("rentahuman", "RentAHuman", "jobbi_feed", "active", "Human-work lane only; excluded from autonomous agent execution.", "https://rentahuman.ai/"),
}

MANUAL_ONLY_SOURCES: dict[str, SourceInfo] = {
    "gitcoin": SourceInfo("gitcoin", "Gitcoin", "manual_link", "manual_only", "No verified public contributor job-search API adapter is configured; add only after confirming current official access.", "https://gitcoin.co/"),
    "upwork": SourceInfo("upwork", "Upwork", "approved_api_only", "manual_only", "Requires approved API access; unauthorized scraping or background automation risks account suspension.", "https://www.upwork.com/developer"),
    "contra": SourceInfo("contra", "Contra", "manual_link", "manual_only", "No automated scraping or outreach; review opportunities manually under platform terms.", "https://contra.com/"),
    "hackerone": SourceInfo("hackerone", "HackerOne", "program_scope_review", "manual_only", "Public API documentation is primarily for program-owner workflows; researcher participation requires in-scope manual validation.", "https://www.hackerone.com/"),
    "immunefi": SourceInfo("immunefi", "Immunefi", "program_scope_review", "manual_only", "Security opportunities require strict scope and human review; automated low-quality reports are prohibited.", "https://immunefi.com/"),
    "freelancer": SourceInfo("freelancer", "Freelancer.com", "manual_link", "manual_only", "No verified approved job-search adapter is configured.", "https://www.freelancer.com/"),
    "fiverr": SourceInfo("fiverr", "Fiverr", "manual_link", "manual_only", "Service marketplace; use manually managed service listings and orders, not scraping.", "https://www.fiverr.com/"),
    "codementor": SourceInfo("codementor", "Codementor", "manual_link", "manual_only", "Mentoring and live interaction are human-led; no automated job-search adapter is configured.", "https://www.codementor.io/"),
}


def source_report(gigs: Iterable[Gig]) -> dict:
    """Return observed source coverage without inventing missing marketplace data."""
    counts = Counter((gig.source or "unknown").strip().lower() for gig in gigs)
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
        "total_indexed_gigs": sum(counts.values()),
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
