"""
Presentation Routes — PipelineFace (Clean Architecture)
========================================================
Controladores e rotas FastAPI desacoplados que convertem requisições HTTP em chamadas aos Casos de Uso.
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel

from web.domain.entities import Comment, ExecutionEvent, PipelineRun
from web.application.config_use_cases import GetAllConfigsUseCase, GetConfigUseCase, UpdateConfigUseCase
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
from web.infrastructure.media_service import MediaStreamingService

from web.application.post_use_cases import (
    ListProfilePostsUseCase, GetSinglePostUseCase, GetPostStatsUseCase, UpdatePostStatusUseCase,
    DeletePostUseCase, RunListPostsUseCase, RunDownloadPendingUseCase, RunDownloadSinglePostUseCase
)
from web.application.pillar_use_cases import (
    ListSEOPillarsUseCase, SaveSEOPillarUseCase, DeleteSEOPillarUseCase
)
from web.application.seo_automation_use_cases import (
    GetGithaContextUseCase, PrioritizeStrategiesUseCase, BuildExecutionPlanUseCase, MarkStrategyAppliedUseCase
)
from web.domain.entities import SEOPillar


router = APIRouter()


class MarkAppliedRequest(BaseModel):
    step_indices: Optional[List[int]] = None
    notes: Optional[str] = None


class SEOPillarRequest(BaseModel):
    id: str
    titulo: str
    keywords: List[str]
    ordem: Optional[int] = 1
    ativo: Optional[bool] = True


class UpdateConfigRequest(BaseModel):
    value: str


class CommentRequest(BaseModel):
    text: str
    author: Optional[str] = "Usuário"


class StatusRequest(BaseModel):
    status: str


class StepRequest(BaseModel):
    step_index: int


class ScraperRequest(BaseModel):
    target_url: str
    only_videos: bool = False
    only_images: bool = False
    max_scrolls: int = 50


class ListPostsRequest(BaseModel):
    target_url: str
    max_scrolls: Optional[int] = None
    only_new: bool = False


class DownloadPendingRequest(BaseModel):
    target_url: str
    batch_size: Optional[int] = 10


class TargetProfileRequest(BaseModel):
    target_url: str
    max_scrolls: Optional[int] = 50


class ExecutionEventRequest(BaseModel):
    run_id: str
    source: str
    step: str
    status: str = "info"
    filename: Optional[str] = None
    target_url: Optional[str] = None
    message: str
    metrics: Dict[str, Any] = {}
    error_details: Optional[str] = None


# Injeção de dependências das rotas
sync_use_case: SyncKnowledgeUseCase = None
get_strategies_use_case: GetStrategiesUseCase = None
get_detail_use_case: GetStrategyDetailUseCase = None
toggle_step_use_case: ToggleStepUseCase = None
update_status_use_case: UpdateStatusUseCase = None
add_comment_use_case: AddCommentUseCase = None
run_pipeline_use_case: RunPipelineUseCase = None
run_scraper_use_case: RunScraperUseCase = None
stop_process_use_case: StopProcessUseCase = None
get_process_status_use_case: GetProcessStatusUseCase = None
record_event_use_case: RecordExecutionEventUseCase = None
get_events_use_case: GetExecutionEventsUseCase = None
save_run_use_case: SavePipelineRunUseCase = None
get_run_use_case: GetPipelineRunUseCase = None
list_runs_use_case: ListPipelineRunsUseCase = None
save_profile_use_case: SaveTargetProfileUseCase = None
get_profiles_use_case: GetTargetProfilesUseCase = None
get_all_configs_use_case: GetAllConfigsUseCase = None
get_config_use_case: GetConfigUseCase = None
update_config_use_case: UpdateConfigUseCase = None
list_posts_use_case: ListProfilePostsUseCase = None
get_single_post_use_case: GetSinglePostUseCase = None
get_post_stats_use_case: GetPostStatsUseCase = None
delete_post_use_case: DeletePostUseCase = None
run_list_posts_use_case: RunListPostsUseCase = None
run_download_pending_use_case: RunDownloadPendingUseCase = None
run_download_single_post_use_case: RunDownloadSinglePostUseCase = None
run_browser_automation_use_case: RunBrowserAutomationUseCase = None
list_pillars_use_case: ListSEOPillarsUseCase = None
save_pillar_use_case: SaveSEOPillarUseCase = None
delete_pillar_use_case: DeleteSEOPillarUseCase = None
media_service: MediaStreamingService = None
mongo_db = None

# SEO Automation & Githa Context Use Cases
get_githa_context_use_case: GetGithaContextUseCase = None
prioritize_strategies_use_case: PrioritizeStrategiesUseCase = None
build_execution_plan_use_case: BuildExecutionPlanUseCase = None
mark_strategy_applied_use_case: MarkStrategyAppliedUseCase = None


def init_routes(
    _sync_use_case, _get_strategies_use_case, _get_detail_use_case,
    _toggle_step_use_case, _update_status_use_case, _add_comment_use_case,
    _run_pipeline_use_case, _run_scraper_use_case, _stop_process_use_case, _get_process_status_use_case,
    _record_event_use_case, _get_events_use_case,
    _save_run_use_case, _get_run_use_case, _list_runs_use_case,
    _save_profile_use_case, _get_profiles_use_case,
    _get_all_configs_use_case, _get_config_use_case, _update_config_use_case,
    _list_posts_use_case, _get_single_post_use_case, _get_post_stats_use_case, _update_post_status_use_case,
    _delete_post_use_case,
    _run_list_posts_use_case, _run_download_pending_use_case, _run_download_single_post_use_case,
    _run_browser_automation_use_case,
    _list_pillars_use_case, _save_pillar_use_case, _delete_pillar_use_case,
    _media_service, _mongo_db,
    _get_githa_context_use_case=None,
    _prioritize_strategies_use_case=None,
    _build_execution_plan_use_case=None,
    _mark_strategy_applied_use_case=None
):
    global sync_use_case, get_strategies_use_case, get_detail_use_case
    global toggle_step_use_case, update_status_use_case, add_comment_use_case
    global run_pipeline_use_case, run_scraper_use_case, stop_process_use_case, get_process_status_use_case
    global record_event_use_case, get_events_use_case
    global save_run_use_case, get_run_use_case, list_runs_use_case
    global save_profile_use_case, get_profiles_use_case
    global get_all_configs_use_case, get_config_use_case, update_config_use_case
    global list_posts_use_case, get_single_post_use_case, get_post_stats_use_case, update_post_status_use_case
    global delete_post_use_case
    global run_list_posts_use_case, run_download_pending_use_case, run_download_single_post_use_case
    global run_browser_automation_use_case
    global list_pillars_use_case, save_pillar_use_case, delete_pillar_use_case
    global media_service, mongo_db
    global get_githa_context_use_case, prioritize_strategies_use_case
    global build_execution_plan_use_case, mark_strategy_applied_use_case

    sync_use_case = _sync_use_case
    get_strategies_use_case = _get_strategies_use_case
    get_detail_use_case = _get_detail_use_case
    toggle_step_use_case = _toggle_step_use_case
    update_status_use_case = _update_status_use_case
    add_comment_use_case = _add_comment_use_case
    run_pipeline_use_case = _run_pipeline_use_case
    run_scraper_use_case = _run_scraper_use_case
    stop_process_use_case = _stop_process_use_case
    get_process_status_use_case = _get_process_status_use_case
    record_event_use_case = _record_event_use_case
    get_events_use_case = _get_events_use_case
    save_run_use_case = _save_run_use_case
    get_run_use_case = _get_run_use_case
    list_runs_use_case = _list_runs_use_case
    save_profile_use_case = _save_profile_use_case
    get_profiles_use_case = _get_profiles_use_case
    get_all_configs_use_case = _get_all_configs_use_case
    get_config_use_case = _get_config_use_case
    update_config_use_case = _update_config_use_case
    list_posts_use_case = _list_posts_use_case
    get_single_post_use_case = _get_single_post_use_case
    get_post_stats_use_case = _get_post_stats_use_case
    update_post_status_use_case = _update_post_status_use_case
    delete_post_use_case = _delete_post_use_case
    run_list_posts_use_case = _run_list_posts_use_case
    run_download_pending_use_case = _run_download_pending_use_case
    run_download_single_post_use_case = _run_download_single_post_use_case
    run_browser_automation_use_case = _run_browser_automation_use_case

    list_pillars_use_case = _list_pillars_use_case
    save_pillar_use_case = _save_pillar_use_case
    delete_pillar_use_case = _delete_pillar_use_case
    media_service = _media_service
    mongo_db = _mongo_db

    get_githa_context_use_case = _get_githa_context_use_case
    prioritize_strategies_use_case = _prioritize_strategies_use_case
    build_execution_plan_use_case = _build_execution_plan_use_case
    mark_strategy_applied_use_case = _mark_strategy_applied_use_case




@router.get("/api/profile-posts")
def get_profile_posts(
    profile_url: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(500)
):
    """Lista os posts catalogados com filtros opcionais."""
    posts = list_posts_use_case.execute(profile_url=profile_url, status=status, limit=limit)
    return {"count": len(posts), "posts": [p.model_dump() for p in posts]}


@router.get("/api/profile-posts/stats")
def get_profile_post_stats(profile_url: Optional[str] = Query(None)):
    """Retorna estatísticas dos posts (total, pending, downloading, downloaded, processed, error)."""
    return get_post_stats_use_case.execute(profile_url=profile_url)


@router.get("/api/profile-posts/{post_id}")
def get_single_profile_post(post_id: str):
    """Retorna os detalhes de um post catalogado pelo post_id."""
    post = get_single_post_use_case.execute(post_id)
    if not post:
        raise HTTPException(status_code=404, detail=f"Post {post_id} não encontrado")
    return post.model_dump()


@router.delete("/api/profile-posts/{post_id}")
@router.post("/api/profile-posts/{post_id}/delete")
def delete_profile_post(post_id: str):
    """Remove um post catalogado do banco de dados pelo post_id."""
    deleted = delete_post_use_case.execute(post_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Post {post_id} não encontrado")
    return {"status": "success", "post_id": post_id, "message": f"Post {post_id} removido com sucesso"}


@router.post("/api/profile-posts/{post_id}/download")
def download_single_post(post_id: str, background_tasks: BackgroundTasks):
    """Dispara o download individual de um post específico."""
    status = get_process_status_use_case.execute()
    if status.get("running"):
        raise HTTPException(status_code=400, detail=f"Processo {status.get('name')} já está em execução.")

    post = run_download_single_post_use_case.repository.find_by_post_id(post_id)
    if not post:
        raise HTTPException(status_code=404, detail=f"Post {post_id} não encontrado")

    background_tasks.add_task(run_download_single_post_use_case.execute, post_id)
    return {"status": "started", "message": f"Download do post {post_id} iniciado em segundo plano"}


@router.patch("/api/profile-posts/{post_id}/status")
def patch_post_status(post_id: str, payload: StatusRequest):
    """Atualiza o status de um post catalogado."""
    updated = update_post_status_use_case.execute(post_id=post_id, status=payload.status)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Post {post_id} não encontrado")
    return {"status": "success", "post_id": post_id, "new_status": payload.status}



@router.post("/api/actions/list-posts")
def action_list_posts(payload: ListPostsRequest, background_tasks: BackgroundTasks):
    """Dispara a listagem/catalogação de posts de um perfil (Step 1)."""
    status = get_process_status_use_case.execute()
    if status.get("running"):
        raise HTTPException(status_code=400, detail=f"Processo {status.get('name')} já está em execução.")

    background_tasks.add_task(run_list_posts_use_case.execute, payload.target_url, payload.max_scrolls, payload.only_new)
    return {"status": "started", "message": f"Listagem de posts iniciada para {payload.target_url}"}


@router.post("/api/actions/download-pending")
def action_download_pending(payload: DownloadPendingRequest, background_tasks: BackgroundTasks):
    """Dispara o download de N posts pendentes (Step 2 em lote)."""
    status = get_process_status_use_case.execute()
    if status.get("running"):
        raise HTTPException(status_code=400, detail=f"Processo {status.get('name')} já está em execução.")

    background_tasks.add_task(run_download_pending_use_case.execute, payload.target_url, payload.batch_size or 10)
    return {"status": "started", "message": f"Download de {payload.batch_size or 10} posts pendentes iniciado"}


@router.get("/api/configs")
def get_configs(group: Optional[str] = Query(None)):
    """Lista todos os parâmetros de configuração do sistema, opcionalmente filtrados por grupo."""
    configs = get_all_configs_use_case.execute(group=group)
    return {"count": len(configs), "configs": [c.model_dump() for c in configs]}


@router.get("/api/configs/{key}")
def get_config(key: str):
    """Retorna um parâmetro de configuração pelo key."""
    cfg = get_config_use_case.execute(key)
    if not cfg:
        raise HTTPException(status_code=404, detail=f"Configuração '{key}' não encontrada")
    return cfg.model_dump()


@router.patch("/api/configs/{key}")
def update_config(key: str, payload: UpdateConfigRequest):
    """Atualiza o valor de um parâmetro de configuração editável."""
    try:
        updated = update_config_use_case.execute(key, payload.value.strip())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not updated:
        raise HTTPException(status_code=404, detail=f"Configuração '{key}' não encontrada ou não é editável")
    return updated.model_dump()


@router.get("/api/seo-pillars")
def get_seo_pillars(apenas_ativos: bool = Query(False)):
    """Lista todos os pilares de SEO cadastrados no MongoDB."""
    if not list_pillars_use_case:
        raise HTTPException(status_code=500, detail="Casos de uso de pilares não inicializados")
    pillars = list_pillars_use_case.execute(apenas_ativos=apenas_ativos)
    return {"count": len(pillars), "pillars": [p.model_dump() for p in pillars]}


@router.post("/api/seo-pillars")
def save_seo_pillar(payload: SEOPillarRequest):
    """Cadastra ou atualiza um pilar de SEO no MongoDB."""
    if not save_pillar_use_case:
        raise HTTPException(status_code=500, detail="Casos de uso de pilares não inicializados")
    pillar = save_pillar_use_case.execute(
        pilar_id=payload.id,
        titulo=payload.titulo,
        keywords=payload.keywords,
        ordem=payload.ordem or 1,
        ativo=payload.ativo if payload.ativo is not None else True
    )
    return pillar.model_dump()


@router.delete("/api/seo-pillars/{pillar_id}")
def delete_seo_pillar(pillar_id: str):
    """Remove um pilar de SEO do MongoDB."""
    if not delete_pillar_use_case:
        raise HTTPException(status_code=500, detail="Casos de uso de pilares não inicializados")
    deleted = delete_pillar_use_case.execute(pillar_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Pilar {pillar_id} não encontrado")
    return {"status": "success", "pillar_id": pillar_id}


@router.get("/api/seo-playbook")
def get_seo_playbook():
    """Retorna o documento do Playbook SEO Consolidado gerado no MongoDB."""
    pb = mongo_db["seo_playbook"].find_one({"id": "playbook_principal"}, {"_id": 0})
    if not pb:
        raise HTTPException(status_code=404, detail="Playbook ainda não foi gerado.")
    return pb


@router.get("/api/target-profiles")
def get_target_profiles(limit: int = Query(20)):
    """Lista os perfis alvo salvos no MongoDB."""
    profiles = get_profiles_use_case.execute(limit=limit)
    return {"count": len(profiles), "profiles": [p.model_dump() for p in profiles]}


@router.post("/api/target-profiles")
def save_target_profile(payload: TargetProfileRequest):
    """Cadastra ou atualiza um perfil alvo no MongoDB."""
    profile = save_profile_use_case.execute(target_url=payload.target_url, max_scrolls=payload.max_scrolls or 50)
    return profile.model_dump()


@router.post("/api/webhooks/execution-event")
def webhook_execution_event(payload: ExecutionEventRequest):
    event = ExecutionEvent(
        run_id=payload.run_id,
        source=payload.source,
        step=payload.step,
        status=payload.status,
        filename=payload.filename,
        target_url=payload.target_url,
        message=payload.message,
        metrics=payload.metrics,
        error_details=payload.error_details,
        created_at=datetime.now().isoformat()
    )
    recorded = record_event_use_case.execute(event)
    return {"status": "success", "event_id": recorded.id}


@router.get("/api/execution-events")
def get_execution_events(
    run_id: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50)
):
    events = get_events_use_case.execute(run_id=run_id, source=source, status=status, limit=limit)
    return {"count": len(events), "events": [e.model_dump() for e in events]}


@router.get("/api/pipeline-runs")
def list_pipeline_runs(
    source: Optional[str] = Query(None),
    limit: int = Query(20)
):
    """Lista todas as execuções (runs) do Pipeline e Scraper."""
    runs = list_runs_use_case.execute(source=source, limit=limit)
    return {"count": len(runs), "runs": [r.model_dump() for r in runs]}


@router.get("/api/pipeline-runs/{run_id}")
def get_pipeline_run(run_id: str):
    """Retorna os detalhes de uma execução específica pelo run_id."""
    run = get_run_use_case.execute(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} não encontrada")
    return run.model_dump()


@router.get("/api/pipeline-runs/{run_id}/events")
def get_run_events(run_id: str, limit: int = Query(100)):
    """Lista todos os execution_events de uma execução pelo run_id."""
    events = get_events_use_case.execute(run_id=run_id, limit=limit)
    return {"run_id": run_id, "count": len(events), "events": [e.model_dump() for e in events]}


@router.post("/api/sync")
def api_sync():
    res = sync_use_case.execute()
    return {"status": "success", "data": res}


@router.get("/api/strategies")
def get_strategies(
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    media_type: Optional[str] = Query(None)
):
    strategies = get_strategies_use_case.execute(status=status, search=search, media_type=media_type)
    return {"count": len(strategies), "strategies": [s.model_dump() for s in strategies]}


@router.get("/api/strategies/{basename}")
def get_strategy_detail(basename: str):
    strategy = get_detail_use_case.execute(basename)
    if not strategy:
        raise HTTPException(status_code=404, detail="Estratégia não encontrada")
    return strategy.model_dump()


class BrowserAutomationRequest(BaseModel):
    basename: Optional[str] = None
    limit: int = 1
    interactive: bool = False


@router.post("/api/actions/browser-automation")
def action_browser_automation(payload: BrowserAutomationRequest, background_tasks: BackgroundTasks):
    """Dispara a automação autônoma de navegador (Browser-Use) para uma ou mais estratégias."""
    status = get_process_status_use_case.execute()
    if status.get("running"):
        raise HTTPException(status_code=400, detail=f"Processo '{status.get('name')}' já está em execução.")

    background_tasks.add_task(run_browser_automation_use_case.execute, payload.basename, payload.limit, payload.interactive)
    return {"status": "started", "message": f"Automação de navegador iniciada em segundo plano para {payload.basename or f'{payload.limit} tarefas'}"}



@router.patch("/api/strategies/{basename}/step")
def toggle_step(basename: str, payload: StepRequest):
    try:
        completed_steps, new_status = toggle_step_use_case.execute(basename, payload.step_index)
        return {"completed_steps": completed_steps, "status": new_status}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/api/strategies/{basename}/status")
def update_status(basename: str, payload: StatusRequest):
    try:
        new_status = update_status_use_case.execute(basename, payload.status)
        return {"status": new_status}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/api/strategies/{basename}/comments")
def add_comment(basename: str, payload: CommentRequest):
    import uuid
    comment = Comment(
        id=str(uuid.uuid4())[:8],
        text=payload.text.strip(),
        author=payload.author or "Usuário",
        created_at=datetime.now().isoformat()
    )
    try:
        created = add_comment_use_case.execute(basename, comment)
        return created.model_dump()
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


# --- Endpoints de Integração Githa Context & SEO Automation ---

@router.get("/api/githa-context")
def get_githa_context():
    """Retorna o contexto de negócio real da clínica Studio Githa extraído do PostgreSQL."""
    if not get_githa_context_use_case:
        raise HTTPException(status_code=503, detail="Githa Context UseCase não inicializado.")
    context = get_githa_context_use_case.execute()
    return context.model_dump()


@router.get("/api/seo/priorities")
def get_seo_priorities(
    status: Optional[str] = Query(None),
    limit: int = Query(50)
):
    """Retorna a lista de estratégias SEO priorizadas pelo impacto no negócio do Studio Githa."""
    if not prioritize_strategies_use_case:
        raise HTTPException(status_code=503, detail="PrioritizeStrategiesUseCase não inicializado.")
    items = prioritize_strategies_use_case.execute(status_filter=status, limit=limit)
    return {"count": len(items), "priorities": [i.model_dump() for i in items]}


@router.get("/api/seo/execution-plan/{basename}")
def get_strategy_execution_plan(basename: str):
    """Retorna o plano de execução enriquecido com dados do Githa para o Chrome DevTools MCP."""
    if not build_execution_plan_use_case:
        raise HTTPException(status_code=503, detail="BuildExecutionPlanUseCase não inicializado.")
    try:
        plan = build_execution_plan_use_case.execute(basename)
        return plan.model_dump()
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/api/seo/mark-applied/{basename}")
def mark_strategy_applied(basename: str, payload: MarkAppliedRequest):
    """Registra a aplicação automatizada de passos de uma estratégia."""
    if not mark_strategy_applied_use_case:
        raise HTTPException(status_code=503, detail="MarkStrategyAppliedUseCase não inicializado.")
    try:
        updated = mark_strategy_applied_use_case.execute(
            basename=basename,
            step_indices=payload.step_indices,
            notes=payload.notes
        )
        return updated.model_dump()
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/api/media/frames/{basename}/{frame_name}")
def serve_frame_image(basename: str, frame_name: str):

    return media_service.serve_frame_image(basename, frame_name)


@router.post("/api/run-pipeline")
def run_pipeline(background_tasks: BackgroundTasks):
    status = get_process_status_use_case.execute()
    if status.get("running"):
        raise HTTPException(status_code=400, detail=f"Processo {status.get('name')} já está em execução.")

    background_tasks.add_task(run_pipeline_use_case.execute)
    return {"status": "started", "message": "Pipeline iniciado em segundo plano"}


@router.post("/api/run-scraper")
def run_scraper(payload: ScraperRequest, background_tasks: BackgroundTasks):
    status = get_process_status_use_case.execute()
    if status.get("running"):
        raise HTTPException(status_code=400, detail=f"Processo {status.get('name')} já está em execução.")

    # Auto-registrar perfil no MongoDB ao iniciar raspagem
    try:
        save_profile_use_case.execute(target_url=payload.target_url, max_scrolls=payload.max_scrolls)
    except Exception as e:
        print(f"Aviso ao registrar perfil: {e}")

    background_tasks.add_task(
        run_scraper_use_case.execute,
        payload.target_url, payload.only_videos, payload.only_images, payload.max_scrolls
    )
    return {"status": "started", "message": f"Scraper iniciado para {payload.target_url}"}


@router.post("/api/stop-process")
def stop_process():
    res = stop_process_use_case.execute()
    return res


@router.get("/api/process-status")
def process_status():
    return get_process_status_use_case.execute()

