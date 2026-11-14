# AI-Worker

Safety-first agent-work pipeline. v0.2 discovers paid software tasks, applies strict payout/risk filters, ranks candidates, and stores an audit trail. Listed rewards are not earnings.

## Current scope
- Reads Jobbi's public read-only JSON feed.
- Inspects canonical public GitHub issue links read-only to collect title, state, labels and acceptance context; issue text is treated as untrusted data.
- Drafts structured work plans through a loopback-only local Ollama model; no paid API or remote model endpoint is used by default.
- Focuses on agent-lane software tasks with USD/USDC rewards.
- Requires an explicitly escrowed reward and B-grade-or-better public payout evidence.
- Rejects closed/expired tasks, unsafe links, malformed expiry data, missing acceptance criteria, and risky categories.
- Ranks candidates and writes a Markdown shortlist.
- Includes a disposable Docker runner and a patch applier that checks diffs before applying them inside the isolated workspace; no network, no capabilities, a read-only root filesystem, resource limits and no host secrets.
- Does not claim gigs, bid, message clients, publish PRs, sign transactions, or spend money.

Jobbi is an index, not the payer. Verify original-board terms, claim process, acceptance criteria, and payout conditions. A listed or escrowed reward is not the same as money received.

## Run on macOS (Python 3.11+)
\`\`\`bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
pytest -q
ai-worker scan

# Inspect a public GitHub issue linked from a bounty listing
ai-worker inspect --url https://github.com/OWNER/REPO/issues/123

# Clone the issue's public repository into a disposable workspace
ai-worker prepare --url https://github.com/OWNER/REPO/issues/123 --workspace .ai-worker/sandboxes/task-123 --scratch-root .ai-worker/sandboxes

# Draft a structured plan with a local Ollama model (no API key)
ollama pull qwen2.5-coder:7b
ollama serve
ai-worker plan --url https://github.com/OWNER/REPO/issues/123

# Draft a code diff locally, save it, then apply it only in the isolated workspace
ai-worker patch draft --url https://github.com/OWNER/REPO/issues/123 --workspace .ai-worker/sandboxes/task-123 --diff-output task.patch
ai-worker patch apply --diff-file task.patch --workspace .ai-worker/sandboxes/task-123 --scratch-root .ai-worker/sandboxes
ai-worker sandbox run --workspace .ai-worker/sandboxes/task-123 --scratch-root .ai-worker/sandboxes -- pytest -q
\`\`\`

## Build the sandbox image
\`\`\`bash
docker build -f sandbox/Dockerfile -t ai-worker-sandbox:py311 .

# Run a command in a disposable, network-isolated workspace
ai-worker sandbox run --workspace .ai-worker/sandboxes/task-123 --scratch-root .ai-worker/sandboxes -- python -m compileall .
\`\`\`

After this PR is merged into the default branch, the read-only opportunity-scan workflow is scheduled every six hours and uploads a report plus SQLite ledger as a 14-day artifact. It can also be triggered manually from GitHub Actions. It never claims tasks or contacts clients.

Daily $5-$10 is a target, not a guarantee. The patch drafter proposes a diff; it does not publish or submit it. Review the diff and run the project's tests before any external submission. See docs/ARCHITECTURE.md and sandbox/README.md.
