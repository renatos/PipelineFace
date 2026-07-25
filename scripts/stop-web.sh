#!/bin/bash
# ============================================================
# PipelineFace — Script para Parar a Aplicação Web & MongoDB
# ============================================================
# Uso:
#   ./scripts/stop-web.sh
# ============================================================

set -euo pipefail

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}======================================================${NC}"
echo -e "${BLUE}  🛑 Parando Aplicação Web & MongoDB (PipelineFace)   ${NC}"
echo -e "${BLUE}======================================================${NC}"

# 1. Parar container da Aplicação Web
if podman ps 2>/dev/null | grep -q "pipelineface_web_app"; then
    echo -e "${YELLOW}Parando container da aplicação web (pipelineface_web_app)...${NC}"
    podman stop pipelineface_web_app >/dev/null 2>&1 || true
fi

# 2. Parar container do MongoDB
if podman ps 2>/dev/null | grep -q "mongo"; then
    echo -e "${YELLOW}Parando container do banco MongoDB (pipelineface_mongodb)...${NC}"
    podman stop pipelineface_mongodb pipelineface_mongodb_1 >/dev/null 2>&1 || true
fi

echo -e "${GREEN}======================================================${NC}"
echo -e "${GREEN}✅ Todos os containers foram encerrados com sucesso!${NC}"
echo -e "${GREEN}======================================================${NC}"
