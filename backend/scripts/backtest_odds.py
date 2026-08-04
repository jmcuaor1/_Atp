#!/usr/bin/env python3
"""
Backtest: compara las probabilidades calibradas del modelo contra las
cuotas históricas de tennis-data.co.uk, para el mismo período del test set.

Responde la pregunta real del proyecto: no "¿el modelo es preciso?" sino
"¿el modelo tiene edge contra el mercado, una vez quitado el margen del
bookmaker (vig)?".

Uso:
  python scripts/backtest_odds.py
"""

from __future__ import annotations

import glob
import os
import re
import sys
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd
import joblib

BACKEND_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BACKEND_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from features import prepare_features_for_training, symmetrize_dataset  # noqa: E402

MIN_YEAR = 2010  # debe coincidir con model.py para reconstruir el mismo split
ODDS_DIR = BACKEND_DIR / "data" / "odds"
RAW_DIR = BACKEND_DIR / "data" / "raw"
MODEL_PATH = BACKEND_DIR / "models" / "tennis_model.pkl"
DATE_TOLERANCE_DAYS = 2  # tolerancia por husos horarios / fecha de inicio de torneo


def strip_accents(text: str) -> str:
    """'muñoz' -> 'munoz', para que coincida con grafías sin tilde/ñ."""
    return "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    )


def normalize_full_name(full_name: str) -> tuple[str, str]:
    """
    'Novak Djokovic' -> ('djokovic', 'n')
    'Alex De Minaur' -> ('deminaur', 'a')  (apellido compuesto: todo menos el
    primer nombre; tennis-data.co.uk lo trata igual, ver normalize_odds_name)
    """
    parts = str(full_name).strip().split()
    if not parts:
        return ("", "")
    last = strip_accents("".join(parts[1:]).lower()) if len(parts) > 1 else strip_accents(parts[0].lower())
    last = re.sub(r"[^a-z]", "", last)
    first_initial = strip_accents(parts[0][0].lower()) if parts[0] else ""
    return (last, first_initial)


def normalize_odds_name(odds_name: str) -> tuple[str, str]:
    """'Djokovic N.' -> ('djokovic', 'n'). Soporta apellidos compuestos ('De Minaur A.')."""
    name = strip_accents(str(odds_name).strip())
    m = re.match(r"^(.+?)\s+([A-Za-z])\.?$", name)
    if not m:
        return (re.sub(r"[^a-z]", "", name.lower()), "")
    last, initial = m.groups()
    last = re.sub(r"[^a-z]", "", last.lower())
    return (last, initial.lower())


def rebuild_test_set():
    """Reconstruye match_test EXACTAMENTE como lo hace model.py, para poder
    cruzarlo con metadata de jugador/fecha que train_tennis_model descarta."""
    all_csv_files = sorted(glob.glob(str(RAW_DIR / "atp_matches_[0-9]*.csv")))
    csv_files = [
        f for f in all_csv_files
        if int(os.path.basename(f).replace("atp_matches_", "").replace(".csv", "")) >= MIN_YEAR
    ]
    raw_data = pd.concat([pd.read_csv(f) for f in csv_files])
    match_df, _ = prepare_features_for_training(raw_data)
    match_df = match_df.sort_values("tourney_date").reset_index(drop=True)
    split_idx = int(len(match_df) * 0.8)
    match_test = match_df.iloc[split_idx:]
    test_df = symmetrize_dataset(match_test)
    return test_df


def predict_on_test_set(test_df: pd.DataFrame):
    model_data = joblib.load(MODEL_PATH)
    model = model_data["model"]
    feature_names = model_data["features"]

    X_test = test_df.reindex(columns=feature_names, fill_value=-1)
    X_test = X_test.apply(pd.to_numeric, errors="coerce").fillna(-1)
    p2_win_proba = model.predict_proba(X_test)[:, 1]

    out = test_df[["tourney_date", "surface", "p1_name", "p2_name", "target"]].copy()
    out["p1_win_prob"] = 1 - p2_win_proba
    out["p2_win_prob"] = p2_win_proba
    if "p1_elo_before_match" in test_df.columns and "p2_elo_before_match" in test_df.columns:
        out["elo_diff"] = test_df["p1_elo_before_match"] - test_df["p2_elo_before_match"]
    return out


# Columnas de tennis-data.co.uk que no se usan para el cruce en sí pero sí
# para segmentar el backtest por torneo/ronda/book (ver segment_backtest.py).
# Se listan explícitamente (en vez de tomar todo el excel) porque no todos
# los años tienen exactamente las mismas columnas de books.
SEGMENT_COLS = [
    "Series", "Court", "Round", "Best of", "WRank", "LRank",
    "PSW", "PSL", "B365W", "B365L",
]


def load_odds() -> pd.DataFrame:
    frames = []
    for path in sorted(ODDS_DIR.glob("*.xlsx")):
        df = pd.read_excel(path)
        frames.append(df)
    if not frames:
        raise FileNotFoundError(f"No hay archivos .xlsx en {ODDS_DIR}")
    odds = pd.concat(frames, ignore_index=True)
    odds["Date"] = pd.to_datetime(odds["Date"], errors="coerce")
    odds = odds.dropna(subset=["Date", "Winner", "Loser", "AvgW", "AvgL"])
    odds["winner_key"] = odds["Winner"].apply(normalize_odds_name)
    odds["loser_key"] = odds["Loser"].apply(normalize_odds_name)
    return odds


def match_predictions_to_odds(predictions: pd.DataFrame, odds: pd.DataFrame) -> pd.DataFrame:
    predictions = predictions.copy()
    predictions["p1_key"] = predictions["p1_name"].apply(normalize_full_name)
    predictions["p2_key"] = predictions["p2_name"].apply(normalize_full_name)

    # Índice por pareja de jugadores (par no ordenado) -> filas de odds candidatas
    odds_by_pair: dict[tuple, list[int]] = {}
    for idx, row in odds.iterrows():
        pair = frozenset([row["winner_key"], row["loser_key"]])
        odds_by_pair.setdefault(pair, []).append(idx)

    matched_rows = []
    for _, pred in predictions.iterrows():
        pair = frozenset([pred["p1_key"], pred["p2_key"]])
        candidate_idxs = odds_by_pair.get(pair)
        if not candidate_idxs:
            continue

        candidates = odds.loc[candidate_idxs]
        date_diff = (candidates["Date"] - pred["tourney_date"]).abs()
        best_idx = date_diff.idxmin()
        if date_diff.loc[best_idx].days > DATE_TOLERANCE_DAYS:
            continue

        odds_row = odds.loc[best_idx]

        # ¿p1 es quien ganó según los datos de cuotas (Winner), o el perdedor (Loser)?
        if pred["p1_key"] == odds_row["winner_key"]:
            fair_denom = (1 / odds_row["AvgW"]) + (1 / odds_row["AvgL"])
            market_p1_win_prob = (1 / odds_row["AvgW"]) / fair_denom
        else:
            fair_denom = (1 / odds_row["AvgW"]) + (1 / odds_row["AvgL"])
            market_p1_win_prob = (1 / odds_row["AvgL"]) / fair_denom

        row_out = {
            "tourney_date": pred["tourney_date"],
            "surface": pred["surface"],
            "p1_name": pred["p1_name"],
            "p2_name": pred["p2_name"],
            "target": pred["target"],  # 1 si p2 ganó
            "model_p2_win_prob": pred["p2_win_prob"],
            "market_p2_win_prob": 1 - market_p1_win_prob,
            "avg_odds_winner": odds_row["AvgW"],
            "avg_odds_loser": odds_row["AvgL"],
        }
        if "elo_diff" in pred.index:
            row_out["elo_diff"] = pred["elo_diff"]
        # Cuotas/metadata extra para segmentación (segment_backtest.py). Se
        # guardan tal cual desde tennis-data.co.uk, orientadas a Winner/Loser
        # (no a p1/p2), porque las dimensiones de segmento (torneo, ronda,
        # ranking) no dependen de qué lado terminó en p1 vs p2.
        for col in SEGMENT_COLS:
            if col in odds_row.index:
                row_out[col] = odds_row[col]
        matched_rows.append(row_out)

    return pd.DataFrame(matched_rows)


def brier(y_true, y_prob) -> float:
    return float(np.mean((np.asarray(y_prob) - np.asarray(y_true)) ** 2))


def log_loss_safe(y_true, y_prob, eps=1e-9) -> float:
    p = np.clip(np.asarray(y_prob), eps, 1 - eps)
    y = np.asarray(y_true)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def main():
    print("=== Backtest: modelo vs. cuotas de mercado ===\n")

    print("1. Reconstruyendo el test set del modelo (mismo split que model.py)...")
    test_df = rebuild_test_set()
    print(f"   {len(test_df)} filas de test (symmetrizadas)")

    print("\n2. Corriendo el modelo entrenado sobre el test set...")
    predictions = predict_on_test_set(test_df)

    print("\n3. Cargando cuotas históricas de tennis-data.co.uk...")
    odds = load_odds()
    print(f"   {len(odds)} partidos con cuotas cargados ({odds['Date'].min().date()} a {odds['Date'].max().date()})")

    print("\n4. Cruzando predicciones con cuotas por nombre normalizado + fecha...")
    matched = match_predictions_to_odds(predictions, odds)
    match_rate = len(matched) / len(predictions) if len(predictions) else 0
    print(f"   {len(matched)} / {len(predictions)} filas de test cruzadas con éxito ({match_rate:.1%})")

    if matched.empty:
        print("\nNo se pudo cruzar ningún partido. Revisa el rango de años de las cuotas descargadas.")
        return

    print("\n=== Resultados sobre el subconjunto cruzado ===")
    y_true = matched["target"].values
    model_prob = matched["model_p2_win_prob"].values
    market_prob = matched["market_p2_win_prob"].values

    print(f"Brier modelo:  {brier(y_true, model_prob):.4f}")
    print(f"Brier mercado: {brier(y_true, market_prob):.4f}  (más bajo = mejor)")
    print(f"LogLoss modelo:  {log_loss_safe(y_true, model_prob):.4f}")
    print(f"LogLoss mercado: {log_loss_safe(y_true, market_prob):.4f}")

    model_acc = float(np.mean((model_prob > 0.5).astype(int) == y_true))
    market_acc = float(np.mean((market_prob > 0.5).astype(int) == y_true))
    print(f"\nAccuracy modelo (subset cruzado):  {model_acc:.4f}")
    print(f"Accuracy mercado (favorito, subset cruzado): {market_acc:.4f}")

    # --- Simulación de apuesta: solo donde el modelo ve EV+ vs. la cuota ofrecida ---
    print("\n=== Simulación de apuesta (stake plano de 1 unidad, cuotas reales con margen) ===")
    bankroll_flat = 0.0
    bankroll_kelly = 1.0
    n_bets = 0
    kelly_fraction = 0.25  # Kelly fraccionado, conservador

    for _, row in matched.iterrows():
        model_p2 = row["model_p2_win_prob"]
        model_p1 = 1 - model_p2
        odds_winner = row["avg_odds_winner"]  # cuota real de quien ganó
        odds_loser = row["avg_odds_loser"]    # cuota real de quien perdió
        actual_p2_won = row["target"] == 1

        # ¿En qué lado apostaría el modelo? Solo si su prob supera la implícita
        # de la cuota ofrecida en ESE lado (edge real, no solo vs. la cuota justa)
        implied_p2 = 1 / (odds_winner if actual_p2_won else odds_loser)
        implied_p1 = 1 / (odds_loser if actual_p2_won else odds_winner)

        bets = []
        if model_p2 > implied_p2:
            odds_p2 = odds_winner if actual_p2_won else odds_loser
            bets.append(("p2", model_p2, odds_p2, actual_p2_won))
        if model_p1 > implied_p1:
            odds_p1 = odds_loser if actual_p2_won else odds_winner
            bets.append(("p1", model_p1, odds_p1, not actual_p2_won))

        for _, p_win, odds_dec, won in bets:
            n_bets += 1
            payout = (odds_dec - 1) if won else -1
            bankroll_flat += payout

            b = odds_dec - 1
            f = max(0.0, (p_win * (b + 1) - 1) / b) if b > 0 else 0.0
            f = min(f * kelly_fraction, 0.05)  # tope de seguridad 5% del bankroll
            bankroll_kelly *= (1 + f * b) if won else (1 - f)

    print(f"Apuestas hechas: {n_bets} / {len(matched)} partidos cruzados")
    print(f"P&L stake plano (1 unidad por apuesta): {bankroll_flat:+.2f} unidades")
    print(f"ROI stake plano: {(bankroll_flat / n_bets * 100) if n_bets else 0:.2f}% por apuesta")
    print(f"Bankroll final Kelly {kelly_fraction:.0%} fraccionado (base 1.0): {bankroll_kelly:.4f}")

    # Guardar el detalle para inspección manual
    out_path = BACKEND_DIR / "data" / "processed" / "backtest_odds_detail.csv"
    matched.to_csv(out_path, index=False)
    print(f"\nDetalle guardado en: {out_path}")


if __name__ == "__main__":
    main()
