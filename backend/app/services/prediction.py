from __future__ import annotations

from features import get_features_for_single_prediction

from app.schemas.predict import PredictionRequest, PredictionResponse
from app.state import app_state


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

    return PredictionResponse(
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
