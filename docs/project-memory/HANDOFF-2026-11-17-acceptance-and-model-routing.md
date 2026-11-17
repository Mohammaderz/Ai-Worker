# Engineering handoff — 2026-11-17 (acceptance gate + local model routing)

**Recorded:** 2026-11-17.  
**Purpose:** preserve the verified sequence of work and the exact known synchronization boundary after Codex reached its usage limit.  
**Evidence provenance:** repository state previously inspected through GitHub, plus Codex logs pasted by the user in the ChatGPT conversation. This document is a handoff record; it is not a substitute for the local worktree diff.

## 1. GitHub state verified for this handoff

Repository: `Mohammaderz/Ai-Worker`.

- Default branch `main` was at `6f89b6dca43ba635e53ec9b2281a7e03814034fa` (message: `Document realized payout latency metrics`).
- Recovery branch `backup/pre-live-ollama-debug-20261117-040907Z` exists at `b190057d3a790ac1690f953af75751aeed65aea2`.
- The recovery commit is a root commit created to preserve a reviewed worktree snapshot; do not move, rewrite, or delete it.
- The intended local engineering branch was `eng/deterministic-acceptance-gate-20261117`, at HEAD `b190057d3a790ac1690f953af75751aeed65aea2` in the last Codex Git inspection.
- That engineering branch was **not present on GitHub** when checked after the Codex logs. Its source/test/documentation changes had not been committed or pushed.
- This handoff is being saved on a separate branch, `handoff/model-router-and-acceptance-state-20261117`, rooted at the recovery commit. It is documentation-only and does not contain the unpushed local code changes.
- No merge into `main` and no modification of the recovery branch is authorized by this handoff.

**Important synchronization boundary:** the local source changes described below are not included in this GitHub documentation commit. They remain to be inspected and pushed from the user's Mac/Codex checkout. Do not report that all code updates are synced until the engineering branch is pushed and its remote SHA and file contents are verified.

## 2. Acceptance and repair pipeline work reported by Codex

The following implementation changes were made locally after the recovery point, according to the supplied Codex logs:

- Added pre-review candidate verification for eligible Python patches in a disposable workspace copy using the Docker sandbox.
- Ran Python compile checks and project tests before independent review.
- Converted concrete compile/test failures into bounded repair findings.
- Preserved bounded stdout/stderr for failed sandbox patch application so apply failures can be diagnosed and passed to repair.
- Added ordered verification-attempt history and passed it, together with the structured plan, to the reviewer.
- Added a deterministic final verification gate. A reviewer `pass` alone cannot make a candidate eligible for handoff when required checks are missing or failed.
- Updated repair-diff handling so a repair response may omit unchanged file sections; omitted original sections are preserved, and changed paths remain constrained by the structured plan and original patch file set.
- Added regression tests for these behaviors.

### Live controlled fixture result — not an end-to-end success

Two controlled attempts used a hand-authored plan and initial patch, real local Qwen repair calls, real local DeepSeek review calls, and the Docker sandbox. Planner and initial drafting were fixtures, not live model outputs.

Observed behavior:

1. The candidate compile check passed.
2. Pytest failed on the `timeout=0` case (one failure, five passing cases in the reported fixture).
3. The failure evidence was supplied to bounded Qwen repair.
4. Qwen returned repairs that were unusable: one repeated the original patch, another produced a diff with invalid hunk counts; a later repair response used hunks relative to the candidate patch instead of the unchanged original workspace and omitted the required source fix.
5. Sandbox `git apply --check` rejected the invalid candidate patch. No patch was applied to the real AI-Worker repository and no handoff was accepted.
6. DeepSeek reviewer returned `blocked` on both final controlled attempts.

**Conclusion:** fail-closed behavior worked; real model-driven repair did not solve this fixture. Do not describe the acceptance/repair flow as fully successful end to end.

### Test evidence for this implementation stage

Before the later model-router additions, Codex reported:

- Full suite: `./.venv/bin/pytest -q` — **298 passed**.
- Sandbox and Node QA subset with dedicated temporary root: **28 passed**.
- Focused pipeline/reviewer suite: **103 passed**.
- `compileall`, `git diff --check`, and direct documentation whitespace scan passed.

The full-suite result of 298 and the 28 sandbox/Node QA result were recorded **before** the model-router/telemetry changes below. They must not be treated as verification of the later local model-router changes.

## 3. Local model routing and telemetry work reported by Codex

The subsequent Codex work began after inspecting the existing runtime. The supplied logs reported:

- The application runtime was configured for Ollama loopback calls only.
- Local Ollama endpoint `127.0.0.1:11434` responded when tested.
- Installed local models: `qwen2.5-coder:7b` and `deepseek-coder:6.7b`.
- Qwen was used for planning/drafting/repair paths; DeepSeek was used for independent review.
- No configured DeepSeek cloud API, Anthropic/Claude provider, Google/Gemini provider, or Codex provider was found in the inspected runtime.
- The known environment variables for DeepSeek/OpenAI/Anthropic/Gemini API keys were absent in the inspected environment, and no `.env` file was present. Secret values were not displayed.

The following local modifications were then reported:

- Added `src/ai_worker/model_router.py` with a conservative local model-routing policy and call metadata helpers.
- Updated `planner.py`, `developer.py`, `reviewer.py`, and `pipeline.py` to use route resolution and collect local Ollama call records.
- Added per-run `model-usage.json` output and summary logic.
- Added `tests/test_model_router.py` and further pipeline telemetry regression coverage.
- Recorded model-call metadata such as selected model, timing, outcome, hashes, and token metadata when available. Missing token counts are intentionally kept unknown rather than fabricated.
- Fixed an empty model override validation issue and improved accounting for failed/retried drafting calls.

### Verification status after model-router additions

The latest supplied Codex test output was:

```
./.venv/bin/pytest -q tests/test_model_router.py tests/test_planner.py tests/test_patch_drafting.py tests/test_reviewer.py tests/test_pipeline.py
193 passed
```

No subsequent full test-suite run, full compile/diff verification, live end-to-end routed workflow, or measured Codex-usage reduction was supplied after these latest model-router edits.

**Important:** this model router currently represents local Ollama routing/telemetry only. It does not establish integration with Claude, Gemini, DeepSeek cloud API, or Codex. It also does not prove any numerical reduction in Codex subscription usage.

## 4. Local worktree state at last supplied Codex checkpoint

The last explicit Git check before the user-provided log ended reported:

- Branch: `eng/deterministic-acceptance-gate-20261117`.
- HEAD and recovery SHA both equal `b190057d3a790ac1690f953af75751aeed65aea2`.
- Existing modifications were unstaged; no staged or untracked files were reported at that earlier checkpoint.
- At least 13 files had already been modified in the acceptance-gate stage. The later routing work added `src/ai_worker/model_router.py` and `tests/test_model_router.py`, and further edited several existing source/test files.
- A full final file count and latest `git status` after the router edits were not provided.

The local worktree therefore needs a fresh Git inspection before any commit, archive, or push.

## 5. User constraints and operating decisions

- Preserve every existing local modification and untracked file. Never use destructive reset/clean/stash/checkout operations to simplify synchronization.
- Keep the recovery branch and its SHA unchanged.
- Do not push to `main`, force-push, merge, or rewrite history.
- Before a push, inspect the exact diff and scan for secrets. Keep local credentials, API keys, private keys, temporary model fixtures, caches, and virtual environments out of Git.
- Codex usage became exhausted during this work. The user explicitly wants Codex calls minimized. Avoid repeated repository-wide scans, duplicate tests, broad context dumps, and unnecessary model calls.
- Local deterministic tools should handle Git inspection, tests, compile checks, static checks, and file searches where possible.
- Ollama/Qwen/DeepSeek local models may be used only with the same security, plan-scope, sandbox, review, and acceptance requirements. Lower cost must never weaken quality or validation.
- Do not claim success, API integration, measured savings, backup integrity, commit, push, or synchronization without fresh evidence.

## 6. Next safe actions

When Codex/local execution is available again:

1. Run a minimal read-only Git inspection: branch, HEAD, recovery SHA, status, and concise diff stat. Do not dump the full repository or full diff unless needed.
2. Confirm the exact modified/untracked file list, including `model_router.py`, tests, and project-memory files.
3. Create a fresh verified local archive of the **current** worktree, excluding secrets and ephemeral files; verify archive integrity and SHA256. The earlier archive predates the latest routing changes and is not a final backup.
4. Run the full suite and compile/diff checks once against the final local source state. Use a dedicated writable pytest temporary directory for sandbox/Node QA tests.
5. Review the local model-router code and its error paths, especially missing token usage, retry recording, override validation, privacy of hashes/metadata, and fail-closed behavior.
6. Update the existing project memory with exact verified results, distinguishing the 298-pass pre-router state from the 193-pass focused post-router state.
7. Commit the accepted local changes on `eng/deterministic-acceptance-gate-20261117` and push that branch with a normal non-force push only after the local diff, secret scan, and checks are complete.
8. Verify the remote branch SHA and changed files on GitHub. Leave `main` and the recovery branch untouched.

## 7. Claims that must remain unverified

- Full model-driven planner → drafter → repair → reviewer → test success.
- Successful repair of the controlled `timeout=0` fixture.
- Runtime integration with Claude, Gemini, DeepSeek cloud API, or Codex.
- Any quantified reduction in Codex usage or subscription cost.
- 24/7 production operation, autonomous recovery, or unattended delivery.
- Push/commit of the local engineering changes.

This handoff exists to preserve the evidence and prevent future sessions from repeating expensive investigations or confusing a local uncommitted change with a GitHub-synchronized implementation.
