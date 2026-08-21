"""
Tests para scripts/log_bet_decision.py — el script de producción que
persiste una decisión de stake por partido en bet_log.jsonl, a diferencia
de preview_stakes.py (dry-run de solo lectura).
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
for p in (BACKEND_DIR, BACKEND_DIR / "scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import log_bet_decision  # noqa: E402


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


NOW = datetime(2026, 8, 14, 12, 0, 0, tzinfo=timezone.utc)
DECISION_DATE = "2026-08-14"


# --- normalización de nombres ------------------------------------------------

def testnames_match_ignores_accents():
    assert log_bet_decision.names_match("José Martínez", "Jose Martinez") is True


def testnames_match_ignores_extra_whitespace():
    assert log_bet_decision.names_match("Novak   Djokovic", "  Novak Djokovic  ") is True


def testnames_match_handles_apellido_coma_nombre_order():
    assert log_bet_decision.names_match("Djokovic, Novak", "Novak Djokovic") is True


def testnames_match_handles_reversed_order_without_comma():
    assert log_bet_decision.names_match("Djokovic Novak", "Novak Djokovic") is True


def testnames_match_false_for_none():
    assert log_bet_decision.names_match(None, "Novak Djokovic") is False


def testnames_match_false_for_genuinely_different_names():
    assert log_bet_decision.names_match("Novak Djokovic", "Carlos Alcaraz") is False


# --- odds_for_predicted_winner endurecido ------------------------------------

def test_odds_for_predicted_winner_matches_after_normalization():
    odds_row = _odds_row(p1_name="Jose Martinez", p2_name="Carlos Alcaraz")
    odds_decimal = log_bet_decision._odds_for_predicted_winner("José Martínez", odds_row)
    assert odds_decimal == 1.8


def test_odds_for_predicted_winner_none_when_still_no_match():
    odds_row = _odds_row(p1_name="Novak Djokovic", p2_name="Carlos Alcaraz")
    assert log_bet_decision._odds_for_predicted_winner("Otro Jugador Totalmente Distinto", odds_row) is None


# --- build_bet_decision_row: name_mismatch real (no matchea ni normalizado) --

def test_build_row_name_mismatch_against_odds_log_is_logged_not_skipped():
    match = _match()
    odds_snapshot = {"evt-1": _odds_row(p1_name="Otro Nombre", p2_name="Y Otro Mas")}
    row = log_bet_decision.build_bet_decision_row(match, odds_snapshot, bankroll=1000, now=NOW, decision_date=DECISION_DATE)
    assert row["excluded"] is True
    assert row["exclusion_reason"] == "name_mismatch"
    assert row["predicted_winner_raw"] == "Novak Djokovic"
    assert row["odds_names_raw"] == ["Otro Nombre", "Y Otro Mas"]
    # el partido queda registrado, no se omite silenciosamente:
    assert row["match_id"] == "evt-1::2026-08-14"


def test_build_row_name_mismatch_within_matches_today_itself():
    match = _match(predicted_winner_name="Nombre Que No Matchea A Nadie")
    row = log_bet_decision.build_bet_decision_row(match, odds_snapshot={}, bankroll=1000, now=NOW, decision_date=DECISION_DATE)
    assert row["excluded"] is True
    assert row["exclusion_reason"] == "name_mismatch"
    assert row["odds_names_raw"] == ["Novak Djokovic", "Carlos Alcaraz"]


# --- build_bet_decision_row: otras exclusiones -------------------------------

def test_build_row_no_odds_available():
    match = _match()
    row = log_bet_decision.build_bet_decision_row(match, odds_snapshot={}, bankroll=1000, now=NOW, decision_date=DECISION_DATE)
    assert row["excluded"] is True
    assert row["exclusion_reason"] == "no_odds_available"
    assert row["predicted_winner_raw"] is None
    assert row["odds_names_raw"] is None


def test_build_row_excluded_by_threshold():
    match = _match(predicted_winner_name="Carlos Alcaraz", player1_win_probability=0.6, player2_win_probability=0.4)
    odds_snapshot = {"evt-1": _odds_row()}
    row = log_bet_decision.build_bet_decision_row(match, odds_snapshot, bankroll=1000, now=NOW, decision_date=DECISION_DATE)
    assert row["excluded"] is True
    assert row["exclusion_reason"] == "threshold"


def test_build_row_excluded_by_low_sample_warning():
    match = _match(low_sample_warning=True)
    odds_snapshot = {"evt-1": _odds_row()}
    row = log_bet_decision.build_bet_decision_row(match, odds_snapshot, bankroll=1000, now=NOW, decision_date=DECISION_DATE)
    assert row["excluded"] is True
    assert row["exclusion_reason"] == "low_sample_warning"


def test_build_row_invalid_odds_marked_as_error_not_raised():
    match = _match()
    odds_snapshot = {"evt-1": _odds_row(odds_p1=1.0)}
    row = log_bet_decision.build_bet_decision_row(match, odds_snapshot, bankroll=1000, now=NOW, decision_date=DECISION_DATE)
    assert row["excluded"] is True
    assert row["exclusion_reason"].startswith("error:")


# --- flujo normal (no excluido) ----------------------------------------------

def test_build_row_normal_match_is_not_excluded():
    match = _match()
    odds_snapshot = {"evt-1": _odds_row()}
    row = log_bet_decision.build_bet_decision_row(match, odds_snapshot, bankroll=1000, now=NOW, decision_date=DECISION_DATE)
    assert row["excluded"] is False
    assert row["exclusion_reason"] is None
    assert row["odds_decimal"] == 1.8
    assert row["stake_amount"] > 0
    assert row["predicted_winner_raw"] is None
    assert row["odds_names_raw"] is None


# --- read_current_bankroll ----------------------------------------------------

def test_read_current_bankroll_defaults_when_no_ledger(tmp_path):
    bankroll = log_bet_decision.read_current_bankroll(tmp_path / "nope.csv", default=1000.0)
    assert bankroll == 1000.0


def test_read_current_bankroll_reads_last_row(tmp_path):
    ledger_path = tmp_path / "bankroll_ledger.csv"
    ledger_path.write_text("timestamp,bankroll_after\n2026-08-10T00:00:00Z,1000\n2026-08-12T00:00:00Z,1123.45\n", encoding="utf-8")
    bankroll = log_bet_decision.read_current_bankroll(ledger_path, default=1000.0)
    assert bankroll == pytest.approx(1123.45)


# --- idempotencia por match_id ------------------------------------------------

def test_load_existing_match_ids_reads_bet_log(tmp_path):
    bet_log_path = tmp_path / "bet_log.jsonl"
    bet_log_path.write_text(json.dumps({"match_id": "evt-1::2026-08-14"}) + "\n", encoding="utf-8")
    assert log_bet_decision.load_existing_match_ids(bet_log_path) == {"evt-1::2026-08-14"}


def test_load_existing_match_ids_missing_file_returns_empty(tmp_path):
    assert log_bet_decision.load_existing_match_ids(tmp_path / "nope.jsonl") == set()


def test_main_running_twice_same_day_does_not_duplicate_lines(monkeypatch, tmp_path):
    bet_log_path = tmp_path / "bet_log.jsonl"
    odds_log_path = tmp_path / "live_odds_log.jsonl"
    odds_log_path.write_text(json.dumps(_odds_row()) + "\n", encoding="utf-8")
    ledger_path = tmp_path / "bankroll_ledger.csv"

    monkeypatch.setattr(log_bet_decision, "BET_LOG_PATH", bet_log_path)
    monkeypatch.setattr(log_bet_decision, "ODDS_LOG_PATH", odds_log_path)
    monkeypatch.setattr(log_bet_decision, "BANKROLL_LEDGER_PATH", ledger_path)

    def fake_get(url, timeout=None):
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"matches": [_match()]})

    monkeypatch.setattr(log_bet_decision.httpx, "get", fake_get)

    log_bet_decision.main()
    log_bet_decision.main()

    lines = [line for line in bet_log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 1
    assert json.loads(lines[0])["match_id"] == f"evt-1::{datetime.now(timezone.utc).date().isoformat()}"


# --- flujo normal end-to-end con varios partidos -----------------------------

def test_main_end_to_end_writes_one_line_per_match(monkeypatch, tmp_path):
    bet_log_path = tmp_path / "bet_log.jsonl"
    odds_log_path = tmp_path / "live_odds_log.jsonl"
    ledger_path = tmp_path / "bankroll_ledger.csv"

    matches = [
        _match(event_id="evt-1"),
        _match(
            event_id="evt-2",
            player1_name="Jannik Sinner", player2_name="Daniil Medvedev",
            predicted_winner_name="Jannik Sinner",
            player1_win_probability=0.6, player2_win_probability=0.4,
        ),
        _match(
            event_id="evt-3",
            player1_name="Andrey Rublev", player2_name="Casper Ruud",
            predicted_winner_name="Andrey Rublev",
            player1_win_probability=0.52, player2_win_probability=0.48,
            low_sample_warning=True,
        ),
    ]
    odds_rows = [
        _odds_row(event_id="evt-1"),
        _odds_row(event_id="evt-2", p1_name="Jannik Sinner", p2_name="Daniil Medvedev", odds_p1=1.4, odds_p2=3.0),
        # evt-3 sin cuota en el log a propósito
    ]
    odds_log_path.write_text("\n".join(json.dumps(r) for r in odds_rows) + "\n", encoding="utf-8")

    monkeypatch.setattr(log_bet_decision, "BET_LOG_PATH", bet_log_path)
    monkeypatch.setattr(log_bet_decision, "ODDS_LOG_PATH", odds_log_path)
    monkeypatch.setattr(log_bet_decision, "BANKROLL_LEDGER_PATH", ledger_path)

    def fake_get(url, timeout=None):
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"matches": matches})

    monkeypatch.setattr(log_bet_decision.httpx, "get", fake_get)

    log_bet_decision.main()

    lines = [json.loads(line) for line in bet_log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 3
    by_event = {row["event_id"]: row for row in lines}
    assert by_event["evt-1"]["excluded"] is False
    assert by_event["evt-2"]["excluded"] is False
    assert by_event["evt-3"]["excluded"] is True
    assert by_event["evt-3"]["exclusion_reason"] == "no_odds_available"
