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
from web.infrastructure.mongo_repository import (
    MongoAppConfigRepository, MongoStrategyRepository, MongoExecutionEventRepository,
    MongoPipelineRunRepository, MongoTargetProfileRepository, MongoProfilePostRepository,
    MongoSEOPillarRepository
)
from web.infrastructure.media_service import MediaStreamingService
from web.infrastructure.process_runner import AsyncProcessRunner

from web.application.config_use_cases import (
    GetAllConfigsUseCase, GetConfigUseCase, UpdateConfigUseCase, GetConfigAsDictUseCase
)
from web.application.sync_use_case import SyncKnowledgeUseCase
from web.application.strategy_use_cases import (
    GetStrategiesUseCase, GetStrategyDetailUseCase, ToggleStepUseCase, UpdateStatusUseCase, AddCommentUseCase,
    RunBrowserAutomationUseCase
)

from web.application.process_use_case import (
    RunPipelineUseCase, RunScraperUseCase, StopProcessUseCase, GetProcessStatusUseCase,
    RecordExecutionEventUseCase, GetExecutionEventsUseCase,
    SavePipelineRunUseCase, GetPipelineRunUseCase, ListPipelineRunsUseCase,
    SaveTargetProfileUseCase, GetTargetProfilesUseCase
)
from web.application.post_use_cases import (
    ListProfilePostsUseCase, GetSinglePostUseCase, GetPostStatsUseCase, UpdatePostStatusUseCase,
    DeletePostUseCase, RunListPostsUseCase, RunDownloadPendingUseCase, RunDownloadSinglePostUseCase
)
from web.application.pillar_use_cases import (
    ListSEOPillarsUseCase, SaveSEOPillarUseCase, DeleteSEOPillarUseCase
)

from web.presentation.routes import router as api_router, init_routes


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
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
    config_repo = MongoAppConfigRepository(mongo_uri=MONGO_URI)  # seed automático
    mongo_repo = MongoStrategyRepository(mongo_uri=MONGO_URI)
    event_repo = MongoExecutionEventRepository(mongo_uri=MONGO_URI)
    run_repo = MongoPipelineRunRepository(mongo_uri=MONGO_URI)
    profile_repo = MongoTargetProfileRepository(mongo_uri=MONGO_URI)
    post_repo = MongoProfilePostRepository(mongo_uri=MONGO_URI)
    pillar_repo = MongoSEOPillarRepository(mongo_uri=MONGO_URI)
    media_service = MediaStreamingService(OUTPUT_FRAMES_DIR)
    process_runner = AsyncProcessRunner(PROJECT_ROOT)

    # 2. Instanciação dos Casos de Uso (Aplicação)
    get_all_configs_use_case = GetAllConfigsUseCase(config_repo)
    get_config_use_case = GetConfigUseCase(config_repo)
    update_config_use_case = UpdateConfigUseCase(config_repo)

    list_pillars_use_case = ListSEOPillarsUseCase(pillar_repo)
    save_pillar_use_case = SaveSEOPillarUseCase(pillar_repo)
    delete_pillar_use_case = DeleteSEOPillarUseCase(pillar_repo)

    sync_use_case = SyncKnowledgeUseCase(
        repository=mongo_repo,
        output_dir=OUTPUT_DIR,
        output_frames_dir=OUTPUT_FRAMES_DIR
    )
    get_strategies_use_case = GetStrategiesUseCase(mongo_repo)
    get_detail_use_case = GetStrategyDetailUseCase(mongo_repo)
    toggle_step_use_case = ToggleStepUseCase(mongo_repo)
    update_status_use_case = UpdateStatusUseCase(mongo_repo)
    add_comment_use_case = AddCommentUseCase(mongo_repo)

    record_event_use_case = RecordExecutionEventUseCase(event_repo)
    get_events_use_case = GetExecutionEventsUseCase(event_repo)

    save_run_use_case = SavePipelineRunUseCase(run_repo)
    get_run_use_case = GetPipelineRunUseCase(run_repo)
    list_runs_use_case = ListPipelineRunsUseCase(run_repo)

    save_profile_use_case = SaveTargetProfileUseCase(profile_repo)
    get_profiles_use_case = GetTargetProfilesUseCase(profile_repo)

    list_posts_use_case = ListProfilePostsUseCase(post_repo)
    get_single_post_use_case = GetSinglePostUseCase(post_repo)
    get_post_stats_use_case = GetPostStatsUseCase(post_repo)
    update_post_status_use_case = UpdatePostStatusUseCase(post_repo)
    delete_post_use_case = DeletePostUseCase(post_repo)

    def on_process_complete():
        sync_use_case.execute()

    def run_proc(cmd, name):
        process_runner.run_process_async(cmd, name, on_complete_callback=on_process_complete)

    run_pipeline_use_case = RunPipelineUseCase(run_proc)
    run_scraper_use_case = RunScraperUseCase(run_proc)
    run_list_posts_use_case = RunListPostsUseCase(run_proc, config_repo)
    run_download_pending_use_case = RunDownloadPendingUseCase(run_proc, config_repo)
    run_download_single_post_use_case = RunDownloadSinglePostUseCase(run_proc, post_repo)
    run_browser_automation_use_case = RunBrowserAutomationUseCase(run_proc)
    stop_process_use_case = StopProcessUseCase(process_runner.terminate_process)
    get_process_status_use_case = GetProcessStatusUseCase(process_runner.get_status)

    # 3. Inicialização e Injeção das Rotas de Apresentação
    init_routes(
        sync_use_case, get_strategies_use_case, get_detail_use_case,
        toggle_step_use_case, update_status_use_case, add_comment_use_case,
        run_pipeline_use_case, run_scraper_use_case, stop_process_use_case, get_process_status_use_case,
        record_event_use_case, get_events_use_case,
        save_run_use_case, get_run_use_case, list_runs_use_case,
        save_profile_use_case, get_profiles_use_case,
        get_all_configs_use_case, get_config_use_case, update_config_use_case,
        list_posts_use_case, get_single_post_use_case, get_post_stats_use_case, update_post_status_use_case,
        delete_post_use_case,
        run_list_posts_use_case, run_download_pending_use_case, run_download_single_post_use_case,
        run_browser_automation_use_case,
        list_pillars_use_case, save_pillar_use_case, delete_pillar_use_case,
        media_service, mongo_repo.db
    )



    app.include_router(api_router)

    @app.get("/")
    def index(request: Request):
        return templates.TemplateResponse(request=request, name="index.html")

    # Executar sincronização inicial ao iniciar
    try:
        sync_use_case.execute()
    except Exception as e:
        print(f"Aviso: Erro na sincronização inicial: {e}")

    # Migração única: autocorreção de post_type de posts com URLs de vídeo (removida do caminho de leitura)
    try:
        post_repo.fix_video_post_types()
    except Exception as e:
        print(f"Aviso: migração de post_type falhou: {e}")

    return app


app = create_app()

