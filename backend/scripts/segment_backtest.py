#!/usr/bin/env python3
"""
Fase 6 — Descubrimiento de segmento con edge real.

backtest_odds.py ya responde "¿el modelo le gana al mercado en promedio?"
(no, ROI -11.76%). Este script responde una pregunta más específica:
"¿hay algún subconjunto de partidos (superficie, nivel de torneo, ronda,
brecha de ranking/Elo, favorito vs. underdog, o book específico) donde el
modelo sí tenga edge?"

Metodología (para no confundir ruido de muestra pequeña con edge real):

  1. Split temporal fijo por construcción: 2022-2023 = discovery,
     2024 = confirmation (holdout). El holdout nunca se usa para elegir
     segmentos, solo para confirmar los que ya pasaron el filtro en discovery.
  2. En discovery, se descartan de entrada los segmentos con menos de
     --min-n apuestas: con muestra chica el intervalo de confianza es
     inservible y no vale la pena ni mirarlo.
  3. Los segmentos se rankean por el LÍMITE INFERIOR del intervalo de
     confianza bootstrap del ROI, no por el ROI puntual, para no premiar
     rachas de suerte.
  4. Cada segmento que pasa el filtro se reevalúa tal cual en el holdout
     de 2024. La decisión final (documentada aparte, no en este script)
     solo debe considerar candidatos que sobrevivan ambos períodos.

Uso:
  python scripts/segment_backtest.py
  python scripts/segment_backtest.py --min-n 100 --bootstrap 5000
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

BACKEND_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = BACKEND_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from backtest_odds import (  # noqa: E402
    rebuild_test_set,
    predict_on_test_set,
    load_odds,
    match_predictions_to_odds,
    brier,
)

DISCOVERY_YEARS = (2022, 2023)
CONFIRMATION_YEARS = (2024,)

# book -> (columna cuota ganador, columna cuota perdedor)
BOOKS = {
    "Avg": ("avg_odds_winner", "avg_odds_loser"),
    "Pinnacle": ("PSW", "PSL"),
    "Bet365": ("B365W", "B365L"),
}

DIMENSIONS = [
    "surface", "Series", "Court", "Round",
    "rank_gap_bucket", "odds_bucket", "elo_diff_bucket", "side",
]


def add_segment_columns(matched: pd.DataFrame) -> pd.DataFrame:
    df = matched.copy()
    df["year"] = pd.to_datetime(df["tourney_date"]).dt.year

    df["rank_gap"] = (df["WRank"] - df["LRank"]).abs()
    df["rank_gap_bucket"] = pd.cut(
        df["rank_gap"], bins=[-1, 10, 30, 80, 1_000_000],
        labels=["<10", "10-30", "30-80", "80+"],
    )

    favorite_odds = df[["avg_odds_winner", "avg_odds_loser"]].min(axis=1)
    df["odds_bucket"] = pd.cut(
        favorite_odds, bins=[0, 1.5, 2, 3, 1_000],
        labels=["<1.5", "1.5-2", "2-3", "3+"],
    )

    df["elo_diff_bucket"] = pd.cut(
        df["elo_diff"].abs(), bins=[-1, 50, 150, 300, 1_000_000],
        labels=["<50", "50-150", "150-300", "300+"],
    )
    return df


def implied_probs(row, wcol: str, lcol: str):
    """Probabilidad implícita (con vig) de que p1/p2 ganen, según la cuota
    real ofrecida por ese book, orientando Winner/Loser -> p1/p2 con target."""
    odds_w, odds_l = row[wcol], row[lcol]
    if row["target"] == 1:  # p2 ganó
        return 1 / odds_l, 1 / odds_w  # implied_p1, implied_p2
    return 1 / odds_w, 1 / odds_l


def devig_market_p2(row, wcol: str, lcol: str) -> float:
    implied_p1, implied_p2 = implied_probs(row, wcol, lcol)
    return implied_p2 / (implied_p1 + implied_p2)


def simulate_bets(df: pd.DataFrame, wcol: str, lcol: str) -> pd.DataFrame:
    """Reproduce la regla de apuesta de backtest_odds.py (bet solo si
    model_prob > prob implícita de la cuota ofrecida en ese lado), pero
    devuelve una fila por apuesta colocada con las columnas de segmento
    del partido, para poder agrupar después."""
    usable = df.dropna(subset=[wcol, lcol]).copy()
    bet_rows = []
    for idx, row in usable.iterrows():
        model_p2 = row["model_p2_win_prob"]
        model_p1 = 1 - model_p2
        implied_p1, implied_p2 = implied_probs(row, wcol, lcol)
        odds_w, odds_l = row[wcol], row[lcol]
        actual_p2_won = row["target"] == 1

        sides = []
        if model_p2 > implied_p2:
            odds_bet = odds_w if actual_p2_won else odds_l
            odds_other = odds_l if actual_p2_won else odds_w
            sides.append(("p2", odds_bet, odds_other, actual_p2_won))
        if model_p1 > implied_p1:
            odds_bet = odds_l if actual_p2_won else odds_w
            odds_other = odds_w if actual_p2_won else odds_l
            sides.append(("p1", odds_bet, odds_other, not actual_p2_won))

        for side, odds_bet, odds_other, won in sides:
            bet_rows.append({
                "match_idx": idx,
                "side": "favorite" if odds_bet < odds_other else "underdog",
                "odds": odds_bet,
                "won": won,
                "payout": (odds_bet - 1) if won else -1.0,
                "surface": row["surface"],
                "Series": row.get("Series"),
                "Court": row.get("Court"),
                "Round": row.get("Round"),
                "rank_gap_bucket": row.get("rank_gap_bucket"),
                "odds_bucket": row.get("odds_bucket"),
                "elo_diff_bucket": row.get("elo_diff_bucket"),
                "year": row["year"],
            })
    return pd.DataFrame(bet_rows)


def bootstrap_roi_ci(payouts: np.ndarray, n_boot: int, seed: int = 42):
    if len(payouts) == 0:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    n = len(payouts)
    means = np.empty(n_boot)
    for i in range(n_boot):
        sample = rng.choice(payouts, size=n, replace=True)
        means[i] = sample.mean()
    lo, hi = np.percentile(means, [2.5, 97.5])
    return (float(lo * 100), float(hi * 100))


def score_segments(bets: pd.DataFrame, min_n: int, n_boot: int) -> pd.DataFrame:
    rows = []
    for dim in DIMENSIONS:
        if dim not in bets.columns:
            continue
        for value, group in bets.groupby(dim, observed=True):
            n = len(group)
            payouts = group["payout"].to_numpy()
            roi = float(payouts.mean() * 100) if n else float("nan")
            ci_low, ci_high = bootstrap_roi_ci(payouts, n_boot)
            rows.append({
                "dimension": dim,
                "value": value,
                "n_bets": n,
                "roi_pct": roi,
                "roi_ci_low": ci_low,
                "roi_ci_high": ci_high,
            })
    result = pd.DataFrame(rows)
    result = result[result["n_bets"] >= min_n].sort_values("roi_ci_low", ascending=False)
    return result.reset_index(drop=True)


def confirm_segments(discovery_result: pd.DataFrame, bets_confirmation: pd.DataFrame, n_boot: int) -> pd.DataFrame:
    rows = []
    for _, seg in discovery_result.iterrows():
        dim, value = seg["dimension"], seg["value"]
        group = bets_confirmation[bets_confirmation[dim] == value]
        n = len(group)
        payouts = group["payout"].to_numpy()
        roi = float(payouts.mean() * 100) if n else float("nan")
        ci_low, ci_high = bootstrap_roi_ci(payouts, n_boot) if n else (float("nan"), float("nan"))
        rows.append({
            "dimension": dim,
            "value": value,
            "discovery_n": seg["n_bets"],
            "discovery_roi_pct": seg["roi_pct"],
            "discovery_roi_ci_low": seg["roi_ci_low"],
            "confirmation_n": n,
            "confirmation_roi_pct": roi,
            "confirmation_roi_ci_low": ci_low,
            "confirmation_roi_ci_high": ci_high,
        })
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--min-n", type=int, default=150, help="Mínimo de apuestas en discovery para considerar un segmento (default: 150)")
    parser.add_argument("--bootstrap", type=int, default=2000, help="Iteraciones de bootstrap para el CI de ROI (default: 2000)")
    parser.add_argument("--book", choices=list(BOOKS) + ["all"], default="all", help="Book contra el que simular las apuestas (default: all)")
    args = parser.parse_args()

    print("=== Fase 6: descubrimiento de segmento con edge real ===\n")

    print("1. Reconstruyendo test set + predicciones + cuotas (igual que backtest_odds.py)...")
    test_df = rebuild_test_set()
    predictions = predict_on_test_set(test_df)
    odds = load_odds()
    matched = match_predictions_to_odds(predictions, odds)
    matched = add_segment_columns(matched)
    print(f"   {len(matched)} partidos cruzados con cuotas\n")

    books_to_run = list(BOOKS.items()) if args.book == "all" else [(args.book, BOOKS[args.book])]

    all_discovery = []
    all_confirmation = []

    for book_name, (wcol, lcol) in books_to_run:
        if wcol not in matched.columns:
            print(f"   [{book_name}] columna {wcol} no está en los datos, se salta.")
            continue

        bets = simulate_bets(matched, wcol, lcol)
        if bets.empty:
            print(f"   [{book_name}] no se generó ninguna apuesta EV+, se salta.")
            continue

        bets_discovery = bets[bets["year"].isin(DISCOVERY_YEARS)]
        bets_confirmation = bets[bets["year"].isin(CONFIRMATION_YEARS)]

        print(f"2. [{book_name}] Escaneando segmentos en discovery ({DISCOVERY_YEARS}), "
              f"{len(bets_discovery)} apuestas totales, min_n={args.min_n}...")
        discovery_result = score_segments(bets_discovery, args.min_n, args.bootstrap)
        discovery_result.insert(0, "book", book_name)
        print(f"   {len(discovery_result)} segmentos pasan el filtro de muestra mínima")

        print(f"3. [{book_name}] Confirmando esos segmentos en holdout ({CONFIRMATION_YEARS})...")
        confirmation_result = confirm_segments(discovery_result, bets_confirmation, args.bootstrap)
        confirmation_result.insert(0, "book", book_name)

        all_discovery.append(discovery_result)
        all_confirmation.append(confirmation_result)
        print()

    if not all_discovery:
        print("No se pudo evaluar ningún book. Revisa las columnas de cuotas disponibles.")
        return

    discovery_df = pd.concat(all_discovery, ignore_index=True).sort_values("roi_ci_low", ascending=False)
    confirmation_df = pd.concat(all_confirmation, ignore_index=True)

    out_dir = BACKEND_DIR / "data" / "processed"
    discovery_path = out_dir / "segment_discovery.csv"
    confirmation_path = out_dir / "segment_confirmation.csv"
    discovery_df.to_csv(discovery_path, index=False)
    confirmation_df.to_csv(confirmation_path, index=False)

    pd.set_option("display.width", 140)
    pd.set_option("display.max_rows", 100)

    print("=== Top 20 segmentos en discovery, por límite inferior del CI de ROI ===")
    print(discovery_df.head(20).to_string(index=False))

    print("\n=== Esos mismos segmentos, evaluados en el holdout de 2024 ===")
    merged = confirmation_df.sort_values("discovery_roi_ci_low", ascending=False)
    print(merged.head(20).to_string(index=False))

    print(f"\nGuardado: {discovery_path}")
    print(f"Guardado: {confirmation_path}")


if __name__ == "__main__":
    main()
