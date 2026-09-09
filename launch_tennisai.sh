#!/usr/bin/env bash
# Arranca el backend (FastAPI) y el frontend (Next.js) si no están corriendo
# ya, y abre la página "hoy" en el navegador. Pensado para el ícono de
# escritorio (launch_tennisai.desktop) — doble clic y listo.

set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

is_listening() {
  ss -ltn 2>/dev/null | grep -q ":$1 "
}

if ! is_listening 8000; then
  cd "$BACKEND_DIR" || exit 1
  nohup venv/bin/python3 -m uvicorn api:app --port 8000 > uvicorn.log 2>&1 &
  disown
fi

if ! is_listening 3000; then
  cd "$FRONTEND_DIR" || exit 1
  nohup npm run dev > next.log 2>&1 &
  disown
fi

# Esperar a que el frontend responda antes de abrir el navegador (hasta ~20s)
for _ in $(seq 1 20); do
  is_listening 3000 && break
  sleep 1
done

xdg-open "http://localhost:3000/today" >/dev/null 2>&1 &
