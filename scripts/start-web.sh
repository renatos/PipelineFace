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
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}======================================================${NC}"
echo -e "${BLUE}  🧠 PipelineFace — Aplicação Web & Pipeline (Podman) ${NC}"
echo -e "${BLUE}======================================================${NC}"

# 1. Garantir que o MongoDB está rodando (inicia existente ou cria novo se não existir)
echo -e "${BLUE}Garantindo que o container do MongoDB está ativo...${NC}"
podman start pipelineface_mongodb 2>/dev/null || podman run -d --name pipelineface_mongodb -p 27017:27017 -v "${PROJECT_DIR}/mongo-data:/data/db" docker.io/library/mongo:7.0 2>/dev/null || true
sleep 1

# 2. Subir/Reiniciar o container da Aplicação Web com volume montado
echo -e "${BLUE}Subindo container da aplicação Web (com FFmpeg & Playwright)...${NC}"
if ! podman image exists pipelineface_app:latest; then
    podman build -t pipelineface_app:latest .
fi

podman rm -f pipelineface_web_app 2>/dev/null || true
podman run -d --name pipelineface_web_app --network host -v "${PROJECT_DIR}:/app" pipelineface_app:latest >/dev/null

echo -e "${GREEN}======================================================${NC}"
echo -e "${GREEN}✅ Aplicação Web (FFmpeg + Playwright) e MongoDB ativos!${NC}"
echo -e "${GREEN}🌐 Acesse no seu navegador: http://localhost:8000${NC}"
echo -e "${GREEN}======================================================${NC}"
