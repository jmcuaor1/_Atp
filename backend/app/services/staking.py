"""
Tamaño de apuesta para la capa de disciplina de apostador profesional
(ver docs/betting_process.md). No decide A QUIÉN apostar — eso ya lo
resuelve win_probability / predicted_winner_name aguas arriba — sino
CUÁNTO apostar y si corresponde excluir el partido.
"""

from __future__ import annotations

from dataclasses import dataclass

# Umbral mínimo de win_probability para apostar. Rango acordado 55%-60%
# en docs/betting_process.md; este valor puntual es el que usa el código.
THRESHOLD = 0.55

# Kelly fraccionado (cuarto de Kelly), no Kelly puro: amortigua la
# varianza de una fórmula que asume que win_probability es exacta,
# cuando en realidad es una estimación del modelo.
KELLY_LAMBDA = 0.25

# Piso de stake cuando se apuesta al predicted_winner sin edge de mercado
# (f_kelly <= 0). Existe porque la regla de negocio es apostar siempre al
# jugador con mayor win_probability, no solo cuando hay edge — a
# diferencia de Kelly puro, que en ese caso daría stake 0 o negativo.
FLOOR_STAKE = 0.01


@dataclass(frozen=True)
class StakeDecision:
    stake_amount: float
    stake_fraction: float
    kelly_fraction_raw: float
    excluded: bool
    exclusion_reason: str | None


def compute_stake(
    win_probability: float,
    odds_decimal: float,
    bankroll: float,
    low_sample_warning: bool,
) -> StakeDecision:
    """
    Calcula el stake para apostar al predicted_winner combinando Kelly
    fraccionado con un piso mínimo.

    Kelly puro (f = (b*p - q) / b) da stake 0 o negativo cuando no hay
    edge sobre la cuota de mercado. Acá no: la regla de negocio (ver
    docs/betting_process.md) es apostar siempre al jugador con mayor
    win_probability, tenga o no edge de mercado. Por eso, cuando
    f_kelly * KELLY_LAMBDA cae por debajo de FLOOR_STAKE (incluido
    negativo), se usa FLOOR_STAKE en su lugar.

    kelly_fraction_raw se calcula siempre (incluso si el partido termina
    excluido) para que la exclusión sea auditable: permite ver, por
    ejemplo, que un partido con buen edge igual quedó afuera por
    low_sample_warning.

    La exclusión por low_sample_warning tiene prioridad sobre cualquier
    win_probability, por alta que sea: no hay stake reducido para esos
    casos, van directo a excluded=True.

    Raises:
        ValueError: si odds_decimal <= 1 (cuota decimal inválida; con
            b = odds_decimal - 1 <= 0 la fórmula de Kelly divide por
            cero o pierde sentido).
    """
    if odds_decimal <= 1:
        raise ValueError(
            f"odds_decimal debe ser > 1 (cuota decimal válida); recibido {odds_decimal!r}"
        )

    b = odds_decimal - 1
    q = 1 - win_probability
    f_kelly = (b * win_probability - q) / b

    if low_sample_warning:
        return StakeDecision(
            stake_amount=0.0,
            stake_fraction=0.0,
            kelly_fraction_raw=f_kelly,
            excluded=True,
            exclusion_reason="low_sample_warning",
        )

    if win_probability < THRESHOLD:
        return StakeDecision(
            stake_amount=0.0,
            stake_fraction=0.0,
            kelly_fraction_raw=f_kelly,
            excluded=True,
            exclusion_reason=f"win_probability {win_probability:.4f} < THRESHOLD {THRESHOLD}",
        )

    stake_fraction = max(f_kelly * KELLY_LAMBDA, FLOOR_STAKE)
    stake_amount = stake_fraction * bankroll

    return StakeDecision(
        stake_amount=stake_amount,
        stake_fraction=stake_fraction,
        kelly_fraction_raw=f_kelly,
        excluded=False,
        exclusion_reason=None,
    )
