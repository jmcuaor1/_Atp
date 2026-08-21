"""
Tests para la Fase 7 (odds_client.py, fetch_live_odds.py, settle_live_odds.py).

Todo acá corre con fixtures fabricadas a mano (con la forma documentada de
las respuestas de The Odds API) y sin red real — no gastan cuota del API
key y no requieren ODDS_API_KEY configurada. Lo único que no se puede
probar sin una key real es el request HTTP en sí (ver docstring de
fetch_live_odds.py / settle_live_odds.py para el flujo end-to-end manual).
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
for p in (BACKEND_DIR / "src", BACKEND_DIR / "scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import odds_client  # noqa: E402
import fetch_live_odds  # noqa: E402
import settle_live_odds  # noqa: E402


def _event(**overrides):
    event = {
        "id": "evt-1",
        "sport_key": "tennis_atp_wimbledon",
        "commence_time": "2026-07-01T12:00:00Z",
        "home_team": "Novak Djokovic",
        "away_team": "Carlos Alcaraz",
        "bookmakers": [
            {
                "key": "pinnacle",
                "title": "Pinnacle",
                "markets": [{
                    "key": "h2h",
                    "outcomes": [
                        {"name": "Novak Djokovic", "price": 1.65},
                        {"name": "Carlos Alcaraz", "price": 2.35},
                    ],
                }],
            },
            {
                "key": "draftkings",
                "title": "DraftKings",
                "markets": [{
                    "key": "h2h",
                    "outcomes": [
                        {"name": "Novak Djokovic", "price": 1.70},
                        {"name": "Carlos Alcaraz", "price": 2.20},
                    ],
                }],
            },
        ],
    }
    event.update(overrides)
    return event


# --- odds_client.extract_book_odds --------------------------------------

def test_extract_book_odds_filters_by_whitelist():
    rows = odds_client.extract_book_odds(_event())
    assert len(rows) == 1
    assert rows[0]["book"] == "pinnacle"
    assert rows[0]["odds_home"] == 1.65
    assert rows[0]["odds_away"] == 2.35


def test_extract_book_odds_empty_when_no_whitelisted_book():
    event = _event(bookmakers=[_event()["bookmakers"][1]])  # solo draftkings
    assert odds_client.extract_book_odds(event) == []


def test_extract_book_odds_skips_market_missing_a_player():
    event = _event(bookmakers=[{
        "key": "pinnacle",
        "markets": [{"key": "h2h", "outcomes": [{"name": "Novak Djokovic", "price": 1.65}]}],
    }])
    assert odds_client.extract_book_odds(event) == []


# --- fetch_live_odds.guess_surface ---------------------------------------

@pytest.mark.parametrize("sport_key,expected", [
    ("tennis_atp_wimbledon", "Grass"),
    ("tennis_atp_french_open", "Clay"),
    ("tennis_atp_us_open", "Hard"),
    ("tennis_atp_miami_open", "Hard"),
])
def test_guess_surface(sport_key, expected):
    assert fetch_live_odds.guess_surface(sport_key) == expected


# --- fetch_live_odds.resolve_player_id / predict (httpx mockeado) --------

def test_resolve_player_id_matches_by_surname_and_initial(monkeypatch):
    candidates = [
        {"id": 104925, "name": "Novak Djokovic", "rank": 1},
        {"id": 999, "name": "Someone Djokovic", "rank": 500},
    ]

    def fake_get(url, params=None, timeout=None):
        assert "players/search" in url
        return SimpleNamespace(json=lambda: candidates, raise_for_status=lambda: None)

    monkeypatch.setattr(fetch_live_odds.httpx, "get", fake_get)
    player = fetch_live_odds.resolve_player_id("Novak Djokovic")
    assert player["id"] == 104925


def test_resolve_player_id_queries_by_last_word_for_compound_surname(monkeypatch):
    """/players/search hace substring literal contra el nombre guardado (con
    espacios), así que la query no puede ser el apellido normalizado sin
    espacios ('deminaur') o nunca matchea 'Alex De Minaur'."""
    candidates = [{"id": 200282, "name": "Alex De Minaur", "rank": 10}]
    seen_queries = []

    def fake_get(url, params=None, timeout=None):
        seen_queries.append(params["q"])
        return SimpleNamespace(json=lambda: candidates, raise_for_status=lambda: None)

    monkeypatch.setattr(fetch_live_odds.httpx, "get", fake_get)
    player = fetch_live_odds.resolve_player_id("Alex de Minaur")
    assert player["id"] == 200282
    assert seen_queries == ["Minaur"]


def test_resolve_player_id_falls_back_to_middle_surname_when_base_has_fewer_apellidos(monkeypatch):
    """La cuota trae 'Daniel Merida Aguilar' pero el dataset ATP solo tiene
    'Daniel Merida' (un apellido). La búsqueda por última palabra ('Aguilar')
    no matchea nada propio; el fallback prueba 'Merida' y sí lo encuentra."""
    responses = {
        "Aguilar": [
            {"id": 104477, "name": "Jorge Aguilar", "rank": 196},
            {"id": 212051, "name": "Joaquin  Aguilar Cardozo ", "rank": 1109},
        ],
        "Merida": [{"id": 900043, "name": "Daniel Merida", "rank": 82}],
    }
    seen_queries = []

    def fake_get(url, params=None, timeout=None):
        seen_queries.append(params["q"])
        return SimpleNamespace(json=lambda: responses.get(params["q"], []), raise_for_status=lambda: None)

    monkeypatch.setattr(fetch_live_odds.httpx, "get", fake_get)
    player = fetch_live_odds.resolve_player_id("Daniel Merida Aguilar")
    assert player["id"] == 900043
    assert seen_queries == ["Aguilar", "Merida"]


def test_resolve_player_id_returns_none_without_match(monkeypatch):
    monkeypatch.setattr(
        fetch_live_odds.httpx, "get",
        lambda url, params=None, timeout=None: SimpleNamespace(json=lambda: [], raise_for_status=lambda: None),
    )
    assert fetch_live_odds.resolve_player_id("Nadie De Nadie") is None


def test_build_log_rows_end_to_end_with_mocks(monkeypatch):
    monkeypatch.setattr(
        fetch_live_odds, "resolve_player_id",
        lambda name: {"id": 104925, "name": "Novak Djokovic"} if "Djokovic" in name
        else {"id": 207989, "name": "Carlos Alcaraz"},
    )
    monkeypatch.setattr(
        fetch_live_odds, "predict",
        lambda p1_id, p2_id, surface: {
            "player1_id": p1_id, "player2_id": p2_id,
            "player1_name": "Novak Djokovic", "player2_name": "Carlos Alcaraz",
            "player1_win_probability": 0.7, "player2_win_probability": 0.3,
        },
    )

    rows = fetch_live_odds.build_log_rows(
        _event(), "tennis_atp_wimbledon", {},
        model_version={"model_trained_at": "2026-08-06T23:21:12+00:00", "model_git_commit": "abc123"},
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["book"] == "pinnacle"
    assert row["p1_id"] == 104925 and row["p2_id"] == 207989
    assert row["model_trained_at"] == "2026-08-06T23:21:12+00:00"
    assert row["model_git_commit"] == "abc123"
    assert row["implied_p1"] == pytest.approx(1 / 1.65)
    assert row["edge_p1"] == pytest.approx(0.7 - 1 / 1.65)


def test_build_log_rows_model_version_defaults_to_none_when_omitted(monkeypatch):
    monkeypatch.setattr(
        fetch_live_odds, "resolve_player_id",
        lambda name: {"id": 104925, "name": "Novak Djokovic"} if "Djokovic" in name
        else {"id": 207989, "name": "Carlos Alcaraz"},
    )
    monkeypatch.setattr(
        fetch_live_odds, "predict",
        lambda p1_id, p2_id, surface: {
            "player1_id": p1_id, "player2_id": p2_id,
            "player1_name": "Novak Djokovic", "player2_name": "Carlos Alcaraz",
            "player1_win_probability": 0.7, "player2_win_probability": 0.3,
        },
    )

    rows = fetch_live_odds.build_log_rows(_event(), "tennis_atp_wimbledon", {})
    assert rows[0]["model_trained_at"] is None
    assert rows[0]["model_git_commit"] is None


def test_fetch_model_version_reads_metadata(monkeypatch):
    def fake_get(url, timeout=None):
        assert url.endswith("/model/info")
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"metadata": {"trained_at": "2026-08-06T23:21:12+00:00", "git_commit": "abc123", "accuracy": 0.66}},
        )

    monkeypatch.setattr(fetch_live_odds.httpx, "get", fake_get)
    version = fetch_live_odds.fetch_model_version()
    assert version == {"model_trained_at": "2026-08-06T23:21:12+00:00", "model_git_commit": "abc123"}


def test_fetch_model_version_returns_nones_on_http_error(monkeypatch):
    def fake_get(url, timeout=None):
        raise fetch_live_odds.httpx.HTTPError("boom")

    monkeypatch.setattr(fetch_live_odds.httpx, "get", fake_get)
    assert fetch_live_odds.fetch_model_version() == {"model_trained_at": None, "model_git_commit": None}


# --- odds_client.determine_winner_side ------------------------------------

def _score_event(**overrides):
    event = {
        "id": "evt-1",
        "completed": True,
        "home_team": "Novak Djokovic",
        "away_team": "Carlos Alcaraz",
        "scores": [
            {"name": "Novak Djokovic", "score": "2"},
            {"name": "Carlos Alcaraz", "score": "0"},
        ],
    }
    event.update(overrides)
    return event


def test_determine_winner_side_home_wins():
    assert odds_client.determine_winner_side(_score_event()) == "home"


def test_determine_winner_side_away_wins():
    event = _score_event(scores=[
        {"name": "Novak Djokovic", "score": "0"},
        {"name": "Carlos Alcaraz", "score": "2"},
    ])
    assert odds_client.determine_winner_side(event) == "away"


def test_determine_winner_side_not_completed():
    assert odds_client.determine_winner_side(_score_event(completed=False)) is None


def test_determine_winner_side_tied_or_missing_scores():
    tied = _score_event(scores=[
        {"name": "Novak Djokovic", "score": "1"},
        {"name": "Carlos Alcaraz", "score": "1"},
    ])
    assert odds_client.determine_winner_side(tied) is None
    assert odds_client.determine_winner_side(_score_event(scores=[])) is None


# --- settle_live_odds.settle_row -----------------------------------------

def _log_row(**overrides):
    row = {
        "event_id": "evt-1", "book": "pinnacle", "sport_key": "tennis_atp_wimbledon",
        "commence_time": "2026-07-01T12:00:00Z", "p1_name": "Novak Djokovic", "p2_name": "Carlos Alcaraz",
        "odds_p1": 1.65, "odds_p2": 2.35,
        "model_p1_prob": 0.7, "model_p2_prob": 0.3,
        "implied_p1": 1 / 1.65, "implied_p2": 1 / 2.35,
        "edge_p1": 0.7 - 1 / 1.65, "edge_p2": 0.3 - 1 / 2.35,
    }
    row.update(overrides)
    return pd.Series(row)


def test_settle_row_bets_only_where_edge_positive_and_wins():
    row = _log_row()  # edge_p1 > 0, edge_p2 < 0 (0.3 - 0.425 < 0)
    bets = settle_live_odds.settle_row(row, winner_side="home")
    assert len(bets) == 1
    assert bets[0]["side"] == "p1"
    assert bets[0]["won"] is True
    assert bets[0]["payout"] == pytest.approx(0.65)


def test_settle_row_loses_when_bet_side_does_not_win():
    row = _log_row()
    bets = settle_live_odds.settle_row(row, winner_side="away")
    assert len(bets) == 1
    assert bets[0]["side"] == "p1"
    assert bets[0]["won"] is False
    assert bets[0]["payout"] == -1.0


def test_settle_row_can_produce_two_bets():
    row = _log_row(implied_p1=0.5, edge_p1=0.2, implied_p2=0.3, edge_p2=0.05)
    bets = settle_live_odds.settle_row(row, winner_side="home")
    assert {b["side"] for b in bets} == {"p1", "p2"}
