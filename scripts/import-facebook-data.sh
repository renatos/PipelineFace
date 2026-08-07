#!/bin/bash
# Torne este script executável executando: chmod +x import-facebook-data.sh

set -euo pipefail

# Definindo cores
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

if [ "$#" -ne 1 ]; then
    echo -e "${RED}Uso: $0 <caminho_para_arquivo_zip>${NC}"
    exit 1
fi

ZIP_FILE="$1"

if [ ! -f "$ZIP_FILE" ]; then
    echo -e "${RED}Erro: Arquivo não encontrado - $ZIP_FILE${NC}"
    exit 1
fi

PROJECT_ROOT=$(cd "$(dirname "$0")/.." && pwd)
TEMP_DIR=$(mktemp -d)

echo -e "${BLUE}Extraindo arquivo ZIP para diretório temporário...${NC}"
unzip -q "$ZIP_FILE" -d "$TEMP_DIR"

echo -e "${BLUE}Copiando arquivos...${NC}"

# Buscar e copiar vídeos
VIDEO_COUNT=0
while IFS= read -r file; do
    if [ -n "$file" ]; then
        cp "$file" "${PROJECT_ROOT}/data/input/videos/"
        ((VIDEO_COUNT+=1))
    fi
done <<< "$(find "$TEMP_DIR" -type f \( -iname \*.mp4 -o -iname \*.mov -o -iname \*.avi -o -iname \*.webm \))"

# Buscar e copiar imagens
IMAGE_COUNT=0
while IFS= read -r file; do
    if [ -n "$file" ]; then
        cp "$file" "${PROJECT_ROOT}/data/input/images/"
        ((IMAGE_COUNT+=1))
    fi
done <<< "$(find "$TEMP_DIR" -type f \( -iname \*.jpg -o -iname \*.jpeg -o -iname \*.png -o -iname \*.gif -o -iname \*.webp \))"

# Buscar e copiar metadados JSON
JSON_COUNT=0
while IFS= read -r file; do
    if [ -n "$file" ]; then
        cp "$file" "${PROJECT_ROOT}/data/input/metadata/"
        ((JSON_COUNT+=1))
    fi
done <<< "$(find "$TEMP_DIR" -type f -iname \*.json)"

echo -e "${BLUE}Limpando diretório temporário...${NC}"
rm -rf "$TEMP_DIR"

echo -e "\n${GREEN}=== Resumo da Importação ===${NC}"
echo -e "Vídeos copiados:     ${YELLOW}${VIDEO_COUNT}${NC}"
echo -e "Imagens copiadas:    ${YELLOW}${IMAGE_COUNT}${NC}"
echo -e "Metadados copiados:  ${YELLOW}${JSON_COUNT}${NC}"
echo -e "${GREEN}Arquivos disponíveis em data/input/${NC}"
