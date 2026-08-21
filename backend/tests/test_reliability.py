"""
Tests para app/services/reliability.py — el conteo de partidos recientes
que alimenta el indicador de "poca muestra" en /matches/today y
/players/{id}. Usa CSVs de prueba en un tmp_path, no los reales de
data/raw/ (esos pesan ~175MB en total).
"""

import pandas as pd
import pytest

from app.services import reliability


def _write_csv(path, rows):
    pd.DataFrame(rows, columns=["winner_id", "loser_id"]).to_csv(path, index=False)


@pytest.fixture
def raw_dir(tmp_path):
    # 2026: Djokovic gana 2, Alcaraz pierde 2 y gana 1 (jugador nuevo, 1 solo partido)
    _write_csv(tmp_path / "atp_matches_2026.csv", [
        (104925, 207989),
        (104925, 207989),
        (207989, 999999),
    ])
    # 2025: Djokovic suma 2 más (total 4), Alcaraz nada
    _write_csv(tmp_path / "atp_matches_2025.csv", [
        (104925, 111111),
        (222222, 104925),
    ])
    # 2020: fuera de la ventana de RECENT_YEARS_SCANNED=2, no debe contar
    _write_csv(tmp_path / "atp_matches_2020.csv", [
        (104925, 333333),
    ] * 20)
    return tmp_path


def test_compute_recent_match_counts_sums_wins_and_losses(raw_dir):
    counts = reliability.compute_recent_match_counts(raw_dir, n_years=2)
    assert counts[104925] == 4  # 2 (2026) + 2 (2025)
    assert counts[207989] == 3  # 1 ganado + 2 perdidos, en 2026


def test_compute_recent_match_counts_ignores_years_outside_window(raw_dir):
    counts = reliability.compute_recent_match_counts(raw_dir, n_years=2)
    assert 333333 not in counts  # solo aparece en el csv de 2020, fuera de ventana


def test_compute_recent_match_counts_empty_dir_returns_empty(tmp_path):
    assert reliability.compute_recent_match_counts(tmp_path, n_years=2) == {}


def test_is_low_sample_below_threshold(raw_dir):
    counts = reliability.compute_recent_match_counts(raw_dir, n_years=2)
    assert reliability.is_low_sample(999999, counts) is True  # nunca aparece como winner/loser en la ventana
    assert reliability.is_low_sample(207989, counts) is True  # 2 partidos, bajo LOW_SAMPLE_THRESHOLD=10


def test_is_low_sample_above_threshold():
    counts = {104925: 15}
    assert reliability.is_low_sample(104925, counts) is False


def test_is_low_sample_exactly_at_threshold_counts_as_low():
    counts = {104925: reliability.LOW_SAMPLE_THRESHOLD}
    assert reliability.is_low_sample(104925, counts) is False  # ">= umbral" ya es suficiente muestra
    counts = {104925: reliability.LOW_SAMPLE_THRESHOLD - 1}
    assert reliability.is_low_sample(104925, counts) is True
