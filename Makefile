# Makefile for DICOM_Viewer monorepo

SHELL := /bin/bash
COMPOSE := docker compose
DEV_FILES := -f docker-compose.yml -f docker-compose.dev.yml
USERHOST ?= dolobos@maicolpue.ing.puc.cl
FRONTEND_PORT ?= 5173

# Default path to write the DuckDB file locally (can be overridden by setting DUCKDB_PATH env)
DUCKDB_PATH ?= /mnt/nas_anakena/datasets/uc-cxr/processed_data/app.duckdb

.PHONY: help build rebuild up down clean logs ps restart dev dev-down backend-shell frontend-shell smoke install-frontend run-frontend run-backend build-db build-db-local deploy-backend tunnel \
	frontend-pm2-start frontend-pm2-restart frontend-pm2-logs frontend-pm2-stop

help: ## Mostrar esta ayuda
	@echo "Comandos disponibles:" && \
	grep -E '^[a-zA-Z0-9_.-]+:.*?## ' Makefile | awk -F':|##' '{printf "  %-18s %s\n", $$1, $$3}'

build: ## Build de imágenes (producción)
	$(COMPOSE) build

rebuild: ## Rebuild sin caché
	$(COMPOSE) build --no-cache

up: ## Levantar stack (producción)
	$(COMPOSE) up -d

down: ## Bajar stack (producción)
	$(COMPOSE) down

clean: ## Bajar y eliminar volúmenes/huérfanos
	$(COMPOSE) down -v --remove-orphans

logs: ## Seguir logs
	$(COMPOSE) logs -f

ps: ## Listar contenedores
	$(COMPOSE) ps

restart: ## Reiniciar servicios
	$(COMPOSE) restart

dev: ## Modo desarrollo con hot-reload (Uvicorn --reload + Vite dev)
	$(COMPOSE) $(DEV_FILES) up -d --build

dev-down: ## Detener modo desarrollo
	$(COMPOSE) $(DEV_FILES) down

backend-shell: ## Entrar al contenedor backend (sh)
	$(COMPOSE) exec backend sh

frontend-shell: ## Entrar al contenedor frontend (sh)
	$(COMPOSE) exec frontend sh

smoke: ## Prueba rápida de salud (requiere stack corriendo)
	bash scripts/smoke.sh

install-frontend: ## Instalar dependencias del frontend localmente
	cd frontend && npm install

run-frontend: ## Ejecutar Vite dev localmente (sin Docker)
	cd frontend && npm run dev

run-backend: ## Ejecutar backend localmente (sin Docker) con reload
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 --app-dir backend

build-db: ## Construir/recargar DuckDB dentro de contenedor (usa overlay dev para montar ./data)
	$(COMPOSE) $(DEV_FILES) run --rm backend python -m app.load_data

build-db-local: ## Construir DuckDB localmente (requiere venv y deps instaladas)
	@echo "Using DUCKDB_PATH=${DUCKDB_PATH}"
	PYTHONPATH=backend DUCKDB_PATH=${DUCKDB_PATH} python3 backend/app/load_data.py

deploy-backend: ## Pull, install deps, and restart systemd service
	cd /home/dolobos/DICOM_Viewer && \
		git pull && \
		. .venv/bin/activate && \
		pip install -r backend/requirements.txt && \
		sudo systemctl restart dicom-backend

tunnel:
	ssh -L 8000:localhost:8000 -L 5173:localhost:5173 $(USERHOST)

FRONTEND_PORT ?= 5173

.PHONY: frontend-pm2-start frontend-pm2-restart frontend-pm2-logs frontend-pm2-stop

frontend-pm2-start: ## Build y levantar frontend en pm2 (vite preview)
	cd frontend && npm ci && npm run build
	pm2 start npm --name dicom-frontend --cwd ./frontend -- run preview -- --host 0.0.0.0 --port $(FRONTEND_PORT)
	pm2 save

frontend-pm2-restart: ## Reiniciar (o crear si no existe) el frontend en pm2
	pm2 restart dicom-frontend || ( $(MAKE) frontend-pm2-start )

frontend-pm2-logs: ## Ver logs del frontend en pm2
	pm2 logs dicom-frontend

frontend-pm2-stop: ## Detener y borrar proceso pm2 del frontend
	-pm2 stop dicom-frontend
	-pm2 delete dicom-frontend

frontend-pm2-static: ## Servir build estático con 'serve'
	cd frontend && npm ci && npm run build
	pm2 start serve --name dicom-frontend --frontend/dist --single --listen $(FRONTEND_PORT)
	pm2 save