# Disposable task sandbox

Build the local image:

\`\`\`bash
docker build -f sandbox/Dockerfile -t ai-worker-sandbox:py311-alpine-nopip-20261119 .
\`\`\`

The runner in ai_worker.sandbox is deliberately restrictive:
- no network access;
- read-only container root filesystem;
- no Linux capabilities and no privilege escalation;
- non-root UID, PID/memory/CPU limits and bounded temporary filesystems;
- only the disposable task workspace is mounted writable;
- no host environment variables, API keys, SSH agents, Docker socket or home directory are mounted;
- command arguments are passed directly, without a host shell;
- timeout cleanup attempts to kill and remove the container.

The Python image includes Git and pinned pytest 9.2.0; pip is used only at build time and removed from the runtime. The separate Node 22 image includes Git and pinned esbuild 0.28.1 for JavaScript/TypeScript syntax transpilation; npm/npx are intentionally absent, so dependency-free package scripts are executed with the built-in `node --run` command. Both images run with no network, no host secrets and only the disposable workspace mounted writable. The developer helper rejects binary patches, path traversal, .git changes, symlinks, submodules, environment files and credential-like paths.

Node QA support contract (npm-free runtime):
- Only the root `package.json` `test` and `build` scripts are executed automatically, via `node --run`.
- No dependency installation happens in the sandbox. Projects declaring external dependencies are not run automatically: unsupported without a validated npm lockfile, skipped when one is present.
- npm workspaces, non-npm installers and project `.npmrc` files are rejected from automated Node checks.
- npm lifecycle hooks (`prebuild`/`postbuild`, `pretest`/`posttest`), `npm_*` environment variables, forwarding of extra command arguments and npm's exact exit-code values are not guaranteed; a non-zero exit code is treated as a failure.

Example (after creating a disposable directory under .ai-worker/sandboxes/):

\`\`\`python
from ai_worker.sandbox import run_in_sandbox

result = run_in_sandbox(
    ".ai-worker/sandboxes/task-123",
    ["python", "-m", "compileall", "."],
    scratch_root=".ai-worker/sandboxes",
)
print(result.exit_code, result.stdout, result.stderr)
\`\`\`

This is a baseline, not a complete hostile-code security boundary. Use a dedicated VM/host for production execution, keep the Docker daemon patched, never mount sensitive paths, and pin the base image by digest. Dependency installation and all external network access must happen in a separate reviewed preparation stage, never inside a task sandbox. Human approval remains required before any claim, bid, message, publication or submission.
