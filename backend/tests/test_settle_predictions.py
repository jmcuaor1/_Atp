"""
Tests para scripts/settle_predictions.py (acierto de pronóstico, distinto
del ROI de apuestas de valor que cubre test_live_odds.py).
"""

import sys
from pathlib import Path

import pandas as pd

BACKEND_DIR = Path(__file__).resolve().parent.parent
for p in (BACKEND_DIR / "src", BACKEND_DIR / "scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import settle_predictions  # noqa: E402


def _log_row(**overrides):
    row = {
        "p1_name": "Novak Djokovic", "p2_name": "Carlos Alcaraz",
        "model_p1_prob": 0.7, "model_p2_prob": 0.3,
    }
    row.update(overrides)
    return pd.Series(row)


def test_predicted_winner_name_picks_higher_probability_side():
    assert settle_predictions.predicted_winner_name(_log_row()) == "Novak Djokovic"


def test_predicted_winner_name_picks_p2_when_favored():
    row = _log_row(model_p1_prob=0.2, model_p2_prob=0.8)
    assert settle_predictions.predicted_winner_name(row) == "Carlos Alcaraz"
