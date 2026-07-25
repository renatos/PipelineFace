#!/bin/bash
# ============================================================
# PipelineFace — Script de Inicialização da Aplicação Web
# ============================================================
# Uso:
#   ./scripts/start-web.sh
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}  🧠 PipelineFace — Aplicação Web (FastAPI) ${NC}"
echo -e "${BLUE}============================================${NC}"

# Garantir que o MongoDB está rodando
if ! podman ps 2>/dev/null | grep -q "mongo"; then
    echo -e "${YELLOW}Iniciando banco de dados MongoDB...${NC}"
    podman-compose up -d mongodb 2>/dev/null || podman run -d --name pipelineface_mongodb -p 27017:27017 -v "${PROJECT_DIR}/mongo-data:/data/db" docker.io/library/mongo:7.0 2>/dev/null || true
    sleep 2
fi

echo -e "${GREEN}✅ MongoDB ativo na porta 27017.${NC}"
echo -e "${BLUE}Iniciando servidor web em http://localhost:8000 ...${NC}"
echo ""

python3 web/server.py
