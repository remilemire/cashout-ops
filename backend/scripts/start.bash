#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/.."

# Preserve Render's forwarded scheme handling. Wildcard X-Forwarded-For
# parsing is not a safe rate-limit identity: configure
# RATE_LIMIT_CLIENT_IP_SOURCE=cloudflare and the trust boundary in README.md.
uv run --active gunicorn -k uvicorn.workers.UvicornWorker app.main:app --bind 0.0.0.0:$PORT --forwarded-allow-ips='*'