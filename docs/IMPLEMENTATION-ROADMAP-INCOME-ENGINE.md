# AI-Worker: Production Income Engine Implementation Roadmap

> Status: implementation specification for the next development cycle  
> Target branch: `reviewer/production-income-engine-roadmap`  
> Scope: additive guidance and acceptance criteria. This document does not claim that the capabilities below already exist.

## 1. Product direction

AI-Worker should not try to become a generic coding-agent clone. Its differentiated product is a **risk-aware, evidence-backed income engine for software work**:

1. Discover legitimate, actionable paid software opportunities.
2. Verify the opportunity, payment terms, and source evidence.
3. Estimate whether the work is economically worthwhile without inventing probabilities.
4. Select a small, diverse workload that fits available capacity.
5. Produce a patch in an isolated workspace.
6. Independently review and test the patch.
7. Require human approval before any external commitment or submission.
8. Track acceptance, actual payment, cost, and net realized outcome.
9. Use verified outcomes to improve future selection.

The primary optimization target is **verified net realized income per engineering hour**, subject to safety and reliability constraints—not advertised bounty totals, raw task count, generated lines of code, or model benchmark scores.

## 2. Existing work: do not duplicate it

At the time this specification was written, the following draft PRs were open. The implementation agent must inspect their latest diffs and CI status before starting overlapping work:

- PR #5 — Expand safe marketplace discovery and repository QA:
  - Bounty Agent read-only discovery adapter, bounded repository profiling, source registry, safe credential handling.
- PR #6 — Prioritize bounty sources using payout evidence:
  - Source evidence ranking, economics/reporting, ledger lifecycle and market-intelligence policy.
- PR #7 — Add diversified opportunity portfolio selection:
  - Source-diversified shortlist, active-work capacity cap, portfolio selection.
- PR #8 — Improve issue-aware repository context:
  - Issue-relevant file prioritization for patch drafting.

These PRs are draft work, not capabilities of `main` until merged. Do not assume their code is present on `main`; do not reimplement their functionality in parallel. If a PR has changed, closed, or merged, refresh the repository state and adapt this plan.

## 3. Priority order

### P0 — Preserve correctness, safety, and a trustworthy baseline

Before adding features:

- Review PRs #5–#8 for correctness, test coverage, security, and overlap.
- Keep the hard eligibility and risk gates authoritative. Ranking bonuses must never override disqualifying evidence.
- Preserve the distinction between advertised reward, budget, escrow evidence, accepted work, and money actually received.
- Never infer that an opportunity is paid merely because its marketplace or source has a good reputation.
- Keep credentials out of source code, logs, reports, generated patches, and Git history.
- Keep third-party code execution isolated; do not mount host secrets or the user's home directory into task sandboxes.
- Keep external actions (claim, bid, message, submit, merge, or payment) behind explicit human approval and supported official APIs.

**Acceptance criteria**
- Existing CI remains green.
- Existing hard eligibility gates have regression tests proving ranking cannot bypass them.
- Reports label unknown or stale payment evidence as unknown/stale, never verified.
- No new external side effect is introduced by a scan or dry-run command.

### P1 — Opportunity evidence and economic decision engine

Build on the existing source registry, payout evidence, scoring, and economics work rather than replacing it.

Each opportunity should retain, where available:

- Stable source and opportunity identifiers.
- Canonical source URL and retrieval timestamp.
- Reward currency and amount, with fixed reward distinguished from bid budget or estimated budget.
- Payment mechanism and evidence grade.
- Evidence URL(s), evidence publisher, evidence timestamp, and expiry/freshness policy.
- Claim availability and deadline.
- Acceptance criteria and required deliverables.
- Repository URL, default branch, issue/PR references.
- Competition indicators (existing PRs, competing submissions, duplicate fixes).
- Repository health indicators (recent activity, CI/test configuration, manifests, lockfiles, language mix).
- Estimated task complexity and estimate confidence, only when evidence supports them.
- Model/API, sandbox, and infrastructure cost.
- Final lifecycle status and independently recorded payout outcome.

Economic calculations must be transparent and conservative.

Use:
- `expected_net_value = p_accept * p_pay_given_accept * net_reward - estimated_execution_cost`
- `expected_net_value_per_hour = expected_net_value / estimated_hours`

However, `p_accept`, `p_pay_given_accept`, and `estimated_hours` must **not** be fabricated by an LLM or filled with arbitrary defaults. Until sufficient outcome data exists:
- expose unknown probabilities as unknown;
- show deterministic facts separately from estimates;
- use scenario/range analysis where appropriate;
- rank using explainable verified features;
- do not label advertised reward as expected earnings.

When calibration becomes possible, use historical, time-bounded, source- and task-type-aware outcome cohorts. Record sample size, confidence interval, calibration date, and drift. Avoid training/evaluating on future outcomes or leaking the target outcome into features.

**Acceptance criteria**
- Every score has an explanation of its contributing features.
- Unknown evidence remains unknown and is not silently imputed.
- Currency conversion, fees, and model costs are explicit and timestamped.
- Unit tests cover zero reward, missing values, stale evidence, non-finite values, currency mismatch, and rejected/pre-submission lifecycle states.
- A report can explain why a higher advertised reward ranked below a smaller but more feasible opportunity.

### P2 — Independent code review and stronger QA

Add a bounded, independent reviewer stage after patch generation and before final approval.

Suggested flow:

1. Planner produces a task plan and explicit acceptance checklist.
2. Developer generates a patch in the isolated workspace.
3. Reviewer receives the original issue, repository context, plan, and diff—but not the developer's private chain-of-thought or unsupported self-assessment.
4. Reviewer checks correctness, scope, security, compatibility, test quality, and acceptance criteria.
5. Deterministic QA tools run in the sandbox.
6. Failed checks return structured findings for a limited repair cycle.
7. A final report presents evidence and unresolved risks to a human.

Reviewer output should be structured:
- finding ID and severity;
- file and line/range where possible;
- concise explanation;
- reproducible evidence or test;
- acceptance criterion affected;
- recommended correction;
- confidence and whether the finding is verified.

The reviewer must be able to reject a patch. Do not force consensus or let the developer mark its own patch as approved. Use a different model/provider when practical, but treat model diversity as a risk-reduction technique, not proof of independence.

Add language-aware QA incrementally:
- Python: compile, lint/type checks where configured, and project tests.
- JavaScript/TypeScript: parse/transpile, project tests, lint/type checks where configured.
- Other languages: detect project toolchain and report unsupported checks explicitly; do not claim full validation from syntax-only checks.

Dependency installation and test execution must use hardened, resource-limited, network-restricted environments. Any required network access should be an explicit, narrowly scoped policy—not an unrestricted default.

**Acceptance criteria**
- Reviewer can return `approve`, `request_changes`, or `inconclusive`.
- A reviewer failure cannot be silently converted into approval.
- Test reports distinguish passed, failed, skipped, unavailable, and not-run checks.
- Repair attempts and total model/sandbox cost have strict configurable limits.
- Tests include intentionally vulnerable, incorrect, incomplete, and out-of-scope patches.

### P3 — Model routing and cost controls

Implement model routing only after recording enough task-level telemetry.

Record per stage:
- provider and model identifier;
- prompt/input and output token counts when available;
- API cost or explicit unknown cost;
- wall-clock time;
- retries and failure reason;
- sandbox/runtime cost where measurable;
- quality outcome and human review result.

Routing policy:
- deterministic tools for deterministic checks;
- low-cost/local models for bounded classification and extraction when quality is sufficient;
- stronger models for complex planning or code generation;
- independent reviewer model/provider where practical;
- fallback only within configured cost and retry budgets.

Every task must have a hard maximum cost, maximum runtime, maximum retry count, and a stop condition. If provider pricing is unknown or stale, report it rather than inventing a cost.

Optimize **cost per accepted and paid task**, not cost per token alone.

### P4 — Outcome learning and financial truth

The ledger should be the system of record for task lifecycle and realized economics.

Track explicit transitions, timestamps, and evidence for:
- discovered;
- eligible;
- shortlisted;
- human-approved;
- claimed/contracted (only when externally confirmed);
- in progress;
- submitted;
- accepted or rejected;
- paid, partially paid, disputed, cancelled, or expired.

Do not permit impossible lifecycle jumps. Distinguish rejection before submission from rejection after submission. Preserve an auditable event history; corrections should be appended with reason and source rather than silently rewriting financial history.

For each completed task calculate, where data exists:
- gross amount actually received;
- fees and conversion costs;
- model/API cost;
- infrastructure cost;
- net realized income;
- active engineering time;
- net income per hour;
- days from submission to acceptance and payment.

Learning may use verified outcomes to improve source and task-type ranking. Keep training data provenance and prevent duplicate or manipulated outcomes from distorting metrics. Do not claim autonomous self-learning until a tested, reproducible update mechanism exists.

**Acceptance criteria**
- Only verified receipts count as realized income.
- Unpaid accepted work is not counted as paid income.
- Partial payments and refunds are represented accurately.
- Reports expose sample size and missing-data rate.
- Every aggregate can be traced back to task records and evidence.

### P5 — Delivery workflow and human controls

After QA is reliable, add integrations for supported official workflows (for example, creating a branch or preparing a draft PR where platform rules and credentials permit).

Default behavior:
- read-only discovery and analysis;
- local isolated patch preparation;
- human approval before claim, bid, message, submission, merge, or payment;
- explicit confirmation of the exact target, content, account, and external action;
- idempotency and duplicate-submission protection;
- audit log for every external action.

Do not automate marketplace interaction through prohibited scraping, browser evasion, or unsupported endpoints. Respect each provider's API terms, rate limits, and authorization scopes.

### P6 — Dashboard and productization

Build a dashboard only after the underlying records are trustworthy. Initial views should include:
- opportunity funnel and source quality;
- shortlisted and active workload;
- review/QA pass and failure rates;
- acceptance and payment rates with denominators;
- realized gross and net income;
- model/API and infrastructure cost;
- net income per hour;
- task aging and payment delays;
- model/provider performance by task type;
- evidence freshness and operational errors.

Do not display forecast revenue as realized revenue. Clearly label estimates, actuals, and unknowns.

Do not launch paid subscriptions or advertise earnings until repeated end-to-end task acceptance and payment are demonstrated.

## 4. Evaluation programme

Create a small, versioned, reproducible evaluation set from real tasks and sanitized repository snapshots. Include:
- clear and ambiguous issues;
- duplicate or already-fixed issues;
- low-quality repositories;
- misleading reward/budget descriptions;
- missing or stale payout evidence;
- unsafe patches and dependency attacks;
- regression-prone changes;
- tasks with strict acceptance criteria.

Track:
- opportunity precision at top K;
- false-positive rate for payment evidence;
- reviewer defect detection and false-positive rate;
- patch acceptance rate;
- paid completion rate;
- median and p90 task duration;
- cost per accepted task;
- cost per paid task;
- net realized income per hour.

Use time-based holdouts for outcome prediction. Never use benchmark scores alone as evidence of commercial success.

## 5. Release gates

Do not progress to the next autonomy level until the preceding gate is met:

1. **Discovery gate:** source adapters are reliable, bounded, and compliant.
2. **Evidence gate:** payout claims are traceable and unknowns remain visible.
3. **Economics gate:** ranking is explainable and does not invent expected earnings.
4. **Execution gate:** sandbox and QA pass adversarial tests.
5. **Review gate:** independent reviewer catches seeded defects with measured false positives.
6. **Outcome gate:** accepted and paid task outcomes are recorded with evidence.
7. **Automation gate:** external actions are permissioned, auditable, and human-approved.
8. **Product gate:** repeated paid outcomes demonstrate a sustainable unit-economic case.

## 6. Immediate implementation checklist

- [ ] Review and reconcile draft PRs #5–#8; do not duplicate their work.
- [ ] Confirm main-branch CI and establish a baseline.
- [ ] Audit the ledger lifecycle and payment-evidence provenance.
- [ ] Specify and implement the independent reviewer interface and structured result schema.
- [ ] Add adversarial reviewer and QA fixtures.
- [ ] Add task-level model/runtime/cost telemetry with unknown-safe handling.
- [ ] Add hard per-task budgets and retry/runtime limits.
- [ ] Add evidence-backed competition and repository-health features where source APIs permit.
- [ ] Add calibrated outcome metrics only after sufficient verified observations.
- [ ] Add dashboard and delivery integrations only after release gates pass.

## 7. Instructions to the implementation agent

Treat this document as a prioritized product and engineering specification, not permission to bypass repository governance.

Before coding:
1. Pull the latest `main` and inspect open PRs #5–#8.
2. Report which checklist items are already implemented in those PRs and which remain missing.
3. Identify conflicts and propose a minimal sequence of non-overlapping PRs.
4. Preserve existing public CLI behavior unless a migration is documented.
5. Add tests with every behavior change.
6. Run the relevant tests and report exact commands/results; never claim tests were run if they were not.
7. Keep changes in feature branches and open draft PRs for review. Do not merge to `main` without repository-owner approval.
8. Do not add secrets, paid service dependencies, or unapproved external side effects.
9. Update the README and architecture docs only when the implementation actually exists.
10. Report limitations and unverified assumptions explicitly.

The first implementation slice should be the **independent reviewer contract + deterministic QA result model + tests**, unless review of the pending PRs reveals that an equivalent capability has already been added.
