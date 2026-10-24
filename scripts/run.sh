#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ -f .env ]; then
  exec uv run --env-file .env main.py "$@"
fi
exec uv run main.py "$@"
