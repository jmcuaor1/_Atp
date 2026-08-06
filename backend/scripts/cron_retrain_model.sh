#!/usr/bin/env bash
# Fase 7 — wrapper para crontab (diario). Descarga los partidos nuevos de
# TML-Database (update_tml_data.py), reentrena el modelo con datos frescos
# (src/model.py) y reinicia uvicorn para que la API sirva las predicciones
# con el modelo nuevo. Si falla cualquier paso, no se toca el modelo/API
# que ya está corriendo — se mantiene el de la última corrida exitosa.

BACKEND_DIR="/home/juanmcr/Desktop/_Atp/backend"
LOG_FILE="$BACKEND_DIR/data/processed/retrain_model_cron.log"

cd "$BACKEND_DIR" || exit 1
mkdir -p "$(dirname "$LOG_FILE")"

{
  echo "===== $(date -u +%Y-%m-%dT%H:%M:%SZ) ====="

  echo "--- Descargando datos nuevos (TML-Database) ---"
  if ! venv/bin/python3 scripts/update_tml_data.py; then
    echo "ERROR: update_tml_data.py falló, no se reentrena (se mantiene el modelo actual)."
    exit 1
  fi

  echo
  echo "--- Reentrenando modelo ---"
  if ! venv/bin/python3 src/model.py; then
    echo "ERROR: model.py falló, no se reinicia la API (se mantiene el modelo actual)."
    exit 1
  fi

  echo
  echo "--- Reiniciando API con el modelo nuevo ---"
  pkill -f "uvicorn api:app" 2>/dev/null
  sleep 2
  nohup venv/bin/uvicorn api:app --port 8000 >> uvicorn.log 2>&1 &
  disown
  sleep 3
  status=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health)
  echo "API status tras reinicio: $status"
} >> "$LOG_FILE" 2>&1
