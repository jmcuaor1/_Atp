from fastapi import APIRouter

from app.schemas.health import HealthResponse
from app.state import app_state

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(
        status="ok" if app_state.is_ready else "degraded",
        model_loaded=app_state.model is not None,
        players_count=app_state.players_count,
        feature_count=len(app_state.model_features),
    )
