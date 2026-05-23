#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="$ROOT/backend"

echo "=== TennisAI Setup ==="

if [[ ! -d "$BACKEND/venv" ]]; then
  python3 -m venv "$BACKEND/venv"
fi

# shellcheck source=/dev/null
source "$BACKEND/venv/bin/activate"
pip install -r "$BACKEND/requirements-train.txt"
python "$BACKEND/scripts/setup_project.py"

echo ""
echo "Frontend: cd frontend && npm install && npm run dev"
echo "API:      cd backend && source venv/bin/activate && uvicorn api:app --reload"
