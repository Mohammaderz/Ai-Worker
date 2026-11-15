#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

fail() {
  printf 'ERROR: %s\n' "$1" >&2
  exit 1
}

if [[ "$(uname -s)" != "Darwin" ]]; then
  fail "This bootstrap script is for macOS only."
fi

if ! command -v python3 >/dev/null 2>&1; then
  fail "Python 3.11+ is required. Install it with Homebrew: brew install python@3.11"
fi

PYTHON_VERSION="$(python3 -c 'import sys; print(str(sys.version_info.major)+"."+str(sys.version_info.minor))')"
python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' \
  || fail "Python 3.11+ is required; found $PYTHON_VERSION."

command -v docker >/dev/null 2>&1 || fail "Docker Desktop is required. Install and open Docker Desktop first."
docker info >/dev/null 2>&1 || fail "Docker is installed but not running. Open Docker Desktop and retry."

command -v ollama >/dev/null 2>&1 || fail "Ollama is required. Install it from https://ollama.com/download and retry."

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"

printf '\nBuilding the isolated Python task image...\n'
docker build -f sandbox/Dockerfile -t ai-worker-sandbox:py311 .

printf '\nBuilding the isolated Node task image...\n'
docker build -f sandbox/Dockerfile.node -t ai-worker-sandbox:node22 .

mkdir -p .ai-worker/sandboxes .ai-worker/proposals data reports

printf '\nRunning the project test suite...\n'
pytest -q

if ! ollama list >/dev/null 2>&1; then
  printf '\nOllama is installed, but its local server is not running. Start the Ollama app or run "ollama serve", then rerun this script to check/download the model.\n'
elif ! ollama list 2>/dev/null | grep -q 'qwen2.5-coder:7b'; then
  printf '\nThe local coding model qwen2.5-coder:7b is not installed.\n'
  read -r -p "Download it now? This requires several GB of disk space. [y/N] " ANSWER
  case "$ANSWER" in
    y|Y|yes|YES) ollama pull qwen2.5-coder:7b ;;
    *) printf 'Skipped model download. Run later: ollama pull qwen2.5-coder:7b\n' ;;
  esac
fi

if ollama list >/dev/null 2>&1 && ! ollama list 2>/dev/null | grep -q 'deepseek-coder:6.7b'; then
  printf '\\nThe independent reviewer model deepseek-coder:6.7b is not installed.\\n'
  read -r -p "Download it now? This requires several GB of disk space. [y/N] " REVIEWER_ANSWER
  case "$REVIEWER_ANSWER" in
    y|Y|yes|YES) ollama pull deepseek-coder:6.7b ;;
    *) printf 'Skipped reviewer model download. The pipeline will safely block patches until it is installed. Run later: ollama pull deepseek-coder:6.7b\\n' ;;
  esac
fi

cat <<'EOF'

AI-Worker local setup is ready.

1. In Terminal A, start the local model server:
   ollama serve

2. In Terminal B, refresh the opportunity list:
   ai-worker scan --limit 1000

3. Copy an eligible Gig ID from reports/latest.md, then run:
   ai-worker pipeline --gig-id SOURCE:NATIVE_ID

Review the generated REPORT.md and patch manually. Nothing is claimed or submitted automatically.
EOF
