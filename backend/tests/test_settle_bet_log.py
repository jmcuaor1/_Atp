"""
Tests para scripts/settle_bet_log.py — liquida bet_log.jsonl (decisiones de
log_bet_decision.py) contra el resultado real del partido y escribe
bankroll_ledger.csv.
"""

import json
import sys
from pathlib import Path

import pandas as pd

BACKEND_DIR = Path(__file__).resolve().parent.parent
for p in (BACKEND_DIR, BACKEND_DIR / "src", BACKEND_DIR / "scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import settle_bet_log  # noqa: E402


def _decision(**overrides):
    row = {
        "match_id": "evt-1::2026-08-14",
        "event_id": "evt-1",
        "predicted_winner_name": "Novak Djokovic",
        "win_probability": 0.7,
        "odds_decimal": 1.8,
        "low_sample_warning": False,
        "excluded": False,
        "exclusion_reason": None,
        "stake_amount": 25.0,
    }
    row.update(overrides)
    return row


def _odds_row(event_id="evt-1", p1_name="Novak Djokovic", p2_name="Carlos Alcaraz",
              sport_key="tennis_atp_wimbledon", commence_time="2026-08-14T12:00:00Z",
              fetched_at="2026-08-14T10:00:00+00:00"):
    return {
        "event_id": event_id, "fetched_at": fetched_at, "sport_key": sport_key,
        "commence_time": commence_time, "p1_name": p1_name, "p2_name": p2_name,
    }


def _score_event(event_id="evt-1", completed=True, home="Novak Djokovic", away="Carlos Alcaraz",
                  home_score="2", away_score="0"):
    return {
        "id": event_id, "completed": completed, "home_team": home, "away_team": away,
        "scores": [{"name": home, "score": home_score}, {"name": away, "score": away_score}],
    }


# --- determine_outcome --------------------------------------------------------

def test_determine_outcome_true_when_predicted_won():
    odds_row = _odds_row()
    assert settle_bet_log.determine_outcome("Novak Djokovic", odds_row, "Novak Djokovic") is True


def test_determine_outcome_false_when_predicted_lost():
    odds_row = _odds_row()
    assert settle_bet_log.determine_outcome("Novak Djokovic", odds_row, "Carlos Alcaraz") is False


def test_determine_outcome_tolerates_accents_and_order():
    odds_row = _odds_row(p1_name="Jose Martinez", p2_name="Carlos Alcaraz")
    assert settle_bet_log.determine_outcome("José Martínez", odds_row, "Jose Martinez") is True


def test_determine_outcome_none_when_predicted_matches_neither_side():
    odds_row = _odds_row()
    assert settle_bet_log.determine_outcome("Nadie De Nadie", odds_row, "Novak Djokovic") is None


# --- build_ledger_row ----------------------------------------------------------

def test_build_ledger_row_win_computes_profit_from_odds():
    decision = _decision(stake_amount=25.0, odds_decimal=1.8)
    row = settle_bet_log.build_ledger_row(decision, "Novak Djokovic", won=True, bankroll_before=1000.0, now="t")
    assert row["profit"] == 20.0  # 25 * (1.8 - 1)
    assert row["bankroll_after"] == 1020.0
    assert row["won"] is True
    assert row["actual_winner_name"] == "Novak Djokovic"


def test_build_ledger_row_loss_forfeits_full_stake():
    decision = _decision(stake_amount=25.0, odds_decimal=1.8)
    row = settle_bet_log.build_ledger_row(decision, "Carlos Alcaraz", won=False, bankroll_before=1000.0, now="t")
    assert row["profit"] == -25.0
    assert row["bankroll_after"] == 975.0


# --- pending_decisions ----------------------------------------------------------

def test_pending_decisions_skips_excluded():
    rows = [_decision(match_id="a", excluded=True), _decision(match_id="b", excluded=False)]
    pending = settle_bet_log.pending_decisions(rows, already_settled_ids=set())
    assert [r["match_id"] for r in pending] == ["b"]


def test_pending_decisions_skips_already_settled():
    rows = [_decision(match_id="a"), _decision(match_id="b")]
    pending = settle_bet_log.pending_decisions(rows, already_settled_ids={"a"})
    assert [r["match_id"] for r in pending] == ["b"]


# --- load_ledger / append_ledger_rows -------------------------------------------

def test_load_ledger_missing_file_returns_empty_with_columns(tmp_path):
    df = settle_bet_log.load_ledger(tmp_path / "nope.csv")
    assert df.empty
    assert list(df.columns) == settle_bet_log.LEDGER_COLUMNS


def test_append_ledger_rows_writes_header_once(tmp_path):
    path = tmp_path / "bankroll_ledger.csv"
    row = settle_bet_log.build_ledger_row(_decision(), "Novak Djokovic", won=True, bankroll_before=1000.0, now="t")
    settle_bet_log.append_ledger_rows(path, [row])
    settle_bet_log.append_ledger_rows(path, [{**row, "match_id": "evt-2::2026-08-14"}])
    df = pd.read_csv(path)
    assert len(df) == 2
    assert list(df.columns) == settle_bet_log.LEDGER_COLUMNS


# --- main end-to-end -------------------------------------------------------------

def test_main_end_to_end_settles_and_updates_bankroll(monkeypatch, tmp_path):
    bet_log_path = tmp_path / "bet_log.jsonl"
    odds_log_path = tmp_path / "live_odds_log.jsonl"
    ledger_path = tmp_path / "bankroll_ledger.csv"

    decisions = [
        _decision(match_id="evt-1::2026-08-14", event_id="evt-1", predicted_winner_name="Novak Djokovic",
                  stake_amount=25.0, odds_decimal=1.8),
        _decision(match_id="evt-2::2026-08-14", event_id="evt-2", predicted_winner_name="Jannik Sinner",
                  stake_amount=10.0, odds_decimal=1.4),
    ]
    bet_log_path.write_text("\n".join(json.dumps(d) for d in decisions) + "\n", encoding="utf-8")

    odds_rows = [
        _odds_row(event_id="evt-1", p1_name="Novak Djokovic", p2_name="Carlos Alcaraz",
                  commence_time="2026-08-14T12:00:00Z"),
        _odds_row(event_id="evt-2", p1_name="Jannik Sinner", p2_name="Daniil Medvedev",
                  sport_key="tennis_atp_wimbledon", commence_time="2026-08-14T09:00:00Z"),
    ]
    odds_log_path.write_text("\n".join(json.dumps(r) for r in odds_rows) + "\n", encoding="utf-8")

    monkeypatch.setattr(settle_bet_log, "BET_LOG_PATH", bet_log_path)
    monkeypatch.setattr(settle_bet_log, "ODDS_LOG_PATH", odds_log_path)
    monkeypatch.setattr(settle_bet_log, "BANKROLL_LEDGER_PATH", ledger_path)
    monkeypatch.setattr(settle_bet_log.odds_client, "get_api_key", lambda: "fake-key")

    def fake_get_scores(sport_key, api_key):
        return [
            _score_event(event_id="evt-1", home="Novak Djokovic", away="Carlos Alcaraz",
                         home_score="2", away_score="0"),  # Djokovic (predicho) gana
            _score_event(event_id="evt-2", home="Jannik Sinner", away="Daniil Medvedev",
                         home_score="0", away_score="2"),  # Sinner (predicho) pierde
        ]

    monkeypatch.setattr(settle_bet_log.odds_client, "get_scores", fake_get_scores)

    settle_bet_log.main()

    df = pd.read_csv(ledger_path)
    assert len(df) == 2
    # se liquida en orden de commence_time: evt-2 (09:00) antes que evt-1 (12:00)
    assert list(df["event_id"]) == ["evt-2", "evt-1"]
    assert df.iloc[0]["won"] == False  # noqa: E712 (viene de CSV como bool numpy)
    # banca: 1000 - 10 (evt-2 pierde) = 990; luego 990 + 25*0.8 = 1010 (evt-1 gana)
    assert df.iloc[0]["bankroll_after"] == 990.0
    assert df.iloc[1]["bankroll_after"] == 1010.0


def test_main_is_idempotent_does_not_resettle(monkeypatch, tmp_path):
    bet_log_path = tmp_path / "bet_log.jsonl"
    odds_log_path = tmp_path / "live_odds_log.jsonl"
    ledger_path = tmp_path / "bankroll_ledger.csv"

    decision = _decision(match_id="evt-1::2026-08-14", event_id="evt-1")
    bet_log_path.write_text(json.dumps(decision) + "\n", encoding="utf-8")
    odds_log_path.write_text(json.dumps(_odds_row(event_id="evt-1")) + "\n", encoding="utf-8")

    monkeypatch.setattr(settle_bet_log, "BET_LOG_PATH", bet_log_path)
    monkeypatch.setattr(settle_bet_log, "ODDS_LOG_PATH", odds_log_path)
    monkeypatch.setattr(settle_bet_log, "BANKROLL_LEDGER_PATH", ledger_path)
    monkeypatch.setattr(settle_bet_log.odds_client, "get_api_key", lambda: "fake-key")
    monkeypatch.setattr(
        settle_bet_log.odds_client, "get_scores",
        lambda sport_key, api_key: [_score_event(event_id="evt-1")],
    )

    settle_bet_log.main()
    settle_bet_log.main()

    df = pd.read_csv(ledger_path)
    assert len(df) == 1


def test_main_no_bet_log_prints_message_and_returns(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(settle_bet_log, "BET_LOG_PATH", tmp_path / "nope.jsonl")
    monkeypatch.setattr(settle_bet_log.odds_client, "get_api_key", lambda: "fake-key")
    settle_bet_log.main()
    assert "Corré log_bet_decision.py primero" in capsys.readouterr().out


def test_main_skips_bets_with_no_result_yet(monkeypatch, tmp_path, capsys):
    bet_log_path = tmp_path / "bet_log.jsonl"
    odds_log_path = tmp_path / "live_odds_log.jsonl"
    ledger_path = tmp_path / "bankroll_ledger.csv"

    bet_log_path.write_text(json.dumps(_decision(match_id="evt-1::2026-08-14", event_id="evt-1")) + "\n", encoding="utf-8")
    odds_log_path.write_text(json.dumps(_odds_row(event_id="evt-1")) + "\n", encoding="utf-8")

    monkeypatch.setattr(settle_bet_log, "BET_LOG_PATH", bet_log_path)
    monkeypatch.setattr(settle_bet_log, "ODDS_LOG_PATH", odds_log_path)
    monkeypatch.setattr(settle_bet_log, "BANKROLL_LEDGER_PATH", ledger_path)
    monkeypatch.setattr(settle_bet_log.odds_client, "get_api_key", lambda: "fake-key")
    monkeypatch.setattr(
        settle_bet_log.odds_client, "get_scores",
        lambda sport_key, api_key: [_score_event(event_id="evt-1", completed=False)],
    )

    settle_bet_log.main()
    assert not ledger_path.exists()
    assert "Ninguno de los partidos pendientes tiene resultado todavía" in capsys.readouterr().out
