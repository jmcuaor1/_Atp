import os
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("ALLOW_START_WITHOUT_MODEL", "true")
os.environ["TESTING"] = "true"

from app.state import app_state  # noqa: E402


@pytest.fixture
def mock_ml_resources():
    """Estado de ML simulado para tests sin archivos .pkl."""
    mock_model = MagicMock()
    mock_model.predict_proba.return_value = [[0.58, 0.42]]

    app_state.model = mock_model
    app_state.model_features = [
        "surface_encoded",
        "p1_rank",
        "p2_rank",
        "p1_elo_before_match",
        "p2_elo_before_match",
        "p1_age",
        "p2_age",
        "p1_ht",
        "p2_ht",
        "p1_rolling_avg_ace",
        "p2_rolling_avg_ace",
        "p1_rolling_avg_df",
        "p2_rolling_avg_df",
        "p1_rolling_avg_1stWon",
        "p2_rolling_avg_1stWon",
        "p1_rank_points",
        "p2_rank_points",
    ]
    app_state.player_profiles = {
        104925: {
            "id": 104925,
            "name": "N. Djokovic",
            "hand": "R",
            "ht": 188,
            "age": 36,
            "ioc": "SRB",
            "rank": 1,
            "rank_points": 9000,
            "elo": 2100,
            "rolling_avg_ace": 5,
            "rolling_avg_df": 2,
            "rolling_avg_1stWon": 40,
        },
        207989: {
            "id": 207989,
            "name": "C. Alcaraz",
            "hand": "R",
            "ht": 183,
            "age": 21,
            "ioc": "ESP",
            "rank": 2,
            "rank_points": 8500,
            "elo": 2050,
            "rolling_avg_ace": 6,
            "rolling_avg_df": 3,
            "rolling_avg_1stWon": 38,
        },
    }
    app_state.model_metadata = {
        "accuracy": 0.67,
        "brier_score": 0.21,
        "feature_count": 17,
        "trained_at": "2025-01-01T00:00:00+00:00",
    }
    yield
    app_state.model = None
    app_state.model_features = []
    app_state.player_profiles = {}
    app_state.model_metadata = {}
