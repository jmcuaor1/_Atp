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
    book: str | None = None
    player1_odds: float | None = None
    player2_odds: float | None = None
    player1_implied_probability: float | None = None
    player2_implied_probability: float | None = None
    player1_edge: float | None = None
    player2_edge: float | None = None
    value_bet_player_name: str | None = None
    suspicious_edge: bool = False
    player1_matches_played: int | None = None
    player2_matches_played: int | None = None
    player1_low_sample: bool = False
    player2_low_sample: bool = False
    low_sample_warning: bool = False


class TodayMatchesResponse(BaseModel):
    matches: list[TodayMatch]
    model_data_cutoff: str | None
    generated_at: str
    cached: bool
