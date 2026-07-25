#!/usr/bin/env python3
"""
PipelineFace Web App Server Launcher
====================================
Wrapper de inicialização compatível que importa a aplicação FastAPI
construída sob a Metodologia de Arquitetura Limpa (web.main).
"""

import sys
from pathlib import Path

# Adicionar pasta raiz ao path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from web.main import app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web.main:app", host="0.0.0.0", port=8000, reload=True)
