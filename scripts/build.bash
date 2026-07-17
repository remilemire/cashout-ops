#!/usr/bin/env bash
set -euo pipefail

# scripts/build.bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/../backend"

uv sync

cd ../frontend

npm ci
npm run build