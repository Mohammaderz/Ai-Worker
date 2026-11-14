from datetime import datetime, timezone
from ai_worker.models import Gig

GRADE_POINTS = {"A+": 20, "A": 18, "A-": 16, "B+": 14, "B": 12, "B-": 9, "C+": 5, "C": 3}
FIT_TERMS = {"python", "javascript", "typescript", "bug", "fix", "testing", "test", "api", "backend", "automation", "github", "documentation", "sdk", "database", "integration", "refactor", "frontend", "cli"}
RISK_TERMS = {"trading", "investment", "invest", "deposit", "wallet seed", "private key", "guaranteed profit", "pay to unlock", "buy token", "pump", "casino", "malware", "credential", "phishing"}

def evaluate(gig: Gig, min_reward: float = 5.0) -> tuple[bool, float, list[str]]:
    text = f"{gig.title} {gig.summary} {' '.join(gig.tags)}".lower()
    if gig.lane != "agent":
        return False, 0, ["Not marked for agent execution"]
    if gig.claims_open is False:
        return False, 0, ["Claims are closed"]
    if gig.expires:
        try:
            expiry = datetime.fromisoformat(gig.expires.replace("Z", "+00:00"))
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            if expiry <= datetime.now(timezone.utc):
                return False, 0, ["Listing is expired"]
        except ValueError:
            pass
    if gig.currency not in {"USD", "USDC"}:
        return False, 0, ["Unsupported or volatile reward currency"]
    if gig.reward_amount is None or gig.reward_amount < min_reward:
        return False, 0, ["Reward missing or below configured minimum"]
    if gig.payout_grade not in GRADE_POINTS:
        return False, 0, ["Insufficient public payout evidence"]
    if not gig.acceptance.strip():
        return False, 0, ["Acceptance criteria are missing"]
    risks = sorted(term for term in RISK_TERMS if term in text)
    if risks:
        return False, 0, [f"Risk terms detected: {', '.join(risks)}"]
    fits = sorted(term for term in FIT_TERMS if term in text)
    if not fits:
        return False, 0, ["No clear software-task fit"]
    score = 20 + GRADE_POINTS[gig.payout_grade] + min(gig.reward_amount, 100) / 5 + min(len(fits), 5) * 4
    return True, round(score, 1), [f"Software fit: {', '.join(fits[:5])}", f"Reward: {gig.reward_amount:g} {gig.currency}", f"Payout evidence: {gig.payout_grade}"]
