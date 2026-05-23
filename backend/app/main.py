import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import CORS_ORIGINS, LOG_LEVEL
from app.routers import health, meta, players, predict
from app.state import load_resources

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Iniciando TennisAI API…")
    if os.getenv("TESTING") != "true":
        load_resources()
    yield
    logger.info("Apagando TennisAI API.")


def create_app() -> FastAPI:
    application = FastAPI(
        title="TennisAI Prediction API",
        description="API para predecir ganadores de partidos ATP con machine learning.",
        version="1.1.0",
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(health.router)
    application.include_router(predict.router)
    application.include_router(players.router)
    application.include_router(meta.router)

    return application


app = create_app()
