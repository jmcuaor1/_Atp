#!/usr/bin/env python3
"""
HERRAMIENTA DE VALIDACIÓN MANUAL, NO el script de producción — ese es
scripts/log_bet_decision.py, que corre por cron y persiste una fila por
partido en data/processed/bet_log.jsonl. Este script se queda como
dry-run de solo lectura a propósito: para cada partido de /matches/today,
cruza el predicted_winner con la cuota más reciente en
data/processed/live_odds_log.jsonl y muestra en consola qué stake daría
compute_stake() (Fase 8, ver app/services/staking.py y
docs/betting_process.md), sin escribir ningún archivo — útil para mirar
el día a ojo antes/aparte de que corra la persistencia real.

Requiere:
  - La API real corriendo (uvicorn api:app --reload, ver API_BASE_URL).
  - fetch_live_odds.py haber corrido al menos una vez, para que haya
    cuotas en live_odds_log.jsonl. Sin eso, todos los partidos van a
    salir marcados "sin cuota disponible".

Uso:
  python scripts/preview_stakes.py
  python scripts/preview_stakes.py --bankroll 5000
  PREVIEW_BANKROLL=5000 python scripts/preview_stakes.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import httpx

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.staking import compute_stake  # noqa: E402

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
LOG_PATH = BACKEND_DIR / "data" / "processed" / "live_odds_log.jsonl"
HTTP_TIMEOUT = 10.0
DEFAULT_BANKROLL = 1000.0

# Motivos de exclusión que sí produce compute_stake(); "sin cuota
# disponible" y "sin predicción del modelo" pasan antes de llegar a
# compute_stake() y se etiquetan acá mismo.
NO_ODDS_REASON = "sin cuota disponible"
NO_PREDICTION_REASON = "sin predicción del modelo"


def fetch_today_matches() -> list[dict]:
    resp = httpx.get(f"{API_BASE_URL}/matches/today", timeout=HTTP_TIMEOUT)
    resp.raise_for_status()
    return resp.json()["matches"]


def load_latest_odds_snapshot(log_path: Path = LOG_PATH) -> dict[str, dict]:
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


def odds_for_predicted_winner(predicted_winner_name: str, odds_row: dict | None) -> float | None:
    """odds_decimal del predicted_winner, leído de `odds_row` (la fila más
    reciente del log para ese event_id). None si no hay snapshot o si el
    nombre no matchea ninguno de los dos jugadores del log — nunca se
    inventa un valor."""
    if odds_row is None:
        return None
    if predicted_winner_name == odds_row.get("p1_name"):
        return odds_row.get("odds_p1")
    if predicted_winner_name == odds_row.get("p2_name"):
        return odds_row.get("odds_p2")
    return None


def _win_probability_of_predicted(match: dict) -> float | None:
    predicted = match.get("predicted_winner_name")
    if predicted == match.get("player1_name"):
        return match.get("player1_win_probability")
    if predicted == match.get("player2_name"):
        return match.get("player2_win_probability")
    return None


def build_preview_row(match: dict, odds_snapshot: dict[str, dict], bankroll: float) -> dict:
    """Une un partido de /matches/today con su cuota (si hay) y corre
    compute_stake(). Nunca lanza: un partido sin predicción, sin cuota, o
    que dispare ValueError en compute_stake() (cuota <= 1) queda marcado
    como excluido con su motivo, y el resto de los partidos se siguen
    procesando igual."""
    matchup = f"{match['player1_name']} vs {match['player2_name']}"
    predicted = match.get("predicted_winner_name")
    win_probability = _win_probability_of_predicted(match)

    row = {
        "matchup": matchup,
        "predicted_winner": predicted,
        "win_probability": win_probability,
        "odds_decimal": None,
        "excluded": True,
        "exclusion_reason": NO_PREDICTION_REASON,
        "kelly_fraction_raw": None,
        "stake_fraction": None,
        "stake_amount": None,
    }

    if predicted is None or win_probability is None:
        return row

    odds_row = odds_snapshot.get(match.get("event_id"))
    odds_decimal = odds_for_predicted_winner(predicted, odds_row)
    row["odds_decimal"] = odds_decimal
    if odds_decimal is None:
        row["exclusion_reason"] = NO_ODDS_REASON
        return row

    low_sample_warning = bool(match.get("low_sample_warning", False))

    try:
        decision = compute_stake(
            win_probability=win_probability,
            odds_decimal=odds_decimal,
            bankroll=bankroll,
            low_sample_warning=low_sample_warning,
        )
    except ValueError as exc:
        row["exclusion_reason"] = f"error: {exc}"
        return row

    row["excluded"] = decision.excluded
    row["exclusion_reason"] = decision.exclusion_reason
    row["kelly_fraction_raw"] = decision.kelly_fraction_raw
    row["stake_fraction"] = decision.stake_fraction
    row["stake_amount"] = decision.stake_amount
    return row


def _truncate(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


def _fmt_pct(value: float | None) -> str:
    return f"{value:.1%}" if value is not None else "—"


def _fmt_num(value: float | None, decimals: int = 2) -> str:
    return f"{value:.{decimals}f}" if value is not None else "—"


def _fmt_excluded(row: dict) -> str:
    if not row["excluded"]:
        return "no"
    reason = row["exclusion_reason"] or "excluido"
    return _truncate(f"sí ({reason})", 30)


_COLUMNS = [
    ("Partido", 38),
    ("Predicho", 20),
    ("P(gana)", 8),
    ("Cuota", 7),
    ("Excluido", 32),
    ("Kelly raw", 10),
    ("Stake %", 8),
    ("Stake", 10),
]


def print_table(rows: list[dict]) -> None:
    header = "  ".join(name.ljust(width) for name, width in _COLUMNS)
    print(header)
    print("-" * len(header))
    for row in rows:
        values = [
            _truncate(row["matchup"], 38),
            _truncate(row["predicted_winner"] or "—", 20),
            _fmt_pct(row["win_probability"]),
            _fmt_num(row["odds_decimal"]),
            _fmt_excluded(row),
            _fmt_num(row["kelly_fraction_raw"], 4),
            _fmt_pct(row["stake_fraction"]),
            _fmt_num(row["stake_amount"]),
        ]
        line = "  ".join(value.ljust(width) for value, (_, width) in zip(values, _COLUMNS))
        print(line)


def summarize(rows: list[dict]) -> dict:
    passed = [r for r in rows if not r["excluded"]]
    excluded = [r for r in rows if r["excluded"]]

    by_reason = {"threshold": 0, "low_sample_warning": 0, NO_ODDS_REASON: 0, "otros": 0}
    for r in excluded:
        reason = r["exclusion_reason"] or ""
        if "THRESHOLD" in reason:
            by_reason["threshold"] += 1
        elif reason == "low_sample_warning":
            by_reason["low_sample_warning"] += 1
        elif reason == NO_ODDS_REASON:
            by_reason[NO_ODDS_REASON] += 1
        else:
            by_reason["otros"] += 1

    return {
        "total": len(rows),
        "passed": len(passed),
        "excluded": len(excluded),
        "by_reason": by_reason,
    }


def print_summary(summary: dict) -> None:
    print(f"\n{summary['passed']}/{summary['total']} partido(s) pasaron el filtro, "
          f"{summary['excluded']} excluido(s):")
    reasons = summary["by_reason"]
    print(f"  - por umbral de win_probability: {reasons['threshold']}")
    print(f"  - por low_sample_warning: {reasons['low_sample_warning']}")
    print(f"  - {NO_ODDS_REASON}: {reasons[NO_ODDS_REASON]}")
    if reasons["otros"]:
        print(f"  - otros (sin predicción del modelo / error de cuota): {reasons['otros']}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--bankroll", type=float, default=None,
        help=f"Banca de ejemplo, unidad abstracta (no dinero real). "
             f"Default: env PREVIEW_BANKROLL o {DEFAULT_BANKROLL:g}.",
    )
    args = parser.parse_args()
    bankroll = args.bankroll if args.bankroll is not None else float(os.getenv("PREVIEW_BANKROLL", DEFAULT_BANKROLL))

    matches = fetch_today_matches()
    if not matches:
        print("No hay partidos hoy en /matches/today.")
        return

    odds_snapshot = load_latest_odds_snapshot(LOG_PATH)
    if not odds_snapshot:
        print(f"Aviso: {LOG_PATH} no existe o está vacío — ningún partido va a tener cuota "
              "disponible. Corré fetch_live_odds.py primero si querés ver stakes reales.\n")

    rows = [build_preview_row(match, odds_snapshot, bankroll) for match in matches]
    print(f"Preview de stakes — banca de ejemplo: {bankroll:g} (unidad abstracta)\n")
    print_table(rows)
    print_summary(summarize(rows))


if __name__ == "__main__":
    main()
