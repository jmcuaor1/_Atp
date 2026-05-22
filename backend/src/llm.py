import os
from dotenv import load_dotenv

load_dotenv()

_client = None


def _get_client():
    global _client
    if _client is None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError(
                "GROQ_API_KEY no encontrada. Crea un archivo .env con GROQ_API_KEY=tu_clave"
            )
        from groq import Groq
        _client = Groq(api_key=api_key)
    return _client


def explain_prediction(player1: str, player2: str, surface: str, prediction: dict) -> str:
    feats = prediction["features"]
    winner = prediction["winner"]
    prob = prediction["probability"]

    h2h_total = feats["h2h_p1"] + feats["h2h_p2"]
    h2h_str = (
        f"Historial H2H: {player1} {feats['h2h_p1']}-{feats['h2h_p2']} {player2}. "
        if h2h_total > 0 else ""
    )

    prompt = (
        "Eres un analista experto en tenis ATP. "
        "Explica en 3-4 oraciones en español la siguiente predicción de partido. "
        "Sé conciso y menciona los factores clave.\n\n"
        f"Partido: {player1} vs {player2} en superficie {surface}.\n"
        f"Predicción: {winner} gana con {prob:.0%} de probabilidad.\n"
        f"{player1} — ranking: #{int(feats['rank_p1'])}, "
        f"tasa victorias en {surface}: {feats['win_rate_p1']:.0%} ({feats['matches_p1']} partidos).\n"
        f"{player2} — ranking: #{int(feats['rank_p2'])}, "
        f"tasa victorias en {surface}: {feats['win_rate_p2']:.0%} ({feats['matches_p2']} partidos).\n"
        f"{h2h_str}"
    )

    client = _get_client()
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=250,
        temperature=0.6,
    )
    return response.choices[0].message.content.strip()
