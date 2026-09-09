#!/usr/bin/env python3
"""
Muestra, de un vistazo, los partidos con edge positivo (valor) capturados en
data/processed/live_odds_log.jsonl y que todavía no arrancaron — la lista
de "candidatos a apostar ahora" que hoy no se ve en ningún lado (ni en la
web, ni impreso por fetch_live_odds.py).

No trae cuotas nuevas ni gasta cuota del API — solo lee lo último que dejó
fetch_live_odds.py (corre cada 6h vía cron_fetch_live_odds.sh). Si un
partido cambió mucho de cuota desde la última corrida, esto puede estar
desactualizado hasta 6h.

Uso:
  python scripts/show_value_bets.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BACKEND_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import odds_client  # noqa: E402

LOG_PATH = BACKEND_DIR / "data" / "processed" / "live_odds_log.jsonl"

MIN_EDGE = 0.0
SUSPICIOUS_EDGE = odds_client.SUSPICIOUS_EDGE_THRESHOLD


def load_latest_snapshot_per_event() -> list[dict]:
    if not LOG_PATH.exists():
        return []
    rows = [json.loads(line) for line in LOG_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    latest: dict[str, dict] = {}
    for row in rows:
        event_id = row["event_id"]
        if event_id not in latest or row["fetched_at"] > latest[event_id]["fetched_at"]:
            latest[event_id] = row
    return list(latest.values())


def main() -> None:
    rows = load_latest_snapshot_per_event()
    if not rows:
        print("live_odds_log.jsonl no existe o está vacío todavía. Corré fetch_live_odds.py primero.")
        return

    now = datetime.now(timezone.utc)
    upcoming = [r for r in rows if datetime.fromisoformat(r["commence_time"].replace("Z", "+00:00")) > now]

    candidates = []
    for row in upcoming:
        if row["edge_p1"] > MIN_EDGE:
            candidates.append((row, "p1", row["p1_name"], row["odds_p1"], row["model_p1_prob"],
                                row["implied_p1"], row["edge_p1"]))
        if row["edge_p2"] > MIN_EDGE:
            candidates.append((row, "p2", row["p2_name"], row["odds_p2"], row["model_p2_prob"],
                                row["implied_p2"], row["edge_p2"]))

    if not candidates:
        print(f"Ningún partido próximo con edge positivo ahora mismo "
              f"(de {len(upcoming)} partido(s) todavía no jugado(s) en el log).")
        return

    candidates.sort(key=lambda c: c[6], reverse=True)
    print(f"{len(candidates)} apuesta(s) con edge positivo, de {len(upcoming)} partido(s) próximo(s) en el log:\n")
    for row, side, name, odds, model_prob, implied_prob, edge in candidates:
        opponent = row["p2_name"] if side == "p1" else row["p1_name"]
        kickoff = row["commence_time"]
        print(f"- {name} vs {opponent}  (arranca {kickoff}, book: {row['book']})")
        print(f"    apostar a: {name}   cuota: {odds}   "
              f"prob. modelo: {model_prob:.1%}   prob. implícita: {implied_prob:.1%}   "
              f"edge: +{edge:.1%}")
        print(f"    (dato de hace {(now - datetime.fromisoformat(row['fetched_at'])).total_seconds() / 3600:.1f}h)")
        if edge > SUSPICIOUS_EDGE:
            print(f"    ATENCIÓN: edge > {SUSPICIOUS_EDGE:.0%} — antes de apostar, chequeá a mano si hay "
                  f"lesión, retiro o baja reciente de {name} o {opponent} que el modelo no vio.")


if __name__ == "__main__":
    main()
