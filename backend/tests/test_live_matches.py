"""
Tests para live_matches.py — en particular el filtro de partidos ya
arrancados (ver commit "no comparar predicción pre-partido con cuota en
vivo"). Todo con fixtures a mano y sin red ni modelo real.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.services import live_matches
from app.state import app_state


# --- _resolve_player: fallback por apellido intermedio ---------------------

def test_resolve_player_falls_back_to_middle_surname(monkeypatch):
    """Mismo caso que Daniel Merida Aguilar (odds) vs Daniel Merida (base):
    la búsqueda por última palabra no matchea nada propio, el fallback
    prueba el apellido intermedio y encuentra al jugador real."""
    responses = {
        "Aguilar": [
            SimpleNamespace(id=104477, name="Jorge Aguilar"),
            SimpleNamespace(id=212051, name="Joaquin  Aguilar Cardozo "),
        ],
        "Merida": [SimpleNamespace(id=900043, name="Daniel Merida")],
    }
    seen_queries = []

    def fake_search_players(query, limit=20):
        seen_queries.append(query)
        return responses.get(query, [])

    monkeypatch.setattr(live_matches, "search_players", fake_search_players)
    player = live_matches._resolve_player("Daniel Merida Aguilar")
    assert player == {"id": 900043, "name": "Daniel Merida"}
    assert seen_queries == ["Aguilar", "Merida"]


def test_resolve_player_still_matches_full_compound_surname(monkeypatch):
    """No romper el caso que ya andaba: apellido compuesto igual de ambos
    lados ('Botic van de Zandschulp' en la cuota y en la base)."""
    monkeypatch.setattr(
        live_matches, "search_players",
        lambda query, limit=20: [SimpleNamespace(id=122298, name="Botic van de Zandschulp")],
    )
    player = live_matches._resolve_player("Botic van de Zandschulp")
    assert player == {"id": 122298, "name": "Botic van de Zandschulp"}


# --- _has_started ----------------------------------------------------------

def test_has_started_true_when_commence_time_in_the_past():
    now = datetime(2026, 8, 10, 1, 0, 0, tzinfo=timezone.utc)
    assert live_matches._has_started("2026-08-10T00:22:22Z", now) is True


def test_has_started_false_when_commence_time_in_the_future():
    now = datetime(2026, 8, 10, 1, 0, 0, tzinfo=timezone.utc)
    assert live_matches._has_started("2026-08-10T22:00:00Z", now) is False


def test_has_started_true_when_commence_time_equals_now():
    now = datetime(2026, 8, 10, 1, 0, 0, tzinfo=timezone.utc)
    assert live_matches._has_started("2026-08-10T01:00:00Z", now) is True


def test_has_started_false_when_commence_time_missing():
    assert live_matches._has_started(None, datetime.now(timezone.utc)) is False


def test_has_started_false_when_commence_time_malformed():
    assert live_matches._has_started("no-es-una-fecha", datetime.now(timezone.utc)) is False


# --- _fetch_today_matches: no calcular edge de partidos ya arrancados -----

def _event(event_id, commence_time, home, away):
    return {
        "id": event_id,
        "commence_time": commence_time,
        "home_team": home,
        "away_team": away,
        "bookmakers": [{
            "key": "betsson",
            "markets": [{
                "key": "h2h",
                "outcomes": [
                    {"name": home, "price": 6.25},
                    {"name": away, "price": 1.12},
                ],
            }],
        }],
    }


@pytest.fixture
def patched_live_matches(monkeypatch):
    now = datetime.now(timezone.utc)
    started_event = _event(
        "evt-started", (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "Botic van de Zandschulp", "Jakub Mensik",
    )
    upcoming_event = _event(
        "evt-upcoming", (now + timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "Rafael Jodar", "Arthur Fils",
    )

    players_by_name = {
        "Zandschulp": [SimpleNamespace(id=122298, name="Botic van de Zandschulp")],
        "Mensik": [SimpleNamespace(id=210150, name="Jakub Mensik")],
        "Jodar": [SimpleNamespace(id=900096, name="Rafael Jodar")],
        "Fils": [SimpleNamespace(id=209950, name="Arthur Fils")],
    }

    monkeypatch.setattr(live_matches, "search_players", lambda query, limit=20: players_by_name.get(query, []))
    monkeypatch.setattr(
        live_matches, "predict_match_sync",
        lambda request: SimpleNamespace(
            player1_win_probability=0.3076,
            player2_win_probability=0.6924,
            predicted_winner_name="player2",
        ),
    )
    monkeypatch.setattr(live_matches.odds_client, "get_api_key", lambda: "fake-key")
    monkeypatch.setattr(live_matches.odds_client, "list_active_tennis_sport_keys", lambda api_key: ["tennis_atp_test"])
    monkeypatch.setattr(
        live_matches.odds_client, "get_odds",
        lambda sport_key, api_key: [started_event, upcoming_event],
    )
    monkeypatch.setattr(app_state, "recent_match_counts", {
        122298: 50, 210150: 50,  # Zandschulp / Mensik: muestra normal
        900096: 3, 209950: 40,   # Jodar: poca muestra / Fils: normal
    })
    return now


def test_started_match_gets_no_edge_and_a_note(patched_live_matches):
    response = live_matches._fetch_today_matches()
    started = next(m for m in response.matches if m.event_id == "evt-started")

    assert started.resolved is True  # la predicción del modelo se sigue mostrando
    assert started.book is None
    assert started.player1_edge is None
    assert started.player2_edge is None
    assert started.value_bet_player_name is None
    assert started.suspicious_edge is False
    assert started.note == (
        "Partido en curso o finalizado: cuota en vivo, no comparable con la predicción pre-partido."
    )


def test_upcoming_match_still_gets_edge_computed(patched_live_matches):
    response = live_matches._fetch_today_matches()
    upcoming = next(m for m in response.matches if m.event_id == "evt-upcoming")

    assert upcoming.note is None
    assert upcoming.book == "betsson"
    assert upcoming.player1_edge is not None
    assert upcoming.player2_edge is not None


def test_low_sample_warning_true_when_either_player_below_threshold(patched_live_matches):
    response = live_matches._fetch_today_matches()
    upcoming = next(m for m in response.matches if m.event_id == "evt-upcoming")

    assert upcoming.player1_matches_played == 3  # Jodar
    assert upcoming.player2_matches_played == 40  # Fils
    assert upcoming.player1_low_sample is True
    assert upcoming.player2_low_sample is False
    assert upcoming.low_sample_warning is True


def test_low_sample_warning_false_when_both_players_well_sampled(patched_live_matches):
    response = live_matches._fetch_today_matches()
    started = next(m for m in response.matches if m.event_id == "evt-started")

    assert started.player1_matches_played == 50
    assert started.player2_matches_played == 50
    assert started.low_sample_warning is False
