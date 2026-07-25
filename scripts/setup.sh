#!/bin/bash
# ============================================================
# PipelineFace — Setup Inicial
# ============================================================

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

PROJECT_ROOT=$(cd "$(dirname "$0")/.." && pwd)

echo -e "${BLUE}=== Iniciando a configuração do PipelineFace ===${NC}"

# 1. Verificar pré-requisitos
echo -e "\n${BLUE}[1/7] Verificando pré-requisitos...${NC}"
for cmd in podman podman-compose; do
    if ! command -v "$cmd" &> /dev/null; then
        echo -e "${RED}Erro: $cmd não está instalado.${NC}"
        exit 1
    fi
done

# Checa se o Ollama está no PATH ou já respondendo na porta padrão
if ! command -v ollama &> /dev/null && ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo -e "${RED}Erro: ollama não está instalado no host ou respondendo na porta 11434.${NC}"
    echo -e "Instale com: curl -fsSL https://ollama.com/install.sh | sh"
    exit 1
fi
echo -e "${GREEN}✅ Pré-requisitos (Podman e Ollama) validados.${NC}"


# 2. Criar diretórios
echo -e "\n${BLUE}[2/7] Criando diretórios...${NC}"
cd "${PROJECT_ROOT}"
mkdir -p data/{input/{videos,images,metadata},output,processing/{audio,frames},scraper/session}
mkdir -p n8n-data postgres-data
echo -e "${GREEN}✅ Diretórios criados.${NC}"

# 3. Permissões
echo -e "\n${BLUE}[3/7] Ajustando permissões...${NC}"
podman unshare chown -R 1000:1000 "${PROJECT_ROOT}/n8n-data" 2>/dev/null || true
echo -e "${GREEN}✅ Permissões ajustadas.${NC}"

# 4. Configurar Ollama do host para aceitar conexões dos containers
echo -e "\n${BLUE}[4/7] Configurando Ollama do host...${NC}"

# Verificar se Ollama está rodando
if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Ollama do host está rodando.${NC}"
else
    echo -e "${YELLOW}⚠️  Ollama não está respondendo. Iniciando...${NC}"
    systemctl --user start ollama 2>/dev/null || ollama serve &
    sleep 3
fi

# Verificar se Ollama aceita conexões externas (necessário para containers)
OLLAMA_HOST_BIND=$(ss -tlnp | grep 11434 | awk '{print $4}')
if echo "$OLLAMA_HOST_BIND" | grep -q "127.0.0.1"; then
    echo -e "${YELLOW}⚠️  Ollama está escutando apenas em localhost (127.0.0.1).${NC}"
    echo -e "${YELLOW}   Para que os containers acessem, configure:${NC}"
    echo -e "   ${BLUE}sudo systemctl edit ollama${NC}"
    echo -e "   Adicione: ${BLUE}Environment=\"OLLAMA_HOST=0.0.0.0\"${NC}"
    echo -e "   Depois: ${BLUE}sudo systemctl restart ollama${NC}"
    echo ""
    echo -e "${YELLOW}   Ou execute temporariamente:${NC}"
    echo -e "   ${BLUE}OLLAMA_HOST=0.0.0.0 ollama serve${NC}"
    echo ""
fi

# 5. Baixar modelos no Ollama do host
echo -e "\n${BLUE}[5/7] Baixando modelos de IA no Ollama do host...${NC}"

pull_model() {
    local model=$1
    echo "📥 Baixando $model..."
    if command -v ollama &> /dev/null; then
        ollama pull "$model"
    else
        # Chama a API HTTP local para baixar o modelo
        curl -s -X POST http://localhost:11434/api/pull -d "{\"name\": \"$model\"}" > /dev/null
        echo -e "   [Enviada solicitação de download para o Ollama]"
    fi
}

pull_model "moondream"
pull_model "qwen2.5:3b"

echo -e "${GREEN}✅ Modelos prontos (ou baixando em background no host).${NC}"


# 6. Build e start dos containers
echo -e "\n${BLUE}[6/7] Construindo e iniciando containers...${NC}"
cd "${PROJECT_ROOT}"

echo "📦 Construindo imagem N8N (com FFmpeg)..."
podman build -t pipelineface-n8n:latest -f Containerfile.n8n .

echo "📦 Construindo imagem Scraper (Playwright + yt-dlp)..."
podman build -t pipelineface-scraper:latest -f scraper/Containerfile ./scraper

echo "🚀 Subindo serviços..."
podman-compose up -d

echo -e "${GREEN}✅ Containers iniciados.${NC}"

# 7. Health checks
echo -e "\n${BLUE}[7/7] Verificando serviços...${NC}"

wait_for() {
    local name=$1 url=$2 retries=15
    echo -ne "  Aguardando ${name}..."
    for i in $(seq 1 $retries); do
        if curl -s -f "$url" > /dev/null 2>&1; then
            echo -e " ${GREEN}Online!${NC}"
            return 0
        fi
        echo -ne "."
        sleep 3
    done
    echo -e " ${YELLOW}Timeout (pode estar inicializando)${NC}"
}

wait_for "Ollama (host)" "http://localhost:11434/api/tags"
wait_for "Whisper" "http://localhost:9000/"
wait_for "N8N" "http://localhost:5678/healthz"

# Resumo
echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}🎉 Setup concluído com sucesso!             ${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo -e "  📊 N8N:          http://localhost:5678"
echo -e "  🧠 Ollama (host): http://localhost:11434"
echo -e "  🎙️  Whisper:       http://localhost:9000"
echo ""
echo -e "  Modelos Ollama disponíveis:"
ollama list 2>/dev/null | head -10 || true
echo ""
echo -e "${YELLOW}Próximos passos:${NC}"
echo -e "  1. Login no Facebook:  ./scripts/scrape.sh --login"
echo -e "  2. Coletar perfil:     ./scripts/scrape.sh --target https://facebook.com/perfil"
echo -e "  3. Abrir N8N:          http://localhost:5678"
echo -e "  4. Importar workflow:  n8n-workflows/facebook-knowledge-extraction.json"
echo ""
