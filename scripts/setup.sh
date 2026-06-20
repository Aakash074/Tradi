#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "=== Tradi Setup ==="

# Backend
echo "Setting up Python backend..."
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd "$ROOT"

# Frontend
echo "Setting up Next.js frontend..."
cd frontend
npm install
cd "$ROOT"

# Environment
if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi

echo ""
echo "Setup complete!"
echo ""
echo "Run V3 agent + API:"
echo "  cd backend && source .venv/bin/activate && cd .."
echo "  python -m tradi.agent --mode paper --config config/production.yaml --live-cmc --duration 48h"
echo ""
echo "Dashboard: cd frontend && npm run dev  →  http://localhost:3000"
echo ""
echo "Preflight: bash scripts/competition_preflight.sh"
echo "Register:  twak compete register  (before June 22 UTC)"
