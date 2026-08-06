from __future__ import annotations

import re
import time
import unicodedata
from datetime import datetime, timezone
from typing import Any

import odds_client

from app.schemas.matches import TodayMatch, TodayMatchesResponse
from app.schemas.predict import PlayerInput, PredictionRequest
from app.services.players import search_players
from app.services.prediction import PredictionError, predict_match_sync
from app.state import app_state

# Cuánto tiempo se reusa la última consulta a The Odds API antes de volver a
# gastar cuota — sin esto, cada recarga del frontend costaría requests reales
# (la cuota gratis es 500/mes y el cron de Fase 7 ya consume una buena parte).
_CACHE_TTL_SECONDS = 30 * 60
_cache: dict[str, Any] = {"data": None, "fetched_at": 0.0}


def _strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def _normalize_full_name(full_name: str) -> tuple[str, str]:
    """Mismo criterio que scripts/backtest_odds.py::normalize_full_name."""
    parts = str(full_name).strip().split()
    if not parts:
        return ("", "")
    last = _strip_accents("".join(parts[1:]).lower()) if len(parts) > 1 else _strip_accents(parts[0].lower())
    last = re.sub(r"[^a-z]", "", last)
    first_initial = _strip_accents(parts[0][0].lower()) if parts[0] else ""
    return (last, first_initial)


def _resolve_player(full_name: str) -> dict | None:
    """Mismo criterio (y mismo fix de apellidos compuestos) que
    scripts/fetch_live_odds.py::resolve_player_id, pero llamando al service
    de búsqueda directo en vez de por HTTP (mismo proceso)."""
    last, initial = _normalize_full_name(full_name)
    if not last:
        return None
    query = full_name.strip().split()[-1]
    for candidate in search_players(query, limit=20):
        cand_last, cand_initial = _normalize_full_name(candidate.name)
        if cand_last == last and cand_initial == initial:
            return {"id": candidate.id, "name": candidate.name}
    return None


def _guess_surface(sport_key: str) -> str:
    """Mismo criterio que scripts/fetch_live_odds.py::guess_surface."""
    key = sport_key.lower()
    clay_hints = ("french_open", "roland_garros", "monte_carlo", "madrid", "rome", "clay", "barcelona")
    grass_hints = ("wimbledon", "queens", "halle", "grass")
    if any(hint in key for hint in clay_hints):
        return "Clay"
    if any(hint in key for hint in grass_hints):
        return "Grass"
    return "Hard"


def _model_data_cutoff() -> str | None:
    date_range = app_state.model_metadata.get("date_range")
    if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
        return str(date_range[1])
    return None


def _fetch_today_matches() -> TodayMatchesResponse:
    api_key = odds_client.get_api_key()
    sport_keys = odds_client.list_active_tennis_sport_keys(api_key)

    matches: list[TodayMatch] = []
    for sport_key in sport_keys:
        surface = _guess_surface(sport_key)
        tournament = sport_key.replace("tennis_atp_", "").replace("_", " ").title()
        events = odds_client.get_odds(sport_key, api_key)

        for event in events:
            home = event.get("home_team", "")
            away = event.get("away_team", "")
            p1 = _resolve_player(home)
            p2 = _resolve_player(away)

            entry = TodayMatch(
                event_id=event["id"],
                tournament=tournament,
                commence_time=event.get("commence_time"),
                surface=surface,
                player1_name=home,
                player2_name=away,
                player1_id=p1["id"] if p1 else None,
                player2_id=p2["id"] if p2 else None,
            )

            if p1 and p2:
                try:
                    prediction = predict_match_sync(
                        PredictionRequest(
                            player1=PlayerInput(id=p1["id"]),
                            player2=PlayerInput(id=p2["id"]),
                            surface=surface,
                        )
                    )
                    entry.player1_win_probability = prediction.player1_win_probability
                    entry.player2_win_probability = prediction.player2_win_probability
                    entry.predicted_winner_name = prediction.predicted_winner_name
                    entry.resolved = True
                except PredictionError as exc:
                    entry.note = exc.message
            else:
                missing = home if not p1 else away
                entry.note = f"Jugador no encontrado en la base del modelo: {missing}"

            matches.append(entry)

    matches.sort(key=lambda m: m.commence_time or "")
    return TodayMatchesResponse(
        matches=matches,
        model_data_cutoff=_model_data_cutoff(),
        generated_at=datetime.now(timezone.utc).isoformat(),
        cached=False,
    )


def get_today_matches(force_refresh: bool = False) -> TodayMatchesResponse:
    now = time.time()
    cached = _cache["data"]
    if not force_refresh and cached is not None and (now - _cache["fetched_at"]) < _CACHE_TTL_SECONDS:
        return cached.model_copy(update={"cached": True})

    result = _fetch_today_matches()
    _cache["data"] = result
    _cache["fetched_at"] = now
    return result
