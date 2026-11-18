# Engineering review and corrective changes — 15 November 2026

This report records the live review of PRs #5–#8 against the implementation roadmap. It distinguishes existing work from corrections made during this review. All PRs listed below remain unmerged; `main` was not modified.

## Repository and PR topology

| PR | Purpose | Base | State at review | CI result |
|---|---|---|---|---|
| #5 | Marketplace discovery, Bounty read-only API, repository profile | `main` | Open, ready for review | 91 tests passed |
| #6 | Payout-evidence ranking and realized source economics | `main` | Open, draft | 89 tests passed |
| #7 | Diversified shortlist and active-work cap | PR #6 branch | Open, draft; one commit behind its updated base | 105 tests passed on its current head |
| #8 | Issue-aware repository context and explicit no-patch state | `main` | Open, ready for review | 82 tests passed |
| #9 | Income-engine implementation roadmap | `main` | Open, draft; documentation-only | 74 tests passed |

PR #7 is intentionally stacked on PR #6. Its current tree already contains the corrected source-payment tuple index, but its recorded base SHA predates the latest corrective commit on PR #6. GitHub reported the PR as mergeable; refresh/re-run its checks after the base branch is synchronized.

## Corrections applied

### PR #5 — Bounty API input validation and income-claim accuracy

Files changed:
- `src/ai_worker/sources/trybounty.py`
- `tests/test_trybounty.py`
- `README.md`
- PR description

Changes:
1. The API-key validation now rejects actual carriage-return and line-feed characters before building the authenticated request. It continues rejecting escaped CR/LF sequences covered by the original test.
2. Added regression coverage for actual CR and LF input.
3. Removed the unsupported "$3–$5 daily target" from the README. The replacement explicitly says there is no verified daily-income estimate yet and that the first milestone is money actually received.
4. Corrected the PR description: PR #5 is open and ready for review, not draft.

Existing Bounty safety boundary remains unchanged: GET-only discovery, no bids/claims/messages/submissions, and results remain outside the coding pipeline pending normalization and the full risk/eligibility gate.

CI: run 43686811383 — success; pytest 91 passed.

### PR #6 — Source economics paid-row indexing

File changed:
- `src/ai_worker/storage.py`
- PR description

Bug:
- `source_performance()` selects rows as `(status, actual_hours, gross_received, fees, submitted_at, accepted_at, paid_at)`.
- The paid-row filter incorrectly checked `r[1] == "paid"`, which compares the hours column to a status string. Consequently, paid task counts and all source-level paid economics were calculated from an empty set.
- The test suite caught this: the earlier run had 88 passed and one failure, where expected paid tasks were 2 but the report returned 0.

Correction:
- Changed the predicate to `r[0] == "paid"`, matching the selected tuple layout.
- PR #7 already contained this same one-index correction in its branch; PR #6 now has it too, so the standalone PR #6 test suite is green.

CI: run 43686718503 — success; pytest 89 passed.

### PR #8 — Bounded issue-aware repository context

Files changed:
- `src/ai_worker/developer.py`
- `tests/test_patch_drafting.py`
- PR description

Bug:
- The issue-aware ranking implementation read every eligible file into an in-memory candidate list before applying the final 60-file / 120 KB prompt limits. A very large or hostile repository could therefore cause excessive traversal, I/O, and memory use.

Correction:
- Replaced unconstrained file collection with deterministic `os.walk` traversal.
- Added hard scan limits:
  - 20,000 directory/file entries;
  - 2,000 eligible candidate files;
  - 2,000,000 bytes of repository text read.
- Preserved the existing 60-file / 120 KB final context limits, issue relevance scoring, excluded-directory rules, symlink checks, sensitive-file exclusions, and deterministic relevance/path ordering.
- Added regression tests for candidate-count and total-byte budgets.

CI: run 43686724998 — success; pytest 82 passed.

## PR #9 documentation alignment

Updated the roadmap wording so it no longer incorrectly describes every PR #5–#8 as draft. Their draft states differ; current GitHub state is authoritative.

CI: run 43686818278 — success; pytest 74 passed. This PR changes documentation only; the test workflow runs the repository suite.

## Existing PR #7 work reviewed

The portfolio selector:
- runs after eligibility/risk gates;
- limits the shortlist and caps active tasks using local ledger states;
- diversifies sources;
- ignores duplicate IDs and non-finite scores;
- does not claim or submit work.

Its current branch includes the corrected `r[0] == "paid"` filter. No duplicate implementation was added.

## Still not implemented — do not describe as completed

The following roadmap items remain future work:
1. Independent reviewer agent with structured approve/request-changes/inconclusive outcomes.
2. Deterministic, language-aware QA result schema distinguishing passed, failed, skipped, unavailable, and not-run checks.
3. Adversarial reviewer fixtures and measured defect-detection / false-positive rates.
4. Evidence-backed competition and repository-health checks.
5. Receipt/payment-evidence provenance and append-only outcome history.
6. Calibrated per-task economics and outcome learning based on a sufficiently large, verified sample.
7. Per-task model/runtime cost telemetry and hard budgets.
8. Dashboard and external delivery integrations.

No claim/bid/message/submission/merge/payment automation was added. No secrets or paid dependencies were introduced. No PR was merged and `main` was not changed.

## Verification limits

The results above are GitHub Actions CI results for the listed commits. They do not verify the user's Mac, local Docker Desktop, Ollama installation/model, live Bounty credentials, live marketplace behavior, acceptance by a client, or receipt of payment.
