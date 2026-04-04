#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-9988}"
STATE_FILE="${STATE_FILE:-$ROOT_DIR/data/app-state.json}"

cd "$ROOT_DIR"
PYTHONPATH=src exec python3 -m media_library_manager.cli serve \
  --host "$HOST" \
  --port "$PORT" \
  --state-file "$STATE_FILE"
