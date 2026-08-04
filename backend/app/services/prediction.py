from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from features import get_features_for_single_prediction

from app.schemas.predict import PredictionRequest, PredictionResponse
from app.state import app_state

logger = logging.getLogger(__name__)

PREDICTIONS_LOG_PATH = (
    Path(__file__).resolve().parent.parent.parent / "data" / "processed" / "predictions_log.jsonl"
)


class PredictionError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _require_ready() -> None:
    if not app_state.is_ready:
        raise PredictionError(
            "Modelo o perfiles de jugador no cargados. La API no está lista.",
            status_code=503,
        )


def _get_profile(player_id: int, label: str) -> dict:
    profile = app_state.player_profiles.get(player_id)
    if profile is None:
        raise PredictionError(
            f"Perfil del {label} (ID: {player_id}) no encontrado en los datos históricos.",
            status_code=404,
        )
    return profile


def _log_prediction(response: PredictionResponse) -> None:
    """
    Deja un registro de cada predicción servida, para poder cruzarlo más
    adelante contra el resultado real y medir accuracy/CLV en vivo (no solo
    en el backtest histórico). Nunca debe romper la respuesta al usuario si
    falla — es un side-effect de auditoría, no parte del contrato de la API.
    """
    try:
        PREDICTIONS_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "logged_at": datetime.now(timezone.utc).isoformat(),
            "player1_id": response.player1_id,
            "player2_id": response.player2_id,
            "player1_name": response.player1_name,
            "player2_name": response.player2_name,
            "player1_win_probability": response.player1_win_probability,
            "player2_win_probability": response.player2_win_probability,
            "predicted_winner_id": response.predicted_winner_id,
            "surface": response.surface,
            "model_trained_at": app_state.model_metadata.get("trained_at"),
            "model_git_commit": app_state.model_metadata.get("git_commit"),
        }
        with PREDICTIONS_LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        logger.exception("No se pudo escribir el log de predicciones (no afecta la respuesta).")


def predict_match_sync(request: PredictionRequest) -> PredictionResponse:
    """Ejecuta la predicción de forma síncrona (para run_in_executor)."""
    _require_ready()

    p1_id = request.player1.id
    p2_id = request.player2.id
    player1_profile = _get_profile(p1_id, "jugador 1")
    player2_profile = _get_profile(p2_id, "jugador 2")

    X_predict = get_features_for_single_prediction(
        player1_profile,
        player2_profile,
        request.surface,
        best_of=request.best_of,
        tourney_level=request.tourney_level,
    )

    missing_cols = set(app_state.model_features) - set(X_predict.columns)
    for col in missing_cols:
        X_predict[col] = -1
    X_predict = X_predict[app_state.model_features]

    probabilities = app_state.model.predict_proba(X_predict)[0]
    p1_win_proba = float(probabilities[0])
    p2_win_proba = float(probabilities[1])

    p1_name = str(player1_profile.get("name", f"Jugador {p1_id}"))
    p2_name = str(player2_profile.get("name", f"Jugador {p2_id}"))
    predicted_winner_id = p1_id if p1_win_proba > p2_win_proba else p2_id
    predicted_winner_name = p1_name if predicted_winner_id == p1_id else p2_name

    response = PredictionResponse(
        player1_id=p1_id,
        player2_id=p2_id,
        player1_name=p1_name,
        player2_name=p2_name,
        player1_win_probability=p1_win_proba,
        player2_win_probability=p2_win_proba,
        predicted_winner_id=predicted_winner_id,
        predicted_winner_name=predicted_winner_name,
        surface=request.surface,
        message="Predicción generada exitosamente.",
    )
    _log_prediction(response)
    return response
