# Disposable task sandbox

Build the local image:

\`\`\`bash
docker build -f sandbox/Dockerfile -t ai-worker-sandbox:py311 .
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

The image includes Git and pinned pytest 8.4.2 so model-proposed text patches can be checked with git apply --check, applied only inside the disposable workspace, and Python test suites can run offline. The developer helper rejects binary patches, path traversal, .git changes, symlinks, submodules, environment files and credential-like paths.

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
