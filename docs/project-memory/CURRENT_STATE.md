# Current project state

**Observed:** 2026-11-17, working directory `/Users/mohmmadrza/AI-Worker`. **Confidence:** high for Git observations at that moment.

## Stage A formally accepted by owner — 2026-11-19 (supersedes older stage status)

**OWNER DECISION (updated 2026-11-19):** Stage A formally accepted under PDF v2.4; SA-29 and final Trivy confirmed PASS by owner (recorded Exit Codes zero and final report hashes). **Stage B is intentionally paused by the owner for pre-start preparation, not because Stage A failed or Stage B encountered a technical blocker**: no Stage B execution/tests/builds until a new explicit owner instruction. The pause is to complete project/document preservation, verify local and remote state, and prepare the development toolchain. Stages C-E NOT STARTED. **Push:** current explicit owner authorization applies only to this preservation package; future pushes need separate authorization. No agent-issued acceptance. Accepted HEAD `73ff4fd5f97ec45ce39df57db2f68fd7b07f15c7`, branch `eng/deterministic-acceptance-gate-20261117`. Records: `/private/tmp/ai-worker-stage-a-owner-acceptance.HytFuA/OWNER-ACCEPTANCE-RECORD.md` and `/private/tmp/ai-worker-final-stage-a-evidence-review.7NAviG/FINAL-EVIDENCE-REVIEW.md`. No main AI-Worker development started.

## Latest verified checkpoint — 2026-11-17

**VERIFIED Git state:** branch `eng/deterministic-acceptance-gate-20261117`; HEAD `b190057d3a790ac1690f953af75751aeed65aea2`. Recovery branch `backup/pre-live-ollama-debug-20261117-040907Z` resolves to the same SHA. No staged paths or untracked paths were present at the latest status check. Unstaged changes were the five project-memory files plus `src/ai_worker/{developer,pipeline,planner,reviewer}.py` and `tests/{test_patch_drafting,test_pipeline,test_planner,test_reviewer}.py`. No Node QA source/test file was changed. No commit or push was made during this milestone. Recheck all state before continuing.

**VERIFIED local recovery archive:** `/private/tmp/AI-Worker-recovery-20261117T050006Z.tar.gz`; 345 archive members, 2,756,123 regular-file payload bytes, SHA256 `5aab2c6cc77cbbcb14f96e78d8ef1a0fc9eb85b44ab1a66009f8d0e68881a837`; gzip/tar members were read to verify integrity. It excludes `.git`, virtual environments, caches, and credential/private-key patterns. It is a local snapshot before this milestone's later edits and does not contain the current final worktree state.

**VERIFIED acceptance-gate change:** Eligible Python candidates are verified in disposable copies before review. Concrete pytest/compile failures are sent to bounded repair; sandbox apply failures now retain exact bounded stdout/stderr and can also be sent to repair. Reviewer receives the plan, latest verification evidence, and ordered evidence from all pre-review and repair verification attempts. Final acceptance requires complete passing verification evidence and reviewer pass; the reviewer cannot override a failed or incomplete check.

**VERIFIED controlled model results:** A hand-authored plan and defective hand-authored patch were run through the real Docker sandbox. Initial pytest failed on `timeout=0` (1 failed, 5 passed). Actual Qwen repair output omitted the source fix and emitted a test hunk based on lines only present after the proposed diff; the final diff failed sandbox `git apply --check`. A second bounded repair asked an ungrounded clarification and was rejected. Actual DeepSeek reviewer returned `blocked` and identified invalid accepted values/inadequate tests. Final gate was false; no handoff or task-workspace application occurred. The planner and initial draft were fixtures, not model outputs. See `ARCHITECTURE.md` for details/artifact path.

**VERIFIED final tests:** `./.venv/bin/pytest -q` — **298 passed**; sandbox + Node QA subset with explicit isolated `--basetemp` — **28 passed**; focused pipeline/reviewer suite after ordered-history forwarding — **103 passed**. `./.venv/bin/python -m compileall -q src/ai_worker tests`, `git diff --check`, and direct trailing-whitespace verification of the five changed memory documents passed after final code and documentation edits.

**Latest checkpoint (2026-11-17):** The earlier branch/worktree list below describes the pre-recovery-backup snapshot and is superseded for current Git state by this section. Branch is `backup/pre-live-ollama-debug-20261117-040907Z`, HEAD `b190057` (`backup: preserve pre-repair worktree 20261117`), tracking the same branch on `origin`. The recovery baseline was pushed after review; current follow-up fixes and memory changes are local, unstaged, and uncommitted. At the start of this follow-up the only post-backup changes were `src/ai_worker/developer.py` and `tests/test_patch_drafting.py`; memory updates add the five files named in the session handoff. Re-run status before relying on this snapshot.

**Verified recovery point:** `/private/tmp/AI-Worker-recovery-20261117T040907Z.tar.gz`, SHA256 `9c691e8936d8bf776c525d83bdd9148352760961c0f3b58f92c1af78ab19f2d2`. Archive listed 351 members and all regular payloads were read successfully to verify gzip/tar integrity. It includes pre-existing modified and untracked project files; excludes `.git`, `.venv`, caches, credential directories/files, and private-key formats. Archive was local and predates the current correction. Backup branch commit `b190057` captures the pre-correction recovery baseline; current local changes are not in that commit or remote branch.

**Memory completeness:** This project memory is an initial snapshot, not a complete historical record. The user has requested a ChatGPT data export; it has not yet been received. Full conversation reconstruction is pending import. This status is recorded 2026-11-17; separate request/receipt dates are not established here.

## Verified engineering progress in this session (2026-11-17)

- Added backward-compatible structured planning steps with IDs, references to legacy implementation-step indexes, dependency IDs, and planned file paths.
- Added validation for identifier/index uniqueness, dependency references, self-dependencies, duplicate edges, cycles, step coverage, and safe planned paths; structured steps are emitted in deterministic topological order.
- Preserved legacy plan payload acceptance and the old serialized `TaskPlan.to_dict()` shape when structured steps are absent.
- Added reusable validation for serialized structured plans. Drafting and repair now reject incomplete/malformed structured plans before model requests; legacy plans without `steps` remain compatible.
- Patch file scope is exact-path and fail-closed for changed paths when a structured plan authorizes no files. Both draft and repair enforce the same plan scope; repair also remains restricted to the original patch file set. Explicitly planned new files work for drafting.
- Standalone CLI `patch draft` now accepts `--plan-file`; omission preserves legacy manual drafting. `README.md` documents the distinction.
- High-assurance engineering instructions were appended to `AGENTS.md`, preserving all existing content.
- Live local Ollama check: `/api/tags` at `127.0.0.1:11434` responded; installed model names included `qwen2.5-coder:7b` and `deepseek-coder:6.7b`. Planner default is `qwen2.5-coder:7b`.
- One captured genuine planning request returned a three-step structured plan with the worker update dependent on the new config helper. Production planner validation and serialized-plan validation accepted it.
- Five captured genuine draft responses returned `needs_information`, asking whether explicitly required and authorized new files should be created. After prompt changes did not resolve the behavior, a narrow redundant-question validator was added; the model repeated the question on its single retry and drafting failed closed. No patch was generated or applied. Raw responses and the isolated fixture are preserved under `/private/tmp/ai-worker-ollama-plan-retry-3vpvdj8g/` for this host session.
- Production plan-scope checks accepted the planned new path `src/config.py` and rejected `tests/test_unplanned.py`. Since no model diff was produced, generated-diff scope behavior was not exercised against a real model result; mocked regression tests cover patch validation.
- Focused suite after the prompt and clarification-validation changes: `./.venv/bin/pytest -q tests/test_planner.py tests/test_developer.py tests/test_patch_drafting.py tests/test_cli.py tests/test_pipeline.py` — **122 passed**.
- Full suite after all code/test edits: `./.venv/bin/pytest -q` — **284 passed**. The only output warning was non-fatal: `flasgger` is unavailable, so Swagger UI/spec endpoints are skipped.
- Compile: `./.venv/bin/python -m compileall -q src/ai_worker tests` — passed. `git diff --check` — passed. Direct trailing-whitespace scan over `AGENTS.md`, `README.md`, and all 9 project-memory Markdown files — none found. `git diff --check` does not inspect untracked documentation by default.
- No remote CI run was performed. One successful plan sample does not prove model reliability; actual drafting of explicitly planned new files remains an observed model-following limitation.
- GitHub PR #30 was rechecked with the GitHub integration on 2026-11-17: open, draft, `merged=false`. Do not infer integration.
- No ChatGPT export was received or imported. Archive reconstruction remains pending and does not block engineering.

## Latest adversarial review and local model verification (2026-11-17)

- Captured request bodies confirm both task text and selected repository files were sent. Qwen nevertheless asked for contents of supplied source files. The earlier question-grounding check only considered issue and plan; it now receives repository context and rejects requests for contents of an exactly named supplied path. Parser now rejects `status="patch"` with unresolved questions. Qwen repeated the request after the bounded retry; fail-closed outcome remains. These are targeted checks, not semantic understanding.
- Two captured Qwen planner outputs passed production validation (one three-step plan with a dependency, one two-step dependency plan). Confirmed draft output samples: Qwen new-file case 5 responses, Qwen existing-file case 4 responses; DeepSeek new-file case 2, DeepSeek existing-file case 1; one DeepSeek retry timed out. DeepSeek returned malformed/incomplete patches and its reviewer missed a deliberately injected boundary defect. No valid model-generated patch was produced.
- In temporary isolated Git repositories, a hand-authored reference patch applied and tests passed (3 passed). A separate injected defect failed tests (1 failed, 2 passed); a Qwen repair based on test failure evidence stayed in scope and tests passed afterward (3 passed). These results verify downstream mechanics only. Since independent review missed the defect and the initial patch was not model-generated, full model-driven E2E **did not pass**.
- Latest focused security/relevant command: `./.venv/bin/pytest -q tests/test_planner.py tests/test_patch_drafting.py tests/test_developer.py tests/test_reviewer.py tests/test_sandbox.py tests/test_pipeline.py` — **204 passed**. Full suite: `./.venv/bin/pytest -q` — **287 passed**, with non-fatal missing-flasgger warning. Compile: `./.venv/bin/python -m compileall -q src/ai_worker tests` — passed. `git diff --check` — passed before these documentation edits; direct documentation whitespace scan must be repeated after edits.
- Evidence artifacts are local temporary directories: `/private/tmp/ai-worker-ollama-plan-retry-3vpvdj8g/`, `/private/tmp/ai-worker-e2e-dz6isk10/`, and `/private/tmp/ai-worker-review-repair-6akzkas6/`. Temporary evidence may not survive host cleanup. No experimental patch was applied to AI-Worker. No model/config install, service restart, global configuration change, or further commit/push occurred.

## Git snapshot

- Branch: `feat/enclosing-scope-definition-expressions`.
- HEAD: `4c7eca7` (`test: cover enclosing scope in function headers`), tracking `origin/feat/enclosing-scope-definition-expressions` at the observed commit.
- Remote: `origin https://github.com/Mohammaderz/Ai-Worker.git`.
- Do not assume the branch is merged; PR #30 was open and draft at the GitHub check.

## Existing worktree changes to preserve

Modified:

- `.gitignore`
- `src/ai_worker/cli.py`
- `src/ai_worker/developer.py`
- `src/ai_worker/pipeline.py`
- `src/ai_worker/planner.py`
- `src/ai_worker/reviewer.py`
- `src/ai_worker/sandbox.py`
- `src/ai_worker/storage.py`
- `src/ai_worker/workspace.py`
- `tests/test_cli.py`
- `tests/test_developer.py`
- `tests/test_patch_drafting.py`
- `tests/test_pipeline.py`
- `tests/test_planner.py`
- `tests/test_sandbox.py`
- `tests/test_storage.py`
- `tests/test_workspace.py`

Untracked:

- `src/ai_worker/node_qa.py`
- `tests/test_node_qa.py`

The user explicitly requested these be preserved in the prior session. This memory task added documentation files only; check current status before future work because the tree may since have changed. No diffs were intentionally reverted or overwritten.

This list is a dated snapshot, not a substitute for checking `git status` before work. Documentation-only memory edits have since added/updated `AGENTS.md` and files under `docs/project-memory/`; inspect current status before assuming their tracked/untracked state.

## Current development context

- Previous task phase stated by user: **Multi-file Planning & Patch Generation**.
- The earlier audit found the plan schema prose-based and not dependency-aware; this session added an optional validated dependency graph and structured file scope. See `ARCHITECTURE.md` and `KNOWN_ISSUES.md` for current behavior and limitations.
- Most recent Git history focuses on Python AST security review and scope/alias correctness; this is separate from the broader product roadmap.
- No application tests were run during the memory-writing task. Do not infer current test health from PR descriptions or old CI results.
- Tests were run in this engineering session as recorded above; those results supersede the prior “no tests run during memory-writing task” note for current code verification.
- This work appended high-assurance instructions to pre-existing untracked `AGENTS.md`, edited the already-modified `src/ai_worker/developer.py` and `tests/test_patch_drafting.py`, and updated project memory. It did not edit `pipeline.py`, reviewer, CLI, planner, Node QA files, or other pre-existing changes. Exact scope details are in the latest session handoff.
- No ChatGPT export has been imported; historical completeness, original decision dates, and full milestone/failed-attempt/unfinished-work chronology remain unresolved.

## Documentation inventory at task start

Existing docs: `README.md`, `docs/ARCHITECTURE.md`, `docs/PRODUCT_REVIEW.md`, `docs/COMPETITIVE_ROADMAP.md`, and `sandbox/README.md`. No root `AGENTS.md` or `docs/project-memory/` files were found. This task created the memory structure without replacing those documents.
