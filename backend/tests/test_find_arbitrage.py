"""
Tests para scripts/find_arbitrage.py (arbitraje entre casas).

Todo con fixtures a mano, sin red real ni ODDS_API_KEY.
"""

import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
for p in (BACKEND_DIR / "src", BACKEND_DIR / "scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import find_arbitrage  # noqa: E402


def _event(**overrides):
    event = {
        "id": "evt-1",
        "home_team": "Novak Djokovic",
        "away_team": "Carlos Alcaraz",
        "bookmakers": [
            {
                "key": "pinnacle",
                "markets": [{
                    "key": "h2h",
                    "outcomes": [
                        {"name": "Novak Djokovic", "price": 1.90},
                        {"name": "Carlos Alcaraz", "price": 1.90},
                    ],
                }],
            },
            {
                "key": "coral",
                "markets": [{
                    "key": "h2h",
                    "outcomes": [
                        {"name": "Novak Djokovic", "price": 2.10},
                        {"name": "Carlos Alcaraz", "price": 1.80},
                    ],
                }],
            },
        ],
    }
    event.update(overrides)
    return event


class TestFindBestOddsPerOutcome:
    def test_picks_highest_price_across_books(self):
        best = find_arbitrage.find_best_odds_per_outcome(_event())
        assert best["Novak Djokovic"] == (2.10, "coral")
        assert best["Carlos Alcaraz"] == (1.90, "pinnacle")

    def test_excludes_exchanges_by_default(self):
        event = _event(bookmakers=_event()["bookmakers"] + [{
            "key": "betfair_ex_uk",
            "markets": [{
                "key": "h2h",
                "outcomes": [
                    {"name": "Novak Djokovic", "price": 5.0},  # mejor cuota cruda, pero es exchange
                    {"name": "Carlos Alcaraz", "price": 1.1},
                ],
            }],
        }])
        best = find_arbitrage.find_best_odds_per_outcome(event)
        assert best["Novak Djokovic"] == (2.10, "coral")  # no la cuota cruda de 5.0 del exchange

    def test_includes_exchanges_net_of_commission_when_flagged(self):
        event = _event(bookmakers=[{
            "key": "betfair_ex_uk",
            "markets": [{
                "key": "h2h",
                "outcomes": [{"name": "Novak Djokovic", "price": 3.0}],
            }],
        }])
        best = find_arbitrage.find_best_odds_per_outcome(event, include_exchanges=True)
        # Ganancia bruta (3.0 - 1) * (1 - comisión) + 1, no la cuota cruda de 3.0
        expected = 1 + (3.0 - 1) * (1 - find_arbitrage.EXCHANGE_COMMISSION_PCT / 100)
        assert best["Novak Djokovic"] == pytest.approx((expected, "betfair_ex_uk"))
        assert best["Novak Djokovic"][0] < 3.0


class TestFindArbitrageInEvent:
    def test_detects_arbitrage_when_implied_sum_below_one(self):
        # Mejores cuotas cruzando books: Djokovic 2.10 (coral), Alcaraz 1.90 (pinnacle)
        # implied_sum = 1/2.10 + 1/1.90 = 0.476 + 0.526 = 1.002 -> NO hay arb con estos números.
        # Se ajusta el fixture para que sí lo haya.
        event = _event(bookmakers=[
            {"key": "pinnacle", "markets": [{"key": "h2h", "outcomes": [
                {"name": "Novak Djokovic", "price": 1.80},
                {"name": "Carlos Alcaraz", "price": 2.05},
            ]}]},
            {"key": "coral", "markets": [{"key": "h2h", "outcomes": [
                {"name": "Novak Djokovic", "price": 2.20},
                {"name": "Carlos Alcaraz", "price": 1.85},
            ]}]},
        ])
        opp = find_arbitrage.find_arbitrage_in_event(event)
        assert opp is not None
        assert opp["odds_home"] == 2.20 and opp["book_home"] == "coral"
        assert opp["odds_away"] == 2.05 and opp["book_away"] == "pinnacle"
        assert opp["guaranteed_margin_pct"] > 0
        assert opp["stake_home_pct"] + opp["stake_away_pct"] == pytest.approx(100.0)

    def test_returns_none_when_no_arbitrage(self):
        # Mismo book en ambos lados, con margen normal de casa (implied_sum > 1)
        event = _event(bookmakers=[
            {"key": "pinnacle", "markets": [{"key": "h2h", "outcomes": [
                {"name": "Novak Djokovic", "price": 1.90},
                {"name": "Carlos Alcaraz", "price": 1.90},
            ]}]},
        ])
        assert find_arbitrage.find_arbitrage_in_event(event) is None

    def test_returns_none_when_outcome_missing(self):
        event = _event(bookmakers=[
            {"key": "pinnacle", "markets": [{"key": "h2h", "outcomes": [
                {"name": "Novak Djokovic", "price": 2.5},
            ]}]},
        ])
        assert find_arbitrage.find_arbitrage_in_event(event) is None


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
