from pydantic import BaseModel


class TodayMatch(BaseModel):
    event_id: str
    tournament: str
    commence_time: str | None
    surface: str
    player1_name: str
    player2_name: str
    player1_id: int | None = None
    player2_id: int | None = None
    player1_win_probability: float | None = None
    player2_win_probability: float | None = None
    predicted_winner_name: str | None = None
    resolved: bool = False
    note: str | None = None


class TodayMatchesResponse(BaseModel):
    matches: list[TodayMatch]
    model_data_cutoff: str | None
    generated_at: str
    cached: bool
