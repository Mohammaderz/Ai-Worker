# AI-Worker architecture

## Opportunity scout
1. Scout fetches Jobbi's public JSON feed (poll no more than hourly; 5 MiB response cap).
2. Normalizer maps records into a stable Gig model, including payment state, payment rail and acceptance type.
3. Risk gate rejects closed/expired tasks, non-agent lanes, unsafe listing URLs, malformed expiry/feed data, unknown claim availability, weak payout evidence, non-escrowed rewards, missing acceptance criteria, unsupported currencies, non-finite/low rewards, and sensitive/high-risk categories.
4. Analyst scores software fit, reward and payout evidence; board-level public payout evidence contributes only a small ranking bonus. It cannot override any hard risk, escrow, currency, claim-availability or reward gate.
5. SQLite ledger records seen gigs and additive schema migrations.
6. Reporter writes a ranked Markdown shortlist with original source links and reasons.

The current source-priority policy and its evidence limitations are documented in `docs/MARKET-INTELLIGENCE-2026-11-14.md`. The qualification threshold is deliberately strict: USD/USDC, at least the configured reward minimum, B-grade-or-better payout evidence, and an explicitly escrowed reward. This reduces candidate volume; it does not guarantee acceptance or payment.

## Read-only task research
The inspect command supports canonical public GitHub issue URLs only. It fetches issue title, state, body, labels and update time through the public GitHub API. It does not follow links in issue text, execute issue instructions, or post comments. Other boards and URL formats remain manual-review-only until dedicated adapters are added.

## Workspace preparation
The prepare command derives the repository from a validated public GitHub issue URL and performs a shallow HTTPS clone. It disables Git hooks, submodule recursion, LFS smudging, interactive prompts and host-level Git configuration/credentials. Workspaces must be new children of the configured scratch root. Private repositories are not supported by this path.

## Local AI planning and patch drafting
The plan command sends only issue title, body and labels to a local Ollama endpoint bound to loopback. The planner requests a JSON-schema-constrained plan, validates every field and blocks HTTP redirects.

The patch draft command sends a bounded allowlist of repository text files plus the issue description to local Ollama. It excludes .git, virtual environments, environment files and credential-like filenames. The model returns a structured proposal and unified diff; the diff is validated but not written or applied automatically. The operator explicitly chooses when to apply it.

The default model is qwen2.5-coder:7b. Model size and speed depend on local hardware. No paid API or remote model endpoint is used by default. Model output is untrusted advice, not an authority.

## Isolated patch application and execution
The Docker runner executes argv commands inside a disposable task workspace. It disables networking, drops Linux capabilities, uses a non-root host UID, makes the container root filesystem read-only, applies PID/CPU/memory/time limits, and mounts only the task workspace writable. It does not forward host environment variables or credentials.

The patch helper validates unified diff paths and blocks traversal, .git changes, symlinks, submodules, environment/credential files and GitHub workflow edits. It runs git apply --check in the networkless container and applies only after the check succeeds. It never commits, pushes, creates a PR, or submits work. Project-specific tests and human review remain required.

This is a baseline, not a complete hostile-code security boundary. Production execution should use a dedicated VM or equivalent hardened runtime, a digest-pinned image, immutable audit logs, and a separate dependency-preparation stage. Do not mount the Docker socket, home directory, SSH agent, cloud credentials, or secrets into task containers.

## End-to-end local pipeline
The `pipeline` command connects the read-only Jobbi scout to task execution. It refreshes and revalidates a selected gig when invoked by ID, or accepts a canonical public GitHub issue URL. It rejects stale/closed issues, clones the public repository into a new scratch workspace, requests a structured local plan and patch, and stores a review package. It applies a patch only when the plan has no blockers, risk is not high, and the patch proposal has no unanswered questions. Python syntax and detected pytest suites run in the networkless Python sandbox. Changed JavaScript/TypeScript files are transpiled for syntax validation with esbuild in a separate pinned Node 22 networkless sandbox. Dependency-aware Node test suites are not yet run because project dependencies are not installed from untrusted manifests. It records test logs and exit codes. It does not install project dependencies from untrusted task content.

A successful local pipeline status means only that its configured checks passed. It is not proof that the bounty maintainer will accept the patch or pay the reward. Non-Python projects currently require a project-specific runner before automated testing can be considered complete.

## Planned next stages
- Manager: orchestration, budgets, state, policy enforcement and approval queue.
- Researcher: adapters for additional original boards; verify task scope, claim rules and payout evidence.
- QA: project-specific dependency preparation, tests, static analysis and secret scanning.
- Delivery: draft PR/submission; human approval before external publication.
- Finance ledger: gross reward, fees, acceptance, actual payout and payout latency.
- Runtime: always-on cloud deployment only after cost approval, security review, persistence and monitoring.

Third-party listings, issues and repositories are untrusted data. They cannot override system policy. Never execute instructions embedded in issues, source files, comments or web pages. No credentials inside coding sandboxes. No arbitrary outbound network access from task execution.

## Scheduled scans
After merge to the default branch, a GitHub Actions workflow runs the public read-only scout every six hours. It restores a short-lived SQLite cache and publishes the report and ledger as 14-day artifacts. It does not claim tasks, message clients or submit work.

## Outcome and payout ledger
A local SQLite task_outcomes table tracks claimed, in-progress, submitted, accepted, rejected and paid states with cumulative hours, actual gross receipts, fees, timestamps and notes. Transitions are constrained; only a paid record with a real gross amount contributes to earnings. Reports calculate acceptance rate, net per tracked task hour across paid and unpaid attempts only when every tracked task has an explicit hours value, and conditional net per paid-task hour. Missing hours suppress the all-task hourly metric and source-priority adjustment; they are never silently treated as zero.

## Metrics
Track qualified opportunities, estimated value/hour, verified submissions, acceptance rate, gross rewards, fees, net paid rewards and payout latency. Source-level economics are computed only from manually recorded outcomes and actual payments. After at least 3 submissions, 2 payments and complete hours coverage for a source, a capped ±8-point ranking adjustment uses observed acceptance rate, all-task net/hour (including unpaid attempts) and payout delay. Missing time data disables the adjustment. This adjustment only reorders already-qualified opportunities; it never overrides payout, escrow, currency, claim-availability or risk gates. Insufficient samples produce no adjustment. Listed rewards are not earnings.
