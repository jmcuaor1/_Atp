FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-api.txt requirements-train.txt ./
RUN pip install --no-cache-dir -r requirements-train.txt

COPY app ./app
COPY api.py .
COPY src ./src
COPY scripts ./scripts
# Los artefactos se montan en runtime (./backend/models) o se generan con el perfil train
RUN mkdir -p models data/raw

ENV LOG_LEVEL=INFO
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')" || exit 1

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
