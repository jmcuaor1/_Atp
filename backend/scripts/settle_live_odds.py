#!/usr/bin/env python3
"""
Fase 7 — cruza data/processed/live_odds_log.jsonl (cuotas + predicción
capturadas en vivo por fetch_live_odds.py) contra los resultados reales de
The Odds API, para calcular el ROI real de las apuestas que el modelo
habría hecho (mismo criterio que backtest_odds.py / segment_backtest.py:
apostar solo donde model_prob > prob. implícita de la cuota).

Corré esto periódicamente (ej. una vez al día) después de que empiecen a
jugarse los partidos que capturó fetch_live_odds.py. Los partidos que
todavía no tienen resultado quedan pendientes para la próxima corrida.

Nota: si corriste fetch_live_odds.py varias veces para el mismo partido
antes de que se jugara (línea moviéndose), acá solo se sentencia el
snapshot más reciente por (event_id, book) — no cada captura repetida — para
no inflar artificialmente el número de apuestas.

Requiere ODDS_API_KEY en backend/.env (ver .env.example).

Uso:
  python scripts/settle_live_odds.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

BACKEND_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BACKEND_DIR / "src"
SCRIPTS_DIR = BACKEND_DIR / "scripts"
for p in (SRC_DIR, SCRIPTS_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import odds_client  # noqa: E402
from segment_backtest import bootstrap_roi_ci  # noqa: E402

LOG_PATH = BACKEND_DIR / "data" / "processed" / "live_odds_log.jsonl"
SETTLED_PATH = BACKEND_DIR / "data" / "processed" / "live_odds_settled.csv"

SETTLED_COLUMNS = [
    "event_id", "book", "side", "sport_key", "commence_time", "settled_at_run",
    "p1_name", "p2_name", "odds", "model_prob", "implied_prob", "won", "payout",
]


def load_log_rows() -> pd.DataFrame:
    if not LOG_PATH.exists():
        return pd.DataFrame()
    rows = [json.loads(line) for line in LOG_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    return pd.DataFrame(rows)


def load_settled() -> pd.DataFrame:
    if SETTLED_PATH.exists():
        return pd.read_csv(SETTLED_PATH)
    return pd.DataFrame(columns=SETTLED_COLUMNS)


def determine_winner_side(score_event: dict) -> str | None:
    """'home' o 'away' si el evento ya terminó y se puede leer un ganador
    claro de scores[]; None si sigue pendiente o el formato es inesperado."""
    if not score_event.get("completed"):
        return None
    home = score_event.get("home_team")
    away = score_event.get("away_team")
    scores = {s.get("name"): s.get("score") for s in (score_event.get("scores") or [])}
    try:
        home_score = int(scores[home])
        away_score = int(scores[away])
    except (KeyError, TypeError, ValueError):
        return None
    if home_score == away_score:
        return None
    return "home" if home_score > away_score else "away"


def settle_row(row: pd.Series, winner_side: str) -> list[dict]:
    """De una fila de live_odds_log.jsonl ya con resultado conocido, produce
    0, 1 o 2 apuestas (una por lado donde el modelo veía EV+), igual que la
    regla de apuesta de backtest_odds.py/segment_backtest.py."""
    p1_won = winner_side == "home"
    bets = []
    if row["edge_p1"] > 0:
        won = bool(p1_won)
        bets.append({"side": "p1", "odds": row["odds_p1"], "model_prob": row["model_p1_prob"],
                     "implied_prob": row["implied_p1"], "won": won,
                     "payout": (row["odds_p1"] - 1) if won else -1.0})
    if row["edge_p2"] > 0:
        won = not p1_won
        bets.append({"side": "p2", "odds": row["odds_p2"], "model_prob": row["model_p2_prob"],
                     "implied_prob": row["implied_p2"], "won": won,
                     "payout": (row["odds_p2"] - 1) if won else -1.0})
    for bet in bets:
        bet.update({
            "event_id": row["event_id"], "book": row["book"], "sport_key": row["sport_key"],
            "commence_time": row.get("commence_time"), "p1_name": row["p1_name"], "p2_name": row["p2_name"],
        })
    return bets


def main():
    api_key = odds_client.get_api_key()

    log_df = load_log_rows()
    if log_df.empty:
        print("live_odds_log.jsonl no existe o está vacío todavía. Corré fetch_live_odds.py primero.")
        return

    settled_df = load_settled()
    already_settled = set(zip(settled_df.get("event_id", []), settled_df.get("book", [])))

    pending = log_df.sort_values("fetched_at").drop_duplicates(subset=["event_id", "book"], keep="last")
    pending = pending[~pending.apply(lambda r: (r["event_id"], r["book"]) in already_settled, axis=1)]

    if pending.empty:
        print("No hay filas pendientes de settle (todo lo capturado ya fue sentenciado).")
    else:
        sport_keys = sorted(pending["sport_key"].unique())
        print(f"Buscando resultados para {len(sport_keys)} torneo(s): {sport_keys}")
        scores_by_event: dict[str, dict] = {}
        for sport_key in sport_keys:
            for score_event in odds_client.get_scores(sport_key, api_key):
                scores_by_event[score_event["id"]] = score_event

        new_bets = []
        for _, row in pending.iterrows():
            score_event = scores_by_event.get(row["event_id"])
            if score_event is None:
                continue
            winner_side = determine_winner_side(score_event)
            if winner_side is None:
                continue
            new_bets.extend(settle_row(row, winner_side))

        if new_bets:
            new_df = pd.DataFrame(new_bets)
            new_df["settled_at_run"] = pd.Timestamp.utcnow().isoformat()
            settled_df = pd.concat([settled_df, new_df[SETTLED_COLUMNS]], ignore_index=True)
            settled_df.to_csv(SETTLED_PATH, index=False)
            print(f"{len(new_bets)} apuesta(s) nueva(s) sentenciada(s), guardadas en {SETTLED_PATH}")
        else:
            print("Ninguno de los partidos pendientes tiene resultado todavía.")

    if settled_df.empty:
        print("\nTodavía no hay ninguna apuesta sentenciada — nada que reportar aún.")
        return

    payouts = settled_df["payout"].to_numpy(dtype=float)
    n = len(payouts)
    roi = float(payouts.mean() * 100)
    ci_low, ci_high = bootstrap_roi_ci(payouts, n_boot=2000)
    print(f"\n=== ROI acumulado en vivo (todas las apuestas sentenciadas hasta ahora) ===")
    print(f"n apuestas: {n}")
    print(f"ROI: {roi:.2f}%  (CI 95%: {ci_low:.2f}% a {ci_high:.2f}%)")
    if n < 150:
        print("Con menos de 150 apuestas el CI todavía es demasiado ancho para sacar conclusiones "
              "(ver criterio usado en Fase 6, segment_decision.md). Seguí corriendo esto con el tiempo.")


if __name__ == "__main__":
    main()
