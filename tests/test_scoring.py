from ai_worker.models import Gig
from ai_worker.scoring import evaluate


def sample(**kwargs):
    data = dict(
        id="task-1",
        title="Fix Python API tests",
        url="https://example.com/task",
        summary="Fix backend bug and add tests",
        tags=["python", "api"],
        lane="agent",
        reward_amount=25,
        currency="USD",
        payout_grade="B",
        payment_state="escrowed",
        payment_rail="stripe",
        acceptance="PR merged with tests passing",
        claims_open=True,
        source="algora",
    )
    data.update(kwargs)
    return Gig(**data)


def test_good_escrowed_bounty_is_eligible():
    ok, score, reasons = evaluate(sample())
    assert ok and score > 0 and reasons


def test_reject_non_agent():
    assert not evaluate(sample(lane="human"))[0]


def test_reject_unsupported_currency():
    assert not evaluate(sample(currency="MEME"))[0]


def test_reject_missing_acceptance():
    assert not evaluate(sample(acceptance=""))[0]


def test_reject_low_payout_grade():
    assert not evaluate(sample(payout_grade="C"))[0]


def test_reject_risky_listing():
    assert not evaluate(sample(summary="Deposit your wallet seed for guaranteed profit"))[0]


def test_reject_low_reward():
    assert not evaluate(sample(reward_amount=2), min_reward=5)[0]


def test_reject_unescrowed_reward():
    assert not evaluate(sample(payment_state="promised"))[0]


def test_reject_non_https_listing():
    assert not evaluate(sample(url="http://example.com/task"))[0]


def test_reject_non_finite_reward():
    assert not evaluate(sample(reward_amount=float("nan")))[0]


def test_reject_invalid_expiry():
    assert not evaluate(sample(expires="tomorrow maybe"))[0]


def test_risk_word_matching_does_not_flag_unrelated_substrings():
    assert evaluate(sample(title="Investigate a Python bug"))[0]


def test_reject_unknown_claim_availability():
    assert not evaluate(sample(claims_open=None))[0]


def test_reject_invalid_minimum_reward():
    assert not evaluate(sample(), min_reward=float("nan"))[0]


def test_feed_normalizer_handles_malformed_nested_metadata():
    gig = Gig.from_feed_item({
        "id": "malformed",
        "url": "https://example.com/task",
        "_jobbi": "not-an-object",
    })
    assert gig.id == "malformed"
    assert gig.payment_state == ""
    assert gig.reward_amount is None


def test_feed_normalizer_handles_malformed_reward_object():
    gig = Gig.from_feed_item({
        "id": "malformed-reward",
        "url": "https://example.com/task",
        "_jobbi": {"reward": ["not", "an", "object"]},
    })
    assert gig.reward_amount is None
    assert gig.currency == ""


def test_rejects_sensitive_identity_and_credential_tasks():
    assert not evaluate(sample(summary="Implement PII export and civil ID upload"))[0]
    assert not evaluate(sample(title="Rotate AWS IAM key and secret key"))[0]


def test_rejects_wallet_bonds_and_high_risk_exploit_tasks():
    assert not evaluate(sample(summary="Connect wallet and post refundable bond"))[0]
    assert not evaluate(sample(title="Remote code execution exploit development"))[0]


def test_rejects_low_information_bounty_spam():
    assert not evaluate(sample(title="ceshi", summary="/bounty $5"))[0]
    assert not evaluate(sample(title="My issue", summary="My issue"))[0]
    assert not evaluate(sample(title="testgogog", summary="/bounty"))[0]


def test_high_value_bounty_is_flagged_for_manual_verification():
    ok, _score, reasons = evaluate(sample(reward_amount=10000))
    assert ok
    assert any("manual scope and escrow verification" in reason for reason in reasons)
