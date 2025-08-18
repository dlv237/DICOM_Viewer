# Makefile for DICOM_Viewer monorepo

SHELL := /bin/bash
COMPOSE := docker compose
DEV_FILES := -f docker-compose.yml -f docker-compose.dev.yml

.PHONY: help build rebuild up down clean logs ps restart dev dev-down backend-shell frontend-shell smoke install-frontend run-frontend run-backend

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
