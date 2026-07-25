#!/bin/bash
# Torne este script executável executando: chmod +x check-status.sh

# Definindo cores
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

PROJECT_ROOT=$(cd "$(dirname "$0")/.." && pwd)

echo -e "${BLUE}=== Status dos Contêineres ===${NC}"
podman ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep -E "n8n|ollama|whisper|postgres|NAMES"

echo -e "\n${BLUE}=== Uso de Recursos ===${NC}"
podman stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" | grep -E "n8n|ollama|whisper|postgres|NAME"

echo -e "\n${BLUE}=== Modelos Ollama Disponíveis ===${NC}"
OLLAMA_CONTAINER=$(podman ps --format '{{.Names}}' | grep -i ollama | head -n 1)
if [ -z "$OLLAMA_CONTAINER" ]; then
    OLLAMA_CONTAINER="ollama"
fi

if podman ps | grep -q "$OLLAMA_CONTAINER"; then
    podman exec "$OLLAMA_CONTAINER" ollama list
else
    echo -e "${RED}O container do Ollama não está em execução.${NC}"
fi

echo -e "\n${BLUE}=== Contagem de Arquivos ===${NC}"
count_files() {
    local dir=$1
    if [ -d "$dir" ]; then
        find "$dir" -type f | wc -l
    else
        echo "0"
    fi
}

V_COUNT=$(count_files "${PROJECT_ROOT}/data/input/videos")
I_COUNT=$(count_files "${PROJECT_ROOT}/data/input/images")
M_COUNT=$(count_files "${PROJECT_ROOT}/data/input/metadata")
O_COUNT=$(count_files "${PROJECT_ROOT}/data/output")
A_COUNT=$(count_files "${PROJECT_ROOT}/data/processing/audio")
F_COUNT=$(count_files "${PROJECT_ROOT}/data/processing/frames")

echo -e "Vídeos (input):        ${YELLOW}${V_COUNT}${NC}"
echo -e "Imagens (input):       ${YELLOW}${I_COUNT}${NC}"
echo -e "Metadados (input):     ${YELLOW}${M_COUNT}${NC}"
echo -e "Áudios (processing):   ${YELLOW}${A_COUNT}${NC}"
echo -e "Frames (processing):   ${YELLOW}${F_COUNT}${NC}"
echo -e "Resultados (output):   ${YELLOW}${O_COUNT}${NC}"
