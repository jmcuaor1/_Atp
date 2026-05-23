import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

BASE_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BASE_DIR / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

MODEL_PATH = Path(os.getenv("MODEL_PATH", BASE_DIR / "models" / "tennis_model.pkl"))
PLAYER_PROFILES_PATH = Path(
    os.getenv("PLAYER_PROFILES_PATH", BASE_DIR / "models" / "player_profiles.pkl")
)

CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
]

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
ALLOW_START_WITHOUT_MODEL = os.getenv("ALLOW_START_WITHOUT_MODEL", "false").lower() == "true"

SURFACES = ("Hard", "Clay", "Grass")
TOURNEY_LEVELS = ("G", "M", "A", "C", "F", "D")
BEST_OF_VALUES = (3, 5)
