# AI-Worker — Engineering Checkpoint

**Checkpoint date:** 2026-11-18  
**Project gate:** Stage A open  
**Documentation branch:** docs/stage-a-checkpoint-2026-11-18  
**Source working branch:** eng/deterministic-acceptance-gate-20261117  
**Source HEAD at checkpoint:** b1c3e6575a69fdae1368233749a00e22462812ef

> This is a state snapshot, not a claim that the project or Stage A is complete. The v2.4 Full Execution Plan remains authoritative.

## 1. Stage status

| Stage | Status | Notes |
|---|---|---|
| A | 🟡 In progress / Gate open | Security, evidence and required integrations still need final reconciliation and acceptance. |
| B | 🔴 Not started | Must wait for accepted Stage A exit. |
| C | 🔴 Not started | Must wait for accepted Stage A exit and its own prerequisites. |
| D | 🔴 Not started | Must wait for Stage B/C requirements in v2.4. |
| E | 🔴 Not started | Multi-agent coordination and concurrency remain gated. |

Stage A percentage: **unknown**. A defensible weighted percentage has not been calculated against every v2.4 criterion.  
Stage A remaining time: **no reliable estimate available**; active work time has not been measured sufficiently.

## 2. Repository and working-tree evidence

- GitHub repository: Mohammaderz/Ai-Worker.
- Local working branch reported: eng/deterministic-acceptance-gate-20261117.
- Local HEAD reported and verified as the base for this documentation branch: b1c3e6575a69fdae1368233749a00e22462812ef.
- Local working-tree state last reported:
  - Modified: sandbox/Dockerfile
  - Modified: sandbox/Dockerfile.node
  - Untracked: .pre-commit-config.yaml
  - Untracked: 13 (zero-byte file; SHA-256 e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855)
- These local changes were not folded into this documentation checkpoint. No source-code commit, reset, clean, stash, deletion, image retag, active-image replacement or dependency mutation was performed as part of this documentation snapshot.
- The documentation branch was created from the source working branch so the checkpoint does not overwrite main.

**Important:** GitHub documentation branch creation does not mean the local uncommitted Dockerfile and pre-commit changes have been committed or preserved as source blobs. Keep the local working tree intact until deliberately reviewed and backed up.

## 3. Docker image inventory

### Active Node image

- Tags: ai-worker-sandbox:node22, ai-worker-sandbox:node22-nonroot-20261118
- Image ID: sha256:e4e5a21c563ff6d1bbd4b5939e8169b8a93834e0d6470e7e328d5024ad3ca5f6
- Debian 12.15
- User: 65532:65532
- Node: v22.23.5
- npm: 10.9.9
- esbuild: 0.25.12
- Git: 2.39.5

### Active Python image

- Tag: ai-worker-sandbox:py311
- Image ID: sha256:ecd3c31f56b2e701fea87ea75c6bbe7140bad609f21030081db3111743b66366
- Debian 13.7
- User: 65532:65532

### Node Alpine + Git candidate

- Tag: ai-worker-sandbox:node22-alpine-git-probe-20261118
- Image ID: sha256:b80c9164962b4df384cf8a0c34172747626545fee6af8e62387d29d5717c16ae
- Alpine 3.24.4; Node 22.23.5; npm 12.2.2; esbuild 0.28.1; Git 2.54.1
- Non-root user 65532:65532
- Candidate only; not approved as an active-image replacement.

### Other Node candidate

- Tag: ai-worker-sandbox:node22-alpine-final-candidate-20261118
- Image ID: sha256:f3fb5568bceb2b0d7a161fc1948b4440b2766cf50aaa8fa3a59966244a32646d
- Alpine 3.24.4; Node 22.23.5; npm 12.2.2; esbuild 0.28.1; Git absent.
- Candidate only.

## 4. Sandbox runtime security — code evidence

The inspected src/ai_worker/sandbox.py Docker invocation includes:

- --network=none by default (bridge only when explicitly enabled).
- --read-only.
- --cap-drop=ALL.
- --security-opt=no-new-privileges:true.
- --pids-limit=128.
- --memory=1g.
- --cpus=1.
- Host UID/GID mapping, with refusal to launch from a root-owned host process.
- A disposable workspace bind mount as the intended writable host mount.
- /tmp tmpfs with noexec,nosuid,nodev,size=256m.
- Runtime timeout bounded to 1–3600 seconds by the API; Pipeline call sites generally cap individual checks at 300–900 seconds.

This disproves the earlier hypothesis that CPU, memory and PID limits were absent. These controls reduce resource-exhaustion impact but do not patch vulnerable packages or prove vulnerable code paths unreachable.

## 5. npm and Node QA behavior

Observed in src/ai_worker/node_qa.py and src/ai_worker/pipeline.py:

- Node project inspection reads the root package.json; it does not recursively discover arbitrary nested package manifests.
- It validates metadata, scripts, dependency fields, package manager and lockfile consistency.
- The inspected code contains no npm install or npm ci invocation.
- Pipeline invokes npm --offline --ignore-scripts run test and npm --offline --ignore-scripts run build only when the project is eligible, has the corresponding script, and declares no external dependencies.
- External dependencies cause automatic Node test/build execution to be skipped; unsupported metadata also prevents execution.
- --ignore-scripts does not disable explicitly requested npm run test/build scripts.
- A find command on the repository root (depth ≤3) returned no package.json; this does not prove the runtime workspace can never contain one.

## 6. Security findings and scan coverage

### Active Node image — confirmed package findings

Active image ID was checked directly and matches the Trivy report metadata:

- npm 10.9.9
- glob 10.5.0
- minimatch 9.0.9

Trivy reported:

| Package | Installed | Vulnerability | Severity | Fixed version |
|---|---:|---|---|---:|
| glob | 10.5.0 | CVE-2026-118773 | MEDIUM | 14.0.2 |
| minimatch | 9.0.9 | CVE-2026-118764 | MEDIUM | 11.0.1 |

These are confirmed findings in the active image, not merely candidate-only findings. The package versions and image ID were independently inspected. Do not label them false positives without reachability evidence and advisory validation.

Current assessment:
- The reported issues concern resource-exhaustion / denial-of-service conditions, not demonstrated remote code execution.
- Sandbox network isolation and resource caps are mitigating controls, not a fix for the vulnerable package versions.
- Actual reachability of the vulnerable glob AbortSignal path and minimatch optimization-level path in npm's execution path remains unproven.
- No package upgrade or image replacement has been approved or performed.

### Candidate Node Alpine + Git

Trivy report was tied to candidate image ID sha256:b80c9164962b4df384cf8a0c34172747626545fee6af8e62387d29d5717c16ae:
- Alpine OS packages: zero findings in that report.
- Node package findings: the same two MEDIUM CVEs in npm's glob 13.0.6 and minimatch 10.2.5.
- No CRITICAL/HIGH Node package findings were shown in that report.
- This candidate passed the actual Runner compatibility check described below, but remains unapproved.

### Other security work

- Active Debian Node image's earlier Trivy report showed significant OS and package findings (reported totals at that scan: 2 CRITICAL, 147 HIGH, 149 LOW, 190 MEDIUM, 9 UNKNOWN across detected targets). Treat these as dated scan evidence, not a fresh scan result.
- Active Python image's earlier Trivy report showed 119 HIGH, 131 LOW, 140 MEDIUM and 7 UNKNOWN across detected targets; package and OS findings remain subject to remediation/triage.
- Trivy config scan reported two LOW findings for missing HEALTHCHECK; no blind HEALTHCHECK change was made.
- Semgrep reported 11 findings, including six mutable GitHub Action tags; triage and remediation/exception decisions remain open.
- OSV no-resolve scan of 50 direct packages returned no findings, but transitive resolution failed because deps.dev returned HTTP 403. Coverage is incomplete and must not be described as a clean full dependency scan.
- Pre-commit configuration contains four hooks (check-ast, check-yaml, check-toml, check-merge-conflict); they were reported PASS. The configuration file remains untracked locally.
- A final Trivy scan after the latest Dockerfile hardening was still open in the v2.4 evidence snapshot.

## 7. Test and acceptance evidence

Reported completed evidence (do not repeat unless a code change invalidates it):

- Fresh macOS virtual-environment bootstrap path completed.
- pip 26.3, setuptools 79.0.1, pytest 9.2.0 observed in that tested environment.
- pip check: no broken requirements.
- pytest: 311 passed in 1.74 seconds.
- Actual run_in_sandbox() Runner compatibility test against Alpine+Git candidate:
  - workspace read/write: PASS
  - Git 2.54.1 detected
  - git apply --check and git apply: PASS
  - TypeScript/esbuild compile and execution returned 42: PASS
  - exit 0; no timeout
- These tests establish only the stated paths. They do not close Stage A or certify VM-grade isolation.
- A direct same-process import pip followed by import setuptools distutils assertion was observed, but the actual bootstrap CLI subprocess path succeeded. Do not change pip/setuptools solely on the basis of that non-representative import-order probe.

## 8. Current open issues

1. Stage A exit criteria must be reconciled line-by-line with the v2.4 Full Execution Plan and Live Checklist.
2. Final post-hardening Trivy scans for relevant active/candidate images and JSON/exit-code evidence remain required.
3. Active Node image has two confirmed MEDIUM CVEs; assess call-path reachability and decide on minimal remediation or a documented exception with evidence.
4. Candidate image is not an approved replacement; compare full Runner/security evidence before any decision.
5. Semgrep findings and mutable GitHub Action references need triage.
6. OSV transitive coverage is incomplete due to deps.dev 403; choose a reliable alternative or document a bounded exception.
7. Backup/restore evidence, sandbox acceptance evidence and essential tool/integration status must meet the exact v2.4 exit criteria.
8. The local uncommitted source changes listed above need deliberate review and backup; do not discard or silently fold them into documentation work.
9. The binary v2.4 PDFs have not yet been committed to this GitHub branch. Their source-library identity and SHA-256 values are recorded in docs/plans/v2.4/README.md.

## 9. Immediate next action

Resume with the pending read-only inspection of npm's internal call sites in the active Node image:
- search the npm-bundled glob package for AbortSignal/signal use;
- search npm-bundled minimatch consumers for optimizationLevel and construction/call sites;
- distinguish internal npm call sites from any paths influenced by task/workspace input.

Do not modify Dockerfiles, npm versions, active image tags or runtime configuration before that evidence is reviewed.

## 10. Session close discipline

At each future handoff, record:
- branch and HEAD;
- Git status, including untracked files;
- exact active/candidate image IDs;
- backup and restore evidence;
- tests actually run and their raw result locations;
- scan report paths, image metadata and exit codes;
- unresolved findings and next single action.

Never claim active work time that was not measured.
