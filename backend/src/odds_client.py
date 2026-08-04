"""
Cliente delgado para The Odds API (https://the-odds-api.com), v4.

Solo hace requests HTTP y parsea la forma de la respuesta — no sabe nada de
nuestro modelo ni de jugadores. Eso vive en scripts/fetch_live_odds.py y
scripts/settle_live_odds.py.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://api.the-odds-api.com/v4"
DEFAULT_TIMEOUT = 15.0
DEFAULT_BOOK_WHITELIST = ("pinnacle", "bet365")


class OddsApiError(Exception):
    pass


def get_api_key() -> str:
    api_key = os.getenv("ODDS_API_KEY")
    if not api_key:
        raise OddsApiError(
            "ODDS_API_KEY no encontrada. Crea un archivo .env con ODDS_API_KEY=tu_clave "
            "(gratis en https://the-odds-api.com)."
        )
    return api_key


def _print_quota(headers: httpx.Headers) -> None:
    remaining = headers.get("x-requests-remaining")
    if remaining is None:
        return
    used = headers.get("x-requests-used")
    last = headers.get("x-requests-last")
    print(f"[odds_client] cuota The Odds API: usados={used} (este request costó {last}), restantes={remaining}")


def _request(path: str, api_key: str, **params: Any) -> Any:
    query = {"apiKey": api_key, **params}
    response = httpx.get(f"{BASE_URL}{path}", params=query, timeout=DEFAULT_TIMEOUT)
    response.raise_for_status()
    _print_quota(response.headers)
    return response.json()


def list_active_tennis_sport_keys(api_key: str) -> list[str]:
    """Torneos ATP activos ahora mismo. El tour no tiene una 'sport_key' fija
    para todo el año: cada torneo aparece/desaparece de /v4/sports mientras
    está en juego (no cuesta cuota consultar este endpoint)."""
    sports = _request("/sports", api_key)
    return [
        s["key"] for s in sports
        if s.get("group") == "Tennis" and s.get("active") and "atp" in s.get("key", "").lower()
    ]


def get_odds(sport_key: str, api_key: str, regions: str = "eu,uk", markets: str = "h2h") -> list[dict]:
    """Eventos + cuotas para un torneo activo. Cuesta cuota (1 por región x
    mercado, ver headers de respuesta)."""
    return _request(
        f"/sports/{sport_key}/odds", api_key,
        regions=regions, markets=markets, oddsFormat="decimal",
    )


def get_scores(sport_key: str, api_key: str, days_from: int = 3) -> list[dict]:
    """Resultados recientes/en vivo para un torneo. Cuesta más cuota si se
    piden partidos ya completados (ver docs de The Odds API)."""
    return _request(f"/sports/{sport_key}/scores", api_key, daysFrom=days_from)


def extract_book_odds(event: dict, book_whitelist: tuple[str, ...] = DEFAULT_BOOK_WHITELIST) -> list[dict]:
    """De un evento de get_odds(), una fila por book presente en la
    whitelist con las cuotas h2h ya separadas por jugador. Lista vacía si el
    evento no trae ninguno de los books pedidos (pasa seguido: no todos los
    books están en todas las regiones/eventos).

    Función pura, sin red — así se puede probar con fixtures.
    """
    home = event.get("home_team")
    away = event.get("away_team")
    rows = []
    for bookmaker in event.get("bookmakers", []):
        key = bookmaker.get("key")
        if key not in book_whitelist:
            continue
        for market in bookmaker.get("markets", []):
            if market.get("key") != "h2h":
                continue
            prices = {o["name"]: o["price"] for o in market.get("outcomes", [])}
            if home not in prices or away not in prices:
                continue
            rows.append({
                "book": key,
                "home_team": home,
                "away_team": away,
                "odds_home": prices[home],
                "odds_away": prices[away],
            })
    return rows
