#!/usr/bin/env python3
"""
Fase 7 — trae cuotas en vivo de The Odds API para partidos ATP activos, las
cruza con jugadores conocidos por el modelo, y llama a la API real de
predicción para dejar un registro conjunto predicción+cuota en
data/processed/live_odds_log.jsonl. Esa es la materia prima para medir
CLV/ROI hacia adelante una vez los partidos se jueguen (ver
settle_live_odds.py) — complementario al backtest histórico
(backtest_odds.py / segment_backtest.py), no un reemplazo: ahí las cuotas
ya eran reales, acá solo cambia que se capturan en vivo en vez de leerse
de un archivo histórico.

Cobertura de The Odds API para tenis: Grand Slam, ATP 1000, ATP 500,
WTA 1000, WTA 500. NO cubre ATP 250 — es normal que en muchas semanas del
calendario no haya ningún torneo ATP activo según este script.

Requiere:
  - ODDS_API_KEY en backend/.env (ver .env.example; gratis en the-odds-api.com)
  - La API real corriendo: uvicorn api:app --reload (default http://localhost:8000,
    configurable con API_BASE_URL en .env)

Uso:
  python scripts/fetch_live_odds.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BACKEND_DIR / "src"
SCRIPTS_DIR = BACKEND_DIR / "scripts"
for p in (SRC_DIR, SCRIPTS_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import odds_client  # noqa: E402
from backtest_odds import normalize_full_name  # noqa: E402

load_dotenv()

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
LOG_PATH = BACKEND_DIR / "data" / "processed" / "live_odds_log.jsonl"
HTTP_TIMEOUT = 10.0


def resolve_player_id(full_name: str) -> dict | None:
    """Busca un nombre de la odds API ('Novak Djokovic') entre los jugadores
    conocidos vía GET /players/search, desambiguando candidatos por
    apellido + inicial del nombre (mismo criterio de normalize_full_name
    que usa backtest_odds.py para cruzar contra tennis-data.co.uk)."""
    last, initial = normalize_full_name(full_name)
    if not last:
        return None
    # /players/search hace substring literal contra el nombre guardado (con
    # espacios), así que no se le puede mandar `last` (que viene sin
    # espacios, p.ej. "deminaur") o nunca matchea apellidos compuestos como
    # "Alex De Minaur" o "Botic Van De Zandschulp". Se busca por la última
    # palabra del nombre en cambio, y se desambigua después con `last`/`initial`.
    query = full_name.strip().split()[-1]
    resp = httpx.get(
        f"{API_BASE_URL}/players/search", params={"q": query, "limit": 20}, timeout=HTTP_TIMEOUT,
    )
    resp.raise_for_status()
    for candidate in resp.json():
        cand_last, cand_initial = normalize_full_name(candidate["name"])
        if cand_last == last and cand_initial == initial:
            return candidate
    return None


def guess_surface(sport_key: str) -> str:
    """The Odds API no manda superficie explícita en /odds. Heurística por
    nombre de torneo en el sport_key; si no reconoce nada, default a Hard
    (la superficie más común en el calendario ATP)."""
    key = sport_key.lower()
    clay_hints = ("french_open", "roland_garros", "monte_carlo", "madrid", "rome", "clay", "barcelona")
    grass_hints = ("wimbledon", "queens", "halle", "grass")
    if any(hint in key for hint in clay_hints):
        return "Clay"
    if any(hint in key for hint in grass_hints):
        return "Grass"
    return "Hard"


def predict(p1_id: int, p2_id: int, surface: str) -> dict | None:
    payload = {"player1": {"id": p1_id}, "player2": {"id": p2_id}, "surface": surface}
    resp = httpx.post(f"{API_BASE_URL}/predict", json=payload, timeout=HTTP_TIMEOUT)
    if resp.status_code != 200:
        print(f"   [predict] {resp.status_code} para ids {p1_id}/{p2_id}: {resp.text[:200]}")
        return None
    return resp.json()


def build_log_rows(event: dict, sport_key: str, prediction_cache: dict) -> list[dict]:
    book_rows = odds_client.extract_book_odds(event)
    if not book_rows:
        return []

    home_player = resolve_player_id(event["home_team"])
    away_player = resolve_player_id(event["away_team"])
    if home_player is None or away_player is None:
        missing = event["home_team"] if home_player is None else event["away_team"]
        print(f"   No se pudo resolver jugador: {missing!r}")
        return []

    cache_key = (home_player["id"], away_player["id"])
    if cache_key not in prediction_cache:
        prediction_cache[cache_key] = predict(home_player["id"], away_player["id"], guess_surface(sport_key))
    prediction = prediction_cache[cache_key]
    if prediction is None:
        return []

    fetched_at = datetime.now(timezone.utc).isoformat()
    rows = []
    for book_row in book_rows:
        implied_p1 = 1 / book_row["odds_home"]
        implied_p2 = 1 / book_row["odds_away"]
        rows.append({
            "fetched_at": fetched_at,
            "event_id": event["id"],
            "sport_key": sport_key,
            "commence_time": event.get("commence_time"),
            "home_team": event.get("home_team"),
            "away_team": event.get("away_team"),
            "p1_id": prediction["player1_id"],
            "p2_id": prediction["player2_id"],
            "p1_name": prediction["player1_name"],
            "p2_name": prediction["player2_name"],
            "book": book_row["book"],
            "odds_p1": book_row["odds_home"],
            "odds_p2": book_row["odds_away"],
            "model_p1_prob": prediction["player1_win_probability"],
            "model_p2_prob": prediction["player2_win_probability"],
            "implied_p1": implied_p1,
            "implied_p2": implied_p2,
            "edge_p1": prediction["player1_win_probability"] - implied_p1,
            "edge_p2": prediction["player2_win_probability"] - implied_p2,
        })
    return rows


def main():
    api_key = odds_client.get_api_key()

    print("1. Buscando torneos ATP activos en The Odds API...")
    sport_keys = odds_client.list_active_tennis_sport_keys(api_key)
    if not sport_keys:
        print("   Ninguno activo ahora mismo (recuerda: no cubre ATP 250, es normal en semanas sin Slam/1000/500).")
        return
    print(f"   {len(sport_keys)} torneo(s) activo(s): {sport_keys}")

    all_rows: list[dict] = []
    for sport_key in sport_keys:
        print(f"\n2. Trayendo cuotas para {sport_key}...")
        events = odds_client.get_odds(sport_key, api_key)
        print(f"   {len(events)} partido(s) con cuota")

        prediction_cache: dict[tuple[int, int], dict | None] = {}
        for event in events:
            all_rows.extend(build_log_rows(event, sport_key, prediction_cache))

    if not all_rows:
        print("\nNo se generó ninguna fila (sin cuotas de pinnacle/bet365 en estos eventos, o jugadores no resueltos vía /players/search).")
        return

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        for row in all_rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"\n{len(all_rows)} fila(s) escritas en {LOG_PATH}")


if __name__ == "__main__":
    main()
