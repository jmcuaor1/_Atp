import pandas as pd
import numpy as np

def calculate_elo_ratings(df_matches, initial_elo=1500, k_factor=32):
    """
    Calcula el rating ELO dinámico para cada jugador a lo largo del tiempo.
    Devuelve el DataFrame con ELOs antes del partido y un diccionario con los ELOs finales de cada jugador.
    """
    df = df_matches.sort_values('tourney_date').reset_index(drop=True)
    elo_dict = {} # player_id -> rating
    p1_elo_list = []
    p2_elo_list = []

    for index, row in df.iterrows():
        p1 = row['winner_id']
        p2 = row['loser_id']
        
        r1 = elo_dict.get(p1, 1500)
        r2 = elo_dict.get(p2, 1500)
        
        # Guardar ratings ANTES del partido para la predicción
        p1_elo_list.append(r1)
        p2_elo_list.append(r2)
        
        # Calcular probabilidad esperada
        e1 = 1 / (1 + 10 ** ((r2 - r1) / 400))
        
        # Actualizar ratings después del resultado
        elo_dict[p1] = r1 + k_factor * (1 - e1)
        elo_dict[p2] = r2 + k_factor * (0 - (1 - e1))
    
    df['winner_elo_before_match'] = p1_elo_list
    df['loser_elo_before_match'] = p2_elo_list
    return df, elo_dict # Return modified df and final elo_dict for all players

def create_rolling_stats_for_all_matches(df_matches, window=10):
    """
    Crea promedios móviles para estadísticas clave (aces, df, 1stWon) para cada jugador
    en cada partido, usando solo datos anteriores.
    Devuelve el DataFrame con las rolling stats añadidas y un diccionario con las últimas
    rolling stats de cada jugador.
    """
    df = df_matches.copy().sort_values('tourney_date').reset_index(drop=True)
    
    # Prepare a long format DataFrame for rolling calculations
    # Winner's stats
    w_df = df[['winner_id', 'tourney_date', 'w_ace', 'w_df', 'w_1stWon']].rename(columns={
        'winner_id': 'player_id', 'w_ace': 'ace', 'w_df': 'df', 'w_1stWon': '1stWon'
    })
    w_df['is_winner'] = 1

    # Loser's stats
    l_df = df[['loser_id', 'tourney_date', 'l_ace', 'l_df', 'l_1stWon']].rename(columns={
        'loser_id': 'player_id', 'l_ace': 'ace', 'l_df': 'df', 'l_1stWon': '1stWon'
    })
    l_df['is_winner'] = 0

    long_df = pd.concat([w_df, l_df]).sort_values(['player_id', 'tourney_date']).reset_index(drop=True)

    # Calculate rolling averages, shifted by 1 to prevent data leakage
    rolling_stats_cols = ['ace', 'df', '1stWon']
    for stat in rolling_stats_cols:
        long_df[f'rolling_avg_{stat}'] = long_df.groupby('player_id')[stat].transform(
            lambda x: x.rolling(window=window, min_periods=1).mean().shift(1)
        )
    
    # Merge rolling stats back to the original match DataFrame
    # For winner
    df = df.merge(long_df[['player_id', 'tourney_date', 'rolling_avg_ace', 'rolling_avg_df', 'rolling_avg_1stWon']],
                  left_on=['winner_id', 'tourney_date'], right_on=['player_id', 'tourney_date'], how='left')
    df = df.rename(columns={
        'rolling_avg_ace': 'p1_rolling_avg_ace',
        'rolling_avg_df': 'p1_rolling_avg_df',
        'rolling_avg_1stWon': 'p1_rolling_avg_1stWon'
    }).drop(columns=['player_id'])

    # For loser
    df = df.merge(long_df[['player_id', 'tourney_date', 'rolling_avg_ace', 'rolling_avg_df', 'rolling_avg_1stWon']],
                  left_on=['loser_id', 'tourney_date'], right_on=['player_id', 'tourney_date'], how='left')
    df = df.rename(columns={
        'rolling_avg_ace': 'p2_rolling_avg_ace',
        'rolling_avg_df': 'p2_rolling_avg_df',
        'rolling_avg_1stWon': 'p2_rolling_avg_1stWon'
    }).drop(columns=['player_id'])

    df = df.fillna(0) # Fill NaNs for new players or early matches

    # Extract final rolling stats state for each player
    latest_rolling_stats = {}
    for player_id in long_df['player_id'].unique():
        player_df = long_df[long_df['player_id'] == player_id].sort_values('tourney_date', ascending=False)
        if not player_df.empty:
            latest_rolling_stats[player_id] = {
                'rolling_avg_ace': player_df['rolling_avg_ace'].iloc[0],
                'rolling_avg_df': player_df['rolling_avg_df'].iloc[0],
                'rolling_avg_1stWon': player_df['rolling_avg_1stWon'].iloc[0]
            }
        else:
            latest_rolling_stats[player_id] = {
                'rolling_avg_ace': 0, 'rolling_avg_df': 0, 'rolling_avg_1stWon': 0
            }

    return df, latest_rolling_stats

def encode_surface(df):
    """
    Convierte superficies (Clay, Hard, Grass) en valores numéricos o One-Hot.
    """
    surface_map = {'Clay': 0, 'Hard': 1, 'Grass': 2, 'Carpet': 3}
    # Ensure 'surface' column exists before mapping
    if 'surface' in df.columns:
        df['surface_encoded'] = df['surface'].map(surface_map).fillna(-1)
    else:
        df['surface_encoded'] = -1 # Default if surface is not provided
    return df

def symmetrize_dataset(df):
    """
    Transforma las columnas winner/loser en player1/player2.
    Crea dos versiones de cada partido para eliminar el sesgo del ganador.
    """
    # Columnas que pertenecen al jugador 1 (ganador original) y jugador 2 (perdedor original)
    w_cols = [c for c in df.columns if any(pre in c for pre in ['winner_', 'w_', 'p1_'])]
    l_cols = [c for c in df.columns if any(pre in c for pre in ['loser_', 'l_', 'p2_'])]

    # Mapeos para estandarizar a p1_ y p2_
    rename_a = {c: c.replace('winner_', 'p1_').replace('w_', 'p1_').replace('p1_', 'p1_') for c in w_cols}
    rename_a.update({c: c.replace('loser_', 'p2_').replace('l_', 'p2_').replace('p2_', 'p2_') for c in l_cols})

    # Crear versión A: Jugador 1 es el ganador
    df_a = df.copy()
    df_a = df_a.rename(columns=rename_a)
    df_a['target'] = 0  # El Jugador 1 (p1) ganó

    # Crear versión B: Intercambiar roles (P2 es ahora el ganador original)
    rename_b = {c: c.replace('winner_', 'p2_').replace('w_', 'p2_').replace('p1_', 'p2_') for c in w_cols}
    rename_b.update({c: c.replace('loser_', 'p1_').replace('l_', 'p1_').replace('p2_', 'p1_') for c in l_cols})

    df_b = df.copy()
    df_b = df_b.rename(columns=rename_b)
    df_b['target'] = 1  # El Jugador 2 (p2) ganó
    
    # Unir ambas versiones
    combined_df = pd.concat([df_a, df_b], axis=0).reset_index(drop=True)
    
    return combined_df

def prepare_features_for_training(raw_df):
    """
    Pipeline principal de Feature Engineering.
    Devuelve el DataFrame procesado y los estados finales de ELO y Rolling Stats.
    """
    df = raw_df.copy()
    
    # 1. Limpieza básica (descartar fechas inválidas en CSV mezclados o scrapeados)
    date_str = df['tourney_date'].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    df['tourney_date'] = pd.to_datetime(date_str, format='%Y%m%d', errors='coerce')
    df = df.dropna(subset=['tourney_date'])
    df = df.sort_values('tourney_date')
    df = df.dropna(subset=['winner_rank', 'loser_rank'])  # Rankings son vitales

    # 2. Ingeniería de características dinámicas (Elo, Rolling Stats)
    df, final_elo_state = calculate_elo_ratings(df)
    df, final_rolling_stats_state = create_rolling_stats_for_all_matches(df)
    
    # 3. Codificación de superficie
    df = encode_surface(df)

    # 4. Estructurar dataset simétrico para evitar sesgos
    processed_df = symmetrize_dataset(df)
    
    # Combine static player info for profiles
    player_profiles = {}
    for player_id in final_elo_state.keys():
        # Try to get static info from the last match they played
        last_match_as_winner = df[df['winner_id'] == player_id].sort_values('tourney_date', ascending=False).head(1)
        last_match_as_loser = df[df['loser_id'] == player_id].sort_values('tourney_date', ascending=False).head(1)
        
        player_info = {}
        if not last_match_as_winner.empty:
            player_info = {
                'name': last_match_as_winner['winner_name'].iloc[0],
                'hand': last_match_as_winner['winner_hand'].iloc[0],
                'ht': last_match_as_winner['winner_ht'].iloc[0],
                'age': last_match_as_winner['winner_age'].iloc[0],
                'ioc': last_match_as_winner['winner_ioc'].iloc[0],
                'rank': last_match_as_winner['winner_rank'].iloc[0],
                'rank_points': last_match_as_winner['winner_rank_points'].iloc[0],
            }
        elif not last_match_as_loser.empty:
            player_info = {
                'name': last_match_as_loser['loser_name'].iloc[0],
                'hand': last_match_as_loser['loser_hand'].iloc[0],
                'ht': last_match_as_loser['loser_ht'].iloc[0],
                'age': last_match_as_loser['loser_age'].iloc[0],
                'ioc': last_match_as_loser['loser_ioc'].iloc[0],
                'rank': last_match_as_loser['loser_rank'].iloc[0],
                'rank_points': last_match_as_loser['loser_rank_points'].iloc[0],
            }
        else: continue # Si no hay datos, saltar
        
        player_profiles[player_id] = {
            'id': player_id,
            **player_info,
            'elo': final_elo_state.get(player_id, 1500),
            **final_rolling_stats_state.get(player_id, {'rolling_avg_ace': 0, 'rolling_avg_df': 0, 'rolling_avg_1stWon': 0})
        }

    return processed_df, player_profiles

def get_features_for_single_prediction(
    player1_profile,
    player2_profile,
    match_surface,
    best_of=3,
    tourney_level="A",
):
    """
    Genera el vector de características para una única predicción utilizando perfiles de jugador precalculados.
    player1_profile, player2_profile: dict con 'id', 'name', 'hand', 'ht', 'age', 'ioc', 'rank', 'elo', 'rolling_avg_ace', etc.
    match_surface: string ('Hard', 'Clay', 'Grass')
    best_of: 3 o 5 sets
    tourney_level: nivel ATP (G, M, A, C, F, D)
    """
    features_row = {
        'p1_id': player1_profile['id'],
        'p1_name': player1_profile['name'],
        'p1_hand': player1_profile['hand'],
        'p1_ht': player1_profile['ht'],
        'p1_age': player1_profile['age'],
        'p1_ioc': player1_profile['ioc'],
        'p1_rank': player1_profile['rank'],
        'p1_rank_points': player1_profile.get('rank_points', 0), # Use .get for optional keys
        'p1_elo_before_match': player1_profile['elo'],
        'p1_rolling_avg_ace': player1_profile['rolling_avg_ace'],
        'p1_rolling_avg_df': player1_profile['rolling_avg_df'],
        'p1_rolling_avg_1stWon': player1_profile['rolling_avg_1stWon'],

        'p2_id': player2_profile['id'],
        'p2_name': player2_profile['name'],
        'p2_hand': player2_profile['hand'],
        'p2_ht': player2_profile['ht'],
        'p2_age': player2_profile['age'],
        'p2_ioc': player2_profile['ioc'],
        'p2_rank': player2_profile['rank'],
        'p2_rank_points': player2_profile.get('rank_points', 0),
        'p2_elo_before_match': player2_profile['elo'],
        'p2_rolling_avg_ace': player2_profile['rolling_avg_ace'],
        'p2_rolling_avg_df': player2_profile['rolling_avg_df'],
        'p2_rolling_avg_1stWon': player2_profile['rolling_avg_1stWon'],

        'surface': match_surface,
        'best_of': best_of,
        'tourney_level': tourney_level,
    }
    
    prediction_df = pd.DataFrame([features_row])
    prediction_df = encode_surface(prediction_df)

    return prediction_df

if __name__ == "__main__":
    # Ejemplo de uso
    # path = "../data/raw/atp_matches_2023.csv"
    # data = pd.read_csv(path)
    # features = prepare_features(data)
    # print(features.head())
    pass