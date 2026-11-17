# Master roadmap

**Status:** Proposed future work unless labeled otherwise. Synthesized 2026-11-17 from explicit user strategic requirements and existing roadmap documents. It is not a delivery commitment.

## North star

Build a broadly capable, safe, evidence-first engineering and work agent. Prove reliability through GitHub issue work first; design interfaces so future GitLab, Bitbucket, Jira, paid task marketplace, and authorized private repository integrations can be added without claiming they exist today.

## Proposed sequence

1. **Establish a trusted baseline.** Reconcile source, tests, PR branches, and docs; preserve the existing worktree; run relevant CI/tests and report actual results.
2. **Strengthen repository intelligence.** Build manifests, entry points, test discovery, symbol/reference and dependency knowledge with bounded context and provenance.
3. **Make planning dependency-aware.** Use a versioned, validated plan schema with stable steps and dependency edges; reject invalid references and cycles; preserve compatibility during migration.
4. **Improve patch and verification quality.** Enforce scope, generate minimal multi-file patches, select real project-specific test commands, and report skipped/incomplete checks honestly.
5. **Harden independent review and repair.** Keep review independent of implementation claims; bound repair attempts and preserve every artifact and failure.
6. **Make runs reproducible and recoverable.** Persist task state, inputs, repository commit, policies, model versions, artifacts, logs, check outcomes, retries, cancellation, and handoff data.
7. **Harden execution.** Define threat model and authorization policy; address disk/file quotas and immutable runtime identity; evaluate stronger VM/microVM isolation before hostile or multi-tenant execution.
8. **Expand integrations deliberately.** Add task-source and repository adapters with least-privilege authorization, separately observable from engineering logic.
9. **Measure commercial viability.** Track verified resolution, acceptance, actual receipts, fees, costs, retention, and support burden. Make no commercial claims without evidence.

## Proposed future initiative: multi-model orchestration

**PROPOSED — not implemented or verified.** Explore coordinated use of ChatGPT/OpenAI, Codex, Claude, Gemini, and DeepSeek as model/agent participants. This is a future initiative, not a claim of existing integrations, access, shared memory, or automatic synchronization.

Potential design areas:

- **Task routing:** select a provider/model by task type, capability, privacy/authorization constraints, budget, and measured performance; record why the route was chosen.
- **Parallel analysis:** request independent, bounded analyses for repository understanding, plan critique, security review, or test strategy where parallelism has measurable value.
- **Independent review:** keep reviewer inputs and role separate from the implementation result; track model/provider identity and avoid treating agreement as proof.
- **Disagreement resolution:** compare evidence and cited source locations, use deterministic checks where possible, expose unresolved conflicts, and route consequential ambiguity to a human rather than majority-voting model opinions.
- **Shared memory:** define a canonical, versioned project-memory format with provenance, permissions, conflict handling, and explicit import/export. Any synchronization between ChatGPT, Codex, or external providers requires a designed and authorized mechanism; none is verified now.
- **Bounded retries:** set per-task and per-provider attempt, time, and cost limits; preserve failures and stop on repeated or conflicting output.
- **Measurement:** evaluate quality (task correctness, regression/security findings, reviewer agreement calibrated against outcomes), cost, and latency on reproducible tasks. Compare single-model and multi-model runs and report uncertainty.

Before implementation, define data handling/retention and provider permissions, threat model untrusted repository content, deterministic evaluation set, budget policy, failure behavior, and human approval boundaries. Do not send private repository material to an external provider without explicit authorization and an appropriate data policy.

## Existing roadmap references

- `docs/COMPETITIVE_ROADMAP.md` contains a proposed product and engineering direction with phases, architecture target, metrics, and release gates.
- `docs/PRODUCT_REVIEW.md` records an independent product/engineering review and specific reliability, validation, and sandbox gaps.
- `docs/ARCHITECTURE.md` records current modules, workflow, and limitations.

These documents are historical plans/reviews, not proof that their recommendations are implemented. Reconcile each item against current source, tests, branch history, and PR merge state before planning work.
