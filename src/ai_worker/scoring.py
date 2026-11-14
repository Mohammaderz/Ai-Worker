import ipaddress
import math
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

from ai_worker.models import Gig


GRADE_POINTS = {"A+": 20, "A": 18, "A-": 16, "B+": 14, "B": 12, "B-": 9, "C+": 5, "C": 3}
MIN_PAYOUT_GRADES = {"A+", "A", "A-", "B+", "B"}
FIT_TERMS = {
    "python", "javascript", "typescript", "bug", "fix", "testing", "test",
    "api", "backend", "automation", "github", "documentation", "sdk",
    "database", "integration", "refactor", "frontend", "cli",
}
RISK_TERMS = {
    "trading", "investment", "invest", "deposit", "wallet seed", "private key",
    "guaranteed profit", "pay to unlock", "buy token", "pump", "casino",
    "malware", "credential", "phishing", "pii", "personal data", "civil id",
    "passport", "government id", "identity document", "medical records",
    "health records", "credit card", "bank account", "access key", "iam key",
    "api key", "secret key", "gdpr", "security remediation",
}


def _contains_term(text: str, term: str) -> bool:
    pattern = r"(?<!\w)" + re.escape(term).replace(r"\ ", r"\s+") + r"(?!\w)"
    return re.search(pattern, text) is not None


def _safe_listing_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        if parsed.scheme != "https" or not host or parsed.username or parsed.password:
            return False
        if host.lower() == "localhost" or host.lower().endswith((".localhost", ".local", ".internal")):
            return False
        if parsed.port not in (None, 443):
            return False
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address and (address.is_private or address.is_loopback or address.is_link_local or address.is_reserved):
            return False
        return True
    except (TypeError, ValueError):
        return False


def evaluate(gig: Gig, min_reward: float = 5.0) -> tuple[bool, float, list[str]]:
    if not math.isfinite(min_reward) or min_reward < 0:
        return False, 0, ["Configured minimum reward is invalid"]
    text = f"{gig.title} {gig.summary} {' '.join(gig.tags)}".lower()

    if gig.lane != "agent":
        return False, 0, ["Not marked for agent execution"]
    if gig.claims_open is not True:
        return False, 0, ["Claim availability is not explicitly confirmed"]
    if not _safe_listing_url(gig.url):
        return False, 0, ["Listing URL is not a safe HTTPS link"]
    if gig.expires:
        try:
            expiry = datetime.fromisoformat(gig.expires.replace("Z", "+00:00"))
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            if expiry <= datetime.now(timezone.utc):
                return False, 0, ["Listing is expired"]
        except (TypeError, ValueError):
            return False, 0, ["Listing expiry timestamp is invalid"]
    if gig.currency not in {"USD", "USDC"}:
        return False, 0, ["Unsupported or volatile reward currency"]
    if gig.reward_amount is None or not math.isfinite(gig.reward_amount) or gig.reward_amount < min_reward:
        return False, 0, ["Reward missing, invalid, or below configured minimum"]
    if gig.payout_grade not in MIN_PAYOUT_GRADES:
        return False, 0, ["Payout evidence below B grade or unavailable"]
    if gig.payment_state != "escrowed":
        return False, 0, ["Reward is not confirmed escrowed"]
    if not gig.acceptance.strip():
        return False, 0, ["Acceptance criteria are missing"]

    risks = sorted(term for term in RISK_TERMS if _contains_term(text, term))
    if risks:
        return False, 0, [f"Risk terms detected: {', '.join(risks)}"]
    fits = sorted(term for term in FIT_TERMS if _contains_term(text, term))
    if not fits:
        return False, 0, ["No clear software-task fit"]

    score = 20 + GRADE_POINTS[gig.payout_grade] + min(gig.reward_amount, 100) / 5 + min(len(fits), 5) * 4
    return True, round(score, 1), [
        f"Software fit: {', '.join(fits[:5])}",
        f"Reward: {gig.reward_amount:g} {gig.currency}",
        f"Payment state: {gig.payment_state}",
        f"Payout evidence: {gig.payout_grade}",
    ]
