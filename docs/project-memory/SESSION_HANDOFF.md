# Session handoff

**Prepared:** 2026-11-17. **Purpose:** resume work without losing the current repository and user constraints.

**Memory status:** Initial snapshot only, not a complete historical record. The user's ChatGPT data export has been requested but has not yet been received. Do not invent missing history or original decision dates. Archive import is outstanding but must not block engineering.

## Read first

1. `AGENTS.md`
2. `CURRENT_STATE.md`
3. `PR_STATUS.md` (refresh live statuses)
4. `DECISIONS.md` and `ARCHITECTURE.md`
5. The relevant source, tests, and current Git diff

## Current state and constraints

- The checkout was on `feat/enclosing-scope-definition-expressions` at `4c7eca7`; PR #30 was open/draft. Verify again.
- Preserve all existing modifications and untracked files listed in `CURRENT_STATE.md`.
- No destructive Git action; no commit, push, merge, or deploy without explicit user permission.
- The active phase remains **Multi-file Planning & Patch Generation**. Previous work hardened serialized graph validation and draft/repair scope, and added CLI `--plan-file`; this milestone persisted engineering standards and validated local model behavior. See `ARCHITECTURE.md` and `KNOWN_ISSUES.md`.
- This milestone appended high-assurance instructions to existing untracked `AGENTS.md`, edited already-modified `src/ai_worker/developer.py` and `tests/test_patch_drafting.py`, and updated project-memory files. It did not edit planner, CLI, pipeline, reviewer, or Node QA files. Preserve all other pre-existing diffs.
- Ollama answered at `127.0.0.1:11434`; `qwen2.5-coder:7b` and `deepseek-coder:6.7b` were listed. One captured planner response returned a three-step graph accepted by production validation. Five captured patch responses asked whether to create explicitly required planned files. A targeted guard now rejects that redundant question and invokes one retry; the model repeated the question, so drafting failed closed. No patch was generated or applied. Evidence is saved under `/private/tmp/ai-worker-ollama-plan-retry-3vpvdj8g/` for this host session. One preliminary planner invocation has no captured response and its receipt is unverified.
- Focused suite after prompt and clarification-validation edits: **122 passed**. Full suite: `./.venv/bin/pytest -q` — **284 passed**. Compile: `./.venv/bin/python -m compileall -q src/ai_worker tests` — passed. `git diff --check` passed; a direct scan found no trailing whitespace in `AGENTS.md`, README, or the 9 memory Markdown files. The full suite emitted only the non-fatal missing-flasgger warning. Real-model drafting behavior is separate from mocked tests.
- PR #30 remained open/draft and unmerged at the 2026-11-17 GitHub check. Recheck status before relying on this snapshot.

## Reliable findings to carry forward

- The strategic product is a broad engineering/work agent, with GitHub as the first proving ground and future integrations possible.
- Structured dependencies are now supported and topologically ordered, but model edges are not semantically proven complete. Plan-derived patch scope applies only when explicit structured steps/files exist; legacy plans remain accepted without plan-level scope.
- Existing docs describe Node support as syntax transpilation only, but untracked Node QA source/tests need inspection.
- PR merge state must be checked directly; open drafts and branch chains are not integrated.
- Commercial claims must be supported by actual evidence; no revenue/profit/customer-validation evidence was found in inspected repository material.
- The requested ChatGPT archive export remains pending. Import and reconcile it when received, but do not pause engineering while waiting.

## Immediate priority order

1. Wait for and import the user's requested ChatGPT data export.
2. Reconstruct the complete AI-Worker conversation history, decisions, requirements, milestones, failed attempts, and unfinished work.
3. Reconcile historical claims against repository source, Git history, GitHub issues, PRs, and CI evidence.
4. Build a complete, searchable, maintainable project memory.
5. Establish a practical shared-memory and handoff workflow between ChatGPT and Codex.
6. Resume feature development after this foundation is established. The user has directed that pending archive work must not block engineering; continue engineering while waiting and retain this as the archive/memory sequence.

## Latest verified implementation and checks

- Serialized structured plans are validated before patch-draft and repair model calls. Validation requires complete base fields, exact one-to-one step descriptions, valid unique IDs, dependency references, acyclic dependencies, and safe file paths.
- Scope uses exact safe relative path spelling. Draft and repair both enforce structured-plan scope; repair is additionally restricted to the original patch's files. A structured plan with no authorized files cannot permit a changed-file patch. Explicitly planned new files are supported during drafting.
- CLI `patch draft --plan-file PATH` loads JSON and passes the plan into `draft_patch`; omitting it retains legacy manual drafting. `README.md` documents this distinction.
- The prompt permits explicitly authorized new files, but the installed model did not follow it in five captured drafting responses. The checker accepted the planned new-file path and rejected an unplanned path; no real generated diff existed to check. A targeted redundant-creation question guard is not general semantic validation. Do not describe live patch generation as successful.
- No remote CI run was performed. Model reliability beyond the single successful plan sample remains unverified.
