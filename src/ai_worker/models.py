from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Gig:
    id: str
    title: str
    url: str
    summary: str = ""
    tags: list[str] = field(default_factory=list)
    lane: str = ""
    reward_amount: float | None = None
    currency: str = ""
    payout_grade: str = ""
    payment_state: str = ""
    payment_rail: str = ""
    acceptance: str = ""
    expires: str = ""
    claims_open: bool | None = None
    source: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_feed_item(cls, item: dict[str, Any]) -> "Gig":
        meta = item.get("_jobbi")
        if not isinstance(meta, dict):
            meta = {}
        reward = meta.get("reward")
        if not isinstance(reward, dict):
            reward = {}
        try:
            amount = float(reward["amount"]) if reward.get("amount") is not None else None
        except (TypeError, ValueError, OverflowError):
            amount = None
        claims_open = meta.get("claims_open")
        if not isinstance(claims_open, bool):
            claims_open = None
        tags = item.get("tags") or []
        if not isinstance(tags, list):
            tags = []
        return cls(
            id=str(item.get("id") or ""),
            title=str(item.get("title") or "Untitled task"),
            url=str(item.get("url") or ""),
            summary=str(item.get("content_text") or item.get("summary") or ""),
            tags=[str(tag) for tag in tags],
            lane=str(meta.get("lane") or ""),
            reward_amount=amount,
            currency=str(reward.get("currency") or "").upper(),
            payout_grade=str(meta.get("payout_grade") or "").upper(),
            payment_state=str(meta.get("payment_state") or "").lower(),
            payment_rail=str(reward.get("rail") or ""),
            acceptance=str(meta.get("acceptance") or ""),
            expires=str(meta.get("expires") or ""),
            claims_open=claims_open,
            source=str(meta.get("source") or ""),
            raw=item,
        )
