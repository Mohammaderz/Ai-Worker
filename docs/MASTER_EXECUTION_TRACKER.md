# AI-Worker — Master Execution Tracker

**Last reviewed:** 2026-11-17  
**Status:** Active engineering backlog; this document is the durable execution register.  
**Authority:** This tracker coordinates the product roadmap, architecture document, existing feature PRs, and local work. It does not claim planned features are implemented.

## 1. Strategic priority — two coordinated paths

The product has two coordinated paths, with an explicit and non-negotiable priority order:

1. **Primary: Autonomous Engineering Agent.** This is the core product and receives first priority for architecture, engineering time, reliability work, and release readiness. It must independently deliver value on authorized software projects: understand repositories and requirements, investigate, plan, implement bounded changes, execute project-aware checks, obtain independent review, perform controlled repairs, and produce evidence-backed handoffs.
2. **Secondary: Opportunity & Revenue Engine.** This discovers and qualifies paid work, estimates risk and expected net economics, tracks the work lifecycle, and records verified receipts. It is a commercial layer built around the engineering core, not a prerequisite for the core to be useful.

**Priority rule:** do not delay, weaken, or over-couple the Autonomous Engineering Agent to build marketplace discovery, bounty automation, or revenue analytics. Keep explicit interfaces between the paths. The core must remain useful for authorized private projects, company engineering teams, and other software-work settings even when no paid-opportunity source is connected.

**Product success:** first prove reliable end-to-end engineering outcomes; then prove repeatable customer value and positive realized unit economics. Neither technical sophistication nor advertised rewards alone prove product-market fit or revenue.

## 2. Product objective

Build a reliable, secure, model-agnostic autonomous software-work agent that can discover a task, understand its requirements and repository, plan and implement a bounded change, run meaningful project-aware checks, independently review the result, repair justified defects, and prepare an evidence-backed delivery package.

The first proving ground is GitHub issue-to-change work. GitHub is not the product boundary: the architecture must eventually support other authorized task sources and private projects through modular connectors.

The commercial objective is verified accepted work and actual received revenue with positive, measured unit economics—not task volume, advertised rewards, model activity, or unverified success claims.

## 3. Product boundaries and non-negotiable rules

- Keep the **Autonomous Engineering Agent (primary product)** independent from the **Opportunity & Revenue Engine (secondary commercial layer)**. Integrate only through explicit contracts; paid-opportunity qualification must never constrain or delay ordinary authorized engineering work.
- Treat issue text, repository files, comments, test output, web pages, and model output as untrusted data, never as policy.
- Separate read, write, execute, network, credential, and external-publication permissions.
- Task execution is offline by default. Dependency preparation must be a separate controlled stage with lockfile validation, trusted registry policy, egress enforcement, quotas, provenance, and no arbitrary install scripts.
- Never mount host credentials, home directories, SSH agents, cloud credentials, or the Docker socket into untrusted task execution.
- Require explicit human approval before claiming, bidding, messaging, committing, pushing, publishing, merging, deploying, spending, or signing.
- Keep budgets for time, tokens, retries, files, output, disk, processes, CPU, memory, and network.
- Distinguish passed, failed, skipped, unavailable, and not-run checks. A skipped check is not a pass.
- Distinguish advertised, escrowed, accepted, pending, and actually received money. Only verified receipts count as income.
- No capability is complete until implementation, tests, failure cases, security review, documentation, and evidence are recorded.

## 4. Current state — evidence-based snapshot

### Repository and integration

- Default branch: `main`.
- The active local engineering line reported for this work is `feat/enclosing-scope-definition-expressions`, with open draft PR #30.
- Open PRs #5–#30 include several independent main-targeting changes and long stacked chains. They must be integrated deliberately; they must not be merged or retargeted as a batch.
- PR #9 contains the production income-engine execution specification. This tracker complements that specification with a single prioritized execution register and a current work queue.
- The local Mac working tree contains uncommitted changes and new Node QA files. Those changes are not represented by the GitHub branch until explicitly committed and pushed. Preserve them; do not reset, clean, overwrite, or force-push.

### Existing capability baseline (main/docs inspection)

- Read-only opportunity discovery and strict risk/payout qualification exist for current supported sources.
- GitHub issue inspection, shallow public-repository preparation, local Ollama planning/patch drafting, disposable Docker execution, and SQLite outcome tracking exist.
- Python checks and JavaScript/TypeScript syntax transpilation exist in the documented baseline.
- The current documented pipeline does not yet run dependency-aware Node test/build suites.
- The Docker sandbox is a development baseline, not a proven hostile multi-tenant boundary.
- A production-grade durable queue, operational multi-model gateway, bounded repair orchestration, multi-agent coordination, and commercial control plane are not established as complete capabilities.

### Local Node QA work (not yet published to GitHub)

- New local module: `src/ai_worker/node_qa.py`; new tests: `tests/test_node_qa.py`.
- Reported focused validation: sandbox + Node QA tests **27 passed**; CLI tests **7 passed**. These are focused local runs, not a current full-suite or GitHub CI result.
- Current safe execution decision: run scripts offline only when no external dependencies are declared. Do not enable Docker bridge networking and describe it as npm-only; it is not an egress allowlist. Projects requiring external packages remain explicitly blocked until controlled dependency preparation exists.
- Pipeline integration, accurate report/manifest states, CLI cleanup, regression coverage, and a full-suite run remain to be completed and verified.

## 5. Prioritized execution backlog

Priority is based on dependency order and risk reduction, not novelty.

### P0 — Integration control and reliable engineering core

**P0.1 — Audit and consolidate existing PR work**
- Inventory each open PR's base, parent, dependencies, changed files, tests, CI status, and overlap.
- Preserve all useful commits and local uncommitted work.
- Identify a small number of coherent integration batches; avoid a chain of tiny PRs.
- Re-run CI on the exact consolidated head and target base.
- Do not merge to `main` without explicit human approval.

**Exit evidence:** reviewed PR dependency graph, documented merge order, no lost changes, current passing CI on each integration candidate.

**P0.2 — Finish project-aware Node QA**
- Detect npm project metadata, package manager, lockfiles, scripts, and dependency requirements safely.
- Run dependency-free npm test/build scripts in the network-disabled sandbox.
- Do not install dependencies until a separate preparation service enforces registry-only egress, lockfile integrity, resource limits, provenance, and install-script policy.
- Record every check as passed/failed/skipped/unavailable/not-run with command, exit code, bounded log path, and reason.
- Cover invalid manifests, malformed/conflicting lockfiles, install-blocked cases, test/build failures, and network isolation.

**Exit evidence:** focused and full test suites pass; test/build commands and skipped reasons are accurately represented in result, report, and manifest; no unrestricted network is enabled.

**P0.3 — Sandbox threat-model and hardening**
- Review Docker flags, mounts, UID/GID, capabilities, read-only root, PID/CPU/memory/time/output/disk limits, cleanup, and image provenance.
- Add adversarial tests for symlinks, path traversal, metadata/private-network access, process/resource exhaustion, credential exposure, and workspace boundary violations.
- Pin images by digest in production configurations.
- Evaluate disposable VM/microVM isolation before accepting hostile multi-tenant workloads.

**Exit evidence:** written threat model, adversarial test results with sample counts, known limitations, and a documented runtime decision.

**P0.4 — Repository Intelligence**
- Build a bounded repository map from manifests, entry points, symbols/references, tests, ownership hints, dependency graph, and relevant history.
- Use issue-aware context selection plus explicit-path pre-read and multi-step investigation.
- Persist a versioned per-repository project brief/memory with provenance, freshness, and invalidation rules.
- Prevent stale memory from overriding current repository evidence.

**Exit evidence:** benchmarked improvement in relevant-context recall and issue-resolution quality without exceeding context/time budgets.

### P1 — Independent quality and controlled repair

**P1.1 — Operational independent reviewer**
- Separate implementer and reviewer contexts; reviewer receives issue, diff, repository evidence, and test evidence.
- Require structured, versioned findings with exact changed-file/line references and severity.
- Fail closed on malformed output, reviewer errors, critical/high findings, or unverifiable locations.
- Deterministic checks remain independent of model judgement.

**P1.2 — Bounded repair loop**
- Allow a small configurable number of repair attempts (initial cap: 3).
- Re-run affected tests and independent review after each repair.
- Stop on no progress, scope expansion, critical security issues, budget exhaustion, repeated failures, or human-required ambiguity.
- Never weaken or delete tests merely to get a green result.

**P1.3 — Evidence-backed delivery package**
- Include issue/acceptance criteria, repository context provenance, plan, changed-file summary, patch hash, commands, environment/image identity, test results/logs, reviewer findings, unresolved risks, and estimated cost.
- A green command is not proof that acceptance criteria were met.
- External publication remains a human-approved action.

**Exit evidence:** reproducible fixture-repository runs, regression tests, fail-closed review behavior, bounded repair, and complete review bundles.

### P2 — Economic engine and model intelligence

**P2.1 — Economic opportunity scoring**
- Separate eligibility gates from ranking.
- Use calibrated historical cohorts for acceptance and payment probabilities; never let an LLM invent probabilities.
- Compute expected net value and expected net hourly value using stage-weighted costs, fees, model/runtime costs, deadline, payout latency, and uncertainty.
- Show sample size, cohort, time window, confidence/uncertainty, and reasons.
- Preserve the distinction between fixed rewards and bid budgets.

**P2.2 — Correct event-based financial evidence**
- Use append-only lifecycle events with provenance and compensating corrections.
- Enforce valid transitions and idempotency.
- Keep submitted-work acceptance denominator separate from pre-submission rejection.
- Preserve previously recorded fees when later updates omit fee values.
- Track partial payment, refunds, disputes, actual hours, model costs, and payout latency.

**P2.3 — Model-agnostic gateway and multi-model collaboration**
- Define provider-neutral interfaces for local Ollama and optional remote providers.
- Support configurable model roles: planner, implementer, reviewer, and repair agent.
- Initial experimentation should compare Qwen and DeepSeek as distinct candidate roles; do not assume model-family diversity guarantees independence.
- Add OpenAI, Claude, Gemini, and other providers only through explicit opt-in, configured credentials, privacy policy, and budget controls.
- Route by task class, observed benchmark quality, latency, context needs, privacy, and cost—not brand preference.
- Record model/provider/version, prompt/template version, token usage, latency, retries, and outcome.
- Keep hard spending ceilings and local-first fallback.

**Exit evidence:** reproducible benchmark shows a measurable quality/cost/latency improvement over the single-model baseline.

### P3 — Durable autonomous operations and expansion

**P3.1 — Durable execution**
- Implement task state machine, idempotency keys, checkpoints, bounded retries, cancellation, timeout, concurrency locks, crash recovery, safe resume, and structured audit events.
- Keep state durable before attempting always-on cloud deployment.

**P3.2 — Multi-agent orchestration**
- Start with modular roles coordinated by one orchestrator; do not prematurely split into microservices.
- Delegate research, planning, implementation, QA, review, and economics only where parallelism improves measured outcomes.
- Use shared task contracts, artifact references, budgets, and stop conditions.

**P3.3 — Connector framework**
- Keep GitHub as the first proving ground.
- Add GitLab, Bitbucket, Jira, authorized private repositories, bounty APIs, and freelance/task marketplaces through isolated adapters.
- Each adapter must own terms-of-service review, authentication scope, pagination, rate limits, freshness, deduplication, coverage, error handling, and auditability.
- Do not imply a source is fully covered without a defined recall/coverage measurement.

**P3.4 — Benchmark and product operations**
- Maintain versioned benchmark fixtures and reproducible runs.
- Measure task resolution, acceptance, paid conversion, realized net/hour, reviewer recall/false positives, regressions, human minutes, latency, cost, and source health.
- Every metric must specify formula, sample size, cohort, time window, uncertainty, and source.
- Build dashboards only as read-only projections of authoritative records.
- Add multi-user isolation, quotas, metering, retention, billing, support, backups, and SLOs only after the core is reliable.

**P3.5 — Commercial proof**
- Complete one authorized real task from discovery through verified acceptance and actual receipt.
- Account for all labor, model, runtime, platform, and payment fees.
- Report positive or negative unit economics honestly; no revenue guarantee.

## 6. Multi-PR integration checkpoint

The following is a coordination snapshot, not an approval to merge:

| PR | Scope | Current dependency/handling |
|---|---|---|
| #5 | Marketplace discovery + repository QA profile | Targets main; inspect and validate before integration |
| #6 | Payout-evidence source priorities | Targets main; inspect overlap with #5 |
| #7 | Opportunity portfolio selection | Stacked on #6; integrate only after its base is reconciled |
| #8 | Issue-aware repository context | Targets main; independent candidate, verify current CI |
| #9 | Production income-engine roadmap | Documentation PR; this tracker is being added here |
| #10 | Reviewer/QA contracts | Stacked on #5; contracts are not yet an operational reviewer |
| #11–#30 | Reviewer and deterministic security-analysis evolution | Long stacked chain; audit ancestry and test each coherent integration unit; do not bulk-retarget or merge |

Before any PR merge: verify exact head SHA, base SHA, changed-file overlap, current CI, local worktree status, and regression impact. Historical green checks are not sufficient.

## 7. Immediate execution queue

1. Finish and validate the current local Node QA integration; preserve the local worktree and publish only after a local status/diff checkpoint.
2. Complete the PR integration DAG audit, including #5–#30, and decide the smallest safe integration batches.
3. Strengthen the primary Autonomous Engineering Agent: Repository Intelligence, deterministic project-aware QA, sandbox hardening, and evidence-backed execution.
4. Make the independent reviewer operational and connect it to the pipeline.
5. Implement the bounded repair loop and reliable delivery package.
6. Build a benchmark baseline before model-routing optimization; add the Qwen/DeepSeek comparative workflow and then the provider-neutral gateway.
7. Add durable orchestration and recovery before cloud/always-on execution.
8. In parallel only where it does not slow the core, validate commercial demand and improve the secondary Opportunity & Revenue Engine: opportunity scoring, lifecycle ledger, and verified payout evidence.
9. Expand connectors and multi-agent execution only after the core reliability/security gates pass.
10. Prove customer value and unit economics with real accepted work and verified receipts; revise the commercial path based on measured evidence.

## 8. Definition of done and status protocol

Every backlog item must have:
- an owner/role, priority, dependencies, scope, and explicit non-goals;
- acceptance criteria and failure/stop conditions;
- implementation and unit/integration/regression/adversarial tests as applicable;
- current CI on the exact candidate commit;
- security, resource, privacy, and cost review;
- documentation and known limitations;
- evidence links and a truthful status.

Use only these statuses: **proposed**, **planned**, **in progress**, **blocked**, **implemented-unverified**, **verified**, **deferred**.

A task moves to **verified** only after its acceptance criteria and required tests/CI pass on the exact code being discussed. Do not mark work complete because a branch, PR, design document, or test stub exists.

When a new product/engineering idea is accepted, record it here (or as a linked GitHub issue) with its rationale, priority, dependency, and acceptance criteria before starting unrelated work. Update this tracker when scope or evidence changes. Keep this file as the durable cross-conversation memory of the project.

## 9. Explicit non-goals for the current stage

- No autonomous bidding, claiming, messaging, external submission, merge, payment, or wallet signing.
- No unrestricted network access from task execution.
- No unbounded repair loops or unlimited agent spawning.
- No premature microservices or always-on cloud deployment before durability/security/cost gates.
- No all-language support at once.
- No revenue, acceptance, quality, or security claims without measured evidence.


## 9. Live integration and payout-readiness audit — 2026-11-17
Fresh GitHub verification:
- `main` head is `6f89b6dca43ba635e53ec9b2281a7e03814034fa`.
- PRs #5–#30 remain open/unmerged at this checkpoint.
- #5 targets main (ready for review); exact-head run #396 passed all workflow steps.
- #6 targets main (draft); head advanced to `437cd4b6764ad755d614a8d3a14ab56c7b7a87e4` for fee preservation; exact-head run #593 was in progress when checked.
- #7 is stacked on #6 but its base SHA `9298e964c445ae6c1e1506ec7d07b1fabdbe7e0b` is behind the new #6 head; do not integrate until synchronized and revalidated.
- #8 targets main and exact-head run #389 passed.
- #9 targets main and exact-head run #586 passed.
- #10 is stacked on #5 and exact-head run #409 passed.
- #11 is based on `product/competitive-roadmap`, a branch not represented by an open PR in this queue; ancestry remains unresolved.
- #22 and #30 exact-head runs #534 and #575 passed. These are spot checks, not evidence that every PR #12–#29 has current green CI.
- #28 and #29 are parallel children of #27; #30 extends #29.
- The local Mac Node QA work described in earlier tracker notes is still not accessible here. Do not overwrite or claim it is published/tested.
- `docs/PROJECT_BRIEF.md` is absent from main at this checkpoint; GitHub returned 404.

### Payout ledger bug fixed on PR #6
Commit `437cd4b6764ad755d614a8d3a14ab56c7b7a87e4` changes omitted fees from implicit zero to `None` and updates SQL to preserve existing fees with `COALESCE`. Explicit `--fees 0` remains a deliberate correction. Regression tests cover storage behavior and CLI default handling. Exact-head CI run #593 was still running when recorded; do not mark verified until it completes successfully. PR #7 now requires base synchronization.

### Bounty integration decision from current official docs
- Official API: https://docs.trybounty.ai/agents/raw-interface/ and OpenAPI: https://api.trybounty.ai/openapi.json
- Terms updated 2026-11-02: https://trybounty.ai/terms-and-conditions
- `payout_cents` is the Agent's actual payout field; bid-flow listings have it null until a bid is accepted. `budget_cents` is only guidance and deprecated `amount_cents` is the buyer's all-in price, not Agent revenue.
- Claim-flow Bounties are funded fixed-payout work, but settlement still depends on verification/review and may be disputed/refunded.
- Stripe Connect is required for payout receipt; Bounty holds earnings until setup is ready. Country support is conditional on Stripe approval, and terms warn non-US payouts may not be available even in listed countries.
- The current OpenAPI list-item schema has no public listing URL field. Do not invent a Bounty page route or insert an API endpoint as if it were a public task link.
- Therefore the current TryBounty adapter remains discovery-only. It must not pass into common `Gig` qualification or the coding pipeline until source URL provenance, payout readiness, claim-vs-bid economics, and risk/acceptance evidence are represented explicitly.

### Required next steps
1. Recheck #6 run #593 and its exact head; if green, synchronize #7 without force-push and rerun its CI.
2. Keep PR integration gated by dependency DAG, changed-file overlap, exact-head CI, and explicit human merge approval.
3. Separate task funding/escrow evidence from operator payout-account readiness in the opportunity model.
4. Add a typed needs-review state for direct-source records whose public URL or payout readiness is unknown; do not force them into the existing strict `Gig` path.
5. Continue project-aware Node QA and sandbox hardening only after preserving/checkpointing the inaccessible local Mac work.
