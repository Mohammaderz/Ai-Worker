# Live Execution Checklist — v2.4

This checklist tracks evidence status at the 2026-11-18 checkpoint. It is not a replacement for the v2.4 Full Execution Plan or its acceptance criteria.

## Stage A — Environment and security gate

| Requirement area | Current state | Evidence / remaining action |
|---|---|---|
| Existing OpenCode/Ollama connections | Needs final reconciliation | Verify actual connection, endpoint, model and permission state against v2.4. |
| Backup and recovery | Open | Require a real restore test, not merely backup-file existence. |
| Docker sandbox | Partial evidence | Runtime flags include read-only root, no network by default, all capabilities dropped, no-new-privileges, PID/RAM/CPU limits and constrained tmpfs. Confirm all required v2.4 acceptance tests and limits. |
| Sandbox Runner | Candidate test PASS | Alpine+Git candidate passed workspace, Git apply and esbuild execution probe. Candidate is not active or approved. |
| Security baseline | Open | Final Trivy after hardening, Semgrep triage, dependency coverage and CVE disposition remain. |
| Active Node image CVEs | Open / confirmed | Active image has glob 10.5.0 / CVE-2026-118773 MEDIUM and minimatch 9.0.9 / CVE-2026-118764 MEDIUM. Reachability assessment pending. |
| Python image security | Open | Earlier Trivy findings need final post-hardening scan and triage. |
| Pre-commit | Reported PASS | Four hooks passed; config remains untracked locally and must be reviewed/backed up. |
| Essential tools | Partial | Inventory exists; final v2.4 requirements must be checked individually. |
| Market pre-check and candidate list | Needs evidence reconciliation | Confirm the required artifact and source evidence from the v2.4 plan. |
| Stage A exit review | NOT ACCEPTED | Do not start Stage B until every exit criterion has evidence and explicit acceptance. |

## Stage B — Qwen3.8:27B

- [ ] Stage A formally accepted.
- [ ] Qwen3.8:27B connection and model identity verified.
- [ ] Resource Gate evidence retained.
- [ ] Tool Calling acceptance (T6) completed.
- [ ] Three consecutive PASS runs retained.

**Status:** Not started.

## Stage C — Kimi Code

- [ ] Stage A and preceding prerequisites accepted.
- [ ] Official Kimi Code connection verified.
- [ ] Tier, quota and privacy behavior documented.
- [ ] T1, T7 and T2 acceptance completed.
- [ ] Three representative executions retained.

**Status:** Not started.

## Stage D — Routing and budget controls

- [ ] Prior stage prerequisites accepted.
- [ ] Model Router implemented and tested.
- [ ] Quota/Budget Manager implemented and tested.
- [ ] T8 acceptance completed.

**Status:** Not started.

## Stage E — Multi-agent orchestration

- [ ] Prior stage prerequisites accepted.
- [ ] Coordinator / Implementer / Reviewer / Verifier / Integrator responsibilities defined and tested.
- [ ] Separate worktrees enforced.
- [ ] Concurrency enabled in stages with evidence and rollback boundaries.

**Status:** Not started.

## Rules

- Do not convert a partial test into a stage PASS.
- Do not count a candidate image as an active-image replacement.
- Do not close security findings without evidence or a documented, approved exception.
- Do not begin product development before v2.4 Stage A–E gates are completed in order.
