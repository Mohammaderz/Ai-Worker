# AI-Worker

Safety-first agent-work pipeline. v0.2 discovers paid software tasks, applies strict payout/risk filters, ranks candidates, and stores an audit trail. Listed rewards are not earnings.

## Current scope
- Reads Jobbi's public read-only JSON feed.
- Requires USD/USDC, an explicitly escrowed reward, B-grade-or-better payout evidence, and the configured minimum reward.
- Rejects closed/expired tasks, unsafe links, malformed metadata, unknown claim availability, non-finite rewards, sensitive identity/credential tasks, and risky categories.
- Tracks payment state, payment rail, and acceptance method in SQLite.
- Inspects canonical public GitHub issue URLs read-only.
- Prepares shallow public-repository workspaces without forwarding host Git credentials.
- Drafts structured plans and unified diffs using a local Ollama model; no paid API or remote model endpoint is used by default.
- Validates and applies patches only inside a disposable, network-isolated Docker workspace.
- Does not claim gigs, bid, message clients, commit, push, publish PRs, sign transactions, or spend money.

Jobbi is an index, not the payer. Verify original-board terms, claim process, acceptance criteria, and payout conditions. A listed or escrowed reward is not the same as money received.

## Install and test (macOS, Python 3.11+)
When the Mac is available, run the guided setup from the repository root:

~~~bash
bash scripts/bootstrap-mac.sh
~~~

The script checks Python, Docker Desktop and Ollama, creates the virtual environment, installs the project, builds both Python and Node sandboxes, runs tests and asks before downloading the multi-GB local model. It does not install Homebrew or start paid services.

Manual setup:
~~~bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
pytest -q
ai-worker scan

# Build the disposable execution image once
docker build -f sandbox/Dockerfile -t ai-worker-sandbox:py311 .
~~~

## Optional local AI model
~~~bash
ollama pull qwen2.5-coder:7b
ollama serve
~~~

Keep Ollama running in that terminal. Run the following workflow commands in a second terminal. The model download uses disk space and the model's speed depends on your Mac's memory and hardware.

## One-command local task pipeline
After a fresh scan, the pipeline can resolve a currently eligible Jobbi gig by ID or accept a canonical public GitHub issue URL. It inspects the issue, prepares a clean workspace, asks local Ollama for a plan and patch, applies only low-risk proposals without unresolved questions, and runs isolated checks. It writes a review package containing issue.json, plan.json, proposal.json, proposal.patch, pipeline-result.json, REPORT.md and test logs.

~~~bash
# Refresh the feed and save eligible candidates
ai-worker scan --limit 1000

# Run one current eligible Jobbi gig (use its exact ID from the report/feed)
ai-worker pipeline --gig-id SOURCE:NATIVE_ID

# Or run a known public GitHub issue directly
ai-worker pipeline --url https://github.com/OWNER/REPO/issues/123
~~~

The current automatic coding path supports gigs whose original listing URL is a canonical public GitHub issue; other board URLs remain visible in the shortlist but need a dedicated adapter or manual issue URL. Python patches receive compileall and detected pytest checks. JavaScript/TypeScript patches receive isolated esbuild syntax transpilation; dependency-aware Node test suites are not run yet because project dependencies are not fetched from untrusted manifests. The pipeline never claims a task, sends a message, commits, pushes, opens a PR or submits work. High-risk plans, unresolved questions and blockers stop before patch application. Python tests run offline in the Docker sandbox; missing project dependencies are reported as test failures rather than installed from untrusted task instructions.

## Track real outcomes and payouts
The local outcome ledger records progress only after you manually claim or submit work. Only a manually recorded `paid` status with the actual received amount counts as income; listed rewards, accepted work and pending payments are not counted as earnings.

~~~bash
ai-worker ledger record --gig-id SOURCE:NATIVE_ID --status claimed
ai-worker ledger record --gig-id SOURCE:NATIVE_ID --status in_progress --actual-hours 1.5
ai-worker ledger record --gig-id SOURCE:NATIVE_ID --status submitted --actual-hours 2.0
ai-worker ledger record --gig-id SOURCE:NATIVE_ID --status accepted
ai-worker ledger record --gig-id SOURCE:NATIVE_ID --status paid --gross-received 25 --fees 1.25 --actual-hours 2.0
ai-worker ledger report
~~~

Hours are cumulative totals for that task, not per-command increments. The report separates gross received, fees, net received, acceptance rate, realized net/hour from paid-task hours, and average/median payout latency.

## Example issue workflow
~~~bash
# Inspect a public issue linked from a bounty listing
ai-worker inspect --url https://github.com/OWNER/REPO/issues/123

# Clone the issue's public repository into a new disposable workspace
ai-worker prepare --url https://github.com/OWNER/REPO/issues/123 --workspace .ai-worker/sandboxes/task-123 --scratch-root .ai-worker/sandboxes

# Draft a structured plan with the local model
ai-worker plan --url https://github.com/OWNER/REPO/issues/123

# Draft a code diff, save it, then apply it only inside the isolated workspace
ai-worker patch draft --url https://github.com/OWNER/REPO/issues/123 --workspace .ai-worker/sandboxes/task-123 --diff-output task.patch
ai-worker patch apply --diff-file task.patch --workspace .ai-worker/sandboxes/task-123 --scratch-root .ai-worker/sandboxes

# Run tests without network access inside the sandbox
ai-worker sandbox run --workspace .ai-worker/sandboxes/task-123 --scratch-root .ai-worker/sandboxes -- pytest -q
~~~

The generated patch is only a proposal. Review it and run the project's own tests before considering any external submission.

## Scheduled opportunity scans
After this PR is merged into the default branch, a read-only GitHub Actions workflow will scan every six hours and upload a report plus SQLite ledger as a 14-day artifact. It can also be triggered manually from GitHub Actions. It never claims tasks or contacts clients.

## Development roadmap
- [docs/MASTER_EXECUTION_TRACKER.md](docs/MASTER_EXECUTION_TRACKER.md) is the durable cross-conversation backlog, priority order, current work status, PR integration queue, and definition-of-done register.
- [docs/PRODUCTION_INCOME_ENGINE_ROADMAP.md](docs/PRODUCTION_INCOME_ENGINE_ROADMAP.md) contains the detailed architecture, phased execution specification, safety requirements, and commercial proof criteria.
- See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [sandbox/README.md](sandbox/README.md).
