#!/usr/bin/env python3
"""
Liquida las apuestas registradas en bet_log.jsonl por log_bet_decision.py:
para cada decisión no excluida que todavía no tenga fila en
bankroll_ledger.csv, busca el resultado real del partido (misma fuente que
settle_predictions.py / settle_live_odds.py: odds_client.get_scores +
determine_winner_side, cruzado por event_id) y aplica la ganancia/pérdida
al stake_amount ya calculado en el momento de la decisión — acá no se
recalcula el stake ni se usa la cuota de cierre, se liquida con las cifras
congeladas en bet_log.jsonl.

sport_key y los nombres de los jugadores no viven en bet_log.jsonl
(log_bet_decision.py no los duplica ahí, solo guarda predicted_winner_name +
event_id) — se toman del último snapshot por event_id en
live_odds_log.jsonl, igual que hace log_bet_decision.py para las cuotas. Si
ese snapshot ya no está (log rotado), el partido queda pendiente hasta que
vuelva a aparecer.

Las decisiones excluidas (excluded=true) nunca llegan acá: no hubo stake,
no hay nada que liquidar, y buscarles resultado solo gastaría cuota de la
API para nada.

Orden de liquidación: por commence_time (el orden en que efectivamente se
jugaron los partidos), no el orden de bet_log.jsonl ni el de llegada de
resultados — así la curva de banca en bankroll_ledger.csv queda coherente
aunque esta corrida liquide varios partidos de una vez.

Requiere ODDS_API_KEY en backend/.env (ver .env.example) y respeta la misma
banca base que log_bet_decision.py (env var INITIAL_BANKROLL, default 1000).

Uso:
  python scripts/settle_bet_log.py
"""

from __future__ import annotations

import json
import os
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
from log_bet_decision import (  # noqa: E402
    BANKROLL_LEDGER_PATH,
    BET_LOG_PATH,
    DEFAULT_INITIAL_BANKROLL,
    ODDS_LOG_PATH,
    load_latest_odds_snapshot,
    names_match,
    read_current_bankroll,
)

LEDGER_COLUMNS = [
    "timestamp_settled", "match_id", "event_id", "predicted_winner_name",
    "actual_winner_name", "won", "odds_decimal", "stake_amount", "profit",
    "bankroll_before", "bankroll_after",
]


# --- Fuentes de datos --------------------------------------------------------

def load_bet_log(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def load_ledger(path: Path) -> pd.DataFrame:
    if path.exists() and path.stat().st_size > 0:
        return pd.read_csv(path)
    return pd.DataFrame(columns=LEDGER_COLUMNS)


def append_ledger_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows, columns=LEDGER_COLUMNS)
    header = not (path.exists() and path.stat().st_size > 0)
    df.to_csv(path, mode="a", header=header, index=False)


def pending_decisions(bet_rows: list[dict], already_settled_ids: set[str]) -> list[dict]:
    """Decisiones no excluidas (hubo stake real) que todavía no tienen fila
    en bankroll_ledger.csv."""
    return [r for r in bet_rows if not r["excluded"] and r["match_id"] not in already_settled_ids]


# --- Resultado y liquidación ---------------------------------------------------

def determine_outcome(predicted_winner_name: str, odds_row: dict, actual_winner_name: str) -> bool | None:
    """True/False si predicted_winner_name matchea (normalizado) contra el
    ganador real; None si ni siquiera matchea a uno de los dos jugadores del
    propio snapshot de cuotas (no debería pasar si la decisión se construyó
    bien en log_bet_decision.py, pero acá no se asume)."""
    if not (names_match(predicted_winner_name, odds_row.get("p1_name"))
            or names_match(predicted_winner_name, odds_row.get("p2_name"))):
        return None
    return names_match(predicted_winner_name, actual_winner_name)


def build_ledger_row(decision: dict, actual_winner_name: str, won: bool, bankroll_before: float, now: str) -> dict:
    stake_amount = decision["stake_amount"]
    odds_decimal = decision["odds_decimal"]
    profit = stake_amount * (odds_decimal - 1) if won else -stake_amount
    return {
        "timestamp_settled": now,
        "match_id": decision["match_id"],
        "event_id": decision["event_id"],
        "predicted_winner_name": decision["predicted_winner_name"],
        "actual_winner_name": actual_winner_name,
        "won": won,
        "odds_decimal": odds_decimal,
        "stake_amount": stake_amount,
        "profit": profit,
        "bankroll_before": bankroll_before,
        "bankroll_after": bankroll_before + profit,
    }


# --- main ----------------------------------------------------------------------

def main() -> None:
    api_key = odds_client.get_api_key()

    bet_rows = load_bet_log(BET_LOG_PATH)
    if not bet_rows:
        print(f"{BET_LOG_PATH} no existe o está vacío todavía. Corré log_bet_decision.py primero.")
        return

    ledger_df = load_ledger(BANKROLL_LEDGER_PATH)
    already_settled_ids = set(ledger_df.get("match_id", []))
    pending = pending_decisions(bet_rows, already_settled_ids)
    if not pending:
        print("No hay apuestas pendientes de liquidar (todo lo registrado ya fue sentenciado o está excluido).")
        return

    odds_snapshot = load_latest_odds_snapshot(ODDS_LOG_PATH)
    enriched = [(row, odds_snapshot[row["event_id"]]) for row in pending if row["event_id"] in odds_snapshot]
    if not enriched:
        print("Ninguna apuesta pendiente tiene snapshot de cuotas todavía (log rotado o event_id nuevo).")
        return

    sport_keys = sorted({odds_row["sport_key"] for _, odds_row in enriched})
    print(f"Buscando resultados para {len(sport_keys)} torneo(s): {sport_keys}")
    scores_by_event: dict[str, dict] = {}
    for sport_key in sport_keys:
        for score_event in odds_client.get_scores(sport_key, api_key):
            scores_by_event[score_event["id"]] = score_event

    resolved = []
    for row, odds_row in enriched:
        score_event = scores_by_event.get(row["event_id"])
        if score_event is None:
            continue
        winner_side = odds_client.determine_winner_side(score_event)
        if winner_side is None:
            continue
        actual_winner_name = odds_row["p1_name"] if winner_side == "home" else odds_row["p2_name"]
        resolved.append((row, odds_row, actual_winner_name))

    if not resolved:
        print("Ninguno de los partidos pendientes tiene resultado todavía.")
        return

    resolved.sort(key=lambda item: item[1].get("commence_time") or "")

    bankroll = read_current_bankroll(
        BANKROLL_LEDGER_PATH, float(os.getenv("INITIAL_BANKROLL", DEFAULT_INITIAL_BANKROLL))
    )
    now = pd.Timestamp.now(tz="UTC").isoformat()

    new_rows = []
    skipped_mismatch = 0
    for row, odds_row, actual_winner_name in resolved:
        won = determine_outcome(row["predicted_winner_name"], odds_row, actual_winner_name)
        if won is None:
            skipped_mismatch += 1
            continue
        ledger_row = build_ledger_row(row, actual_winner_name, won, bankroll, now)
        bankroll = ledger_row["bankroll_after"]
        new_rows.append(ledger_row)

    if skipped_mismatch:
        print(f"ADVERTENCIA: {skipped_mismatch} apuesta(s) con predicted_winner_name que ya no matchea "
              f"contra el snapshot de cuotas actual — quedan pendientes, revisar a mano.")

    if not new_rows:
        print("No se pudo liquidar ninguna apuesta pendiente en esta corrida.")
        return

    append_ledger_rows(BANKROLL_LEDGER_PATH, new_rows)
    wins = sum(1 for r in new_rows if r["won"])
    print(f"{len(new_rows)} apuesta(s) liquidada(s), banca actualizada en {BANKROLL_LEDGER_PATH}")
    print(f"\n=== Resumen de esta corrida ===")
    print(f"{wins}/{len(new_rows)} ganadas")
    print(f"Banca: {bankroll:.2f} (unidad abstracta)")


if __name__ == "__main__":
    main()
