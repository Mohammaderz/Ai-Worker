# AI-Worker

Safety-first agent-work pipeline. v0.2 discovers paid software tasks, applies strict payout/risk filters, ranks candidates, and stores an audit trail. Listed rewards are not earnings.

## Current scope
- Reads Jobbi's public read-only JSON feed.
- Focuses on agent-lane software tasks with USD/USDC rewards.
- Requires an explicitly escrowed reward and B-grade-or-better public payout evidence.
- Rejects closed/expired tasks, unsafe links, malformed expiry data, missing acceptance criteria, and risky categories.
- Ranks candidates and writes a Markdown shortlist.
- Includes a disposable Docker runner baseline with no network, no capabilities, a read-only root filesystem, resource limits and no host secrets.
- Does not claim gigs, bid, message clients, publish PRs, sign transactions, or spend money.

Jobbi is an index, not the payer. Verify original-board terms, claim process, acceptance criteria, and payout conditions. A listed or escrowed reward is not the same as money received.

## Run on macOS (Python 3.11+)
\`\`\`bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
pytest -q
ai-worker scan
\`\`\`

## Build the sandbox image
\`\`\`bash
docker build -f sandbox/Dockerfile -t ai-worker-sandbox:py311 .

# Run a command in a disposable, network-isolated workspace
ai-worker sandbox run --workspace .ai-worker/sandboxes/task-123 --scratch-root .ai-worker/sandboxes -- python -m compileall .
\`\`\`

Daily $5-$10 is a target, not a guarantee. The coding agent and task orchestration are still being built. See docs/ARCHITECTURE.md and sandbox/README.md.
