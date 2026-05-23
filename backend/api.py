<<<<<<< HEAD
"""
Punto de entrada legacy para uvicorn: uvicorn api:app --reload
La aplicación vive en app.main.
"""

from app.main import app

__all__ = ["app"]

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
=======
import sys
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent))

from src.features import get_players
from src.model import predict_winner
from src.llm import explain_prediction

app = FastAPI(title="ATP Tennis Predictor", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
FRONTEND_INDEX = FRONTEND_DIR / "index.html"


@app.get("/", include_in_schema=False)
def root():
    if FRONTEND_INDEX.exists():
        return FileResponse(FRONTEND_INDEX)
    return HTMLResponse("<h2>ATP Tennis Predictor — API running. Go to <a href='/docs'>/docs</a></h2>")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/players")
def players():
    return get_players()


@app.get("/api/surfaces")
def surfaces():
    return ["Hard", "Clay", "Grass", "Carpet"]


class PredictRequest(BaseModel):
    player1: str
    player2: str
    surface: str
    player1_rank: Optional[int] = None
    player2_rank: Optional[int] = None
    explain: bool = True


@app.post("/api/predict")
def predict(req: PredictRequest):
    try:
        result = predict_winner(
            req.player1,
            req.player2,
            req.surface,
            req.player1_rank,
            req.player2_rank,
        )
        if req.explain:
            try:
                result["explanation"] = explain_prediction(
                    req.player1, req.player2, req.surface, result
                )
            except Exception as e:
                result["explanation"] = f"(Explicación no disponible: {e})"
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Serve remaining frontend static assets (CSS, JS, images if any)
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
>>>>>>> daab2e1cdb2d49c4091b6dfcafe4a8caa0d5a9c3
