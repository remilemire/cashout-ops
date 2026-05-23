#!/usr/bin/env bash
set -euo pipefaul

# backend/scripts/start.bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/.." # /backend

gunicorn -k uvicorn.workers.UvicornWorker app:app --bind 0.0.0.0:$PORT