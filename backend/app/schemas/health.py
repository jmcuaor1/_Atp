from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    players_count: int
    feature_count: int
