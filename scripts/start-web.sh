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

# 1. Garantir que o MongoDB está rodando
if ! podman ps 2>/dev/null | grep -q "mongo"; then
    echo -e "${BLUE}Iniciando container do MongoDB...${NC}"
    podman run -d --name pipelineface_mongodb -p 27017:27017 -v "${PROJECT_DIR}/mongo-data:/data/db" docker.io/library/mongo:7.0 2>/dev/null || true
    sleep 2
fi

# 2. Subir o container da Aplicação Web com o código mapeado via volume (sem necessidade de reconstruir imagem a cada alteração)
if ! podman ps 2>/dev/null | grep -q "pipelineface_web_app"; then
    echo -e "${BLUE}Subindo container da aplicação Web (com FFmpeg & Playwright)...${NC}"
    if ! podman image exists pipelineface_app:latest; then
        podman build -t pipelineface_app:latest .
    fi
    podman rm -f pipelineface_web_app 2>/dev/null || true
    podman run -d --name pipelineface_web_app --network host -v "${PROJECT_DIR}:/app" pipelineface_app:latest >/dev/null
fi

echo -e "${GREEN}======================================================${NC}"
echo -e "${GREEN}✅ Aplicação Web (FFmpeg + Playwright) e MongoDB ativos!${NC}"
echo -e "${GREEN}🌐 Acesse no seu navegador: http://localhost:8000${NC}"
echo -e "${GREEN}======================================================${NC}"
