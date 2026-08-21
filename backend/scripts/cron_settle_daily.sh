#!/usr/bin/env bash
# Wrapper para crontab (diario). Corre settle_predictions.py (acierto de
# pronóstico), settle_live_odds.py (ROI de value bets), y la capa de
# disciplina de apostador profesional de Fase 8: log_bet_decision.py
# (registra la decisión de stake del día contra /matches/today, antes de
# que arranquen los partidos -- ver docs/betting_process.md, "sin apuestas
# en caliente") y settle_bet_log.py (liquida contra resultado real y
# actualiza bankroll_ledger.csv). Los cuatro scripts son idempotentes --
# cada uno solo procesa lo que todavía no procesó -- así que no hay
# problema en que corran acá TODOS los días y encima una vez por semana en
# el resumen (cron_weekly_summary.sh, que llama a los dos primeros).
#
# log_bet_decision.py necesita la API local respondiendo (usa
# /matches/today); si no está arriba la levanta, igual que
# cron_fetch_live_odds.sh.

BACKEND_DIR="/home/juanmcr/Desktop/_Atp/backend"
LOG_FILE="$BACKEND_DIR/data/processed/settle_daily_cron.log"

cd "$BACKEND_DIR" || exit 1
mkdir -p "$(dirname "$LOG_FILE")"

{
  echo "===== $(date -u +%Y-%m-%dT%H:%M:%SZ) ====="

  echo "--- Acierto de pronóstico ---"
  venv/bin/python3 scripts/settle_predictions.py

  echo
  echo "--- ROI de value bets ---"
  venv/bin/python3 scripts/settle_live_odds.py

  echo
  echo "--- Decisión de apuesta profesional (Fase 8) ---"
  status=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health)
  if [ "$status" != "200" ]; then
    echo "API no responde (status=$status), levantando uvicorn en background..."
    nohup venv/bin/uvicorn api:app --port 8000 >> uvicorn.log 2>&1 &
    disown
    sleep 5
  fi
  venv/bin/python3 scripts/log_bet_decision.py

  echo
  echo "--- Liquidar apuestas (Fase 8) ---"
  venv/bin/python3 scripts/settle_bet_log.py
} >> "$LOG_FILE" 2>&1
