from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import joblib

from app.config import ALLOW_START_WITHOUT_MODEL, MODEL_PATH, PLAYER_PROFILES_PATH

logger = logging.getLogger(__name__)


@dataclass
class AppState:
    model: Any = None
    model_features: list[str] = field(default_factory=list)
    player_profiles: dict[int, dict[str, Any]] = field(default_factory=dict)
    model_metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_ready(self) -> bool:
        return self.model is not None and bool(self.player_profiles)

    @property
    def players_count(self) -> int:
        return len(self.player_profiles)


app_state = AppState()


def _normalize_profiles(raw: dict) -> dict[int, dict[str, Any]]:
    normalized: dict[int, dict[str, Any]] = {}
    for key, profile in raw.items():
        player_id = int(key)
        profile = dict(profile)
        profile["id"] = player_id
        normalized[player_id] = profile
    return normalized


def load_resources() -> None:
    """Carga modelo y perfiles. Falla al arrancar si los archivos no existen."""
    if not MODEL_PATH.is_file():
        msg = f"No se encontró el modelo en {MODEL_PATH}"
        if ALLOW_START_WITHOUT_MODEL:
            logger.warning(msg)
            return
        raise FileNotFoundError(msg)

    if not PLAYER_PROFILES_PATH.is_file():
        msg = f"No se encontraron perfiles en {PLAYER_PROFILES_PATH}"
        if ALLOW_START_WITHOUT_MODEL:
            logger.warning(msg)
            return
        raise FileNotFoundError(msg)

    logger.info("Cargando modelo desde %s", MODEL_PATH)
    model_data = joblib.load(MODEL_PATH)

    if isinstance(model_data, dict):
        app_state.model = model_data.get("model")
        app_state.model_features = list(model_data.get("features") or [])
        app_state.model_metadata = dict(model_data.get("metadata") or {})
    else:
        app_state.model = model_data
        app_state.model_features = []

    if not app_state.model_features and hasattr(app_state.model, "calibrated_classifiers_"):
        base = app_state.model.calibrated_classifiers_[0].base_estimator
        names = getattr(base, "feature_names_in_", [])
        app_state.model_features = list(names)

    if app_state.model is None:
        raise RuntimeError("El archivo del modelo no contiene un estimador válido.")

    logger.info("Cargando perfiles desde %s", PLAYER_PROFILES_PATH)
    raw_profiles = joblib.load(PLAYER_PROFILES_PATH)
    app_state.player_profiles = _normalize_profiles(raw_profiles)

    logger.info(
        "Recursos cargados: %d jugadores, %d features",
        app_state.players_count,
        len(app_state.model_features),
    )
