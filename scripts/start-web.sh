#!/bin/bash
# ============================================================
# PipelineFace — Script de Inicialização da Aplicação & Serviços
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
echo -e "${BLUE}  🧠 PipelineFace — Inicializando Serviços (Compose) ${NC}"
echo -e "${BLUE}======================================================${NC}"

# Parar/remover containers legados para evitar conflitos de portas
podman rm -f pipelineface_web_app pipelineface_mongodb pipelineface_mongodb_1 pipelineface_whisper pipelineface_whisper_1 pipelineface_scraper pipelineface_scraper_1 2>/dev/null || true

# Iniciar ou subir toda a pilha declarada no docker-compose.yml via podman-compose
podman-compose up -d

echo -e "${GREEN}======================================================${NC}"
echo -e "${GREEN}✅ Pilha de containers ativa com sucesso!${NC}"
echo -e "${GREEN}  🟢 MongoDB:     mongodb://localhost:27017${NC}"
echo -e "${GREEN}  🎙️  Whisper REST: http://localhost:9000/asr${NC}"
echo -e "${GREEN}  🌐 Aplicação Web: http://localhost:8000${NC}"
echo -e "${GREEN}======================================================${NC}"
