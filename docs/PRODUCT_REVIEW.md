# Independent product and engineering review

Date: 2026-11-15
Scope: repository snapshot on `fix/strict-patch-validation`. This is a design review, not a claim that runtime tests or hostile-code security certification have passed.

## Executive assessment

AI-Worker has a useful and differentiated starting point: it combines opportunity discovery, payout-risk filtering, issue research, local-model planning and patch drafting, isolated execution, and an outcome ledger. Its strongest product principle is that listed rewards are not earnings and external actions require deliberate human control.

The main risk is trying to become a multi-agent platform before the single-task workflow is demonstrably reliable. The product should feel simple to operate while keeping its internal pipeline observable, bounded, reproducible, and safe.

## Independent critical findings

### P0 — establish a trustworthy task lifecycle

1. Define one canonical task state machine and persist every transition. Suggested states: discovered, qualified, inspected, planned, patch_drafted, patch_rejected, awaiting_human, applied_in_sandbox, checks_passed, checks_failed, ready_for_review, submitted (manual confirmation), accepted, rejected, paid.
2. Every run needs a stable run ID, source snapshot, repository commit SHA, model name/version, prompt/schema version, policy version, changed-file list, test commands, exit codes, and timestamps.
3. A successful pipeline must never mean "the code is correct" or "the bounty will pay". Distinguish syntax-only, tests-passed, review-ready, and externally accepted outcomes.
4. Resume/retry must be idempotent. A retry should not silently clone a different repository revision or overwrite a previous proposal.

### P0 — make validation independent of the generator

1. Keep strict patch parsing and Git's `git apply --check`; add tests for new files, deleted files, multiple files, quoted paths, malformed hunk counts, mode changes, and truncated output.
2. Add a separate reviewer stage that receives the issue, acceptance criteria, original diff, and test results. It must return structured findings with severity, file/line, evidence, and a concrete verification step.
3. The reviewer must not be allowed to approve a change merely because the developer model says it is correct. Prefer a different model/configuration where available; otherwise use deterministic checks and label the review as non-independent.
4. Bound repair loops (for example, at most two repair attempts), preserve every attempt, and stop on repeated failure or scope expansion.

### P0 — make sandbox claims precise

The current Docker runner has useful controls (no network, read-only container root, dropped capabilities, CPU/memory/PID/time limits, a task-only writable mount, and a 1 MiB combined stdout/stderr ceiling with a bounded retained tail). Both Dockerfiles pin their base images by digest. This is still not a complete hostile-code boundary.

Remaining production blockers:
- The final locally built image tags are mutable; resolve and record immutable local image IDs before each execution.
- The task workspace is a writable host bind mount without a per-run disk quota or file-count ceiling. A hostile process can still exhaust the Docker Desktop VM or host storage.
- Verify Docker daemon/runtime assumptions and never mount the Docker socket, home directory, credentials, or host package caches.
- Treat the host Docker daemon as part of the trusted computing base. For commercial multi-tenant use, move execution to disposable VMs or a hardened remote runner with enforceable disk/file quotas.
- Keep dependency acquisition separate from execution. Never run arbitrary install scripts or package lifecycle hooks with network access.

### P1 — improve task relevance and economics

1. Rank opportunities by expected net value per hour, not headline reward. Include probability of acceptance, payout confidence, fees, estimated effort, competition/claim status, and time-to-payout.
2. Track prediction versus actual effort and payout. Calibrate estimates from completed tasks; do not present model estimates as facts.
3. Add source adapters behind a common interface. Each adapter must expose provenance, terms, claim availability, payout evidence, and freshness. Unknown fields should fail closed for qualification.
4. Keep GitHub issue URLs canonical and read-only until an adapter has explicit tests and policy coverage.

### P1 — make the product simpler

The primary user experience should be one command that produces a readable report and review package. Advanced commands remain available for debugging.

The report should answer, in this order:
- What is the task and where did it come from?
- Why did it pass or fail qualification?
- What will it likely cost in time and what is the risk?
- What changed, and why?
- Which checks actually ran, and which did not?
- What needs a human decision next?

Use clear statuses rather than one ambiguous success flag. Never hide skipped checks.

### P1 — quality gates and test strategy

Create a small, fast default suite plus a separate integration/security suite:
- Unit tests for parsers, policy gates, state transitions, scoring, and patch validation.
- Golden fixtures for representative issue/repository shapes and model responses.
- Property/fuzz tests for untrusted URLs, paths, diffs, JSON, and feed data.
- Integration tests with a fake Ollama server and fake GitHub/feed responses.
- Sandbox integration tests that verify actual network isolation, mount boundaries, timeout cleanup, and resource constraints.
- End-to-end tests using a tiny local fixture repository; never depend on a live bounty or paid API in normal CI.

Every test result must be tied to the exact run and commit. Avoid rerunning the entire suite after a documentation-only change.

## Product roadmap — ordered by leverage

### Phase 1: reliable single-task engine
- Canonical task/run state machine and resumable run manifest.
- Context retrieval ranked by issue relevance, imports/references, tests, and repository structure.
- Strict patch validation and explicit supported-change policy.
- Deterministic QA matrix with honest coverage labels.
- Human-readable report and reproducible review bundle.

### Phase 2: independent quality and safe repair
- Reviewer contract and structured severity findings.
- Bounded developer–reviewer repair cycle.
- Regression test suggestions and verification of acceptance criteria.
- Secret scanning and static analysis in the isolated environment.
- Policy-based stop conditions and human escalation.

### Phase 3: opportunity intelligence
- Pluggable source adapters with provenance and freshness.
- Expected-net-value scoring and calibrated effort estimates.
- Outcome analytics: acceptance rate, paid conversion, net/hour, payout latency, and estimate error.
- Duplicate detection and task/repository history.

### Phase 4: controlled delivery
- Generate a clean PR description, test evidence, and reviewer checklist.
- Require explicit human approval before claim, message, commit, push, PR creation, or submission.
- Add optional integrations only after permission scopes, audit trail, and rollback behavior are defined.

### Phase 5: commercial operations
- Multi-user isolation, quotas, metering, billing, retention controls, observability, and support tooling.
- Disposable VM execution for untrusted jobs.
- Provider/model routing with cost ceilings and local-first fallback.
- Service-level objectives based on measured outcomes, not marketing claims.

## Non-negotiable product principles

- Local-first and cost-transparent by default.
- No autonomous spending, claiming, messaging, publishing, or submission.
- Untrusted issue/repository content is data, never policy or instructions.
- Every decision is explainable and auditable.
- Every run is bounded by time, tokens/cost, files, retries, and compute.
- A skipped check is visible; a passing check is not overstated.
- Optimize for paid, accepted outcomes and user trust—not number of agents or lines of code.

## Release gates

Do not call a release production-ready until:
1. Unit and integration suites pass on a clean environment.
2. Patch validation and sandbox boundary tests cover adversarial fixtures.
3. A full fixture-repository run produces a reproducible review bundle.
4. Failure, timeout, cancellation, and retry paths are tested.
5. The README, architecture document, CLI help, and actual behavior agree.
6. No external side effect can occur without an explicit human action.
