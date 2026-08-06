#!/usr/bin/env python3
"""
Fase 7 — manda un email una sola vez cuando data/processed/live_odds_settled.csv
llega a 150 apuestas liquidadas (el mínimo que la Fase 6 ya estableció para
que el intervalo de confianza del ROI sea confiable, ver segment_decision.md).
Pensado para correr al final de cron_weekly_summary.sh.

Requiere en backend/.env:
  GMAIL_ADDRESS, GMAIL_APP_PASSWORD (remitente, app password de Gmail)
  NOTIFY_EMAIL_TO (destinatario)

Uso:
  python scripts/notify_threshold.py          # chequeo normal
  python scripts/notify_threshold.py --test   # manda un correo de prueba y listo
"""

from __future__ import annotations

import os
import smtplib
import sys
from email.mime.text import MIMEText
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = BACKEND_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from segment_backtest import bootstrap_roi_ci  # noqa: E402

load_dotenv(BACKEND_DIR / ".env")

SETTLED_PATH = BACKEND_DIR / "data" / "processed" / "live_odds_settled.csv"
FLAG_PATH = BACKEND_DIR / "data" / "processed" / "threshold_150_notified.flag"
THRESHOLD = 150


def send_email(subject: str, body: str) -> None:
    sender = os.environ["GMAIL_ADDRESS"]
    password = os.environ["GMAIL_APP_PASSWORD"]
    recipient = os.environ["NOTIFY_EMAIL_TO"]

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(sender, password)
        server.send_message(msg)


def main() -> None:
    if "--test" in sys.argv:
        send_email(
            "TennisAI — prueba de notificación (Fase 7)",
            "Correo de prueba del cron semanal de la Fase 7. Si llegó, el envío funciona.",
        )
        print("Correo de prueba enviado.")
        return

    if FLAG_PATH.exists():
        print("Ya se avisó una vez (ver threshold_150_notified.flag), no se repite.")
        return

    if not SETTLED_PATH.exists():
        print("Todavía no existe live_odds_settled.csv.")
        return

    df = pd.read_csv(SETTLED_PATH)
    n = len(df)
    if n < THRESHOLD:
        print(f"n={n} apuestas liquidadas, todavía no llega al umbral de {THRESHOLD}.")
        return

    payouts = df["payout"].to_numpy(dtype=float)
    roi = float(payouts.mean() * 100)
    ci_low, ci_high = bootstrap_roi_ci(payouts, n_boot=2000)

    body = (
        f"Se llegó a {n} apuestas liquidadas en la Fase 7 (CLV en vivo) — "
        f"ya hay muestra suficiente para sacar una conclusión con la misma vara "
        f"que la Fase 6 (mínimo 150 apuestas).\n\n"
        f"ROI acumulado: {roi:.2f}%\n"
        f"Intervalo de confianza 95% (bootstrap): {ci_low:.2f}% a {ci_high:.2f}%\n\n"
        f"Detalle completo en backend/data/processed/weekly_summary.txt, "
        f"o pedile a Claude el veredicto go/no-go completo."
    )
    send_email(f"TennisAI — se llegó a {n} apuestas (umbral de 150 alcanzado)", body)
    FLAG_PATH.write_text(f"Notificado el {pd.Timestamp.now(tz='UTC').isoformat()} con n={n}\n")
    print(f"Correo enviado, n={n}.")


if __name__ == "__main__":
    main()
