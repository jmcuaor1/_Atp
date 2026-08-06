#!/usr/bin/env python3
"""
Actualiza data/raw/ con partidos 2025+ desde TML-Database
(github.com/Tennismylife/TML-Database), que reemplaza al repo original de
Sackmann (JeffSackmann/tennis_atp, dado de baja — ver git log de este
commit para el contexto).

Problema que resuelve este script: TML usa su propio esquema de IDs de
jugador (alfanumérico, ej. "S0AG") que NO tiene relación con los IDs
numéricos que ya usa este proyecto (ej. Sinner = 206173, heredados de
Sackmann). Pegar los CSVs de TML tal cual duplicaría a cada jugador bajo
una identidad nueva, perdiendo todo el Elo/rolling stats acumulado.

Este script arma un "puente" nombre → ID:
  1. Nombre normalizado (apellido + inicial, sin acentos) coincide
     exactamente con un jugador ya conocido → reusa ESE id numérico.
  2. Coincide por apellido+inicial pero hay más de un candidato → se
     resuelve por el de mayor ranking (mejor conocido) y se deja constancia
     en el reporte para revisión manual.
  3. No coincide con nadie conocido (jugador nuevo, debutó después de 2024)
     → se le asigna un id numérico nuevo, secuencial a partir de
     NEW_ID_BASE, determinístico (mismo nombre → mismo id nuevo en
     corridas futuras, para no romper continuidad).

Uso:
  python scripts/update_tml_data.py
"""

from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

import httpx
import joblib
import pandas as pd

BACKEND_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BACKEND_DIR / "data" / "raw"
PROFILES_PATH = BACKEND_DIR / "models" / "player_profiles.pkl"
REPORT_PATH = BACKEND_DIR / "data" / "processed" / "tml_id_bridge_report.txt"

# El repo de GitHub quedó congelado (solo referencia histórica, según su
# propio README) — la fuente que sí se actualiza es esta API en vivo del
# sitio hermano (verificado: 2026.csv ahí tiene mtime de días, no meses).
TML_BASE_URL = "https://stats.tennismylife.org/data"
YEARS_TO_PULL = [2025, 2026]  # años que faltan desde que Sackmann se dio de baja (datos hasta dic. 2024)
NEW_ID_BASE = 900001  # muy por encima del id numérico más alto ya usado (~213000), sin riesgo de colisión

REFERENCE_COLUMNS = [
    "tourney_id", "tourney_name", "surface", "draw_size", "tourney_level", "tourney_date",
    "match_num", "winner_id", "winner_seed", "winner_entry", "winner_name", "winner_hand",
    "winner_ht", "winner_ioc", "winner_age", "loser_id", "loser_seed", "loser_entry",
    "loser_name", "loser_hand", "loser_ht", "loser_ioc", "loser_age", "score", "best_of",
    "round", "minutes", "w_ace", "w_df", "w_svpt", "w_1stIn", "w_1stWon", "w_2ndWon",
    "w_SvGms", "w_bpSaved", "w_bpFaced", "l_ace", "l_df", "l_svpt", "l_1stIn", "l_1stWon",
    "l_2ndWon", "l_SvGms", "l_bpSaved", "l_bpFaced", "winner_rank", "winner_rank_points",
    "loser_rank", "loser_rank_points",
]


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def normalize_name(full_name: str) -> tuple[str, str, str]:
    """(nombre completo normalizado, apellido normalizado, inicial) — mismo
    criterio de apellido+inicial que ya se usa en el resto del proyecto para
    cruzar nombres entre fuentes (ver backtest_odds.normalize_full_name)."""
    parts = str(full_name).strip().split()
    if not parts:
        return ("", "", "")
    full_norm = re.sub(r"[^a-z]", "", strip_accents(" ".join(parts).lower()))
    last = re.sub(r"[^a-z]", "", strip_accents("".join(parts[1:]).lower())) if len(parts) > 1 else re.sub(r"[^a-z]", "", strip_accents(parts[0].lower()))
    initial = strip_accents(parts[0][0].lower()) if parts[0] else ""
    return (full_norm, last, initial)


def download_year(year: int) -> pd.DataFrame:
    url = f"{TML_BASE_URL}/{year}.csv"
    resp = httpx.get(url, timeout=30.0)
    resp.raise_for_status()
    try:
        return pd.read_csv(pd.io.common.BytesIO(resp.content), dtype={"winner_id": str, "loser_id": str})
    except UnicodeDecodeError:
        return pd.read_csv(pd.io.common.BytesIO(resp.content), dtype={"winner_id": str, "loser_id": str}, encoding="latin-1")


def build_reference_lookup() -> tuple[dict[str, tuple[int, str, float]], dict[tuple[str, str], list[tuple[int, str, float]]]]:
    """Devuelve (por nombre completo exacto, por apellido+inicial) → [(id, nombre, rank)]."""
    profiles = joblib.load(PROFILES_PATH)
    by_full: dict[str, tuple[int, str, float]] = {}
    by_last_initial: dict[tuple[str, str], list[tuple[int, str, float]]] = {}
    for player_id, profile in profiles.items():
        name = str(profile.get("name", ""))
        rank = profile.get("rank")
        rank = float(rank) if rank is not None else float("inf")
        full_norm, last, initial = normalize_name(name)
        by_full[full_norm] = (int(player_id), name, rank)
        by_last_initial.setdefault((last, initial), []).append((int(player_id), name, rank))
    return by_full, by_last_initial


def main() -> None:
    print("1. Cargando jugadores ya conocidos por el modelo...")
    by_full, by_last_initial = build_reference_lookup()
    print(f"   {len(by_full)} jugadores de referencia.")

    # Cacheado por NOMBRE normalizado, no por el id crudo de TML: ese id a
    # veces viene vacío en la fuente (NaN), y NaN no sirve como clave de
    # caché (además de que pandas .astype(str) no lo convierte a "nan" de
    # forma confiable) — el nombre es de todos modos lo único que se usa
    # para resolver, así que cachear por ahí es más simple y más robusto.
    resolved: dict[str, int] = {}  # nombre normalizado -> id numérico
    ambiguous: list[str] = []
    matched_existing = 0

    all_frames: dict[int, pd.DataFrame] = {}
    all_names: set[str] = set()

    for year in YEARS_TO_PULL:
        print(f"\n2. Descargando {year}.csv de TML-Database...")
        df = download_year(year)
        print(f"   {len(df)} partidos.")
        all_frames[year] = df
        all_names.update(df["winner_name"].astype(str))
        all_names.update(df["loser_name"].astype(str))

    for name in sorted(all_names):
        full_norm, last, initial = normalize_name(name)
        if not full_norm:
            continue

        if full_norm in by_full:
            resolved[name] = by_full[full_norm][0]
            matched_existing += 1
            continue

        candidates = by_last_initial.get((last, initial), [])
        if len(candidates) == 1:
            resolved[name] = candidates[0][0]
            matched_existing += 1
            continue
        if len(candidates) > 1:
            best = sorted(candidates, key=lambda c: c[2])[0]
            resolved[name] = best[0]
            matched_existing += 1
            ambiguous.append(
                f"{name} — {len(candidates)} candidatos por apellido+inicial, "
                f"se usó el de mejor ranking: {best[1]} (id {best[0]})"
            )
            continue

        # jugador nuevo: id determinístico según orden alfabético (mismo
        # nombre siempre cae en el mismo id nuevo entre corridas, porque
        # all_names se recorre ordenado)
        resolved[name] = NEW_ID_BASE + sum(1 for n in resolved.values() if n >= NEW_ID_BASE)

    minted_new = sum(1 for v in resolved.values() if v >= NEW_ID_BASE)
    new_id_names = {name: pid for name, pid in resolved.items() if pid >= NEW_ID_BASE}

    print(f"\n3. Resolución de IDs: {matched_existing} coincidieron con jugadores ya conocidos, "
          f"{minted_new} jugadores nuevos recibieron id nuevo.")
    if ambiguous:
        print(f"   {len(ambiguous)} casos ambiguos (revisar reporte).")

    print("\n4. Reescribiendo CSVs con ids resueltos en data/raw/...")
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for year, df in all_frames.items():
        df["winner_id"] = df["winner_name"].astype(str).map(resolved).astype("Int64")
        df["loser_id"] = df["loser_name"].astype(str).map(resolved).astype("Int64")
        missing = df["winner_id"].isna().sum() + df["loser_id"].isna().sum()
        if missing:
            print(f"   ADVERTENCIA {year}: {missing} ids sin resolver (no debería pasar).")

        out_cols = [c for c in REFERENCE_COLUMNS if c in df.columns]
        out_path = RAW_DIR / f"atp_matches_{year}.csv"
        df[out_cols].to_csv(out_path, index=False)
        print(f"   {out_path} ({len(df)} partidos)")

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with REPORT_PATH.open("w", encoding="utf-8") as fh:
        fh.write(f"Puente de IDs TML -> Sackmann — {matched_existing} existentes, {minted_new} nuevos\n\n")
        fh.write("=== Jugadores nuevos (sin historial antes de 2025) ===\n")
        for name, new_id in sorted(new_id_names.items(), key=lambda kv: kv[1]):
            fh.write(f"{new_id}: {name}\n")
        fh.write("\n=== Casos ambiguos (revisar a mano si el jugador importa) ===\n")
        for line in ambiguous:
            fh.write(line + "\n")
    print(f"\nReporte detallado en {REPORT_PATH}")
    print("\nListo. Corré 'python src/model.py' para reentrenar con los datos nuevos.")


if __name__ == "__main__":
    main()
