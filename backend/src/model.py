<<<<<<< HEAD
import pandas as pd
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report, brier_score_loss
from sklearn.calibration import CalibratedClassifierCV
import os
import joblib
import glob
import sys
from datetime import datetime, timezone

# Añadimos el directorio actual al path para poder importar features
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
if PARENT_DIR not in sys.path:
    sys.path.append(PARENT_DIR)

if CURRENT_DIR not in sys.path:
    sys.path.append(CURRENT_DIR)

from features import prepare_features_for_training

def train_tennis_model(df):
    """
    Entrena un modelo XGBoost para predecir el ganador de un partido.
    """
    # 1. Definir columnas a eliminar (Data Leakage)
    # NO podemos usar estadísticas que se generan DURANTE el partido (aces, break points, etc.)
    # para predecir el resultado, porque no las conocemos antes de empezar.
    leakage_cols = [
        'p1_ace', 'p1_df', 'p1_svpt', 'p1_1stIn', 'p1_1stWon', 'p1_2ndWon', 
        'p1_SvGms', 'p1_bpSaved', 'p1_bpFaced',
        'p2_ace', 'p2_df', 'p2_svpt', 'p2_1stIn', 'p2_1stWon', 'p2_2ndWon', 
        'p2_SvGms', 'p2_bpSaved', 'p2_bpFaced', 
        'minutes', 'score', 'round', 'match_num'
    ]
    
    # Columnas de identificación que no sirven para el patrón matemático
    meta_cols = [
        'tourney_id', 'tourney_name', 'tourney_date', 'p1_id', 'p2_id', 
        'p1_name', 'p2_name', 'p1_seed', 'p2_seed', 'p1_entry', 'p2_entry',
        'p1_ioc', 'p2_ioc', 'p1_hand', 'p2_hand', 'surface', 'best_of', 'tourney_level' # Add best_of and tourney_level to meta_cols
    ]
    
    drop_cols = [c for c in leakage_cols + meta_cols if c in df.columns]
    
    # 2. Separar características (X) y objetivo (y)
    # Solo nos quedamos con variables numéricas (rankings, edad, altura, etc.)
    X = df.drop(columns=['target'] + drop_cols)
    # Ensure all columns are numeric and handle NaNs
    X = X.apply(pd.to_numeric, errors='coerce').fillna(-1) # Convert all to numeric, then fill NaNs
    y = df['target']
    
    print(f"Entrenando con columnas: {list(X.columns)}")

    # 3. Split cronológico (más realista para deportes)
    # Assuming df is already sorted by tourney_date from prepare_features_for_training
    split_idx = int(len(df) * 0.8)
    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]
    
    feature_names = list(X.columns)

    # 4. Modelo con Calibración (Vital para apuestas/probabilidades reales)
    base_model = xgb.XGBClassifier(
        n_estimators=200, # Increased estimators
        learning_rate=0.05, # Reduced learning rate
        max_depth=5, # Slightly reduced max_depth
        subsample=0.8, # Added subsample
        colsample_bytree=0.8, # Added colsample_bytree
        random_state=42,
        eval_metric='logloss'
    )
    
    # CalibratedClassifierCV for better probability estimates
    model = CalibratedClassifierCV(base_model, method='sigmoid', cv=5)

    # 5. Entrenamiento
    print("Iniciando entrenamiento con calibración...")
    model.fit(X_train, y_train)

    # 6. Evaluación
    y_pred = model.predict(X_test)
    y_proba = model.predict_proba(X_test)[:, 1] # Probability of player 2 winning
    print("\n--- Resultados del Modelo ---")
    print(f"Accuracy: {accuracy_score(y_test, y_pred):.4f}")
    print(f"Brier Score (Probabilidades): {brier_score_loss(y_test, y_proba):.4f}")
    print("\nReporte Detallado:")
    print(classification_report(y_test, y_pred))

    metrics = {
        "accuracy": float(accuracy_score(y_test, y_pred)),
        "brier_score": float(brier_score_loss(y_test, y_proba)),
        "train_samples": int(len(X_train)),
        "test_samples": int(len(X_test)),
        "feature_count": len(feature_names),
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }

    return model, feature_names, metrics

if __name__ == "__main__":
    # Obtenemos la ruta base del proyecto de forma absoluta
    SRC_DIR = os.path.dirname(os.path.abspath(__file__))
    BACKEND_DIR = os.path.dirname(SRC_DIR)
    RAW_DATA_PATH = os.path.join(BACKEND_DIR, "data", "raw")

    # Cargar múltiples años si existen
    csv_files = sorted(glob.glob(os.path.join(RAW_DATA_PATH, "atp_matches_[0-9]*.csv")))
    
    if csv_files:
        print(f"Cargando {len(csv_files)} archivos de datos...")
        # Load all CSVs and concatenate them
        raw_data = pd.concat([pd.read_csv(f) for f in csv_files])
        
        # Transformar datos usando nuestro archivo de features
        processed_df, player_profiles = prepare_features_for_training(raw_data)
        
        # Entrenar
        trained_model, feature_names, metrics = train_tennis_model(processed_df)

        # Guardar el modelo en un archivo .pkl
        model_dir = os.path.join(BACKEND_DIR, "models")
        os.makedirs(model_dir, exist_ok=True)
        model_path = os.path.join(model_dir, "tennis_model.pkl")
        metrics["csv_files"] = [os.path.basename(f) for f in csv_files]
        metrics["players_count"] = len(player_profiles)
        # Guardamos un diccionario con metadatos útiles
        model_data = {
            'model': trained_model,
            'features': feature_names,
            'metadata': metrics,
        }
        joblib.dump(model_data, model_path)
        print(f"\nModelo guardado exitosamente en: {model_path}")

        # Guardar los perfiles de jugador para la API
        player_profiles_path = os.path.join(model_dir, "player_profiles.pkl")
        joblib.dump(player_profiles, player_profiles_path)
        print(f"Perfiles de jugador guardados exitosamente en: {player_profiles_path}")
    else:
        print("Error: No se encontraron archivos CSV en backend/data/raw/")
        print("Ejecuta primero: python scripts/download_atp_data.py")
=======
import numpy as np
from pathlib import Path
from typing import Optional
from .features import build_features

MODEL_PATH = Path(__file__).parent.parent / "models" / "xgboost_model.pkl"

_model = None
_model_checked = False


def _get_model():
    global _model, _model_checked
    if not _model_checked:
        _model_checked = True
        if MODEL_PATH.exists():
            try:
                import joblib
                _model = joblib.load(MODEL_PATH)
            except Exception:
                _model = None
    return _model


def predict_winner(
    player1: str,
    player2: str,
    surface: str,
    rank1: Optional[int] = None,
    rank2: Optional[int] = None,
) -> dict:
    feats = build_features(player1, player2, surface, rank1, rank2)
    model = _get_model()

    if model is not None:
        X = np.array([[
            feats["rank_diff"],
            feats["win_rate_diff"],
            feats["win_rate_p1"],
            feats["win_rate_p2"],
        ]])
        prob_p1 = float(model.predict_proba(X)[0][1])
        model_used = "xgboost"
    else:
        # Weighted heuristic: rank (50%) + surface win rate (35%) + H2H (15%)
        score = 0.0
        r1, r2 = feats["rank_p1"], feats["rank_p2"]
        score += (r2 - r1) / max(r1 + r2, 1) * 0.50
        score += feats["win_rate_diff"] * 0.35
        h_total = feats["h2h_p1"] + feats["h2h_p2"]
        if h_total > 0:
            score += (feats["h2h_p1"] / h_total - 0.5) * 2 * 0.15
        prob_p1 = float(1 / (1 + np.exp(-score * 4)))
        model_used = "heuristic"

    winner = player1 if prob_p1 >= 0.5 else player2
    loser = player2 if winner == player1 else player1
    prob_winner = prob_p1 if winner == player1 else 1 - prob_p1

    return {
        "winner": winner,
        "loser": loser,
        "probability": round(prob_winner, 3),
        "prob_p1": round(prob_p1, 3),
        "prob_p2": round(1 - prob_p1, 3),
        "features": feats,
        "model": model_used,
    }
>>>>>>> daab2e1cdb2d49c4091b6dfcafe4a8caa0d5a9c3
