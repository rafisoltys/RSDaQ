#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
if [ -f "$REPO_DIR/.venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source "$REPO_DIR/.venv/bin/activate"
fi
cd "$REPO_DIR"
exec python -m rsdaq "$@"
