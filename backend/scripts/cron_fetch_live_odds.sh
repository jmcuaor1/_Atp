#!/usr/bin/env bash
# Fase 7 — wrapper para crontab. Levanta la API local si hace falta, corre
# fetch_live_odds.py y deja todo registrado en data/processed/fetch_live_odds_cron.log
# (no en el jsonl de datos, ese lo escribe el script de Python).

BACKEND_DIR="/home/juanmcr/Desktop/_Atp/backend"
LOG_FILE="$BACKEND_DIR/data/processed/fetch_live_odds_cron.log"

cd "$BACKEND_DIR" || exit 1
mkdir -p "$(dirname "$LOG_FILE")"

{
  echo "===== $(date -u +%Y-%m-%dT%H:%M:%SZ) ====="

  status=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health)
  if [ "$status" != "200" ]; then
    echo "API no responde (status=$status), levantando uvicorn en background..."
    nohup venv/bin/uvicorn api:app --port 8000 >> uvicorn.log 2>&1 &
    disown
    sleep 5
  fi

  run_output=$(venv/bin/python3 scripts/fetch_live_odds.py 2>&1)
  echo "$run_output"

  remaining=$(echo "$run_output" | grep -o "restantes=[0-9]*" | tail -1 | cut -d= -f2)
  if [ -n "$remaining" ] && [ "$remaining" -lt 50 ]; then
    echo "ADVERTENCIA: cuota de The Odds API baja ($remaining restantes) — considerar bajar la frecuencia del cron (actualmente cada 6h)."
  fi
} >> "$LOG_FILE" 2>&1
