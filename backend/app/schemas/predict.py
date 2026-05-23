from typing import Literal

from pydantic import BaseModel, Field, model_validator

Surface = Literal["Hard", "Clay", "Grass"]
TourneyLevel = Literal["G", "M", "A", "C", "F", "D"]
BestOf = Literal[3, 5]


class PlayerInput(BaseModel):
    id: int = Field(..., gt=0, description="ID ATP del jugador")

    model_config = {
        "json_schema_extra": {
            "examples": [{"id": 104925}],
        }
    }


class PredictionRequest(BaseModel):
    player1: PlayerInput
    player2: PlayerInput
    surface: Surface = Field(..., description="Superficie del partido")
    best_of: BestOf = Field(3, description="Mejor de 3 o 5 sets")
    tourney_level: TourneyLevel = Field(
        "A",
        description="Nivel del torneo (G=Grand Slam, M=Masters, A=ATP, etc.)",
    )

    @model_validator(mode="after")
    def players_must_differ(self) -> "PredictionRequest":
        if self.player1.id == self.player2.id:
            raise ValueError("Los dos jugadores deben tener IDs distintos")
        return self

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "player1": {"id": 104925},
                    "player2": {"id": 207989},
                    "surface": "Hard",
                    "best_of": 3,
                    "tourney_level": "A",
                }
            ]
        }
    }


class PredictionResponse(BaseModel):
    player1_id: int
    player2_id: int
    player1_name: str
    player2_name: str
    player1_win_probability: float = Field(..., ge=0, le=1)
    player2_win_probability: float = Field(..., ge=0, le=1)
    predicted_winner_id: int
    predicted_winner_name: str
    surface: str
    message: str
