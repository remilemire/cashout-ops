#!/usr/bin/env bash
set -euo pipefail

# backend/scripts/build.bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/.."

# --active so Render uses the correct venv
uv sync --active

cd ../frontend

npm ci
npm run build