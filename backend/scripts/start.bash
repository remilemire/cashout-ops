#!/usr/bin/env bash
set -euo pipefail

# backend/scripts/start.bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/.."

# Behind Render only the platform proxy can reach the service, so trusting
# X-Forwarded-For from any peer is safe there; uvicorn's worker then rewrites
# request.client to the real client for per-IP rate limiting.
uv run gunicorn -k uvicorn.workers.UvicornWorker app.main:app --bind 0.0.0.0:$PORT --forwarded-allow-ips='*'