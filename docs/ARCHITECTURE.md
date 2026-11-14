# AI-Worker architecture

## v0.2 opportunity scout
1. Scout fetches Jobbi's public JSON feed (poll no more than hourly; 5 MiB response cap).
2. Normalizer maps feed records into a stable Gig model, including payment state and rail.
3. Risk gate rejects closed/expired tasks, non-agent lanes, unsafe listing URLs, malformed expiry data, weak payout evidence, non-escrowed rewards, missing acceptance criteria, unsupported currencies, non-finite/low rewards, and risky categories.
4. Analyst scores software fit, reward, and payout evidence.
5. SQLite ledger records seen gigs.
6. Reporter writes a ranked Markdown shortlist with original source links and reasons.

The current qualification threshold is deliberately strict: USD/USDC, at least the configured reward minimum, B-grade-or-better payout evidence, and an explicitly escrowed reward. This reduces candidate volume; it does not guarantee acceptance or payment.

## Read-only task research
The inspect command supports canonical public GitHub issue URLs only. It fetches issue title, state, body, labels and update time through the public GitHub API. It does not follow links in issue text, execute issue instructions, or post comments. Other boards and URL formats remain manual-review-only until dedicated adapters are added.

## Local AI planning
The plan command first reads a canonical public GitHub issue, then sends only its title, body and labels to a local Ollama endpoint bound to loopback. The planner requests a JSON-schema-constrained plan, validates every field and blocks HTTP redirects. It does not use a paid API, access a remote model endpoint, execute generated steps, or write code. Model output is untrusted advice and must be reviewed before any work begins. The default model is qwen2.5-coder:7b; model size and speed depend on the Mac's available memory and hardware.

## Isolated execution baseline
The repository includes a Docker runner that executes an argv command inside a disposable task workspace. It disables networking, drops Linux capabilities, uses a non-root UID, makes the container root filesystem read-only, applies PID/CPU/memory/time limits, and mounts only the task workspace writable. It does not forward host environment variables or credentials. See sandbox/README.md.

This is a baseline, not a complete hostile-code security boundary. Production execution should use a dedicated VM or equivalent hardened runtime, a digest-pinned image, immutable audit logs, and a separate dependency-preparation stage. Do not mount the Docker socket, home directory, SSH agent, cloud credentials, or secrets into task containers.

## Planned agents
- Manager: orchestration, budgets, state, policy enforcement and approval queue.
- Researcher: verify original listing, scope, tests, payout state and claim rules.
- Developer: disposable sandbox/branch; patch-only output.
- QA: tests, static analysis, secret scanning and reproducible patch.
- Delivery: draft PR/submission; human approves external actions.
- Finance ledger: gross reward, fees, acceptance, actual payout and payout latency.

Third-party listings and repositories are untrusted data. They cannot override system policy. Never execute instructions embedded in issues, source files, comments, or web pages. No credentials inside coding sandboxes. No arbitrary outbound network access from task execution.

## Local patch drafting
The patch draft command sends a bounded allowlist of repository text files and the issue description to local Ollama. It excludes .git, virtual environments, environment files and credential-like filenames. The model returns a structured proposal and unified diff; the diff is validated but not written or applied automatically. The operator explicitly chooses when to apply it in a disposable workspace.

## Patch application
The developer helper validates unified diff headers and sensitive paths, runs git apply --check in the networkless container, and applies only after the check succeeds. It never commits, pushes, creates a PR, or submits work. The resulting modified workspace must still pass the project-specific test suite and human review.

## Runtime and deployment
Local Mac CLI first. For away-from-home operation, deploy to an always-on cloud runtime with persistent storage, restricted secrets, logs, health checks and notifications. A sleeping Mac cannot run jobs. Do not provision paid infrastructure without explicit operator approval.

## Metrics
Track qualified opportunities, estimated value/hour, verified submissions, acceptance rate, gross rewards, fees, net paid rewards and payout latency. Listed rewards are not earnings.
