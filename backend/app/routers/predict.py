import asyncio
from functools import partial

from fastapi import APIRouter, HTTPException

from app.dependencies import require_model_ready
from app.schemas.predict import PredictionRequest, PredictionResponse
from app.services.prediction import PredictionError, predict_match_sync

router = APIRouter(tags=["predictions"])


@router.post("/predict", response_model=PredictionResponse)
async def predict_match(request: PredictionRequest) -> PredictionResponse:
    require_model_ready()
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(
            None,
            partial(predict_match_sync, request),
        )
    except PredictionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
