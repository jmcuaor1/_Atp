# TennisAI

Plataforma de predicción de partidos ATP con machine learning (XGBoost calibrado) y frontend Next.js.

## Requisitos

- **Python 3.11+** (recomendado; 3.14 puede dar conflictos con algunas dependencias)
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
python scripts/download_atp_data.py --start-year 2015 --end-year 2024
python src/model.py
```

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

## Estructura del proyecto

```
_Atp/
├── backend/
│   ├── app/              # API FastAPI (routers, servicios)
│   ├── src/              # Features ML y entrenamiento
│   ├── scripts/          # Descarga de datos y setup
│   ├── models/           # tennis_model.pkl, player_profiles.pkl
│   └── data/raw/         # CSV ATP
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

Los CSV provienen del repositorio [tennis_atp](https://github.com/JeffSackmann/tennis_atp) (datos históricos ATP). No uses el scraper antiguo (`src/scraper.py`); está deprecado.

## Licencia

Uso educativo / personal. Los datos ATP pertenecen a sus respectivos titulares; revisa las condiciones del repositorio de datos antes de un uso comercial.
