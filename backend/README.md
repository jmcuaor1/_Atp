# TennisAI Backend

API FastAPI para predicción de partidos ATP.

## Instalación (API)

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements-api.txt
cp .env.example .env
```

## Entrenar modelo

Descarga automática de CSV oficiales:

```bash
pip install -r requirements-train.txt
python scripts/download_atp_data.py --start-year 2015 --end-year 2024
python src/model.py
```

O todo en uno:

```bash
python scripts/setup_project.py
```

Genera `models/tennis_model.pkl` y `models/player_profiles.pkl`.

## Ejecutar API

```bash
uvicorn api:app --reload --host 0.0.0.0 --port 8000
```

Documentación interactiva: http://localhost:8000/docs

## Endpoints

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/health` | Estado del servicio |
| POST | `/predict` | Predicción entre dos jugadores |
| GET | `/players/search?q=` | Buscar jugadores |
| GET | `/players/{id}` | Perfil de jugador |
| GET | `/surfaces` | Superficies válidas |
| GET | `/model/info` | Metadatos del modelo |

## Tests

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

## Docker

Desde la raíz del proyecto (`_Atp/`):

```bash
docker compose --profile setup run --rm download-data
docker compose --profile setup run --rm train
docker compose up --build
```
