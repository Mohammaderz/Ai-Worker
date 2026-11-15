# AI-Worker: Competitive Product & Engineering Roadmap

**Status:** Proposed product direction, based on repository review and public competitor research (2026-11-15).  
**Baseline:** `improve-issue-context` at `c950421f91b1212893d418aac5152d3d4e86b6ae`.  
**Rule:** This document is a plan, not a claim that the listed capabilities are implemented.

## 1. Product thesis

Build a trustworthy, model-flexible software-engineering agent that turns a well-scoped GitHub issue into a verified, reviewable change set and (only with explicit authorization) a pull request.

The differentiator is **evidence-first engineering**: the agent must show what it inspected, why it changed each file, which checks ran, what passed or failed, what remains uncertain, and how much the task cost.

Do not compete by claiming to be universally smarter than every frontier model. Compete on measurable task completion, safe execution, review quality, recoverability, cost transparency, and excellent GitHub workflow integration.

## 2. Current repository reality

The current repository is more than a blank coding-agent scaffold. It already contains:

- A read-only Jobbi opportunity scout with strict reward, escrow, payout-evidence, expiry, URL, and risk filters.
- A local Ollama issue planner and structured patch drafter.
- GitHub issue inspection and shallow public-repository workspace preparation.
- Patch validation/application in a disposable Docker sandbox.
- Python compile/pytest checks and JavaScript/TypeScript syntax transpilation.
- SQLite opportunity and realized-payout tracking.
- GitHub Actions tests and a scheduled opportunity scan.

Important limitations visible in the current design:

- The pipeline is primarily local and Ollama-oriented; there is no provider-neutral model router yet.
- Repository context is a bounded file allowlist/ranking strategy, not a full semantic index or dependency graph.
- Node projects receive syntax transpilation, not dependency-aware test execution.
- The Docker sandbox is explicitly a baseline, not a production hostile-code boundary.
- There is no persistent multi-step task manager, resumable job queue, independent reviewer, benchmark harness, or customer-facing SaaS control plane.
- The product currently combines two related but distinct ideas: finding paid software opportunities and safely completing software tasks. Keep these as separate modules with separate success metrics; do not let bounty qualification logic constrain ordinary GitHub issue solving.

## 3. Competitive landscape and lessons

Evaluate at least these products continuously:

- **Claude Code:** terminal/IDE/web workflows, configurable permissions, hooks, tools and long-running tasks. Lesson: strong tool-use workflow and explicit permission boundaries.
- **OpenAI Codex:** local and cloud software-engineering tasks. Lesson: isolated task execution, clear task lifecycle and reviewable outcomes.
- **Cursor:** codebase search, multi-file editing, terminal execution, subagents and cloud agents. Lesson: excellent developer experience, delegation and fast iteration.
- **GitHub Copilot coding agent:** native GitHub issue-to-PR workflow and GitHub Actions integration. Lesson: minimize friction where work already happens.
- **Devin:** delegated, long-running engineering tasks in a managed environment. Lesson: persistence, asynchronous progress and useful status reporting.
- **OpenHands:** open architecture and extensible runtime. Lesson: provider/runtime flexibility and self-hosting.
- Also track Cline, Aider, OpenCode, Gemini CLI/Jules, SWE-agent and emerging agents.

Competitor feature pages are not independent proof of quality. Treat vendor claims, third-party rankings and benchmark scores separately. Record publication date, source, methodology and whether a claim was independently reproduced.

## 4. Product pillars

### P0 — Trust, safety and reproducibility

- Treat issues, comments, repository files, test output and model output as untrusted data.
- Use explicit capability policies: read, write, execute, network, credentials and external publication are separate permissions.
- Keep task execution isolated; never mount host home directories, SSH agents, Docker socket or cloud credentials into an untrusted task container.
- Move production execution toward disposable VM/microVM isolation, immutable image digests, resource quotas, egress policy and cleanup verification.
- Add secret scanning, dependency and license checks, patch path validation, symlink/submodule protections, and audit events.
- Require explicit human approval before claim, bid, message, commit, push, PR publication, merge, deployment or payment-related action.
- Make all state transitions and tool calls auditable and replayable where possible.

### P1 — Reliable issue-to-change workflow

- Intake and normalize issue, acceptance criteria, labels, comments and linked context without following arbitrary instructions.
- Ask for clarification when requirements are materially ambiguous; do not hallucinate acceptance criteria.
- Build a repository map: manifests, entry points, tests, ownership hints, dependency graph and relevant code paths.
- Create an explicit plan with risks, expected files, test strategy and stop conditions.
- Draft minimal patches with bounded scope.
- Apply only in disposable workspaces; preserve the original checkout.
- Run the most relevant tests first, then broader checks based on change impact.
- Produce a review packet containing evidence, diff summary, logs, test coverage and unresolved risks.

### P2 — Independent quality system

- Separate implementer and reviewer roles; reviewer receives the issue, original diff and evidence, not the implementer's hidden reasoning.
- Add static analysis, formatting, type checks, dependency checks and secret scanning where project tooling permits.
- Detect flaky tests and distinguish infrastructure failures from code failures.
- Add regression-oriented test generation and mutation/coverage signals where practical.
- Never equate "command exited 0" with "issue solved"; evaluate acceptance criteria explicitly.
- Block automatic publication when evidence is incomplete or risk exceeds policy.

### P3 — Model and cost intelligence

- Introduce provider adapters behind a common interface; retain local Ollama as a first-class privacy/cost option.
- Route by task type, context size, latency, quality history, privacy policy and budget.
- Support fallback only when policy allows; record provider/model/version and token/cost usage.
- Add prompt/context caching and context compaction with provenance.
- Track cost per attempt, cost per verified success, latency and retry rate.
- Do not hard-code a model as "best"; benchmark models on our own task distribution.

### P4 — Persistent orchestration

- Add durable task state, idempotent steps, retries with bounded budgets, cancellation and resume after process/worker restarts.
- Use a queue and worker model only after local single-task correctness is strong.
- Add specialist agents only where they have independent inputs and measurable value: researcher, planner, implementer, test engineer, reviewer and security auditor.
- Keep a deterministic policy engine outside model control; agents may propose actions but cannot grant themselves permissions.
- Add concurrency limits, per-user budgets and workspace lifecycle cleanup.

### P5 — GitHub and developer experience

- Support repository installation/authorization with least-privilege scopes.
- Add webhook-driven issue intake, status updates and draft PR creation behind approval.
- Show live task stages, evidence, diffs, logs, costs and human decisions.
- Add CLI first, then web dashboard and team controls.
- Support private repositories only after credential isolation and authorization design are reviewed.
- Keep an API and plugin/tool interface for integrations.

### P6 — Commercial readiness

- Separate open-source/core self-hosted capability from hosted service value.
- Test pricing against measured compute/model cost, not guesses.
- Potential plans: local/self-hosted, individual, team and enterprise; do not launch paid tiers before reliability and unit economics are known.
- Measure activation, repeat usage, verified resolution rate, PR acceptance, retention, support burden and gross margin.
- Do not count listed bounty rewards as revenue; only realized payments belong in income metrics.

## 5. Architecture target

Preferred logical components:

1. **API/CLI gateway** — authentication, request validation, rate limits and user intent.
2. **Task orchestrator** — durable state machine, budgets, retries, approvals and cancellation.
3. **GitHub adapter** — issues, repositories, comments, branches and PRs with least privilege.
4. **Repository intelligence** — file map, symbol/reference search, manifests, tests and bounded context retrieval.
5. **Model gateway** — provider adapters, model routing, structured outputs and usage metering.
6. **Agent roles** — researcher, planner, implementer, test engineer, reviewer and security reviewer.
7. **Execution runtime** — isolated ephemeral workspaces with no ambient credentials.
8. **Verification engine** — project-aware tests, static analysis, security and acceptance-criteria evaluation.
9. **Evidence/audit store** — append-only events, artifacts, provenance and reproducible reports.
10. **Product surface** — CLI, GitHub status/PR and eventually a web dashboard.

Keep the current modules working while introducing interfaces. Avoid a premature rewrite or microservice explosion. Start as a well-separated Python application; extract services only when scale or isolation requirements justify it.

## 6. Benchmark and release gates

Create a reproducible evaluation set of real, legally usable issues across bug fixes, tests, docs, refactors, features and dependency updates. Pin repository commit, issue snapshot, environment, model and test commands.

For every run record:

- task and repository identifiers, commit SHA and task category;
- model/provider/version, prompt/config version and context sources;
- patch size, files changed, tool calls, retries and wall-clock time;
- test commands, exit codes, logs and coverage deltas where available;
- security findings, reviewer findings and human intervention;
- total cost and cost per verified success.

Primary metrics:

- Verified issue-resolution rate (not just patch generation rate).
- Acceptance-criteria pass rate.
- PR acceptance/merge rate, reported separately from automated test pass rate.
- Regression and revert rate.
- Security findings introduced.
- Human minutes required per task.
- Median/P95 completion time.
- Cost per verified success.
- Recovery success after interrupted runs.

Compare against relevant agents on the same tasks and conditions where possible. Stratify results by task type and difficulty. Never compare cherry-picked demos or vendor-reported numbers as if they were controlled experiments.

Release gates:
- No unresolved critical/high security issue.
- No unauthorized network or credential access from task execution.
- All changes traceable to a task and evidence packet.
- Deterministic tests pass on supported environments.
- Failure modes stop safely and preserve logs.
- Human approval gates are enforced for external side effects.
- Benchmark results and limitations are published honestly.

## 7. Phased implementation order

1. **Baseline audit:** inspect every module, workflow, dependency, permission and test; map actual behavior and gaps.
2. **Reliability foundation:** typed task state, structured errors, artifact provenance, idempotency and end-to-end integration tests.
3. **Repository intelligence:** improve context selection with manifests, test discovery, symbol/reference search and relevance evaluation.
4. **Verification/review:** independent review, acceptance checks, static analysis and language-aware test adapters.
5. **Runtime hardening:** threat model, sandbox tests, immutable images and eventually VM isolation.
6. **Model gateway:** provider interface, routing, budgets, fallback and cost telemetry.
7. **Persistent orchestration:** resumable queue, cancellation, bounded retries and specialist agents.
8. **GitHub delivery:** least-privilege app integration, draft PR flow and approval controls.
9. **Benchmark lab:** public reproducible results and regression gates.
10. **Commercial product:** onboarding, dashboard, billing, support, privacy and unit economics.

## 8. Immediate next engineering actions

Before broad feature work:

1. Finish and review PR #8; do not merge automatically.
2. Audit the complete current source and test suite locally.
3. Run full tests and CI, including Docker/Node smoke tests.
4. Add an architecture decision record for the product boundary: coding agent core vs. optional paid-opportunity scout.
5. Add end-to-end fixtures for at least one Python bug issue and one non-Python issue.
6. Build a first benchmark runner and store baseline results before optimizing.
7. Prioritize the highest-risk correctness/security gaps found by the audit.

## 9. Research references

- Claude Code product: https://claude.com/product/claude-code
- Cursor Agent docs: https://cursor.com/help/ai-features/agent
- Cursor Agent overview: https://prod.cursor.com/docs/agent/overview
- Claude platform agent capabilities: https://platform.claude.com/docs/en/build-with-claude/overview
- Encore 2026 coding-agent comparison: https://encore.dev/articles/best-ai-coding-agents
- Task-stratified PR acceptance study (2026): https://arxiv.org/abs/2602.08915
- Post-merge maintenance study (2026): https://arxiv.org/abs/2609.17598
- Agent comparison and evidence grades: https://www.agentclearinghouse.org/compare/coding-agents.html

Research is a living input. Re-verify vendor capabilities, pricing, benchmark methodology and dates before making product or purchasing decisions.
