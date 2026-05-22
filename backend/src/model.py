import numpy as np
from pathlib import Path
from typing import Optional
from .features import build_features

MODEL_PATH = Path(__file__).parent.parent / "models" / "xgboost_model.pkl"

_model = None
_model_checked = False


def _get_model():
    global _model, _model_checked
    if not _model_checked:
        _model_checked = True
        if MODEL_PATH.exists():
            try:
                import joblib
                _model = joblib.load(MODEL_PATH)
            except Exception:
                _model = None
    return _model


def predict_winner(
    player1: str,
    player2: str,
    surface: str,
    rank1: Optional[int] = None,
    rank2: Optional[int] = None,
) -> dict:
    feats = build_features(player1, player2, surface, rank1, rank2)
    model = _get_model()

    if model is not None:
        X = np.array([[
            feats["rank_diff"],
            feats["win_rate_diff"],
            feats["win_rate_p1"],
            feats["win_rate_p2"],
        ]])
        prob_p1 = float(model.predict_proba(X)[0][1])
        model_used = "xgboost"
    else:
        # Weighted heuristic: rank (50%) + surface win rate (35%) + H2H (15%)
        score = 0.0
        r1, r2 = feats["rank_p1"], feats["rank_p2"]
        score += (r2 - r1) / max(r1 + r2, 1) * 0.50
        score += feats["win_rate_diff"] * 0.35
        h_total = feats["h2h_p1"] + feats["h2h_p2"]
        if h_total > 0:
            score += (feats["h2h_p1"] / h_total - 0.5) * 2 * 0.15
        prob_p1 = float(1 / (1 + np.exp(-score * 4)))
        model_used = "heuristic"

    winner = player1 if prob_p1 >= 0.5 else player2
    loser = player2 if winner == player1 else player1
    prob_winner = prob_p1 if winner == player1 else 1 - prob_p1

    return {
        "winner": winner,
        "loser": loser,
        "probability": round(prob_winner, 3),
        "prob_p1": round(prob_p1, 3),
        "prob_p2": round(1 - prob_p1, 3),
        "features": feats,
        "model": model_used,
    }
