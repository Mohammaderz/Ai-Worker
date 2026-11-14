"""Read-only adapter for the official Bounty Agent API (trybounty.ai).

This module only lists open work. It never bids, claims, messages, or submits.
The Agent API key is read from the caller environment and is never persisted.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen


API_ROOT = "https://api.trybounty.ai"
USER_AGENT = "AI-Worker/0.2 (+https://github.com/Mohammaderz/AI-Worker)"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class _NoRedirectHandler(HTTPRedirectHandler):
    """Never forward an Agent bearer token through an HTTP redirect."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _safe_urlopen(request: Request, timeout: int):
    return build_opener(_NoRedirectHandler).open(request, timeout=timeout)


class BountyAPIError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class BountyOpportunity:
    id: str
    title: str
    description: str
    verification: str
    category: str
    tags: list[str]
    currency: str
    flow: str
    status: str
    version: int
    fixed_payout: float | None
    budget_guide: float | None
    expires_at: float | None
    created_at: float | None

    def to_dict(self) -> dict:
        return asdict(self)


def _money_cents(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return round(value / 100, 2)


def _normalize(item: dict) -> BountyOpportunity | None:
    bounty_id = item.get("_id")
    title = item.get("title")
    if not isinstance(bounty_id, str) or not bounty_id.strip():
        return None
    if not isinstance(title, str) or not title.strip():
        return None
    if item.get("test") is True or item.get("status") != "open":
        return None
    flow = item.get("flow")
    if not isinstance(flow, str) or flow not in {"claim", "bid"}:
        return None
    tags = item.get("tags")
    if not isinstance(tags, list):
        tags = []
    payout = _money_cents(item.get("payout_cents"))
    budget = _money_cents(item.get("budget_cents"))
    if flow == "bid":
        # A budget is only guidance; it is not the agent payout or an offer.
        payout = None
    expires = item.get("expires_at")
    created = item.get("created_at")
    version = item.get("version")
    return BountyOpportunity(
        id=bounty_id.strip(),
        title=title.strip(),
        description=str(item.get("description") or ""),
        verification=str(item.get("verification") or ""),
        category=str(item.get("category") or ""),
        tags=[str(tag) for tag in tags if isinstance(tag, (str, int, float))],
        currency=str(item.get("currency") or "").upper(),
        flow=flow,
        status="open",
        version=version if isinstance(version, int) and not isinstance(version, bool) else 0,
        fixed_payout=payout,
        budget_guide=budget,
        expires_at=float(expires) if isinstance(expires, (int, float)) and math.isfinite(expires) else None,
        created_at=float(created) if isinstance(created, (int, float)) and math.isfinite(created) else None,
    )


def fetch_open_bounties(api_key: str, limit: int = 100, timeout: int = 20, opener=_safe_urlopen) -> list[BountyOpportunity]:
    """Fetch open Bounties through the official authenticated, read-only list endpoint."""
    if not isinstance(api_key, str) or not api_key.strip():
        raise BountyAPIError("Set BOUNTY_AGENT_API_KEY in your local environment; never paste it into chat or commit it.")
    if len(api_key) > 4096 or "\\r" in api_key or "\\n" in api_key:
        raise BountyAPIError("The BOUNTY_AGENT_API_KEY value is malformed; check the local environment variable.")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
        raise BountyAPIError("Limit must be an integer from 1 to 1000.")
    if isinstance(timeout, bool) or not isinstance(timeout, int) or not 3 <= timeout <= 60:
        raise BountyAPIError("Timeout must be between 3 and 60 seconds.")

    results: list[BountyOpportunity] = []
    cursor = ""
    seen_cursors: set[str] = set()
    pages_fetched = 0
    while len(results) < limit:
        pages_fetched += 1
        if pages_fetched > 20:
            raise BountyAPIError("Bounty API exceeded the 20-page safety cap; check the API cursor behavior before retrying.")
        page_limit = min(100, limit - len(results))
        params = {"status": "open", "limit": page_limit}
        if cursor:
            params["cursor"] = cursor
        request = Request(
            f"{API_ROOT}/v1/agent/bounties?{urlencode(params)}",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {api_key.strip()}",
                "User-Agent": USER_AGENT,
            },
            method="GET",
        )
        try:
            with opener(request, timeout=timeout) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise BountyAPIError("Bounty API response exceeded the 2 MiB safety limit.")
            payload = json.loads(raw.decode("utf-8"))
        except BountyAPIError:
            raise
        except HTTPError as exc:
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            if exc.code == 429 and retry_after:
                raise BountyAPIError(f"Bounty API rate limited this read; retry after {retry_after} seconds.") from exc
            if exc.code in {401, 403}:
                raise BountyAPIError("Bounty API rejected the Agent key or Agent access. Check the dashboard key.") from exc
            raise BountyAPIError(f"Bounty API returned HTTP {exc.code}.") from exc
        except (URLError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
            raise BountyAPIError(f"Could not read Bounty API: {exc.__class__.__name__}.") from exc

        if not isinstance(payload, dict) or not isinstance(payload.get("bounties"), list):
            raise BountyAPIError("Unexpected Bounty API response shape.")
        for raw_item in payload["bounties"]:
            if isinstance(raw_item, dict):
                normalized = _normalize(raw_item)
                if normalized is not None:
                    results.append(normalized)
                    if len(results) >= limit:
                        break
        has_more = payload.get("has_more")
        next_cursor = payload.get("next_cursor")
        if has_more is not True:
            break
        if not isinstance(next_cursor, str) or not next_cursor or next_cursor in seen_cursors:
            raise BountyAPIError("Bounty API pagination cursor is missing or repeated.")
        seen_cursors.add(next_cursor)
        cursor = next_cursor
    return results[:limit]
