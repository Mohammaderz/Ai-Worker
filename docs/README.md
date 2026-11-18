# Project Documentation Index

This directory is the documentation entry point for AI-Worker.

## Source of truth and precedence

1. **Execution requirements:** the Persian full execution plan v2.4 in docs/plans/v2.4/ (the original PDF is authoritative).
2. **Live gate status:** [Execution checklist v2.4](EXECUTION_CHECKLIST_v2.4.md), updated from verified evidence.
3. **Latest engineering checkpoint:** [Project status 2026-11-18](PROJECT_STATUS_2026-11-18.md).
4. **Architecture:** [ARCHITECTURE.md](ARCHITECTURE.md).

Do not infer that a stage is complete from elapsed time, planned work, a successful isolated test, or an image candidate. Only evidence satisfying the v2.4 exit criteria can close a gate.

## Execution order

- Stage A — environment, integrations, backup/recovery, sandbox, security baseline, essential tools, market pre-check and candidate list.
- Stage B — Qwen3.8:27B, resource gate, tool calling, T6 and three consecutive PASS runs.
- Stage C — official Kimi Code connection, tier/quota/privacy controls, T1/T7/T2 and three representative runs.
- Stage D — Model Router, Quota/Budget Manager and T8.
- Stage E — Coordinator / Implementer / Reviewer / Verifier / Integrator with isolated worktrees and staged concurrency.

Stages B–E must not begin until Stage A is complete and explicitly accepted under v2.4.

## Current checkpoint

See [Project status 2026-11-18](PROJECT_STATUS_2026-11-18.md). At this checkpoint Stage A remains open; Stages B–E have not started.

## Evidence discipline

- Label facts, inferences and unresolved questions separately.
- Do not mark tests PASS unless actually run and outputs retained.
- Keep active Docker images separate from candidates.
- Do not silently replace dependencies, tags, branches, configuration or local work.
- Record exact image IDs, report paths, commit IDs and test evidence when available.
