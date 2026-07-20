#!/usr/bin/env bash
set -euo pipefail

# backend/scripts/pre-deploy.bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/.."

uv run alembic upgrade head