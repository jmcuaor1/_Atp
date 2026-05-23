from fastapi import HTTPException

from app.state import app_state


def require_model_ready() -> None:
    if not app_state.is_ready:
        raise HTTPException(
            status_code=503,
            detail="Modelo o perfiles de jugador no cargados. La API no está lista.",
        )
