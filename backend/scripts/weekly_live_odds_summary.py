#!/usr/bin/env python3
"""
Resumen de cobertura del log crudo de la Fase 7 (CLV en vivo). No sentencia
nada ni calcula ROI (eso lo hace settle_live_odds.py) — solo reporta cuánto
se acumuló en data/processed/live_odds_log.jsonl, que llena fetch_live_odds.py
vía cron cada 6h. Pensado para correr una vez por semana (ver
scripts/cron_weekly_summary.sh).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
LOG_PATH = BACKEND_DIR / "data" / "processed" / "live_odds_log.jsonl"


def main() -> None:
    if not LOG_PATH.exists():
        print("Todavía no existe live_odds_log.jsonl — el cron de fetch_live_odds.py no corrió con éxito ninguna vez.")
        return

    rows = [json.loads(line) for line in LOG_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        print("live_odds_log.jsonl existe pero está vacío.")
        return

    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    fetched_ats = [datetime.fromisoformat(r["fetched_at"]) for r in rows]
    rows_last_week = [r for r, dt in zip(rows, fetched_ats) if dt >= week_ago]

    unique_events = {r["event_id"] for r in rows}
    unique_events_last_week = {r["event_id"] for r in rows_last_week}
    books = {r["book"] for r in rows}

    print(f"Filas totales acumuladas: {len(rows)}")
    print(f"Filas nuevas en los últimos 7 días: {len(rows_last_week)}")
    print(f"Partidos únicos (todo el historial): {len(unique_events)}")
    print(f"Partidos únicos (últimos 7 días): {len(unique_events_last_week)}")
    print(f"Books presentes: {', '.join(sorted(books))}")
    print(f"Rango de fechas capturadas: {min(fetched_ats).date()} a {max(fetched_ats).date()}")


if __name__ == "__main__":
    main()
