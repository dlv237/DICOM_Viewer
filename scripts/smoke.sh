#!/usr/bin/env bash
set -euo pipefail

# Simple smoke script to validate backend API and frontend build locally

# Backend health
curl -sf http://localhost:8000/health | jq . || curl -sf http://localhost:8000/health

# Frontend index
curl -sI http://localhost:5173 | head -n 1
