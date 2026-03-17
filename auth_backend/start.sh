#!/usr/bin/env bash
set -euo pipefail

# Preview/runtime start script for auth_backend.
# Ensures we:
# - use the container's virtualenv python if present
# - bind to the platform-allocated port (defaults to 3001 for this container)
# - listen on 0.0.0.0 so the port is reachable outside the container

cd "$(dirname "$0")"

HOST="${HOST:-0.0.0.0}"

# Port selection:
# Different preview/proxy environments may inject different env var names.
# Prefer explicit PORT, but fall back to other common ones.
PORT="${PORT:-${KAVIA_PORT:-${APP_PORT:-3001}}}"

# Prefer local venvs if they exist (repo includes both patterns in some setups).
if [[ -x ".venv/bin/python" ]]; then
  PYTHON_BIN=".venv/bin/python"
elif [[ -x "venv/bin/python" ]]; then
  PYTHON_BIN="venv/bin/python"
else
  PYTHON_BIN="python"
fi

exec "${PYTHON_BIN}" -m uvicorn src.api.main:app --host "${HOST}" --port "${PORT}"
