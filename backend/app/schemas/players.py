from pydantic import BaseModel, Field


class PlayerSearchResult(BaseModel):
    id: int
    name: str
    rank: float | None = None
    ioc: str | None = None
    elo: float | None = None


class PlayerProfileResponse(BaseModel):
    id: int
    name: str
    hand: str | None = None
    ht: float | None = None
    age: float | None = None
    ioc: str | None = None
    rank: float | None = None
    rank_points: float | None = None
    elo: float = Field(..., description="Rating ELO actual")
    rolling_avg_ace: float = 0
    rolling_avg_df: float = 0
    rolling_avg_1stWon: float = 0
