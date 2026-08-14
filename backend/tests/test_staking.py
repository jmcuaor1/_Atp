"""
Tests para app/services/staking.py — el tamaño de apuesta (Kelly
fraccionado con piso mínimo) que implementa docs/betting_process.md.
"""

import pytest

from app.services import staking


def test_below_threshold_is_excluded():
    decision = staking.compute_stake(
        win_probability=0.549, odds_decimal=2.0, bankroll=1000, low_sample_warning=False
    )
    assert decision.excluded is True
    assert decision.exclusion_reason is not None and "THRESHOLD" in decision.exclusion_reason
    assert decision.stake_amount == 0.0
    assert decision.stake_fraction == 0.0


def test_at_threshold_is_not_excluded():
    decision = staking.compute_stake(
        win_probability=0.55, odds_decimal=2.0, bankroll=1000, low_sample_warning=False
    )
    assert decision.excluded is False
    assert decision.exclusion_reason is None
    # b=1, q=0.45 -> f_kelly = (1*0.55 - 0.45) / 1 = 0.10
    assert decision.kelly_fraction_raw == pytest.approx(0.10)
    assert decision.stake_fraction == pytest.approx(0.10 * staking.KELLY_LAMBDA)
    assert decision.stake_amount == pytest.approx(1000 * 0.10 * staking.KELLY_LAMBDA)


def test_low_sample_warning_excludes_even_with_high_probability():
    decision = staking.compute_stake(
        win_probability=0.9, odds_decimal=1.5, bankroll=1000, low_sample_warning=True
    )
    assert decision.excluded is True
    assert decision.exclusion_reason == "low_sample_warning"
    assert decision.stake_amount == 0.0
    assert decision.stake_fraction == 0.0
    # kelly_fraction_raw se calcula igual, para que la exclusión sea auditable.
    # b=0.5, q=0.1 -> f_kelly = (0.5*0.9 - 0.1) / 0.5 = 0.7
    assert decision.kelly_fraction_raw == pytest.approx(0.7)


def test_negative_kelly_uses_floor_stake():
    # Favorito fuerte pero el mercado ya lo sabe (cuota muy baja): sin
    # edge, f_kelly da negativo grande.
    decision = staking.compute_stake(
        win_probability=0.9, odds_decimal=1.05, bankroll=1000, low_sample_warning=False
    )
    assert decision.excluded is False
    assert decision.kelly_fraction_raw < 0
    assert decision.stake_fraction == pytest.approx(staking.FLOOR_STAKE)
    assert decision.stake_amount == pytest.approx(1000 * staking.FLOOR_STAKE)


def test_large_positive_kelly_exceeds_floor():
    # Edge grande: cuota generosa relativa a la probabilidad del modelo.
    decision = staking.compute_stake(
        win_probability=0.7, odds_decimal=3.0, bankroll=1000, low_sample_warning=False
    )
    # b=2, q=0.3 -> f_kelly = (2*0.7 - 0.3) / 2 = 0.55
    assert decision.kelly_fraction_raw == pytest.approx(0.55)
    expected_fraction = 0.55 * staking.KELLY_LAMBDA
    assert expected_fraction > staking.FLOOR_STAKE
    assert decision.stake_fraction == pytest.approx(expected_fraction)
    assert decision.stake_amount == pytest.approx(1000 * expected_fraction)


def test_odds_of_one_raises_value_error():
    with pytest.raises(ValueError):
        staking.compute_stake(
            win_probability=0.6, odds_decimal=1.0, bankroll=1000, low_sample_warning=False
        )
