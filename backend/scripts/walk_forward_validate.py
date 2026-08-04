#!/usr/bin/env python3
"""
Validación walk-forward: en vez de un único split 80/20, entrena con todo
lo anterior a cada temporada y evalúa solo en esa temporada. Responde si el
accuracy/Brier del modelo es estable año a año o si el número reportado en
un solo split fue una racha (buena o mala).

Uso:
  python scripts/walk_forward_validate.py
"""

from __future__ import annotations

import glob
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import accuracy_score, brier_score_loss

BACKEND_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BACKEND_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from features import prepare_features_for_training, symmetrize_dataset  # noqa: E402

MIN_YEAR = 2010
TEST_YEARS = [2020, 2021, 2022, 2023, 2024]

LEAKAGE_COLS = [
    'p1_ace', 'p1_df', 'p1_svpt', 'p1_1stIn', 'p1_1stWon', 'p1_2ndWon',
    'p1_SvGms', 'p1_bpSaved', 'p1_bpFaced',
    'p2_ace', 'p2_df', 'p2_svpt', 'p2_1stIn', 'p2_1stWon', 'p2_2ndWon',
    'p2_SvGms', 'p2_bpSaved', 'p2_bpFaced',
    'minutes', 'score', 'round', 'match_num',
]
META_COLS = [
    'tourney_id', 'tourney_name', 'tourney_date', 'p1_id', 'p2_id',
    'p1_name', 'p2_name', 'p1_seed', 'p2_seed', 'p1_entry', 'p2_entry',
    'p1_ioc', 'p2_ioc', 'p1_hand', 'p2_hand', 'surface', 'best_of', 'tourney_level',
]


def to_xy(sym_df: pd.DataFrame):
    drop_cols = [c for c in LEAKAGE_COLS + META_COLS if c in sym_df.columns]
    X = sym_df.drop(columns=['target'] + drop_cols)
    X = X.apply(pd.to_numeric, errors='coerce').fillna(-1)
    y = sym_df['target']
    return X, y


def main():
    RAW_DIR = BACKEND_DIR / "data" / "raw"
    all_csv = sorted(glob.glob(str(RAW_DIR / "atp_matches_[0-9]*.csv")))
    csv_files = [
        f for f in all_csv
        if int(os.path.basename(f).replace("atp_matches_", "").replace(".csv", "")) >= MIN_YEAR
    ]
    raw = pd.concat([pd.read_csv(f) for f in csv_files])
    match_df, _ = prepare_features_for_training(raw)
    match_df = match_df.sort_values('tourney_date').reset_index(drop=True)

    print(f"{'Año':6s} {'Train':>8s} {'Test':>8s} {'Accuracy':>10s} {'Brier':>8s}")
    print("-" * 46)
    results = []
    for year in TEST_YEARS:
        train_part = match_df[match_df['tourney_date'] < f"{year}-01-01"]
        test_part = match_df[
            (match_df['tourney_date'] >= f"{year}-01-01") &
            (match_df['tourney_date'] < f"{year + 1}-01-01")
        ]
        if train_part.empty or test_part.empty:
            continue

        train_df = symmetrize_dataset(train_part)
        test_df = symmetrize_dataset(test_part)
        X_train, y_train = to_xy(train_df)
        X_test, y_test = to_xy(test_df)
        X_test = X_test.reindex(columns=X_train.columns, fill_value=-1)

        base_model = xgb.XGBClassifier(
            n_estimators=200, learning_rate=0.05, max_depth=5,
            subsample=0.8, colsample_bytree=0.8, random_state=42, eval_metric='logloss',
        )
        model = CalibratedClassifierCV(base_model, method='sigmoid', cv=5)
        model.fit(X_train, y_train)

        y_pred = model.predict(X_test)
        y_proba = model.predict_proba(X_test)[:, 1]
        acc = accuracy_score(y_test, y_pred)
        brier = brier_score_loss(y_test, y_proba)
        results.append((year, len(X_train), len(X_test), acc, brier))
        print(f"{year:<6d} {len(X_train):>8d} {len(X_test):>8d} {acc:>10.4f} {brier:>8.4f}")

    accs = [r[3] for r in results]
    briers = [r[4] for r in results]
    print("-" * 46)
    print(f"Accuracy: media={np.mean(accs):.4f}  desv.est={np.std(accs):.4f}  min={min(accs):.4f}  max={max(accs):.4f}")
    print(f"Brier:    media={np.mean(briers):.4f}  desv.est={np.std(briers):.4f}  min={min(briers):.4f}  max={max(briers):.4f}")


if __name__ == "__main__":
    main()
