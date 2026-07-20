#!/usr/bin/env bash
set -euo pipefail

# backend/scripts/start.bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/.."

uv run gunicorn -k uvicorn.workers.UvicornWorker app.main:app --bind 0.0.0.0:$PORT