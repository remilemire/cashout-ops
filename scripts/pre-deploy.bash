#!/usr/bin/env bash
set -euo pipefail

# scripts/pre-deploy.bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/../backend"

uv run alembic upgrade head