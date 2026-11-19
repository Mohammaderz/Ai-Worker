# Session handoff

**Prepared:** 2026-11-17. **Purpose:** resume work without losing the current repository and user constraints.

## Stage A acceptance / Stage B paused — 2026-11-19

**Updated 2026-11-19:** The owner formally accepted Stage A under PDF v2.4; SA-29 and final Trivy were confirmed PASS from recorded evidence. **Stage B is explicitly PAUSED by owner** — no Stage B execution, tests or builds until a new explicit owner instruction. Stages C-E NOT STARTED. **Push:** the owner's current authorization is limited to this preservation package only; any future push requires separate explicit authorization. Accepted HEAD `73ff4fd5f97ec45ce39df57db2f68fd7b07f15c7`. Records: `/private/tmp/ai-worker-stage-a-owner-acceptance.HytFuA/OWNER-ACCEPTANCE-RECORD.md` and `/private/tmp/ai-worker-final-stage-a-evidence-review.7NAviG/FINAL-EVIDENCE-REVIEW.md`. These entries record decisions only; no Stage B work was started.

## Latest engineering checkpoint — 2026-11-17

**VERIFIED Git:** branch `eng/deterministic-acceptance-gate-20261117`, HEAD `b190057d3a790ac1690f953af75751aeed65aea2`. The recovery branch `backup/pre-live-ollama-debug-20261117-040907Z` still resolves to `b190057d3a790ac1690f953af75751aeed65aea2`. Current edits remain unstaged/uncommitted. No commit or push was performed. Inspect status and diffs before further work.

**Verified implementation:** `pipeline.py` performs candidate verification in a disposable copy before eligible Python proposals reach the reviewer. Required compile/pytest failures are passed as bounded repair findings. Candidate patch-application diagnostics now retain bounded stdout/stderr and are repairable. The reviewer gets the current structured plan, latest verification evidence, and ordered evidence for previous candidate/repair attempts; deterministic final acceptance rejects patch-not-applied, missing, timed-out, nonzero, or malformed required checks regardless of reviewer verdict. Every repair remains bounded to original authorized file scope.

**Actual controlled fixture outcome:** The plan and initial two-file patch were hand-authored; local models ran only repair (Qwen `qwen2.5-coder:7b`) and independent review (DeepSeek `deepseek-coder:6.7b`). Real Docker sandbox initially applied the defective patch and pytest reported **1 failed, 5 passed**, with zero timeout the failing case. Qwen's repair omitted the source correction and returned a test hunk anchored to candidate-only lines; `git apply --check` rejected it. A second bounded repair asked an ungrounded clarification and was rejected. DeepSeek reviewer returned `blocked` with findings. Final gate false and no task-workspace patch was accepted. Do not label this model-driven E2E success. Artifacts: `/private/tmp/ai-worker-acceptance-fixture-dljdypov/retry3-proposals/` (two completed equivalent run directories). Earlier retry artifacts under `retry-proposals/` had reused a post-repair patch as if it were an initial draft; treat them as diagnostic history, not a clean rerun.

**Final verification:** Full suite: **298 passed**. Sandbox + Node QA subset with dedicated `--basetemp`: **28 passed**. Pipeline/reviewer suite after ordered-history forwarding: **103 passed**. Compileall, `git diff --check`, and direct trailing-whitespace checks over changed memory docs passed. A focused test run using pytest's default temp root once errored because of temp-directory ownership; the same tests passed with `--basetemp=/private/tmp/ai-worker-pytest-isolated-20261117`.

**Next engineering work:** Keep the acceptance gate fail-closed; investigate a safe way to reconcile model repair patches authored relative to the candidate instead of the unchanged repository. Consider moving Node QA into pre-review evidence so the independent reviewer sees Node results as well as the final gate enforcing them. Do not apply or normalize patches outside the hardened sandbox. Model repair did not fix the demonstrated task in this fixture.

**Latest handoff update:** 2026-11-17, after local recovery backup, adversarial model review, and focused/full test runs. Facts in the older snapshot below that conflict with the latest status/results are superseded by “Latest verified checkpoint”.

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

## Latest verified checkpoint

- Local recovery archive: `/private/tmp/AI-Worker-recovery-20261117T040907Z.tar.gz`, SHA256 `9c691e8936d8bf776c525d83bdd9148352760961c0f3b58f92c1af78ab19f2d2`; 351 members, full payload integrity read passed. Git recovery commit `b190057` is on `backup/pre-live-ollama-debug-20261117-040907Z`, pushed to the verified `origin` remote. It is the pre-fix baseline. No fixes after that backup are pushed.
- Root cause: live requests included issue, plan, and source context, but Qwen asked for contents of files already present. The former clarification relevance check grounded only on issue/plan. It now checks exact supplied context paths and rejects such questions; patch responses carrying questions are invalid. Qwen still repeated the redundant request and failed closed. No generated patch was applied.
- Model comparison: Qwen produced two valid structured plans in captured requests, but draft samples for both new-file and existing-file tasks remained unsuccessful. DeepSeek output was malformed or semantically incomplete; one retry timed out. The DeepSeek reviewer passed a deliberate zero-boundary defect without findings. Do not claim live model compatibility or E2E success.
- Downstream temporary harness only: hand-authored two-file patch applied, tests 3 passed; deliberately injected defect produced 1 failed / 2 passed; Qwen repair using test-failure evidence stayed in scope and tests 3 passed. This does not satisfy full model-driven E2E because model draft and independent review stages failed.
- Test results for the latest source/test state: focused security/relevant suite **204 passed**; full `./.venv/bin/pytest -q` **287 passed** (non-fatal missing-flasgger warning); compileall passed. Re-run diff/whitespace checks after documentation edits.
- Post-backup local changes are uncommitted and unstaged: `src/ai_worker/developer.py`, `tests/test_patch_drafting.py`, and project-memory updates. Preserve pre-existing Node QA files; they were not modified by this milestone. No commit/push after the recovery baseline.
- Next engineering task: improve test-feedback-based acceptance and independent review so requirements are checked against actual test evidence; address the verified reviewer miss. Then rerun isolated end-to-end with a model-generated patch and report each stage separately. Avoid model prompt escalation without addressing grounding/verification, and do not weaken path/scope controls. Continue engineering while the requested ChatGPT export remains pending.
