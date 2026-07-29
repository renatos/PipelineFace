#!/bin/bash
# ============================================================
# PipelineFace — Script para Encerrar Todos os Serviços
# ============================================================
# Uso:
#   ./scripts/stop-web.sh
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}======================================================${NC}"
echo -e "${BLUE}  🛑 Parando Todos os Serviços (PipelineFace)        ${NC}"
echo -e "${BLUE}======================================================${NC}"

# Tentar parar via podman-compose
podman-compose down 2>/dev/null || true

# Forçar remoção de qualquer container estritamente associado ao pipelineface
echo -e "${YELLOW}Encerrando containers remanescentes...${NC}"
podman rm -f pipelineface_web_app pipelineface_mongodb pipelineface_mongodb_1 pipelineface_whisper pipelineface_whisper_1 pipelineface_scraper pipelineface_scraper_1 2>/dev/null || true

echo -e "${GREEN}======================================================${NC}"
echo -e "${GREEN}✅ Todos os containers foram encerrados com sucesso!${NC}"
echo -e "${GREEN}======================================================${NC}"
