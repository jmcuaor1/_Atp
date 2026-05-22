import pandas as pd
import numpy as np
from pathlib import Path
from functools import lru_cache
from typing import Optional

DATA_DIR = Path(__file__).parent.parent / "data" / "raw"


@lru_cache(maxsize=1)
def _load_matches() -> pd.DataFrame:
    """Load main ATP singles matches from 2010 onwards (cached)."""
    files = sorted(DATA_DIR.glob("atp_matches_20[12][0-9].csv"))
    if not files:
        return pd.DataFrame()
    dfs = []
    for f in files:
        try:
            dfs.append(pd.read_csv(f, low_memory=False))
        except Exception:
            pass
    if not dfs:
        return pd.DataFrame()
    df = pd.concat(dfs, ignore_index=True)
    df["tourney_date"] = pd.to_numeric(df["tourney_date"], errors="coerce")
    return df


def get_players(min_matches: int = 30) -> list:
    df = _load_matches()
    if df.empty:
        return []
    counts = (
        df["winner_name"].value_counts()
        .add(df["loser_name"].value_counts(), fill_value=0)
    )
    return sorted(counts[counts >= min_matches].index.tolist())


def _surface_stats(df: pd.DataFrame, player: str, surface: str) -> dict:
    recent = df[df["tourney_date"] >= 20190101]
    if surface != "All":
        recent = recent[recent["surface"] == surface]
    won = len(recent[recent["winner_name"] == player])
    lost = len(recent[recent["loser_name"] == player])
    total = won + lost
    return {"win_rate": won / total if total > 0 else 0.5, "matches": total}


def _latest_rank(df: pd.DataFrame, player: str) -> float:
    w = df[df["winner_name"] == player]["winner_rank"].dropna()
    l = df[df["loser_name"] == player]["loser_rank"].dropna()
    combined = pd.concat([w, l])
    return float(combined.iloc[-1]) if not combined.empty else 200.0


def build_features(
    player1: str,
    player2: str,
    surface: str,
    rank1: Optional[int] = None,
    rank2: Optional[int] = None,
) -> dict:
    df = _load_matches()
    r1 = float(rank1) if rank1 else _latest_rank(df, player1)
    r2 = float(rank2) if rank2 else _latest_rank(df, player2)
    s1 = _surface_stats(df, player1, surface)
    s2 = _surface_stats(df, player2, surface)
    h2h_p1 = len(df[(df["winner_name"] == player1) & (df["loser_name"] == player2)])
    h2h_p2 = len(df[(df["winner_name"] == player2) & (df["loser_name"] == player1)])
    return {
        "rank_p1": r1,
        "rank_p2": r2,
        "rank_diff": r2 - r1,
        "win_rate_p1": s1["win_rate"],
        "win_rate_p2": s2["win_rate"],
        "win_rate_diff": s1["win_rate"] - s2["win_rate"],
        "matches_p1": s1["matches"],
        "matches_p2": s2["matches"],
        "h2h_p1": h2h_p1,
        "h2h_p2": h2h_p2,
    }
