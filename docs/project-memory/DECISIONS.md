# Decisions and constraints

**Updated/recorded:** 2026-11-17. **History status:** Initial snapshot; the requested ChatGPT data export has not yet been received. Original decision dates are not inferred.

## Agreed decisions

| Decision | Type | Original decision date | Recorded in memory | Evidence | Confidence |
|---|---|---|---|---|---|
| AI-Worker's long-term objective is a broad engineering/work agent; GitHub is the first proving ground. | AGREED strategic requirement | Unknown; pending archive import | 2026-11-17 | User instruction in available conversation | High that it was stated; adoption date unknown |
| Dependency-aware multi-file planning is a core capability to build toward. | AGREED strategic requirement; not a claim of current implementation | Unknown; pending archive import | 2026-11-17 | User instruction in available conversation; planner audit | High that it was stated; adoption date unknown |
| Commercial claims require evidence; no unsupported revenue, profitability, or customer-validation claims. | AGREED strategic requirement | Unknown; pending archive import | 2026-11-17 | User instruction in available conversation; consistent with README/product review | High that it was stated; adoption date unknown |
| Preserve working-tree modifications and untracked files; do not perform destructive Git operations. | AGREED explicit operating constraint | Unknown; pending archive import | 2026-11-17 | User instructions in available conversation | High that it was stated; adoption date unknown |
| Do not commit, push, merge, or deploy without permission. | AGREED explicit operating constraint | Unknown; pending archive import | 2026-11-17 | User instruction in available conversation | High that it was stated; adoption date unknown |
| Historical PR state must be verified; an open or draft PR is not integrated. | AGREED explicit operating constraint | Unknown; pending archive import | 2026-11-17 | User instruction and GitHub PR snapshot | High that it was stated; adoption date unknown |
| Import missing historical conversation context rather than invent it. | AGREED explicit documentation rule | Unknown; pending archive import | 2026-11-17 | User instructions in available conversation | High that it was stated; adoption date unknown |

## Documented project principles (historical, verify current implementation)

- Third-party listings, issues, source files, and model outputs are untrusted data, not policy (`README.md`, `docs/ARCHITECTURE.md`).
- External side effects such as claiming, messaging, commits, pushes, PR publication, and submission require human authorization; current documented workflow does not perform them autonomously.
- Listed rewards are not earnings; only actual paid receipts are income (`README.md`).
- Keep the system local-first and bounded while improving safety and evidence (`docs/COMPETITIVE_ROADMAP.md`).

## Open decisions

- How should plan dependencies be represented and versioned while retaining compatibility with existing plan JSON and callers?
- Which non-GitHub integrations should be prioritized, and what authorization model should private repository access use?
- What runtime and tenant isolation will be required before hosted or multi-user operation?
- When, if ever, should any external action be automated beyond a human-approved draft?
- What measured task success and unit-economics thresholds justify commercial deployment?

No answer is inferred here. See `MASTER_ROADMAP.md` and `KNOWN_ISSUES.md`.

## Memory and collaboration work in progress

- **AGREED:** Wait for and import the user's requested ChatGPT data export before claiming complete historical reconstruction. The request is recorded 2026-11-17; export receipt date is unknown/pending.
- **OPEN:** Establish a practical shared-memory and handoff workflow between ChatGPT and Codex. No automatic synchronization is verified as implemented.

## Engineering decisions recorded during implementation

These are current implementation choices made in response to the user request available on 2026-11-17. This is the known decision/recording date, not a claim about any earlier discussion.

- **AGREED / IMPLEMENTED:** Keep the legacy prose `implementation_steps` contract. Add an optional structured graph keyed by IDs and indexed back to legacy steps. Accept legacy plan payloads and preserve the legacy `to_dict()` shape when no graph is present.
- **AGREED / IMPLEMENTED:** Deterministically topologically order structured steps; reject duplicate IDs/indexes, missing/self dependencies, duplicate edges, cycles, and unsafe file paths with actionable diagnostics.
- **AGREED / IMPLEMENTED:** Enforce plan file scope for patches and repairs when a structured plan explicitly declares steps/files. Preserve legacy plans that contain no structured scope. For repairs, the original-patch file boundary remains an additional hard limit.
- **LIMITATION:** Model-proposed dependencies and file scopes receive structural validation, not proof that they capture every real code dependency or the correct implementation scope.
