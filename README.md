# DICOM Viewer Monorepo

Este monorepo contiene:
- backend/: API FastAPI con DuckDB
- frontend/: React + Vite (TypeScript)
- docker-compose.yml: orquestación de ambos servicios

## Requisitos
- Docker y Docker Compose

## Ejecutar con Docker Compose

```bash
docker compose build
docker compose up -d
```

- Backend: http://localhost:8000/health
- Frontend: http://localhost:5173

El frontend llama al backend vía `/api` (proxy de Vite en dev) o `VITE_API_URL` cuando se construye en Docker.

## Desarrollo local (opcional)

Backend:
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 --app-dir backend
```

Frontend:
```bash
cd frontend
npm install
npm run dev
```

## Modo desarrollo con Docker (hot reload)

Para evitar rebuilds de contenedores en cada cambio, usa el overlay dev que monta el código y corre servidores en modo watch:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

- Backend: Uvicorn con `--reload` recargará al editar `backend/app/main.py` y demás archivos.
- Frontend: Vite `npm run dev` soporta hot module replacement; al editar `frontend/src/**/*` se recarga automáticamente.

Detener:
```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml down
```

## Notas
- La base de datos DuckDB persiste en el volumen `duckdb_data`.
- Cambia `VITE_API_URL` en `docker-compose.yml` si el backend corre en otra URL.
