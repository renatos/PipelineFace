"""
Main Application — PipelineFace (Clean Architecture)
====================================================
Ponto de montagem e fábrica do FastAPI com Injeção de Dependências.
"""

import os
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates

# Imports das Camadas da Arquitetura Limpa
from web.infrastructure.mongo_repository import MongoStrategyRepository
from web.infrastructure.media_service import MediaStreamingService
from web.infrastructure.process_runner import AsyncProcessRunner

from web.application.sync_use_case import SyncKnowledgeUseCase
from web.application.strategy_use_cases import (
    GetStrategiesUseCase, GetStrategyDetailUseCase, ToggleStepUseCase, UpdateStatusUseCase, AddCommentUseCase
)
from web.application.process_use_case import (
    RunPipelineUseCase, RunScraperUseCase, GetProcessStatusUseCase
)
from web.presentation.routes import router as api_router, init_routes


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
INPUT_VIDEOS_DIR = DATA_DIR / "input" / "videos"
INPUT_IMAGES_DIR = DATA_DIR / "input" / "images"
OUTPUT_DIR = DATA_DIR / "output"
OUTPUT_FRAMES_DIR = OUTPUT_DIR / "frames"

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
TEMPLATES_DIR = PROJECT_ROOT / "web" / "templates"


def create_app() -> FastAPI:
    app = FastAPI(title="PipelineFace Web Manager (Clean Architecture)", version="3.0.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    # 1. Instanciação da Infraestrutura
    mongo_repo = MongoStrategyRepository(mongo_uri=MONGO_URI)
    media_service = MediaStreamingService(INPUT_VIDEOS_DIR, INPUT_IMAGES_DIR, OUTPUT_FRAMES_DIR)
    process_runner = AsyncProcessRunner(PROJECT_ROOT)

    # 2. Instanciação dos Casos de Uso (Aplicação)
    sync_use_case = SyncKnowledgeUseCase(
        repository=mongo_repo,
        output_dir=OUTPUT_DIR,
        input_videos_dir=INPUT_VIDEOS_DIR,
        input_images_dir=INPUT_IMAGES_DIR,
        output_frames_dir=OUTPUT_FRAMES_DIR
    )
    get_strategies_use_case = GetStrategiesUseCase(mongo_repo)
    get_detail_use_case = GetStrategyDetailUseCase(mongo_repo)
    toggle_step_use_case = ToggleStepUseCase(mongo_repo)
    update_status_use_case = UpdateStatusUseCase(mongo_repo)
    add_comment_use_case = AddCommentUseCase(mongo_repo)

    # Callback para auto-sincronização após término de processo
    def on_process_complete():
        sync_use_case.execute()

    def run_proc(cmd, name):
        process_runner.run_process_async(cmd, name, on_complete_callback=on_process_complete)

    run_pipeline_use_case = RunPipelineUseCase(run_proc)
    run_scraper_use_case = RunScraperUseCase(run_proc)
    get_process_status_use_case = GetProcessStatusUseCase(process_runner.get_status)

    # 3. Inicialização e Injeção das Rotas de Apresentação
    init_routes(
        sync_use_case, get_strategies_use_case, get_detail_use_case,
        toggle_step_use_case, update_status_use_case, add_comment_use_case,
        run_pipeline_use_case, run_scraper_use_case, get_process_status_use_case,
        media_service
    )

    app.include_router(api_router)

    @app.get("/")
    def index(request: Request):
        return templates.TemplateResponse("index.html", {"request": request})

    # Executar sincronização inicial ao iniciar
    try:
        sync_use_case.execute()
    except Exception as e:
        print(f"Aviso: Erro na sincronização inicial: {e}")

    return app


app = create_app()
