#!/bin/bash
# ============================================================
# PipelineFace — Script Shell de Limpeza do MongoDB
# ============================================================
# Mantém unicamente `target_profiles` e `app_config` intactos.
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}======================================================${NC}"
echo -e "${BLUE}  🧹 PipelineFace — Limpeza de Dados do MongoDB        ${NC}"
echo -e "${BLUE}======================================================${NC}"

if podman ps 2>/dev/null | grep -q "pipelineface_web_app"; then
    podman exec pipelineface_web_app python3 scripts/clean-db.py
else
    python3 scripts/clean-db.py
fi

echo -e "${GREEN}======================================================${NC}"
