#!/usr/bin/env python3
"""
Script de PRODUCCIÓN que persiste, a diferencia de preview_stakes.py (que
sigue existiendo como herramienta de solo lectura para revisar el preview a
ojo, sin escribir nada — ver su docstring). Pensado para correrse una vez
por día, justo después de que /matches/today tenga los partidos del día
(vía cron), y deja una línea por partido en data/processed/bet_log.jsonl
con la decisión de stake tomada (Fase 8, ver app/services/staking.py y
docs/betting_process.md).

Cruce de nombres con live_odds_log.jsonl: a diferencia de preview_stakes.py,
que si el nombre no matcheaba omitía el partido en silencio, acá eso no es
aceptable porque estamos persistiendo — se prueba primero el match exacto,
después uno normalizado (minúsculas, sin tildes, espacios colapsados,
orden "Nombre Apellido" y "Apellido, Nombre"), y si sigue sin matchear el
partido se loguea igual con excluded=true, exclusion_reason="name_mismatch"
y los nombres crudos de ambas fuentes en predicted_winner_raw /
odds_names_raw, para poder auditar el mismatch después sin reconstruirlo a
mano de los logs fuente. El mismo tratamiento aplica si predicted_winner_name
no matchea ni siquiera a player1_name/player2_name dentro del propio
/matches/today (bug de datos ya observado corriendo preview_stakes.py) —
es la misma familia de problema (no se puede confiar en la igualdad
exacta de un nombre de jugador entre dos fuentes), así que usa la misma
categoría.

Bankroll: lee data/processed/bankroll_ledger.csv (columna 'bankroll_after',
la fila más reciente = banca actual) si ya existe. Ese archivo lo escribe
settle_bet_log.py (siguiente entrega, todavía no implementada, corre
después de que el partido termina) — este script NUNCA escribe ahí, solo
lee. Si el archivo no existe todavía (banca inicial, antes del primer
settle), usa el valor de la variable de entorno INITIAL_BANKROLL (default
1000, unidad abstracta, no dinero real).

Idempotencia: la clave de una decisión es match_id = "{event_id}::{fecha
UTC de la corrida}". Si ya hay una línea con ese match_id en bet_log.jsonl,
el partido se saltea (se loguea a stdout por qué) y NO se vuelve a escribir
ni se pisa la decisión existente, aunque los datos de entrada hayan
cambiado — así una corrida repetida de cron no puede alterar una decisión
de stake ya tomada.

Requiere la API real corriendo (uvicorn api:app --reload, ver API_BASE_URL).

Uso:
  python scripts/log_bet_decision.py
  INITIAL_BANKROLL=5000 python scripts/log_bet_decision.py
"""

from __future__ import annotations

import json
import os
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pandas as pd

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.staking import compute_stake  # noqa: E402

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
ODDS_LOG_PATH = BACKEND_DIR / "data" / "processed" / "live_odds_log.jsonl"
BET_LOG_PATH = BACKEND_DIR / "data" / "processed" / "bet_log.jsonl"
BANKROLL_LEDGER_PATH = BACKEND_DIR / "data" / "processed" / "bankroll_ledger.csv"
HTTP_TIMEOUT = 10.0
DEFAULT_INITIAL_BANKROLL = 1000.0

# Únicos valores válidos de exclusion_reason por diseño (además de None):
# "threshold", "low_sample_warning", "no_odds_available", "name_mismatch".
# Un "error: ..." solo puede aparecer si compute_stake() recibe una cuota
# corrupta (odds_decimal <= 1) en el log — no debería pasar en la práctica,
# pero un partido con datos rotos no puede tumbar el resto del batch.
EXCLUSION_REASONS = ("threshold", "low_sample_warning", "no_odds_available", "name_mismatch")


# --- Fuentes de datos --------------------------------------------------------

def fetch_today_matches() -> list[dict]:
    resp = httpx.get(f"{API_BASE_URL}/matches/today", timeout=HTTP_TIMEOUT)
    resp.raise_for_status()
    return resp.json()["matches"]


def load_latest_odds_snapshot(log_path: Path) -> dict[str, dict]:
    """event_id -> fila más reciente (mayor fetched_at) de
    live_odds_log.jsonl. Dict vacío si el log no existe todavía o está
    vacío (mismo criterio que scripts/show_value_bets.py)."""
    if not log_path.exists():
        return {}
    latest: dict[str, dict] = {}
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        event_id = row["event_id"]
        if event_id not in latest or row["fetched_at"] > latest[event_id]["fetched_at"]:
            latest[event_id] = row
    return latest


def read_current_bankroll(ledger_path: Path, default: float) -> float:
    """Última banca registrada (columna 'bankroll_after') en
    bankroll_ledger.csv. `default` si el archivo no existe, está vacío, o
    no tiene esa columna todavía (banca inicial antes del primer
    settle_bet_log.py)."""
    if not ledger_path.exists():
        return default
    df = pd.read_csv(ledger_path)
    if df.empty or "bankroll_after" not in df.columns:
        return default
    last_value = df["bankroll_after"].iloc[-1]
    return default if pd.isna(last_value) else float(last_value)


def load_existing_match_ids(bet_log_path: Path) -> set[str]:
    if not bet_log_path.exists():
        return set()
    ids: set[str] = set()
    for line in bet_log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        match_id = json.loads(line).get("match_id")
        if match_id:
            ids.add(match_id)
    return ids


def append_bet_log_rows(bet_log_path: Path, rows: list[dict]) -> None:
    bet_log_path.parent.mkdir(parents=True, exist_ok=True)
    with bet_log_path.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


# --- Matching de nombres, endurecido -----------------------------------------

def _normalize_name(name: str | None) -> str:
    if not name:
        return ""
    decomposed = unicodedata.normalize("NFKD", name)
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(without_accents.lower().split())


def _name_variants(name: str | None) -> set[str]:
    """Formas normalizadas de `name` a probar antes de darlo por
    no-matcheado: la forma tal cual, y una forma con el orden de tokens
    invertido (cubre tanto 'Apellido, Nombre' con coma explícita como el
    caso sin coma de dos tokens en orden 'Apellido Nombre')."""
    if not name:
        return set()
    normalized = _normalize_name(name)
    variants = {normalized}
    if "," in name:
        parts = [p.strip() for p in name.split(",", 1)]
        if len(parts) == 2 and parts[0] and parts[1]:
            variants.add(_normalize_name(f"{parts[1]} {parts[0]}"))
    else:
        tokens = normalized.split()
        if len(tokens) >= 2:
            variants.add(" ".join([tokens[-1], *tokens[:-1]]))
    return variants


def names_match(a: str | None, b: str | None) -> bool:
    """Sin guión bajo a propósito: settle_bet_log.py la importa de acá en vez
    de duplicarla, para cruzar predicted_winner_name contra el nombre real
    del ganador con la misma tolerancia (acentos, espacios, orden Nombre
    Apellido / Apellido, Nombre) que se usó al construir la decisión."""
    if a is None or b is None:
        return False
    if a == b:
        return True
    return bool(_name_variants(a) & _name_variants(b))


def _resolve_predicted_win_probability(match: dict) -> float | None:
    """win_probability del predicted_winner_name de `match`, matcheando
    contra player1_name/player2_name del propio partido (exacto, después
    normalizado). None si predicted_winner_name es None o no matchea a
    ninguno de los dos — el llamador decide qué hacer con eso."""
    predicted = match.get("predicted_winner_name")
    if predicted is None:
        return None
    if names_match(predicted, match.get("player1_name")):
        return match.get("player1_win_probability")
    if names_match(predicted, match.get("player2_name")):
        return match.get("player2_win_probability")
    return None


def _odds_for_predicted_winner(predicted_winner_name: str, odds_row: dict) -> float | None:
    """odds_decimal del predicted_winner en `odds_row` (exacto, después
    normalizado). None si no matchea ninguno de los dos nombres del log."""
    if names_match(predicted_winner_name, odds_row.get("p1_name")):
        return odds_row.get("odds_p1")
    if names_match(predicted_winner_name, odds_row.get("p2_name")):
        return odds_row.get("odds_p2")
    return None


def _normalize_exclusion_reason(raw_reason: str | None) -> str | None:
    """compute_stake() devuelve un mensaje descriptivo (ver
    app/services/staking.py); acá se colapsa a una de las categorías
    fijas de EXCLUSION_REASONS para que bet_log.jsonl sea fácil de
    agregar/filtrar."""
    if raw_reason is None:
        return None
    if raw_reason == "low_sample_warning":
        return "low_sample_warning"
    if "THRESHOLD" in raw_reason:
        return "threshold"
    return raw_reason


# --- Construcción de la decisión ---------------------------------------------

def build_bet_decision_row(
    match: dict, odds_snapshot: dict[str, dict], bankroll: float, now: datetime, decision_date: str,
) -> dict:
    """Une un partido de /matches/today con su cuota (si hay) y corre
    compute_stake(). Nunca lanza: cualquier caso sin datos suficientes,
    con un nombre que no matchea ni normalizado, o que dispare ValueError
    en compute_stake() (cuota <= 1) queda representado en la fila con su
    exclusion_reason, en vez de tumbar el resto del batch."""
    event_id = match.get("event_id")
    predicted_raw = match.get("predicted_winner_name")

    row = {
        "match_id": f"{event_id}::{decision_date}",
        "event_id": event_id,
        "timestamp_decision": now.isoformat(),
        "predicted_winner_name": predicted_raw,
        "win_probability": None,
        "odds_decimal": None,
        "low_sample_warning": bool(match.get("low_sample_warning", False)),
        "excluded": True,
        "exclusion_reason": None,
        "kelly_fraction_raw": None,
        "stake_fraction": None,
        "stake_amount": None,
        "predicted_winner_raw": None,
        "odds_names_raw": None,
    }

    def _mark_name_mismatch(other_names: list[str | None]) -> dict:
        row["exclusion_reason"] = "name_mismatch"
        row["predicted_winner_raw"] = predicted_raw
        row["odds_names_raw"] = other_names
        return row

    win_probability = _resolve_predicted_win_probability(match)
    if win_probability is None:
        return _mark_name_mismatch([match.get("player1_name"), match.get("player2_name")])
    row["win_probability"] = win_probability

    odds_row = odds_snapshot.get(event_id)
    if odds_row is None:
        row["exclusion_reason"] = "no_odds_available"
        return row

    odds_decimal = _odds_for_predicted_winner(predicted_raw, odds_row)
    if odds_decimal is None:
        return _mark_name_mismatch([odds_row.get("p1_name"), odds_row.get("p2_name")])
    row["odds_decimal"] = odds_decimal

    try:
        decision = compute_stake(
            win_probability=win_probability,
            odds_decimal=odds_decimal,
            bankroll=bankroll,
            low_sample_warning=row["low_sample_warning"],
        )
    except ValueError as exc:
        row["exclusion_reason"] = f"error: {exc}"
        return row

    row["excluded"] = decision.excluded
    row["exclusion_reason"] = _normalize_exclusion_reason(decision.exclusion_reason)
    row["kelly_fraction_raw"] = decision.kelly_fraction_raw
    row["stake_fraction"] = decision.stake_fraction
    row["stake_amount"] = decision.stake_amount
    return row


# --- Resumen para stdout ------------------------------------------------------

def summarize(rows: list[dict]) -> dict:
    passed = [r for r in rows if not r["excluded"]]
    excluded = [r for r in rows if r["excluded"]]

    by_reason = {reason: 0 for reason in EXCLUSION_REASONS}
    by_reason["otros"] = 0
    for r in excluded:
        reason = r["exclusion_reason"] or ""
        if reason in by_reason:
            by_reason[reason] += 1
        else:
            by_reason["otros"] += 1

    return {"total": len(rows), "passed": len(passed), "excluded": len(excluded), "by_reason": by_reason}


def print_summary(summary: dict) -> None:
    print(f"\n{summary['passed']}/{summary['total']} partido(s) pasaron el filtro, "
          f"{summary['excluded']} excluido(s):")
    reasons = summary["by_reason"]
    print(f"  - por threshold: {reasons['threshold']}")
    print(f"  - por low_sample_warning: {reasons['low_sample_warning']}")
    print(f"  - por no_odds_available: {reasons['no_odds_available']}")
    print(f"  - por name_mismatch: {reasons['name_mismatch']}")
    if reasons["otros"]:
        print(f"  - otros (error de cuota inválida): {reasons['otros']}")


# --- main ---------------------------------------------------------------------

def main() -> None:
    now = datetime.now(timezone.utc)
    decision_date = now.date().isoformat()

    bankroll = read_current_bankroll(BANKROLL_LEDGER_PATH, float(os.getenv("INITIAL_BANKROLL", DEFAULT_INITIAL_BANKROLL)))
    print(f"Banca actual: {bankroll:g} (unidad abstracta)")

    matches = fetch_today_matches()
    if not matches:
        print("No hay partidos hoy en /matches/today.")
        return

    odds_snapshot = load_latest_odds_snapshot(ODDS_LOG_PATH)
    all_rows = [build_bet_decision_row(match, odds_snapshot, bankroll, now, decision_date) for match in matches]

    existing_match_ids = load_existing_match_ids(BET_LOG_PATH)
    new_rows = []
    for row in all_rows:
        if row["match_id"] in existing_match_ids:
            print(f"  saltado (ya registrado hoy): {row['match_id']}")
            continue
        new_rows.append(row)
        existing_match_ids.add(row["match_id"])  # por si dos partidos del batch compartieran match_id

    if new_rows:
        append_bet_log_rows(BET_LOG_PATH, new_rows)
        print(f"\n{len(new_rows)} decisión(es) nueva(s) escritas en {BET_LOG_PATH}")
    else:
        print("\nNinguna decisión nueva para escribir (todo lo de hoy ya estaba registrado).")

    print_summary(summarize(all_rows))


if __name__ == "__main__":
    main()
