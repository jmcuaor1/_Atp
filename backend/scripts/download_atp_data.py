#!/usr/bin/env python3
"""
Descarga partidos ATP desde el repositorio público de Jeff Sackmann.
https://github.com/JeffSackmann/tennis_atp

Uso:
  python scripts/download_atp_data.py
  python scripts/download_atp_data.py --start-year 2018 --end-year 2024
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE_URL = "https://raw.githubusercontent.com/JeffSackmann/tennis_atp/master"


def download_file(url: str, destination: Path) -> bool:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size > 0:
        print(f"  [ok] Ya existe: {destination.name}")
        return True

    print(f"  [..] Descargando {destination.name}...")
    try:
        urllib.request.urlretrieve(url, destination)
        return True
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            print(f"  [x] No disponible ({exc.code}): {url}")
        else:
            print(f"  [x] Error HTTP {exc.code}: {url}")
        return False
    except urllib.error.URLError as exc:
        print(f"  [x] Error de red: {exc.reason}")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Descargar CSV de partidos ATP")
    parser.add_argument(
        "--start-year",
        type=int,
        default=2015,
        help="Primer año a descargar (default: 2015)",
    )
    parser.add_argument(
        "--end-year",
        type=int,
        default=2024,
        help="Último año a descargar (default: 2024)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Carpeta de salida (default: backend/data/raw)",
    )
    args = parser.parse_args()

    backend_dir = Path(__file__).resolve().parent.parent
    output_dir = args.output or (backend_dir / "data" / "raw")

    if args.start_year > args.end_year:
        print("Error: start-year no puede ser mayor que end-year")
        return 1

    print(f"Destino: {output_dir}")
    print(f"Años: {args.start_year}–{args.end_year}\n")

    ok_count = 0
    for year in range(args.start_year, args.end_year + 1):
        filename = f"atp_matches_{year}.csv"
        url = f"{BASE_URL}/{filename}"
        dest = output_dir / filename
        if download_file(url, dest):
            ok_count += 1

    print(f"\nListo: {ok_count} archivos en {output_dir}")
    if ok_count == 0:
        print("No se descargó ningún archivo. Comprueba tu conexión.")
        return 1

    print("\nSiguiente paso: entrenar el modelo")
    print("  python src/model.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
