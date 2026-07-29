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
echo -e "${BLUE}Garantindo que o container do MongoDB está ativo (porta 27017)...${NC}"
podman start pipelineface_mongodb 2>/dev/null || podman run -d --name pipelineface_mongodb -p 27017:27017 -v "${PROJECT_DIR}/mongo-data:/data/db" docker.io/library/mongo:7.0 2>/dev/null || true
sleep 1

# 2. Garantir que o Whisper ASR está rodando (porta 9000)
echo -e "${BLUE}Garantindo que o container do Whisper ASR está ativo (porta 9000)...${NC}"
podman start pipelineface_whisper_1 2>/dev/null || podman run -d --name pipelineface_whisper_1 -p 9000:9000 -e ASR_MODEL=base docker.io/onerahmet/openai-whisper-asr-webservice:latest 2>/dev/null || true
sleep 1

# 3. Garantir que o Scraper está rodando
echo -e "${BLUE}Garantindo que o container do Scraper está ativo...${NC}"
podman start pipelineface_scraper_1 2>/dev/null || true
sleep 1

# 4. Subir/Reiniciar o container da Aplicação Web
echo -e "${BLUE}Subindo container da aplicação Web (com FFmpeg & Playwright)...${NC}"
if ! podman image exists pipelineface_app:latest; then
    podman build -t pipelineface_app:latest .
fi

podman rm -f pipelineface_web_app 2>/dev/null || true
podman run -d --name pipelineface_web_app -e TZ=America/Sao_Paulo --network host -v "${PROJECT_DIR}:/app" pipelineface_app:latest >/dev/null

echo -e "${GREEN}======================================================${NC}"
echo -e "${GREEN}✅ Todos os containers ativos com sucesso!${NC}"
echo -e "${GREEN}  🟢 MongoDB:     mongodb://localhost:27017${NC}"
echo -e "${GREEN}  🎙️  Whisper REST: http://localhost:9000/asr${NC}"
echo -e "${GREEN}  🌐 Aplicação Web: http://localhost:8000${NC}"
echo -e "${GREEN}======================================================${NC}"

