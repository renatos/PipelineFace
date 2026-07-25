#!/bin/bash
# ============================================================
# PipelineFace — Script de Coleta do Facebook
# ============================================================
# Wrapper para executar o scraper dentro do container.
# Uso:
#   ./scripts/scrape.sh --login
#   ./scripts/scrape.sh --target https://facebook.com/perfil
#   ./scripts/scrape.sh --target https://facebook.com/perfil --only-videos
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# Cores
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

info()  { echo -e "${BLUE}ℹ️  $*${NC}"; }
ok()    { echo -e "${GREEN}✅ $*${NC}"; }
warn()  { echo -e "${YELLOW}⚠️  $*${NC}"; }
error() { echo -e "${RED}❌ $*${NC}"; }

# Verificar se o container do scraper está rodando
if ! podman-compose ps 2>/dev/null | grep -q "scraper"; then
    warn "Container do scraper não está rodando."
    info "Iniciando serviços..."
    podman-compose up -d scraper
    sleep 3
fi

echo ""
echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}  🧠 PipelineFace — Facebook Scraper       ${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""

# Se é login, precisa de interface gráfica
if echo "$@" | grep -q "\-\-login"; then
    info "Modo login: o navegador será aberto para autenticação."
    warn "NOTA: Para login interativo, o navegador precisa de display."
    warn "Se estiver em servidor sem GUI, faça login localmente primeiro."
    echo ""

    # Verificar se DISPLAY está disponível
    if [ -z "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ]; then
        warn "Nenhum display detectado."
        info "Alternativa: Execute localmente com:"
        echo ""
        echo "  cd scraper"
        echo "  pip install -r requirements.txt"
        echo "  playwright install chromium"
        echo "  python facebook_scraper.py --login --session-dir ../data/scraper/session"
        echo ""
        exit 1
    fi

    # Para login com GUI, compartilhar o display X11
    podman-compose exec \
        -e DISPLAY="${DISPLAY:-:0}" \
        scraper \
        python facebook_scraper.py "$@"
else
    # Execução headless normal
    info "Executando scraper em modo headless..."
    echo ""
    podman-compose exec scraper python facebook_scraper.py "$@"
fi

echo ""
ok "Coleta finalizada!"
info "Verifique os arquivos em:"
echo "  📹 Vídeos:    data/input/videos/"
echo "  🖼️  Imagens:   data/input/images/"
echo "  📋 Metadados: data/input/metadata/"
echo ""
info "Para extrair o conhecimento via Pipeline Python, execute:"
echo -e "  ${GREEN}python pipeline.py${NC}"
echo ""
