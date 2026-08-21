"""
Cuántos partidos recientes tiene un jugador en los datos crudos — señal de
qué tan confiable es la predicción del modelo para él. Las rolling stats
(ver src/features.py::create_rolling_stats_for_all_matches) se calculan
sobre una ventana de los últimos 10 partidos; un jugador con menos
historial que eso arrastra una ventana incompleta (o directamente en cero,
ver el fillna(0) de esa función para "new players or early matches").

Esto es puramente informativo para la API/frontend — no alimenta al
modelo ni al entrenamiento, así que vive en app/ y no en src/features.py.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pandas as pd

from app.config import BASE_DIR

logger = logging.getLogger(__name__)

RAW_DATA_DIR = BASE_DIR / "data" / "raw"
# Mismo tamaño que la ventana de rolling stats en src/features.py.
LOW_SAMPLE_THRESHOLD = 10
# Alcanza de sobra para superar el umbral en cualquier jugador activo del
# circuito, sin escanear las ~6 décadas de historia en data/raw/.
RECENT_YEARS_SCANNED = 2

_YEAR_RE = re.compile(r"atp_matches_(\d{4})\.csv$")


def _recent_raw_files(raw_dir: Path, n_years: int) -> list[Path]:
    dated = []
    for path in raw_dir.glob("atp_matches_*.csv"):
        match = _YEAR_RE.search(path.name)
        if match:
            dated.append((int(match.group(1)), path))
    dated.sort(key=lambda t: t[0], reverse=True)
    return [path for _, path in dated[:n_years]]


def compute_recent_match_counts(
    raw_dir: Path = RAW_DATA_DIR, n_years: int = RECENT_YEARS_SCANNED
) -> dict[int, int]:
    """player_id -> partidos jugados (ganados o perdidos) en los `n_years`
    años más recientes disponibles en `raw_dir`. Dict vacío si no hay datos."""
    counts: dict[int, int] = {}
    files = _recent_raw_files(raw_dir, n_years)
    if not files:
        logger.warning("No se encontraron atp_matches_*.csv en %s; recent_match_counts queda vacío.", raw_dir)
        return counts

    for path in files:
        try:
            df = pd.read_csv(path, usecols=["winner_id", "loser_id"])
        except (FileNotFoundError, ValueError, pd.errors.EmptyDataError) as exc:
            logger.warning("No se pudo leer %s para contar partidos: %s", path, exc)
            continue
        for col in ("winner_id", "loser_id"):
            for player_id, n in df[col].dropna().astype(int).value_counts().items():
                counts[player_id] = counts.get(player_id, 0) + int(n)
    return counts


def is_low_sample(player_id: int, counts: dict[int, int]) -> bool:
    return counts.get(player_id, 0) < LOW_SAMPLE_THRESHOLD
