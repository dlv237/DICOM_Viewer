# syntax=docker/dockerfile:1
FROM python:3.11-slim

# Install build deps (if needed by duckdb) and runtime deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Create non-root user
RUN useradd -m appuser

# App code
COPY backend /app

# Data folder for DuckDB
RUN mkdir -p /data && chown -R appuser:appuser /data && chown -R appuser:appuser /app

ENV DUCKDB_PATH=/data/app.duckdb
ENV PORT=8000

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
