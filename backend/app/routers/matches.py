from fastapi import APIRouter, HTTPException

import odds_client

from app.dependencies import require_model_ready
from app.schemas.matches import TodayMatchesResponse
from app.services.live_matches import get_today_matches

router = APIRouter(tags=["matches"])


@router.get("/matches/today", response_model=TodayMatchesResponse)
def today_matches(refresh: bool = False) -> TodayMatchesResponse:
    require_model_ready()
    try:
        return get_today_matches(force_refresh=refresh)
    except odds_client.OddsApiError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
