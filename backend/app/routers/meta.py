from fastapi import APIRouter

from app.config import BEST_OF_VALUES, SURFACES, TOURNEY_LEVELS
from app.dependencies import require_model_ready
from app.schemas.meta import ModelInfoResponse, SurfacesResponse
from app.state import app_state

router = APIRouter(tags=["metadata"])


@router.get("/surfaces", response_model=SurfacesResponse)
def list_surfaces() -> SurfacesResponse:
    return SurfacesResponse(surfaces=list(SURFACES))


@router.get("/tourney-levels")
def list_tourney_levels() -> dict:
    return {"tourney_levels": list(TOURNEY_LEVELS)}


@router.get("/best-of-values")
def list_best_of() -> dict:
    return {"best_of": list(BEST_OF_VALUES)}


@router.get("/model/info", response_model=ModelInfoResponse)
def model_info() -> ModelInfoResponse:
    require_model_ready()
    return ModelInfoResponse(
        model_loaded=app_state.model is not None,
        feature_count=len(app_state.model_features),
        players_count=app_state.players_count,
        metadata=app_state.model_metadata,
    )
