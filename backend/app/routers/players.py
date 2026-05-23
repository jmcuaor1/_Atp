from fastapi import APIRouter, HTTPException, Query

from app.dependencies import require_model_ready
from app.schemas.players import PlayerProfileResponse, PlayerSearchResult
from app.services.players import get_player_profile, search_players

router = APIRouter(prefix="/players", tags=["players"])


@router.get("/search", response_model=list[PlayerSearchResult])
def search_players_endpoint(
    q: str = Query(..., min_length=1, description="Nombre o ID del jugador"),
    limit: int = Query(20, ge=1, le=50),
) -> list[PlayerSearchResult]:
    require_model_ready()
    return search_players(q, limit=limit)


@router.get("/{player_id}", response_model=PlayerProfileResponse)
def get_player_endpoint(player_id: int) -> PlayerProfileResponse:
    require_model_ready()
    profile = get_player_profile(player_id)
    if profile is None:
        raise HTTPException(
            status_code=404,
            detail=f"Jugador con ID {player_id} no encontrado.",
        )
    return profile
