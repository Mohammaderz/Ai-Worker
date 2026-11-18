# AI-Worker — Production Income Engine Execution Plan

> Status: execution specification, not a claim of implementation or production readiness.
> Canonical tracker: https://github.com/Mohammaderz/Ai-Worker/issues/31

## Product objective

Build a reliable, evidence-driven software-work income engine. Success means completing legitimate work, delivering accepted results, receiving real payments, and demonstrating positive realized net hourly income—not merely finding listings, generating patches, or passing internal tests.

## Non-negotiable operating rules

- Preserve existing behavior and user changes; inspect before modifying.
- Treat issue text, repository files, comments, webpages, model output, and dependency scripts as untrusted data.
- No claim, bid, message, submission, commit/push to third-party repositories, PR publication, merge, deployment, payment, or transaction signing without explicit human authorization.
- No secrets, host credentials, SSH agents, Docker socket, or unrelated project data inside task execution.
- No unbounded network, compute, disk, process, retry, token, or spend budgets.
- No fabricated trust, acceptance, payment, income, benchmark, coverage, or security metrics.
- A feature is not complete until code, tests, CI, failure cases, documentation, and acceptance evidence are recorded.

## Architecture: modular roles, not premature microservices

Implement the following as explicit modules/contracts coordinated by one orchestrator. Split into separate processes/services only when measured scaling or isolation requirements justify it.

1. **Opportunity Hunter** — source adapters, pagination, rate limits, deduplication, freshness/expiry, coverage and scan-health records.
2. **Trust & Risk Analyzer** — evidence-backed trust and payment assessment, scam indicators, contract/legal/security risks, sensitive-data/access requests.
3. **Project Intelligence** — issue/document/repository analysis, language/framework/dependency/architecture mapping, complexity/time estimate, uncertainty and structured Project Brief.
4. **Economic Decision Engine** — gross reward, fees, model/runtime/infrastructure costs, estimated hours, acceptance and conditional payment probability, payout latency, expected net value and expected net hourly value.
5. **Developer** — bounded plans, scoped multi-file patches, architectural consistency, traceable changes and tests.
6. **QA** — project-aware syntax, type, lint, build and actual test execution; acceptance-criteria checks; regression checks.
7. **Independent Reviewer** — separate review context/model where useful, deterministic checks, evidence-backed findings, exact changed-file/line validation, security and architecture review.
8. **Delivery & Finance** — human-approved delivery preparation, lifecycle tracking, actual receipt/fees/costs/hours and auditable outcome records.

## Opportunity and payment states

- `Verified`: sufficient current evidence for identity/source, payment terms and payout path.
- `Needs Review`: incomplete or ambiguous evidence without a decisive fraud indicator; retain for human review and never silently discard.
- `Rejected`: concrete evidence of fraud, unsafe terms, prohibited activity, invalid/expired opportunity, or no credible payment path.
- Record evidence source, timestamp, grade/confidence, rationale, reviewer and expiry. USD/USDC, escrow and B-grade evidence are useful controls, not proof that every individual listing will pay.

## Economic model

Use calibrated historical data only. Never let an LLM invent numeric probabilities.

`Expected Net Value = P(acceptance) × P(payment | acceptance) × Net Reward − stage-weighted expected costs`

`Expected Net Hourly = Expected Net Value / Estimated Hours`

- Keep acceptance and payment probabilities separate and show sample size, cohort, time window and uncertainty.
- Model costs by lifecycle stage; do not charge later-stage costs to opportunities rejected earlier.
- Separate advertised, escrowed, accepted, invoiced and actually received amounts.
- Track partial payments, refunds, disputes, fees, currency and payout latency.
- Rank by expected net value/hour subject to hard trust, eligibility, deadline and budget gates; explain every score.
- If evidence is insufficient, show unknown/Needs Review rather than a made-up probability.

## QA and language support

Use capability profiles and explicit check states: `passed`, `failed`, `skipped`, `unavailable`, `not_run`. Distinguish code failures from infrastructure failures and preserve command, exit code, bounded logs and environment identity.

Prioritize Python and JavaScript/TypeScript/Node first, then expand based on real opportunity volume and benchmark results. Detect manifests, lockfiles, package managers, scripts, test frameworks, type checks and build commands. Transpilation alone is not TypeScript type checking or project testing. Install dependencies only in a separate controlled preparation stage with pinned/locked inputs, trusted registries, script policy, network allowlists, quotas and provenance. Run task code/tests offline by default.

## Sandbox security

Current Docker isolation is a development baseline, not a guarantee against hostile multi-tenant code. Harden with non-root execution, read-only base image, disposable workspace, no host mounts except narrowly scoped task data, no Docker socket, no credentials, network disabled during execution, CPU/RAM/PID/time/output/file/disk quotas, syscall filtering, AppArmor/SELinux where supported, metadata/private-network blocking, image digests, cleanup and audit logs. Threat-model and adversarially test escape paths. Evaluate disposable VM/microVM isolation (e.g. Firecracker) before commercial hostile-code workloads.

## Developer → Validator → QA → Reviewer → Repair loop

1. Build a bounded repository context and plan.
2. Validate plan scope and acceptance criteria.
3. Draft patch; validate paths, diff structure and changed-file scope.
4. Run deterministic checks and project-aware QA.
5. Run independent review with evidence-linked findings.
6. On fixable findings, allow a bounded repair attempt (initial cap 3; increase to 5 only when measured benefit justifies cost).
7. Re-run all affected checks and review; never weaken/delete tests to obtain green status.
8. Stop on critical security findings, scope expansion, repeated non-progress, budget exhaustion or uncertainty requiring human input.
9. Persist every attempt, patch hash, model/version, checks, findings and decision.

## Ledger and lifecycle correctness

Use append-only lifecycle events with timestamps and provenance; derive projections/reports from events. Preserve corrections as compensating events rather than erasing history.

Track discovered, screened, qualified, human-approved/claimed, in-progress, submitted, accepted/rejected, paid/partially-paid/refunded/disputed and closed states, plus discovery/review/start/finish/submission/decision/payment timestamps, gross, fees, net, actual hours, model/API/runtime costs, model/version, patch and test-report identifiers, evidence and failure reason.

- Acceptance denominator includes only tasks with valid `submitted_at`; pre-submission rejection is excluded, post-submission rejection is included.
- Re-recording payment without a new fee value must preserve the prior fee.
- Validate legal state transitions and idempotency; never infer a submission from a generic rejected status.
- Distinguish estimated from realized values and never label pending/accepted/advertised reward as income.

## Model gateway and learning

Create provider-neutral interfaces for Ollama/local models and optional GPT, Claude and Gemini APIs. API providers require explicit opt-in and configured credentials. Route by task complexity, context needs, observed quality, latency, privacy and budget. Keep a lightweight model for extraction/simple work; use stronger coding/planning and a distinct reviewer when benchmarks show value. Model-family diversity alone does not prove reviewer independence.

Record provider/model/version, tokens, latency, cost, retries, task class and outcome. Hard-stop on budget. Build a versioned benchmark set; calibrate predictions and routing only on sufficient, representative outcomes, with offline evaluation and explicit approval before policy changes. No online self-modification based on unverified model claims.

## Opportunity source adapters

Each adapter owns official/public API or permitted access, pagination, rate limits, retry/backoff, error handling, freshness, deduplication, expiry, coverage and terms-of-service compliance. Track last successful scan, scan interval, observed pages/items, errors and known blind spots. Never claim 100% recall. Add sources only when data quality and lawful access justify them; GitHub is the first proving ground, not the final boundary.

## Orchestration, recovery and observability

Use a durable task state machine, idempotency keys, checkpoints, bounded retries, timeout/cancellation, concurrency locks, crash recovery and safe resume. Persist structured logs and correlation IDs. Dashboard is a read-only projection of verified database records and must clearly distinguish estimates from realized financial facts. Show opportunity states, running/blocked/ready/delivered/accepted/paid work, actual gross/fees/net/net-hourly, acceptance/payment rates, model and infrastructure costs, source health, model health, sandbox health and system errors.

## Benchmark and acceptance metrics

Measure with versioned, reproducible datasets and real outcomes:
- opportunity recall/precision with a defined ground-truth set;
- trust/payment classification quality and calibration;
- task success and verified resolution;
- acceptance rate (submitted denominator only);
- payment rate (accepted denominator, with explicit cohort maturity);
- realized net hourly income and cost per accepted/paid task;
- reviewer recall and false-positive rate;
- regression/revert rate, human minutes, latency and cost;
- sandbox escape rate from adversarial tests (report sample size; zero observed is not proof of zero risk).

Every metric must include formula, sample count, period, cohort, uncertainty and source. A target such as 90% applies to a named metric and benchmark, never to the product in general.

## Phased delivery and dependencies

### Phase 0 — Repository and integration audit
- Inventory main, all open PRs, local uncommitted changes, CI and feature overlap.
- Build a dependency DAG; identify stale/stacked branches and common ancestors.
- Preserve every useful commit; consolidate related work into a small number of coherent integration PRs with correct base branches.
- Fix acceptance denominator and fee-preservation regressions; validate ledger lifecycle and patch/reviewer contracts.
- Review current Docker threat model, resource limits and cleanup.
**Exit:** audited PR DAG, no lost changes, passing full CI on integration branch, written merge order.

### Phase 1 — Reliable end-to-end engineering core
- Complete Repository Intelligence: plan-aware explicit-path pre-read, structural files, symbols/references, bounded multi-step investigation and diagnostics.
- Complete patch validation, QA contracts and independent reviewer.
- Execute actual Python and JS/TS project checks in isolated environments.
- Add bounded repair loop and human-ready delivery package.
**Exit:** benchmarked issue-to-patch flow with reproducible evidence and no external submission.

### Phase 2 — Trust, discovery and economics
- Adapter framework, coverage/freshness and deduplication.
- Verified / Needs Review / Rejected evidence states.
- Explainable technical and economic scoring with calibrated probabilities.
- Correct event-based ledger and realized finance.
**Exit:** audited real opportunity records and defensible shortlist; no invented probabilities.

### Phase 3 — Multi-model routing and orchestration
- Provider interface and optional API adapters.
- Complexity-aware routing, independent review, telemetry and budgets.
- Durable queue, checkpoints, safe resume and concurrency control.
**Exit:** benchmark demonstrates quality/cost/latency improvement over baseline.

### Phase 4 — Learning, dashboard and product operations
- Versioned benchmark, outcome analysis and offline calibration.
- Dashboard derived only from authoritative records.
- Recovery, observability, backups and operational controls.
**Exit:** reproducible metrics and recovery tests.

### Phase 5 — Commercial hardening and first paid proof
- VM/microVM decision backed by threat model and adversarial results.
- Source-specific legal/terms review and human-controlled delivery.
- Complete one real project from discovery to actual payment through authorized platform steps.
**Exit:** independently verifiable acceptance and received funds, full cost accounting and positive or transparently reported unit economics.

## PR and merge policy

- Do not create many tiny stacked PRs.
- Before creating a PR, declare its parent/base, dependencies, scope and exit criteria.
- Prefer one coherent PR per independently testable capability; parallelize only genuinely independent work.
- Keep a single integration queue/branch where necessary; retarget stacked PRs only after preserving and validating their commits.
- Never merge solely because a PR is open, non-draft or has historical CI. Re-run current checks on the exact head and integration base.
- Do not rewrite or force-push user branches without explicit authorization.
- Do not merge to main without explicit human approval.

## Explicitly deferred

No auto-bidding/submission across platforms; no autonomous payments/signing; no unbounded anonymous code execution; no premature microservices; no model proliferation without benchmark evidence; no claim of full autonomy; no all-language support at once; no revenue claims from tests or listed rewards.

## Definition of done for every capability

Implementation + unit/regression/adversarial tests as applicable + CI on exact commit + failure scenarios + resource/cost limits + documentation + known limitations + measured acceptance criteria + proof that existing capabilities and approval boundaries remain intact.

## First proof milestone

Complete one authorized real software task end-to-end: find a legitimate opportunity, verify payer/payment terms, understand repository and issue, implement and test, independently review and repair, prepare delivery for human approval, submit only through the authorized human-controlled route, then record acceptance and actual received payment. This is the first commercial proof—not a promise of guaranteed earnings.
