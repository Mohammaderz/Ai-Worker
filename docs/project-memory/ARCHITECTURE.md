# Architecture knowledge

**Snapshot date:** 2026-11-17. **Confidence:** high for module boundaries in checked-out tree; details can change with uncommitted modifications.

## Verified current structure

- `src/ai_worker/sources/`: task-source adapters, including GitHub issue and Jobbi sources.
- `models.py`, `scoring.py`, `storage.py`, `report.py`: opportunity representation, ranking, SQLite persistence, and reports.
- `workspace.py`: public repository workspace preparation.
- `planner.py`: loopback-local Ollama planning and `TaskPlan` validation.
- `developer.py`: bounded repository context, patch proposal schema, unified-diff validation, repair boundaries, and sandboxed patch application.
- `reviewer.py`: structured patch review and deterministic security checks.
- `sandbox.py`, `sandbox/Dockerfile`, `sandbox/Dockerfile.node`: isolated Python and Node execution environments.
- `pipeline.py`: end-to-end task orchestration and artifact/review/repair/check reporting.
- `cli.py`: command-line entry points.
- `node_qa.py`: untracked in this checkout on 2026-11-17; inspect before relying on its behavior.

Evidence: `src/ai_worker/`, `tests/`, `README.md`, and `docs/ARCHITECTURE.md`. Exact behavior is source-of-truth; README and docs may lag the worktree.

## Planning and patch flow

**VERIFIED implementation update (2026-11-17):** `planner.PLAN_SCHEMA` retains the legacy prose `implementation_steps` field and adds an optional structured `steps` array. Each structured item has a stable-within-this-plan ID, a zero-based index into the legacy step list, dependency IDs, and authorized file paths. `_validate_plan()` accepts old payloads without `steps`; structured payloads require one-to-one mapping to implementation steps, valid unique IDs and indexes, known non-self dependencies, no duplicate edges, and safe relative file paths. It rejects cycles with a diagnostic naming the unresolved cycle members and returns a deterministic topological order (ties preserve model order). `TaskPlan.steps` is additive. When an old plan has no graph, `TaskPlan.to_dict()` omits `steps` so the legacy serialized shape is preserved. Evidence: `src/ai_worker/planner.py`; tests in `tests/test_planner.py`.

The planner prompt requests structured steps but only evidence-supported dependency edges and paths; intended new files must be listed explicitly. This is a model-proposed graph validated structurally, not a statically inferred or semantically proven dependency graph. IDs are stable within one plan, not across separate planning runs.

`developer.collect_repo_context()` ranks bounded repository files and includes a Python AST based cross-file reference analysis for context selection. This can help surface related files, but it does not produce a complete repository dependency graph. Structured plan dependencies now impose a deterministic order on plan steps; they do not claim completeness of repository dependencies. A model may return multiple diff sections; `validate_patch_text()` permits up to `MAX_PATCH_FILES` and validates paths and hunk structure. Multiple diff sections alone do not establish dependency-aware planning.

**VERIFIED patch-scope behavior (2026-11-17):** When a plan contains `steps`, `draft_patch()` and `repair_patch()` validate the complete serialized plan (including one-to-one descriptions, unique IDs, dependency references, cycle detection, and safe paths) before model requests. Changed paths must exactly match one of the safe file paths in those steps; comparisons preserve case and Unicode spelling to avoid authorizing a different path on case-sensitive filesystems. A structured plan with no authorized files cannot authorize a changed-file patch. Repairs also remain bounded to the original patch's `allowed_files`, so adding a separately planned file during repair is not sufficient. Explicitly listed new files are supported during drafting. Legacy plans without a structured `steps` field remain accepted and retain existing patch path validation, but they cannot provide plan-based file authorization. Evidence: `src/ai_worker/developer.py`, `src/ai_worker/planner.py`, `tests/test_patch_drafting.py`, and pipeline propagation in `src/ai_worker/pipeline.py` / `tests/test_pipeline.py`.

The end-to-end pipeline passes its plan to drafting and repair. The standalone CLI `patch draft` accepts optional `--plan-file` JSON and passes it to `draft_patch()`; omitting the option preserves legacy manual drafting without plan-derived scope. The README documents this distinction. The reviewer consumes the issue, diff, and repository context, not the plan; deterministic scope enforcement occurs in draft/repair before application.

**VERIFIED live local-model exercise (2026-11-17):** The configured loopback Ollama service answered `/api/tags` at `127.0.0.1:11434`. Planner default `qwen2.5-coder:7b` and reviewer model `deepseek-coder:6.7b` were listed as installed. One captured real planning response from `qwen2.5-coder:7b` passed both `_validate_plan()` in `plan_github_issue()` and `validate_serialized_task_plan()`. It returned three steps; the worker update depended on adding `src/config.py`. This is evidence for one request only, not general model reliability.

Five captured real patch-drafting responses for that plan returned `needs_information`, asking whether explicitly requested/authorized new files should be created. The prompt was clarified and then strengthened, but the model continued asking. A targeted deterministic check now rejects a clarification asking whether to create a planned path when the issue explicitly requires that path; this invokes the existing single bounded retry. In the final live run, the model repeated the redundant clarification on retry, and `draft_patch()` failed closed with an actionable `PatchError`. Outputs were schema-valid but did not satisfy the task; treat this as a verified model instruction-following limitation, not a parser/schema success. No patch was generated or applied. In the same isolated fixture, the production scope checker accepted `src/config.py` as a planned new-file path and rejected `tests/test_unplanned.py`; because no model diff was returned, actual generated-patch scope could not be exercised. Raw responses, inputs, errors, and proposals are retained under `/private/tmp/ai-worker-ollama-plan-retry-3vpvdj8g/` for the current host session. No global configuration, model, or service state was changed. One preliminary planning invocation left only its request fixture and no captured response; its receipt/result is unverified and excluded from the confirmed response count.

The pipeline collects context, asks for a plan, drafts a patch, reviews it, may attempt bounded repair, and conditionally applies/checks the candidate in an isolated workspace. Confirm actual flow in `pipeline.py` before changing architecture, especially because it is modified locally.

## Safety and current limitations documented by the project

- GitHub inspection and public repository preparation are described as read-only/public-only; private repository support is not established.
- Local Ollama is the default model path; a provider-neutral model gateway is not established.
- Patch paths and content are validated; actual applicability is checked by `git apply --check` in a sandbox.
- Docker execution is explicitly a local baseline, not production multi-tenant isolation. Docs identify writable workspace disk/file quotas and immutable runtime image identity as gaps; verify latest source before asserting current status.
- Node/TypeScript support documented in README is syntax transpilation, not dependency-aware test execution. `node_qa.py` is an untracked file and may represent work beyond those docs; inspect it and its tests.
- Persistent resumable task state and concurrency are strategic goals, not verified current features.

Primary references: `README.md`, `docs/ARCHITECTURE.md`, `docs/PRODUCT_REVIEW.md`, `src/ai_worker/planner.py`, `src/ai_worker/developer.py`, `src/ai_worker/pipeline.py`, `src/ai_worker/reviewer.py`, `src/ai_worker/sandbox.py`.
