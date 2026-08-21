#!/usr/bin/env python3
"""
Sentencia el acierto de pronóstico (¿ganó quién el modelo decía que iba a
ganar?) para los partidos capturados en data/processed/live_odds_log.jsonl —
NO el ROI de apuestas de valor, eso lo hace settle_live_odds.py.

Es una métrica distinta y complementaria: acá cuenta cualquier partido donde
el modelo tenía una probabilidad más alta para un lado, sin importar si esa
probabilidad superaba a la cuota del mercado (edge). Sirve para responder
"¿cuántos partidos acierta el modelo en la práctica?", separado de si esos
aciertos son o no rentables para apostar.

Nota: usa el último snapshot por event_id (según fetched_at) como "la"
predicción del partido, igual que settle_live_odds.py con las cuotas. Si el
modelo se reentrenó varias veces el mismo día y cambió de pronóstico, acá
solo queda registrada la última corrida antes del partido.

Requiere ODDS_API_KEY en backend/.env (ver .env.example).

Uso:
  python scripts/settle_predictions.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

BACKEND_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BACKEND_DIR / "src"
for p in (SRC_DIR,):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import odds_client  # noqa: E402

LOG_PATH = BACKEND_DIR / "data" / "processed" / "live_odds_log.jsonl"
ACCURACY_PATH = BACKEND_DIR / "data" / "processed" / "prediction_accuracy_log.csv"

ACCURACY_COLUMNS = [
    "event_id", "date", "p1_name", "p2_name", "predicted_winner", "actual_winner", "correct", "note",
]


def load_log_rows() -> pd.DataFrame:
    if not LOG_PATH.exists():
        return pd.DataFrame()
    rows = [json.loads(line) for line in LOG_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    return pd.DataFrame(rows)


def load_accuracy() -> pd.DataFrame:
    if ACCURACY_PATH.exists():
        return pd.read_csv(ACCURACY_PATH)
    return pd.DataFrame(columns=ACCURACY_COLUMNS)


def predicted_winner_name(row: pd.Series) -> str:
    return row["p1_name"] if row["model_p1_prob"] > row["model_p2_prob"] else row["p2_name"]


def main():
    api_key = odds_client.get_api_key()

    log_df = load_log_rows()
    if log_df.empty:
        print("live_odds_log.jsonl no existe o está vacío todavía. Corré fetch_live_odds.py primero.")
        return

    accuracy_df = load_accuracy()
    already_settled = set(accuracy_df.get("event_id", []))

    pending = log_df.sort_values("fetched_at").drop_duplicates(subset=["event_id"], keep="last")
    pending = pending[~pending["event_id"].isin(already_settled)]

    if pending.empty:
        print("No hay predicciones pendientes de sentenciar (todo lo capturado ya fue evaluado).")
    else:
        sport_keys = sorted(pending["sport_key"].unique())
        print(f"Buscando resultados para {len(sport_keys)} torneo(s): {sport_keys}")
        scores_by_event: dict[str, dict] = {}
        for sport_key in sport_keys:
            for score_event in odds_client.get_scores(sport_key, api_key):
                scores_by_event[score_event["id"]] = score_event

        new_rows = []
        for _, row in pending.iterrows():
            score_event = scores_by_event.get(row["event_id"])
            if score_event is None:
                continue
            winner_side = odds_client.determine_winner_side(score_event)
            if winner_side is None:
                continue
            actual_winner = row["p1_name"] if winner_side == "home" else row["p2_name"]
            predicted = predicted_winner_name(row)
            new_rows.append({
                "event_id": row["event_id"],
                "date": str(row.get("commence_time", ""))[:10],
                "p1_name": row["p1_name"],
                "p2_name": row["p2_name"],
                "predicted_winner": predicted,
                "actual_winner": actual_winner,
                "correct": predicted == actual_winner,
                "note": "",
            })

        if new_rows:
            new_df = pd.DataFrame(new_rows)
            accuracy_df = pd.concat([accuracy_df, new_df[ACCURACY_COLUMNS]], ignore_index=True)
            accuracy_df.to_csv(ACCURACY_PATH, index=False)
            print(f"{len(new_rows)} predicción(es) nueva(s) sentenciada(s), guardadas en {ACCURACY_PATH}")
        else:
            print("Ninguno de los partidos pendientes tiene resultado todavía.")

    if accuracy_df.empty:
        print("\nTodavía no hay ninguna predicción sentenciada — nada que reportar aún.")
        return

    n = len(accuracy_df)
    correct = int(accuracy_df["correct"].astype(bool).sum())
    print(f"\n=== Acierto de pronóstico acumulado (todos los partidos sentenciados hasta ahora) ===")
    print(f"n partidos: {n}")
    print(f"Aciertos: {correct}/{n} ({correct / n * 100:.1f}%)")


if __name__ == "__main__":
    main()
