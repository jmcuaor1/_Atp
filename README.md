# TennisAI

Plataforma de predicción de partidos ATP con machine learning (XGBoost calibrado sobre Elo dinámico, rolling stats y fatiga reciente) y frontend Next.js.

**Estado actual: funcional y honesto, pero sin edge confirmado para apostar.** El modelo predice con 65.9% de accuracy y probabilidades razonablemente calibradas, pero al compararlo contra cuotas reales de mercado (ver [`backend/scripts/backtest_odds.py`](backend/scripts/backtest_odds.py)) el mercado sigue siendo más preciso. Ver [Estado del modelo](#estado-del-modelo-y-viabilidad-para-apostar) más abajo antes de usar esto para apostar dinero real.

## Requisitos

- **Python 3.11+** (probado también con 3.14)
- **Node.js 20+**
- Opcional: **Docker** y **Docker Compose**

## Inicio rápido (local)

### 1. Configurar el backend (datos + modelo)

```bash
cd backend
python -m venv venv
# Windows: venv\Scripts\activate
# Linux/macOS: source venv/bin/activate

pip install -r requirements-train.txt

# Descargar CSV oficiales (Jeff Sackmann) y entrenar
python scripts/setup_project.py
```

O por pasos:

```bash
python scripts/download_atp_data.py --start-year 2010 --end-year 2024
python src/model.py
```

(`src/model.py` solo entrena con partidos desde 2010 aunque descargues años anteriores — antes de esa fecha el ranking ATP es poco confiable, ver `MIN_YEAR` en el script.)

### 2. Arrancar la API

```bash
cd backend
pip install -r requirements-api.txt
cp .env.example .env
uvicorn api:app --reload --port 8000
```

Documentación: http://localhost:8000/docs

### 3. Arrancar el frontend

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

Abre http://localhost:3000

## Docker Compose

**Primera vez** (descargar datos y entrenar en tu máquina):

```bash
docker compose --profile setup run --rm download-data
docker compose --profile setup run --rm train
```

**Uso diario** (API + web):

```bash
docker compose up --build
```

- Frontend: http://localhost:3000  
- API: http://localhost:8000  
- Health: http://localhost:8000/health  

Los modelos se leen desde `backend/models/` (montado en el contenedor).

## Estado del modelo y viabilidad para apostar

Métricas reales del modelo actual (2010-2024, split cronológico 80/20, ver `backend/models/tennis_model.pkl` → `metadata`):

| Métrica | Valor |
|---|---|
| Accuracy (test) | 65.86% |
| Brier Score (test) | 0.2122 |
| Accuracy walk-forward (2020-2024, por temporada) | 65.3%–67.2% (estable, sin rachas) |
| Baseline (regresión logística sobre ranking) | 64% |

El modelo supera al baseline de ranking por apenas ~2 puntos. Más importante: al compararlo contra **cuotas históricas reales** de mercado (`tennis-data.co.uk`, 2022-2024) con `backend/scripts/backtest_odds.py`, el mercado le gana en Brier, log-loss y accuracy, y una simulación de apuesta (apostando solo donde el modelo veía valor esperado positivo) da un ROI de **-11.76% por apuesta**. Es decir: preciso, pero no rentable contra las casas de apuestas tal como está hoy.

Para reproducir el backtest necesitas descargar las cuotas manualmente (no se versionan en el repo por copyright del proveedor):

```bash
mkdir -p backend/data/odds
curl -o backend/data/odds/2022.xlsx http://www.tennis-data.co.uk/2022/2022.xlsx
curl -o backend/data/odds/2023.xlsx http://www.tennis-data.co.uk/2023/2023.xlsx
curl -o backend/data/odds/2024.xlsx http://www.tennis-data.co.uk/2024/2024.xlsx
python backend/scripts/backtest_odds.py
```

Validación por temporada (¿el resultado es estable o una racha?):

```bash
python backend/scripts/walk_forward_validate.py
```

**¿Hay algún segmento (superficie, torneo, favorito/underdog, book) donde sí
haya edge?** Se probaron 69 combinaciones de segmento × book sobre 2022-2024
con un split discovery (2022-2023) / confirmación holdout (2024) para no
confundir ruido de muestra chica con edge real. Resultado: **ninguna** tuvo
ROI con intervalo de confianza positivo en ambos períodos a la vez. Detalle
completo y metodología en
[`backend/data/processed/segment_decision.md`](backend/data/processed/segment_decision.md).

```bash
python backend/scripts/segment_backtest.py
```

### Fase 7: CLV en vivo (hacia adelante, sin resultado todavía)

Todo lo anterior es backtest histórico. Para saber si el modelo tiene edge
*en la práctica*, no solo contra datos pasados, `scripts/fetch_live_odds.py`
trae cuotas en vivo de [The Odds API](https://the-odds-api.com) para
partidos ATP activos, las cruza con una predicción real (llamando al propio
`/predict`), y deja todo registrado en `data/processed/live_odds_log.jsonl`.
Más adelante, cuando esos partidos ya se jugaron, `scripts/settle_live_odds.py`
trae el resultado y calcula el ROI real acumulado.

**Cobertura parcial**: el tier gratis de The Odds API cubre Grand Slam,
ATP 1000, ATP 500, WTA 1000 y WTA 500 — **no ATP 250**, así que en varias
semanas del calendario no va a haber ningún torneo ATP activo para trackear.

```bash
# 1. Conseguir un API key gratis en https://the-odds-api.com y agregarlo a backend/.env
#    (ODDS_API_KEY=..., ver .env.example)
# 2. Con la API real corriendo (uvicorn api:app --reload):
python backend/scripts/fetch_live_odds.py

# 3. Días/semanas después, cuando esos partidos ya se jugaron:
python backend/scripts/settle_live_odds.py
```

Esto **no tiene conclusión todavía** — a diferencia de las Fases 1-6, acá
hay que dejarlo correr y acumular apuestas sentenciadas con el tiempo (ver
el umbral de muestra mínima usado en Fase 6) antes de que el ROI reportado
signifique algo.

## Estructura del proyecto

```
_Atp/
├── backend/
│   ├── app/              # API FastAPI (routers, servicios)
│   ├── src/              # Features ML (Elo, rolling stats, fatiga) y entrenamiento
│   ├── scripts/
│   │   ├── download_atp_data.py     # Descarga CSV oficiales (Jeff Sackmann)
│   │   ├── setup_project.py         # Descarga + entrena en un paso
│   │   ├── backtest_odds.py         # Modelo vs. cuotas reales de mercado
│   │   ├── segment_backtest.py      # Busca segmentos con edge (Fase 6)
│   │   ├── fetch_live_odds.py       # Captura cuotas en vivo (Fase 7)
│   │   ├── settle_live_odds.py      # Sentencia apuestas en vivo (Fase 7)
│   │   └── walk_forward_validate.py # Validación por temporada
│   ├── models/            # tennis_model.pkl, player_profiles.pkl (generados)
│   └── data/
│       ├── raw/            # CSV ATP (Jeff Sackmann)
│       ├── odds/            # Cuotas históricas (no versionado, descarga manual)
│       └── processed/       # Curva de calibración, detalle de backtests
├── frontend/             # Next.js + shadcn/ui
└── docker-compose.yml
```

## API principal

| Endpoint | Descripción |
|----------|-------------|
| `GET /health` | Estado del servicio |
| `POST /predict` | Predicción entre dos jugadores |
| `GET /players/search?q=` | Buscar jugador por nombre |
| `GET /players/{id}` | Perfil del jugador |
| `GET /model/info` | Métricas del modelo |

## Tests

```bash
cd backend
pip install -r requirements-dev.txt
set TESTING=true          # Windows
export TESTING=true       # Linux/macOS
pytest tests/ -v
```

## Variables de entorno

| Variable | Ubicación | Descripción |
|----------|-----------|-------------|
| `NEXT_PUBLIC_API_URL` | frontend `.env.local` | URL del backend |
| `CORS_ORIGINS` | backend `.env` | Orígenes permitidos |
| `MODEL_PATH` | backend `.env` | Ruta al `.pkl` (opcional) |

## Datos

- Resultados y estadísticas de partidos: repositorio [tennis_atp](https://github.com/JeffSackmann/tennis_atp) de Jeff Sackmann (datos históricos ATP).
- Cuotas históricas para el backtest: [tennis-data.co.uk](http://www.tennis-data.co.uk) (uso libre para desarrollo/análisis de sistemas de apuestas; los archivos no se redistribuyen en este repo por el copyright del proveedor sobre el formato de sus planillas — se descargan aparte, ver [Estado del modelo](#estado-del-modelo-y-viabilidad-para-apostar)).
