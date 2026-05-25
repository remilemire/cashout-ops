#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Setting Up Backend"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

cd "$SCRIPT_DIR/backend"

if [ ! -f .env ]; then
  echo "• Creating backend environment file..."
  cp .env.example .env
fi

echo "• Initializing Python virtual environment..."
python3 -m venv .venv

echo "• Activating virtual environment..."
source .venv/bin/activate

echo "• Installing backend dependencies..."
pip install --upgrade pip
pip install -e .[dev]

echo
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Setting Up Frontend"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

cd ../frontend

echo "• Installing frontend dependencies..."
npm ci

echo "• Building frontend assets..."
npm run build

echo
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Setting Up Database"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

cd ../backend

echo "• Starting Docker services..."
docker compose up -d

echo "• Applying database migrations..."
alembic upgrade head

echo
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Setup Complete"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo