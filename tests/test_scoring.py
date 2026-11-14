from ai_worker.models import Gig
from ai_worker.scoring import evaluate

def sample(**kwargs):
    data = dict(id="task-1", title="Fix Python API tests", url="https://example.com/task",
        summary="Fix backend bug and add tests", tags=["python","api"], lane="agent",
        reward_amount=25, currency="USD", payout_grade="B",
        acceptance="PR merged with tests passing", claims_open=True, source="algora")
    data.update(kwargs)
    return Gig(**data)

def test_good_bounty_is_eligible():
    ok, score, reasons = evaluate(sample())
    assert ok and score > 0 and reasons

def test_reject_non_agent():
    assert not evaluate(sample(lane="human"))[0]

def test_reject_unsupported_currency():
    assert not evaluate(sample(currency="MEME"))[0]

def test_reject_missing_acceptance():
    assert not evaluate(sample(acceptance=""))[0]

def test_reject_low_payout_grade():
    assert not evaluate(sample(payout_grade="D"))[0]

def test_reject_risky_listing():
    assert not evaluate(sample(summary="Deposit your wallet seed for guaranteed profit"))[0]

def test_reject_low_reward():
    assert not evaluate(sample(reward_amount=2), min_reward=5)[0]
