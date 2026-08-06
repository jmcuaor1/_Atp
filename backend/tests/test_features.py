"""
Tests unitarios para src/features.py.

Cubren, sobre todo, regresiones de los bugs encontrados durante el
desarrollo del proyecto:
- calculate_elo_ratings: el Elo debe actualizarse correctamente y respetar
  el orden de rondas dentro de un mismo tourney_date.
- create_rolling_stats_for_all_matches: NO debe duplicar filas cuando un
  jugador tiene varios partidos con el mismo tourney_date (bug de la
  Fase 2 — merge many-to-many por (player_id, tourney_date) ambigua).
- symmetrize_dataset: debe balancear target 50/50, duplicar exactamente
  2x las filas, y NO corromper columnas que no son winner_/loser_ (bug de
  'draw_size' -> 'drap1_size' de la Fase 1, por detección de prefijo con
  "in" en vez de "startswith").
- compute_fatigue_features: debe usar solo partidos anteriores (sin fuga).
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from features import (  # noqa: E402
    calculate_elo_ratings,
    calculate_surface_elo_ratings,
    compute_fatigue_features,
    compute_h2h_features,
    create_return_stats_for_all_matches,
    create_rolling_stats_for_all_matches,
    encode_surface,
    symmetrize_dataset,
)


def _base_match(**overrides):
    row = {
        "tourney_id": "2024-001",
        "tourney_name": "Test Open",
        "surface": "Hard",
        "tourney_date": pd.Timestamp("2024-01-01"),
        "round": "R32",
        "winner_id": 1,
        "loser_id": 2,
        "w_ace": 5,
        "w_df": 1,
        "w_1stWon": 20,
        "l_ace": 3,
        "l_df": 2,
        "l_1stWon": 15,
        "winner_rank": 10,
        "loser_rank": 20,
    }
    row.update(overrides)
    return row


class TestCalculateEloRatings:
    def test_starts_at_1500_and_winner_gains_rating(self):
        df = pd.DataFrame([_base_match()])
        result, elo_dict = calculate_elo_ratings(df)

        assert result["winner_elo_before_match"].iloc[0] == 1500
        assert result["loser_elo_before_match"].iloc[0] == 1500
        assert elo_dict[1] > 1500  # ganador sube
        assert elo_dict[2] < 1500  # perdedor baja

    def test_elo_carries_over_between_matches(self):
        df = pd.DataFrame([
            _base_match(winner_id=1, loser_id=2, tourney_date=pd.Timestamp("2024-01-01")),
            _base_match(winner_id=1, loser_id=3, tourney_date=pd.Timestamp("2024-02-01")),
        ])
        result, _ = calculate_elo_ratings(df)

        second_match = result[result["loser_id"] == 3].iloc[0]
        assert second_match["winner_elo_before_match"] > 1500

    def test_round_order_breaks_ties_on_same_tourney_date(self):
        # Mismo torneo, misma tourney_date: el jugador 1 gana en R32 y luego
        # en la Final. Si el desempate por ronda funciona, el Elo de entrada
        # a la Final debe reflejar ya la victoria de R32 (> 1500).
        same_date = pd.Timestamp("2024-01-01")
        df = pd.DataFrame([
            _base_match(winner_id=1, loser_id=99, round="F", tourney_date=same_date),
            _base_match(winner_id=1, loser_id=2, round="R32", tourney_date=same_date),
        ])
        result, _ = calculate_elo_ratings(df)

        final_row = result[(result["round"] == "F")].iloc[0]
        assert final_row["winner_elo_before_match"] > 1500


class TestCalculateSurfaceEloRatings:
    def test_starts_at_1500_and_winner_gains_rating(self):
        df = pd.DataFrame([_base_match()])
        result, elo_dict = calculate_surface_elo_ratings(df)

        assert result["winner_surface_elo_before_match"].iloc[0] == 1500
        assert result["loser_surface_elo_before_match"].iloc[0] == 1500
        assert elo_dict[(1, "Hard")] > 1500
        assert elo_dict[(2, "Hard")] < 1500

    def test_rating_does_not_carry_over_across_surfaces(self):
        # Jugador 1 se hace fuerte en Hard; en su primer partido en Clay
        # debe arrancar de nuevo en 1500, no heredar el Elo de Hard.
        df = pd.DataFrame([
            _base_match(winner_id=1, loser_id=2, surface="Hard", tourney_date=pd.Timestamp("2024-01-01")),
            _base_match(winner_id=1, loser_id=3, surface="Clay", tourney_date=pd.Timestamp("2024-02-01")),
        ])
        result, _ = calculate_surface_elo_ratings(df)

        clay_match = result[result["loser_id"] == 3].iloc[0]
        assert clay_match["winner_surface_elo_before_match"] == 1500

    def test_rating_carries_over_within_same_surface(self):
        df = pd.DataFrame([
            _base_match(winner_id=1, loser_id=2, surface="Clay", tourney_date=pd.Timestamp("2024-01-01")),
            _base_match(winner_id=1, loser_id=3, surface="Clay", tourney_date=pd.Timestamp("2024-02-01")),
        ])
        result, _ = calculate_surface_elo_ratings(df)

        second_match = result[result["loser_id"] == 3].iloc[0]
        assert second_match["winner_surface_elo_before_match"] > 1500


class TestCreateRollingStats:
    def test_no_row_duplication_when_player_shares_tourney_date(self):
        # Regresión del bug crítico: un jugador con 3 partidos en la MISMA
        # tourney_date (como en un torneo real) no debe multiplicar filas.
        same_date = pd.Timestamp("2024-01-01")
        df = pd.DataFrame([
            _base_match(winner_id=1, loser_id=2, round="R32", tourney_date=same_date),
            _base_match(winner_id=1, loser_id=3, round="R16", tourney_date=same_date),
            _base_match(winner_id=1, loser_id=4, round="QF", tourney_date=same_date),
        ])
        result, _ = create_rolling_stats_for_all_matches(df)
        assert len(result) == len(df)

    def test_rolling_avg_uses_only_past_matches(self):
        df = pd.DataFrame([
            _base_match(winner_id=1, loser_id=2, w_ace=10, tourney_date=pd.Timestamp("2024-01-01")),
            _base_match(winner_id=1, loser_id=3, w_ace=20, tourney_date=pd.Timestamp("2024-02-01")),
        ])
        result, _ = create_rolling_stats_for_all_matches(df, window=10)

        first_match = result[result["loser_id"] == 2].iloc[0]
        second_match = result[result["loser_id"] == 3].iloc[0]

        # Sin historial previo -> 0 (fillna), no leakage del propio partido
        assert first_match["p1_rolling_avg_ace"] == 0
        # El segundo partido de player 1 debe ver el ace count del primero (10)
        assert second_match["p1_rolling_avg_ace"] == 10


class TestEncodeSurface:
    def test_known_surfaces_mapped(self):
        df = pd.DataFrame({"surface": ["Hard", "Clay", "Grass", "Carpet"]})
        result = encode_surface(df)
        assert result["surface_encoded"].tolist() == [1, 0, 2, 3]

    def test_unknown_surface_defaults_to_minus_one(self):
        df = pd.DataFrame({"surface": ["Indoor Sand"]})
        result = encode_surface(df)
        assert result["surface_encoded"].iloc[0] == -1


class TestSymmetrizeDataset:
    def test_doubles_rows_and_balances_target(self):
        df = pd.DataFrame([_base_match(), _base_match(winner_id=3, loser_id=4)])
        result = symmetrize_dataset(df)

        assert len(result) == len(df) * 2
        assert (result["target"] == 0).sum() == len(df)
        assert (result["target"] == 1).sum() == len(df)

    def test_does_not_corrupt_non_player_columns(self):
        # Regresión del bug 'draw_size' -> 'drap1_size': draw_size contiene
        # la subcadena 'w_' mitad de palabra pero NO es una columna de
        # winner/loser, no debe ser tocada por el renombrado.
        df = pd.DataFrame([_base_match(draw_size=32)])
        result = symmetrize_dataset(df)

        assert "draw_size" in result.columns
        assert "drap1_size" not in result.columns
        assert "drap2_size" not in result.columns
        assert result["draw_size"].iloc[0] == 32

    def test_swaps_player_identity_correctly(self):
        df = pd.DataFrame([_base_match(winner_id=1, loser_id=2)])
        result = symmetrize_dataset(df)

        p1_wins_row = result[result["target"] == 0].iloc[0]
        p2_wins_row = result[result["target"] == 1].iloc[0]
        assert p1_wins_row["p1_id"] == 1 and p1_wins_row["p2_id"] == 2
        assert p2_wins_row["p1_id"] == 2 and p2_wins_row["p2_id"] == 1


class TestComputeFatigueFeatures:
    def test_first_match_gets_default_no_fatigue(self):
        df = pd.DataFrame([_base_match(winner_id=1, loser_id=2)])
        result, _ = compute_fatigue_features(df)

        assert result["p1_days_since_last_match"].iloc[0] == 365
        assert result["p1_matches_last_14d"].iloc[0] == 0

    def test_counts_matches_within_window_excluding_current(self):
        # Jugador 1 juega 3 partidos en 10 días (dentro de la ventana de 14).
        df = pd.DataFrame([
            _base_match(winner_id=1, loser_id=2, tourney_date=pd.Timestamp("2024-01-01")),
            _base_match(winner_id=1, loser_id=3, tourney_date=pd.Timestamp("2024-01-05")),
            _base_match(winner_id=1, loser_id=4, tourney_date=pd.Timestamp("2024-01-10")),
        ])
        result, _ = compute_fatigue_features(df, window_days=14)

        third_match = result[result["loser_id"] == 4].iloc[0]
        # Debe contar los 2 partidos anteriores (01-01 y 01-05), no el actual
        assert third_match["p1_matches_last_14d"] == 2
        assert third_match["p1_days_since_last_match"] == 5


class TestCreateReturnStats:
    def test_first_match_defaults_to_zero(self):
        df = pd.DataFrame([_base_match(
            winner_id=1, loser_id=2,
            w_bpSaved=3, w_bpFaced=5, w_svpt=50, w_2ndWon=10,
            l_bpSaved=1, l_bpFaced=4, l_svpt=40, l_2ndWon=5,
        )])
        result, _ = create_return_stats_for_all_matches(df)

        assert result["p1_rolling_avg_bp_saved_pct"].iloc[0] == 0
        assert result["p1_rolling_avg_return_win_pct"].iloc[0] == 0
        assert result["p2_rolling_avg_bp_saved_pct"].iloc[0] == 0
        assert result["p2_rolling_avg_return_win_pct"].iloc[0] == 0

    def test_uses_only_past_matches_and_opponent_serve_stats(self):
        df = pd.DataFrame([
            _base_match(
                winner_id=1, loser_id=2, tourney_date=pd.Timestamp("2024-01-01"),
                w_bpSaved=3, w_bpFaced=5, w_svpt=50, w_1stWon=30, w_2ndWon=10,
                l_bpSaved=1, l_bpFaced=4, l_svpt=40, l_1stWon=20, l_2ndWon=5,
            ),
            _base_match(
                winner_id=1, loser_id=3, tourney_date=pd.Timestamp("2024-02-01"),
                w_bpSaved=0, w_bpFaced=0, w_svpt=0, w_1stWon=0, w_2ndWon=0,
                l_bpSaved=0, l_bpFaced=0, l_svpt=0, l_1stWon=0, l_2ndWon=0,
            ),
        ])
        result, _ = create_return_stats_for_all_matches(df)
        second_match = result[result["loser_id"] == 3].iloc[0]

        # Resiliencia en el propio saque del jugador 1 en el partido anterior: 3/5
        assert second_match["p1_rolling_avg_bp_saved_pct"] == pytest.approx(0.6)
        # Resto del jugador 1 contra el saque del jugador 2 en el partido anterior: (40-20-5)/40
        assert second_match["p1_rolling_avg_return_win_pct"] == pytest.approx(0.375)


class TestComputeH2HFeatures:
    def test_first_meeting_has_zero_h2h(self):
        df = pd.DataFrame([_base_match(winner_id=1, loser_id=2)])
        result, _ = compute_h2h_features(df)

        assert result["winner_h2h_wins"].iloc[0] == 0
        assert result["loser_h2h_wins"].iloc[0] == 0

    def test_h2h_accumulates_from_previous_meetings(self):
        df = pd.DataFrame([
            _base_match(winner_id=1, loser_id=2, tourney_date=pd.Timestamp("2024-01-01")),
            _base_match(winner_id=1, loser_id=2, tourney_date=pd.Timestamp("2024-02-01")),
        ])
        result, h2h_dict = compute_h2h_features(df)

        second_match = result.iloc[1]
        assert second_match["winner_h2h_wins"] == 1  # ya le había ganado una vez antes
        assert second_match["loser_h2h_wins"] == 0
        assert h2h_dict[1][2] == 2

    def test_h2h_tracks_wins_regardless_of_who_wins_current_match(self):
        # Jugador 1 le gana a 2 en el primer cruce; en la revancha gana el 2.
        df = pd.DataFrame([
            _base_match(winner_id=1, loser_id=2, tourney_date=pd.Timestamp("2024-01-01")),
            _base_match(winner_id=2, loser_id=1, tourney_date=pd.Timestamp("2024-02-01")),
        ])
        result, _ = compute_h2h_features(df)

        rematch = result.iloc[1]
        # "winner" de esta fila es el jugador 2, que antes tenía 0 victorias sobre 1
        assert rematch["winner_h2h_wins"] == 0
        # "loser" de esta fila es el jugador 1, que ya le había ganado una vez a 2
        assert rematch["loser_h2h_wins"] == 1


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
