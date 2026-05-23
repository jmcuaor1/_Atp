#!/usr/bin/env python3
"""
Configuración inicial: descarga datos + entrena modelo.
Uso: python scripts/setup_project.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def run(cmd: list[str], cwd: Path) -> None:
    print(f"\n>>> {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def main() -> int:
    backend_dir = Path(__file__).resolve().parent.parent
    scripts_dir = backend_dir / "scripts"

    print("=== TennisAI — configuración inicial ===\n")

    run([sys.executable, str(scripts_dir / "download_atp_data.py")], backend_dir)
    run([sys.executable, str(backend_dir / "src" / "model.py")], backend_dir)

    model_path = backend_dir / "models" / "tennis_model.pkl"
    if model_path.is_file():
        print(f"\n[ok] Proyecto listo. Modelo en: {model_path}")
        print("  Inicia la API: uvicorn api:app --reload")
    else:
        print("\n[x] No se genero el modelo. Revisa los CSV en data/raw/")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
