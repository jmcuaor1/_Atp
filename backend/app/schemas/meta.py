from pydantic import BaseModel


class SurfacesResponse(BaseModel):
    surfaces: list[str]


class ModelInfoResponse(BaseModel):
    model_loaded: bool
    feature_count: int
    players_count: int
    metadata: dict
