#!/usr/bin/env bash
set -euo pipefail

# backend/scripts/build.bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/.." # /backend

pip install --upgrade pip
pip install .

cd ../frontend

npm ci
npm run build