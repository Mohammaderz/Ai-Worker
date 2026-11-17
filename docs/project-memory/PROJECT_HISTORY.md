# Project history

**Snapshot date:** 2026-11-17. **Confidence:** high for repository/Git/GitHub observations made on this date; medium for older narrative derived from repository documentation and PR descriptions. This is not a full conversation transcript.

**History completeness:** Initial snapshot only. The user's ChatGPT data export has been requested but has not yet been received. Full conversation-history reconstruction is pending that export. Dates below are observation/recording dates unless explicitly established by a source; do not treat them as original decision dates.

## Verified repository history

- The current local checkout is `feat/enclosing-scope-definition-expressions`, at `4c7eca7` (`test: cover enclosing scope in function headers`). The recent commit chain extends Python deterministic security-review alias analysis through function definition expressions, comprehensions, walrus bindings, and enclosing scopes. Evidence: `git log --oneline --decorate -20` and `src/ai_worker/reviewer.py` history. **High confidence.**
- The repository began as an opportunity scout and grew to include read-only issue inspection, local-model planning/patch proposals, sandboxed patch application, a task pipeline, review, repository intelligence, and outcome tracking. Evidence: current README, `docs/ARCHITECTURE.md`, and merged PRs #1–#4. **High confidence.**
- Current docs explicitly distinguish advertised task rewards from actual received income and warn that successful local checks do not establish maintainer acceptance or payment. Evidence: `README.md`, `docs/ARCHITECTURE.md`, and `docs/PRODUCT_REVIEW.md`. **High confidence.**

## Historical direction and decisions

- **HISTORICAL / AGREED:** GitHub issues are the first software-task proving ground; the current public issue workflow is read-only until local planning, patch proposal, review, and isolated checks. The project docs describe other boards as discovery-only or requiring adapters/manual review. **Historical context; confirmed by current docs. Original decision date: unknown, pending archive import. Recorded in this memory: 2026-11-17.**
- Earlier PR descriptions establish the explicit boundary against autonomous claiming, bidding, messaging, committing, pushing, PR publication, and submission. PR descriptions are historical claims about the PR; the current source and docs must be checked before assuming any behavior. **High confidence that the boundary was documented; current behavior should be re-inspected.**
- The prior conversation's architecture audit found the current `TaskPlan` uses prose lists and does not encode dependency edges. The repository context analyzer finds some Python cross-file references for context ranking, but this is not a dependency-aware plan. See prior assistant audit in conversation and `src/ai_worker/planner.py`. **High confidence for the audited snapshot; re-check source.**

## Conversation-history limitation

The user has requested a ChatGPT data export, but it has not yet been received. Only the currently available conversation context is evidence. Earlier user discussions, decisions, requirements, milestones, failed attempts, and unfinished work may be missing. Do not fill gaps by guessing; complete reconstruction after the export is imported, or ask the user when a detail is needed sooner.

## Date and provenance policy

For every historical decision or event, record the date the fact was added to this memory separately from the date the decision/event originally occurred. If the original date is not supported by an imported conversation, dated repository artifact, PR, issue, or CI record, mark it **unknown — pending archive import**. The current conversation supplies the strategic requirements and documentation instructions recorded on 2026-11-17, but does not establish when those decisions were first made.
