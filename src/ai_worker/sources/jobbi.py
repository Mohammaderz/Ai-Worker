import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from ai_worker.models import Gig

FEED_URL = "https://jobbi.org/gigs.json"
USER_AGENT = "AI-Worker/0.1 (+https://github.com/Mohammaderz/Ai-Worker)"

class FeedError(RuntimeError):
    pass

def fetch_gigs(limit: int = 100, timeout: int = 25) -> list[Gig]:
    """Fetch Jobbi's public read-only feed. Poll no more than hourly."""
    params = urlencode({"lane": "agent", "limit": max(1, min(limit, 1000))})
    request = Request(f"{FEED_URL}?{params}", headers={
        "Accept": "application/feed+json, application/json",
        "User-Agent": USER_AGENT,
    })
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise FeedError(f"Could not read Jobbi feed: {exc}") from exc
    items = payload.get("items", []) if isinstance(payload, dict) else []
    if not isinstance(items, list):
        raise FeedError("Unexpected feed format: items is not a list")
    gigs = [Gig.from_feed_item(item) for item in items if isinstance(item, dict)]
    return [gig for gig in gigs if gig.id and gig.url]
