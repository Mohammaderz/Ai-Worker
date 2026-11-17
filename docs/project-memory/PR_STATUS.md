# Pull request status snapshot

**Checked:** 2026-11-17 (GitHub search for `Mohammaderz/Ai-Worker`, all states). **Confidence:** high for this query result at check time; statuses can change. Recheck live GitHub before acting. “Merged” below is based on GitHub's `merged` field, not branch ancestry.

## Status summary

- Merged: #1, #2, #3, #4.
- Open and non-draft: #5, #8.
- Open drafts: #6, #7, #9–#30.
- Closed, unmerged draft: #32 (description says it was superseded by expanded roadmap in PR #9).
- No PR #31 appeared in this repository search result. This is not evidence that no PR with that number ever existed; confirm via GitHub if relevant.

## Known PRs

| PR | Title | State at snapshot | Notes |
|---:|---|---|---|
| 1 | Build AI-Worker v0.2 scout, local coding agent and sandbox | Merged | Historical foundation. |
| 2 | Add end-to-end bounty pipeline, payout ledger and scheduled scanner | Merged | Historical integration. |
| 3 | Improve bounty quality filters and flag suspicious high rewards | Merged | Historical quality filters. |
| 4 | Add isolated Node and TypeScript static validation | Merged | Node syntax validation; docs say dependency-aware Node tests are not run. |
| 5 | Expand safe marketplace discovery and repository QA | Open, non-draft | Do not assume integrated. |
| 6 | Prioritize bounty sources using payout evidence | Open, draft | Targets `main`; do not assume integrated. |
| 7 | Add diversified opportunity portfolio selection | Open, draft | Depends on PR #6 branch according to its base branch. |
| 8 | Improve issue-aware repository context | Open, non-draft | Do not assume integrated. |
| 9 | Add production income engine implementation roadmap | Open, draft | Roadmap only; its body/status should be rechecked before relying on details. |
| 10 | Add fail-closed reviewer and deterministic QA contracts | Open, draft | Historical PR record; inspect branch and current source. |
| 11 | Add independent fail-closed patch review | Open, draft | Historical PR record; inspect branch and current source. |
| 12 | Validate reviewer findings against changed diff lines | Open, draft | Historical PR record; inspect branch and current source. |
| 13 | Add deterministic security checks to independent reviewer | Open, draft | Followed by Python AST/security-analysis work in subsequent PRs. |
| 14 | Use Python AST for deterministic security review | Open, draft | Subsequent scope extensions are separate PRs. |
| 15 | Detect multiline dynamic execution in security review | Open, draft | Open draft. |
| 16 | Detect imported aliases of dynamic execution | Open, draft | Open draft. |
| 17 | Resolve dynamic execution aliases from full changed files | Open, draft | Open draft. |
| 18 | Detect assignment aliases of eval and exec | Open, draft | Open draft. |
| 19 | Invalidate dynamic execution aliases after reassignment | Open, draft | Open draft. |
| 20 | Make dynamic execution alias analysis order-aware | Open, draft | Open draft. |
| 21 | Track dynamic execution aliases through conditional branches | Open, draft | Open draft. |
| 22 | Track dynamic execution aliases through compound control flow | Open, draft | Open draft. |
| 23 | Analyze dynamic execution within isolated function scopes | Open, draft | PR description reports tests; treat as PR-provided evidence, not current local test result. |
| 24 | Handle lambda scopes and annotations in security review | Open, draft | Open draft. |
| 25 | Respect global and nonlocal bindings in security analysis | Open, draft | Open draft. |
| 26 | Respect comprehension scopes in deterministic security review | Open, draft | Open draft. |
| 27 | Track walrus bindings in security call analysis | Open, draft | Open draft. |
| 28 | Respect shadowed builtins modules in security analysis | Open, draft | Open draft. |
| 29 | Propagate walrus bindings through comprehension scopes | Open, draft | Open draft. |
| 30 | Respect enclosing scope in function definition expressions | Open, draft | Current checkout branch matches its head branch; PR description listed local/CI validation as pending at last description observed. |
| 32 | Add production income engine execution roadmap | Closed, unmerged draft | Description says superseded by expanded roadmap on PR #9; no changes claimed discarded. |

## Provenance and caveats

Source: GitHub PR search via connected GitHub integration, queried 2026-11-17; local branch and recent commits from `git log --oneline --decorate -20`. The PR search summary above is a status inventory, not a review of all PR diffs, checks, comments, or branch dependencies. Never merge or close based solely on this file.
