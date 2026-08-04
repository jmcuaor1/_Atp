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

from features import prepare_features_for_training, symmetrize_dataset

def train_tennis_model(match_df):
    """
    Entrena un modelo XGBoost para predecir el ganador de un partido.

    Recibe el DataFrame a nivel de partido (1 fila por partido, sin
    symmetrizar). El split cronológico se hace ANTES de symmetrizar y cada
    mitad se symmetriza por separado: si se symmetriza primero y se separa
    después, el "gemelo" de un partido de test (mismo partido con p1/p2
    invertidos) puede terminar en el set de entrenamiento, filtrando la
    respuesta exacta hacia el modelo (esto causaba un accuracy ~100%
    ficticio antes de este fix).
    """
    # 0. Split cronológico sobre partidos únicos, ANTES de symmetrizar
    match_df = match_df.sort_values('tourney_date').reset_index(drop=True)
    split_idx = int(len(match_df) * 0.8)
    match_train = match_df.iloc[:split_idx]
    match_test = match_df.iloc[split_idx:]

    train_df = symmetrize_dataset(match_train)
    test_df = symmetrize_dataset(match_test)

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

    drop_cols = [c for c in leakage_cols + meta_cols if c in train_df.columns]

    # 2. Separar características (X) y objetivo (y) en train y test por separado
    # Solo nos quedamos con variables numéricas (rankings, edad, altura, etc.)
    X_train = train_df.drop(columns=['target'] + drop_cols)
    X_train = X_train.apply(pd.to_numeric, errors='coerce').fillna(-1)
    y_train = train_df['target']

    X_test = test_df.drop(columns=['target'] + drop_cols)
    X_test = X_test.apply(pd.to_numeric, errors='coerce').fillna(-1)
    X_test = X_test.reindex(columns=X_train.columns, fill_value=-1)
    y_test = test_df['target']

    feature_names = list(X_train.columns)
    print(f"Entrenando con columnas: {feature_names}")
    print(f"Train: {len(X_train)} filas ({match_train['tourney_date'].min()} a {match_train['tourney_date'].max()})")
    print(f"Test:  {len(X_test)} filas ({match_test['tourney_date'].min()} a {match_test['tourney_date'].max()})")

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

    # 7. Curva de calibración (vital: un Brier bajo no garantiza que p=0.70
    # signifique 70% real, hay que verlo)
    calibration_data = None
    try:
        from sklearn.calibration import calibration_curve
        prob_true, prob_pred = calibration_curve(y_test, y_proba, n_bins=10, strategy="quantile")
        calibration_data = {"prob_true": prob_true.tolist(), "prob_pred": prob_pred.tolist()}
        print("\nCalibración (prob. predicha -> frecuencia real):")
        for pt, pp in zip(prob_pred, prob_true):
            print(f"  {pp:.3f} predicho -> {pt:.3f} real")

        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt

            fig, ax = plt.subplots(figsize=(5, 5))
            ax.plot(prob_pred, prob_true, marker="o", label="Modelo")
            ax.plot([0, 1], [0, 1], linestyle="--", color="gray", label="Calibración perfecta")
            ax.set_xlabel("Probabilidad predicha")
            ax.set_ylabel("Frecuencia real observada")
            ax.set_title("Curva de calibración - test set")
            ax.legend()
            fig.tight_layout()

            plots_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "processed")
            os.makedirs(plots_dir, exist_ok=True)
            calibration_plot_path = os.path.join(plots_dir, "calibration_curve.png")
            fig.savefig(calibration_plot_path)
            plt.close(fig)
            print(f"\nCurva de calibración guardada en: {calibration_plot_path}")
        except ImportError:
            print("\n(matplotlib no disponible: se omite el gráfico, se guardan los datos igual)")
    except Exception as e:
        print(f"\nNo se pudo calcular la curva de calibración: {e}")

    metrics = {
        "accuracy": float(accuracy_score(y_test, y_pred)),
        "brier_score": float(brier_score_loss(y_test, y_proba)),
        "train_samples": int(len(X_train)),
        "test_samples": int(len(X_test)),
        "feature_count": len(feature_names),
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "calibration": calibration_data,
    }

    return model, feature_names, metrics

if __name__ == "__main__":
    # Obtenemos la ruta base del proyecto de forma absoluta
    SRC_DIR = os.path.dirname(os.path.abspath(__file__))
    BACKEND_DIR = os.path.dirname(SRC_DIR)
    RAW_DATA_PATH = os.path.join(BACKEND_DIR, "data", "raw")

    # Cargar múltiples años si existen
    # Acotamos el rango a partir de MIN_YEAR: antes de mediados de los 80s el
    # ranking ATP es poco confiable o inexistente (mezclar esas eras con el
    # tenis actual añade ruido, no señal, para predecir partidos de hoy).
    MIN_YEAR = 2010
    all_csv_files = sorted(glob.glob(os.path.join(RAW_DATA_PATH, "atp_matches_[0-9]*.csv")))
    csv_files = [
        f for f in all_csv_files
        if int(os.path.basename(f).replace("atp_matches_", "").replace(".csv", "")) >= MIN_YEAR
    ]

    if csv_files:
        print(f"Cargando {len(csv_files)} archivos de datos...")
        # Load all CSVs and concatenate them
        raw_data = pd.concat([pd.read_csv(f) for f in csv_files])

        # Transformar datos usando nuestro archivo de features (1 fila por
        # partido, sin symmetrizar todavía; ver train_tennis_model)
        match_df, player_profiles = prepare_features_for_training(raw_data)

        # Entrenar
        trained_model, feature_names, metrics = train_tennis_model(match_df)

        # Guardar el modelo en un archivo .pkl
        model_dir = os.path.join(BACKEND_DIR, "models")
        os.makedirs(model_dir, exist_ok=True)
        model_path = os.path.join(model_dir, "tennis_model.pkl")
        metrics["csv_files"] = [os.path.basename(f) for f in csv_files]
        metrics["players_count"] = len(player_profiles)
        metrics["date_range"] = [
            str(match_df["tourney_date"].min()),
            str(match_df["tourney_date"].max()),
        ]
        try:
            import subprocess
            metrics["git_commit"] = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=BACKEND_DIR, text=True
            ).strip()
        except Exception:
            metrics["git_commit"] = None
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
