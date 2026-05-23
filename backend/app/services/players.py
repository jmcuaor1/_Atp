from __future__ import annotations

from app.schemas.players import PlayerProfileResponse, PlayerSearchResult
from app.state import app_state


def search_players(query: str, limit: int = 20) -> list[PlayerSearchResult]:
    if not query.strip():
        return []

    needle = query.strip().lower()
    results: list[PlayerSearchResult] = []

    for player_id, profile in app_state.player_profiles.items():
        name = str(profile.get("name", ""))
        if needle in name.lower() or needle in str(player_id):
            results.append(
                PlayerSearchResult(
                    id=player_id,
                    name=name,
                    rank=_optional_float(profile.get("rank")),
                    ioc=profile.get("ioc"),
                    elo=_optional_float(profile.get("elo")),
                )
            )
        if len(results) >= limit:
            break

    results.sort(key=lambda p: (p.rank is None, p.rank or 9999))
    return results[:limit]


def get_player_profile(player_id: int) -> PlayerProfileResponse | None:
    profile = app_state.player_profiles.get(player_id)
    if profile is None:
        return None

    return PlayerProfileResponse(
        id=player_id,
        name=str(profile.get("name", f"Jugador {player_id}")),
        hand=profile.get("hand"),
        ht=_optional_float(profile.get("ht")),
        age=_optional_float(profile.get("age")),
        ioc=profile.get("ioc"),
        rank=_optional_float(profile.get("rank")),
        rank_points=_optional_float(profile.get("rank_points")),
        elo=float(profile.get("elo", 1500)),
        rolling_avg_ace=float(profile.get("rolling_avg_ace", 0)),
        rolling_avg_df=float(profile.get("rolling_avg_df", 0)),
        rolling_avg_1stWon=float(profile.get("rolling_avg_1stWon", 0)),
    )


def _optional_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
