# AI-Worker

Safety-first agent-work pipeline. v0.1 discovers paid software tasks, filters risk, ranks candidates, and stores an audit trail. Listed rewards are not earnings.

## Current scope
- Reads Jobbi's public read-only JSON feed.
- Focuses on agent-lane software tasks with USD/USDC rewards.
- Filters closed/expired tasks, weak payout evidence, missing acceptance criteria, and risky categories.
- Ranks candidates and writes a Markdown shortlist.
- Does not claim gigs, bid, message clients, publish PRs, sign transactions, or spend money.

Jobbi is an index, not the payer. Verify original-board terms, claim process, acceptance criteria, and payout conditions.

## Run on macOS (Python 3.11+)
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
ai-worker scan
```

Daily $5-$10 is a target, not a guarantee. Future coding and delivery agents will work in isolated environments and require human approval before external actions. See docs/ARCHITECTURE.md.
