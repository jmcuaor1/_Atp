#!/usr/bin/env bash
# Fase 7 — wrapper para crontab (semanal). Corre weekly_live_odds_summary.py
# (cobertura del log crudo), settle_live_odds.py (intenta liquidar partidos
# ya jugados y calcula ROI acumulado si hay apuestas sentenciadas) y
# notify_threshold.py (manda un email una sola vez al llegar a 150 apuestas
# liquidadas). Todo queda en un único archivo legible que se sobreescribe
# cada semana.

BACKEND_DIR="/home/juanmcr/Desktop/_Atp/backend"
SUMMARY_FILE="$BACKEND_DIR/data/processed/weekly_summary.txt"

cd "$BACKEND_DIR" || exit 1

{
  echo "===== Resumen semanal Fase 7 — $(date -u +%Y-%m-%dT%H:%M:%SZ) ====="
  echo
  echo "--- Cobertura del log de cuotas en vivo ---"
  venv/bin/python3 scripts/weekly_live_odds_summary.py
  echo
  echo "--- Liquidación de apuestas / ROI acumulado ---"
  venv/bin/python3 scripts/settle_live_odds.py
  echo
  echo "--- Aviso por email (umbral de 150 apuestas) ---"
  venv/bin/python3 scripts/notify_threshold.py
} > "$SUMMARY_FILE" 2>&1

echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) resumen semanal actualizado en $SUMMARY_FILE" >> "$BACKEND_DIR/data/processed/fetch_live_odds_cron.log"
