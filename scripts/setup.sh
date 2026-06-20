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
echo "Start backend:  cd backend && source .venv/bin/activate && uvicorn main:app --reload --port 8000"
echo "Start frontend: cd frontend && npm run dev"
echo ""
echo "Register for competition (before June 22 UTC): twak compete register"
