"""
Tests para scripts/preview_stakes.py — el dry-run de solo lectura que
previsualiza qué stake daría compute_stake() para los partidos de hoy,
sin escribir ningún archivo.
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
for p in (BACKEND_DIR, BACKEND_DIR / "scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import preview_stakes  # noqa: E402


def _match(**overrides):
    match = {
        "event_id": "evt-1",
        "player1_name": "Novak Djokovic",
        "player2_name": "Carlos Alcaraz",
        "player1_win_probability": 0.7,
        "player2_win_probability": 0.3,
        "predicted_winner_name": "Novak Djokovic",
        "low_sample_warning": False,
    }
    match.update(overrides)
    return match


def _odds_row(event_id="evt-1", p1_name="Novak Djokovic", p2_name="Carlos Alcaraz", odds_p1=1.8, odds_p2=2.0, fetched_at="2026-08-14T10:00:00+00:00"):
    return {
        "event_id": event_id,
        "fetched_at": fetched_at,
        "p1_name": p1_name,
        "p2_name": p2_name,
        "odds_p1": odds_p1,
        "odds_p2": odds_p2,
    }


# --- load_latest_odds_snapshot ---------------------------------------------

def test_load_latest_odds_snapshot_missing_file_returns_empty(tmp_path):
    assert preview_stakes.load_latest_odds_snapshot(tmp_path / "nope.jsonl") == {}


def test_load_latest_odds_snapshot_keeps_most_recent_row_per_event(tmp_path):
    log_path = tmp_path / "live_odds_log.jsonl"
    older = _odds_row(odds_p1=1.5, fetched_at="2026-08-14T06:00:00+00:00")
    newer = _odds_row(odds_p1=1.8, fetched_at="2026-08-14T12:00:00+00:00")
    log_path.write_text(
        json.dumps(older) + "\n" + json.dumps(newer) + "\n", encoding="utf-8"
    )
    snapshot = preview_stakes.load_latest_odds_snapshot(log_path)
    assert snapshot["evt-1"]["odds_p1"] == 1.8


# --- odds_for_predicted_winner ----------------------------------------------

def test_odds_for_predicted_winner_matches_p1():
    assert preview_stakes.odds_for_predicted_winner("Novak Djokovic", _odds_row()) == 1.8


def test_odds_for_predicted_winner_matches_p2():
    assert preview_stakes.odds_for_predicted_winner("Carlos Alcaraz", _odds_row()) == 2.0


def test_odds_for_predicted_winner_none_without_snapshot():
    assert preview_stakes.odds_for_predicted_winner("Novak Djokovic", None) is None


def test_odds_for_predicted_winner_none_when_name_does_not_match():
    assert preview_stakes.odds_for_predicted_winner("Otro Jugador", _odds_row()) is None


# --- build_preview_row + summarize: los 3 escenarios pedidos ---------------

def test_build_preview_row_normal_match_is_not_excluded():
    match = _match()
    odds_snapshot = {"evt-1": _odds_row()}
    row = preview_stakes.build_preview_row(match, odds_snapshot, bankroll=1000)
    assert row["excluded"] is False
    assert row["odds_decimal"] == 1.8
    assert row["stake_amount"] is not None and row["stake_amount"] > 0


def test_build_preview_row_excluded_by_threshold():
    match = _match(
        predicted_winner_name="Carlos Alcaraz",
        player1_win_probability=0.6,
        player2_win_probability=0.4,
    )
    odds_snapshot = {"evt-1": _odds_row()}
    row = preview_stakes.build_preview_row(match, odds_snapshot, bankroll=1000)
    assert row["excluded"] is True
    assert "THRESHOLD" in row["exclusion_reason"]


def test_build_preview_row_excluded_by_low_sample():
    match = _match(low_sample_warning=True)
    odds_snapshot = {"evt-1": _odds_row()}
    row = preview_stakes.build_preview_row(match, odds_snapshot, bankroll=1000)
    assert row["excluded"] is True
    assert row["exclusion_reason"] == "low_sample_warning"


def test_build_preview_row_no_odds_snapshot_is_excluded_without_inventing_a_value():
    match = _match(event_id="evt-sin-cuota")
    row = preview_stakes.build_preview_row(match, odds_snapshot={}, bankroll=1000)
    assert row["excluded"] is True
    assert row["exclusion_reason"] == preview_stakes.NO_ODDS_REASON
    assert row["odds_decimal"] is None
    assert row["stake_amount"] is None


def test_build_preview_row_no_prediction_does_not_crash():
    match = _match(predicted_winner_name=None, player1_win_probability=None, player2_win_probability=None)
    row = preview_stakes.build_preview_row(match, odds_snapshot={}, bankroll=1000)
    assert row["excluded"] is True
    assert row["exclusion_reason"] == preview_stakes.NO_PREDICTION_REASON


def test_build_preview_row_invalid_odds_marked_as_error_not_raised():
    match = _match()
    odds_snapshot = {"evt-1": _odds_row(odds_p1=1.0)}
    row = preview_stakes.build_preview_row(match, odds_snapshot, bankroll=1000)
    assert row["excluded"] is True
    assert row["exclusion_reason"].startswith("error:")


def test_summarize_counts_each_category_correctly():
    normal = preview_stakes.build_preview_row(_match(), {"evt-1": _odds_row()}, bankroll=1000)
    by_threshold = preview_stakes.build_preview_row(
        _match(predicted_winner_name="Carlos Alcaraz", player1_win_probability=0.6, player2_win_probability=0.4),
        {"evt-1": _odds_row()}, bankroll=1000,
    )
    by_low_sample = preview_stakes.build_preview_row(
        _match(low_sample_warning=True), {"evt-1": _odds_row()}, bankroll=1000,
    )
    no_odds = preview_stakes.build_preview_row(_match(event_id="evt-2"), odds_snapshot={}, bankroll=1000)

    summary = preview_stakes.summarize([normal, by_threshold, by_low_sample, no_odds])
    assert summary["total"] == 4
    assert summary["passed"] == 1
    assert summary["excluded"] == 3
    assert summary["by_reason"]["threshold"] == 1
    assert summary["by_reason"]["low_sample_warning"] == 1
    assert summary["by_reason"][preview_stakes.NO_ODDS_REASON] == 1
    assert summary["by_reason"]["otros"] == 0


# --- fetch_today_matches: mock de red, mismo patrón que test_live_odds.py --

def test_fetch_today_matches_calls_matches_today_endpoint(monkeypatch):
    def fake_get(url, timeout=None):
        assert url.endswith("/matches/today")
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"matches": [_match()]},
        )

    monkeypatch.setattr(preview_stakes.httpx, "get", fake_get)
    matches = preview_stakes.fetch_today_matches()
    assert matches == [_match()]


# --- garantía de solo lectura ------------------------------------------------

def test_main_does_not_write_any_file(monkeypatch, tmp_path, capsys):
    log_path = tmp_path / "live_odds_log.jsonl"
    log_path.write_text(json.dumps(_odds_row()) + "\n", encoding="utf-8")
    monkeypatch.setattr(preview_stakes, "LOG_PATH", log_path)

    def fake_get(url, timeout=None):
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"matches": [_match()]},
        )

    monkeypatch.setattr(preview_stakes.httpx, "get", fake_get)
    monkeypatch.setattr(sys, "argv", ["preview_stakes.py"])

    files_before = set(tmp_path.iterdir())
    preview_stakes.main()
    files_after = set(tmp_path.iterdir())

    assert files_before == files_after  # no se creó ni modificó ningún archivo
    out = capsys.readouterr().out
    assert "Novak Djokovic" in out
