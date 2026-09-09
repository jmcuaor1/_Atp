#!/usr/bin/env python3
"""
Fase 8 (exploratoria) — arbitraje entre casas de apuestas ("surebets").

A diferencia de todo lo anterior (Fases 1-7), esto NO depende de que nuestro
modelo prediga mejor que nadie. La matemática es distinta: en un mercado de
2 resultados (ganador de un partido), si la MEJOR cuota de cualquier casa
para el jugador 1 y la MEJOR cuota de cualquier otra casa para el jugador 2
dan una suma de probabilidades implícitas (1/cuota) menor a 1, hay una
combinación de apuestas que gana plata garantizada sin importar quién gane
el partido — el margen ("vig") de cada casa individual sigue siendo mayor a
cero, pero como cada una subestima a un jugador distinto, la combinación
queda con margen negativo.

The Odds API (con regions=eu,uk) devuelve ~30 bookmakers por evento — mucho
más que los 2 (Pinnacle, Bet365) que veníamos usando para comparar contra
el modelo. Ese es justamente el insumo que hace falta para esto: cuanta más
diversidad de casas, más chance de que alguna se atrase respecto a las
demás en mover su línea.

Advertencias importantes (no son detalles menores):
  - Esto es un ESCÁNER/detector, no un ejecutor de apuestas. Encontrar una
    oportunidad no significa que siga viva para cuando la cargues a mano en
    dos casas distintas — las cuotas se mueven en minutos u segundos.
  - Requiere cuentas fondeadas en VARIAS casas (no solo una) para poder
    ejecutar ambas patas.
  - Las casas de apuestas detectan patrones de arbitraje y limitan o cierran
    cuentas que lo hacen seguido ("gubbing") — es un riesgo operativo real,
    no solo matemático.
  - Con cron cada 6h (la cadencia actual de Fase 7) este script solo sirve
    para ESTUDIAR cuán seguido aparecen oportunidades, no para capturarlas
    en la práctica — para eso se necesitaría polling de segundos/minutos,
    que consumiría la cuota gratis de The Odds API mucho más rápido.

Uso:
  python scripts/find_arbitrage.py
  python scripts/find_arbitrage.py --min-margin 0.5   # % mínimo de ganancia garantizada para reportar
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BACKEND_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import odds_client  # noqa: E402

LOG_PATH = BACKEND_DIR / "data" / "processed" / "arbitrage_scan_log.jsonl"

# Los exchanges (a diferencia de una casa de cuota fija) cobran comisión
# sobre lo GANADO, no reflejada en el "price" que devuelve la API — mezclar
# su cuota cruda con la de una casa de cuota fija sobreestima el margen
# real. Se excluyen por default; --include-exchanges los vuelve a sumar
# aplicándoles una comisión estimada conservadora.
EXCHANGE_BOOKS = {"betfair_ex_uk", "betfair_ex_eu", "betfair_ex_au", "matchbook", "smarkets"}
EXCHANGE_COMMISSION_PCT = 5.0  # conservador; Betfair varía 2-5% según volumen/cuenta


def find_best_odds_per_outcome(event: dict, include_exchanges: bool = False) -> dict[str, tuple[float, str]]:
    """Para cada resultado (nombre de jugador), la mejor cuota disponible y
    qué casa la ofrece, mirando TODAS las casas del evento (sin whitelist —
    a diferencia de odds_client.extract_book_odds, que sí filtra)."""
    best: dict[str, tuple[float, str]] = {}
    for bookmaker in event.get("bookmakers", []):
        book_key = bookmaker.get("key")
        is_exchange = book_key in EXCHANGE_BOOKS
        if is_exchange and not include_exchanges:
            continue
        for market in bookmaker.get("markets", []):
            if market.get("key") != "h2h":
                continue
            for outcome in market.get("outcomes", []):
                name = outcome.get("name")
                price = outcome.get("price")
                if name is None or price is None:
                    continue
                if is_exchange:
                    # Cuota neta de comisión: lo que "price" implica de
                    # ganancia (price - 1) se reduce por la comisión antes
                    # de convertirlo de nuevo a formato decimal.
                    price = 1 + (price - 1) * (1 - EXCHANGE_COMMISSION_PCT / 100)
                if name not in best or price > best[name][0]:
                    best[name] = (price, book_key)
    return best


def find_arbitrage_in_event(event: dict, include_exchanges: bool = False) -> dict | None:
    """None si no hay arbitraje (o faltan datos); si hay, devuelve el
    detalle con las dos mejores cuotas, el reparto de stake para ganancia
    garantizada, y el % de esa ganancia sobre el total apostado."""
    home = event.get("home_team")
    away = event.get("away_team")
    best = find_best_odds_per_outcome(event, include_exchanges=include_exchanges)

    if home not in best or away not in best:
        return None

    odds_home, book_home = best[home]
    odds_away, book_away = best[away]

    implied_sum = (1 / odds_home) + (1 / odds_away)
    if implied_sum >= 1:
        return None

    margin_pct = (1 - implied_sum) / implied_sum * 100
    stake_home_pct = (1 / odds_home) / implied_sum * 100
    stake_away_pct = (1 / odds_away) / implied_sum * 100

    return {
        "event_id": event.get("id"),
        "commence_time": event.get("commence_time"),
        "home_team": home,
        "away_team": away,
        "odds_home": odds_home,
        "book_home": book_home,
        "odds_away": odds_away,
        "book_away": book_away,
        "implied_prob_sum": implied_sum,
        "guaranteed_margin_pct": margin_pct,
        "stake_home_pct": stake_home_pct,
        "stake_away_pct": stake_away_pct,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-margin", type=float, default=0.0, help="Margen mínimo (%%) para reportar una oportunidad")
    parser.add_argument(
        "--include-exchanges", action="store_true",
        help="Incluir exchanges (Betfair Exchange, Matchbook, Smarkets) aplicándoles una comisión estimada del "
             f"{EXCHANGE_COMMISSION_PCT}%%. Por default se excluyen: mezclar su cuota cruda con la de una casa de "
             "cuota fija sobreestima el margen real.",
    )
    args = parser.parse_args()

    api_key = odds_client.get_api_key()

    print("1. Buscando torneos ATP activos en The Odds API...")
    sport_keys = odds_client.list_active_tennis_sport_keys(api_key)
    if not sport_keys:
        print("   Ninguno activo ahora mismo (no cubre ATP 250, es normal en semanas sin Slam/1000/500).")
        return
    print(f"   {len(sport_keys)} torneo(s) activo(s): {sport_keys}")

    opportunities: list[dict] = []
    events_scanned = 0
    for sport_key in sport_keys:
        print(f"\n2. Escaneando cuotas de {sport_key}...")
        events = odds_client.get_odds(sport_key, api_key)
        events_scanned += len(events)
        for event in events:
            opp = find_arbitrage_in_event(event, include_exchanges=args.include_exchanges)
            if opp is not None and opp["guaranteed_margin_pct"] >= args.min_margin:
                opp["sport_key"] = sport_key
                opportunities.append(opp)

    print(f"\n{events_scanned} partido(s) escaneados, {len(opportunities)} oportunidad(es) de arbitraje encontradas.")

    if opportunities:
        for opp in sorted(opportunities, key=lambda o: o["guaranteed_margin_pct"], reverse=True):
            print(
                f"\n  {opp['home_team']} vs {opp['away_team']} ({opp['sport_key']})\n"
                f"    {opp['home_team']}: cuota {opp['odds_home']} en {opp['book_home']} "
                f"-> {opp['stake_home_pct']:.1f}% del stake\n"
                f"    {opp['away_team']}: cuota {opp['odds_away']} en {opp['book_away']} "
                f"-> {opp['stake_away_pct']:.1f}% del stake\n"
                f"    Ganancia garantizada: {opp['guaranteed_margin_pct']:.2f}% "
                f"(si podés cargar ambas apuestas a estas cuotas antes de que cambien)"
            )

        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        scanned_at = datetime.now(timezone.utc).isoformat()
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            for opp in opportunities:
                fh.write(json.dumps({"scanned_at": scanned_at, **opp}, ensure_ascii=False) + "\n")
        print(f"\nGuardado en {LOG_PATH}")
    else:
        print("Nada por ahora — normal, no es un fallo del script. Las oportunidades de arbitraje son raras "
              "entre casas grandes/eficientes (Pinnacle, Bet365, etc.); si aparecen, suele ser en casas más "
              "chicas o mercados con poca liquidez.")


if __name__ == "__main__":
    main()
