"""
Presentation Routes — PipelineFace (Clean Architecture)
========================================================
Controladores e rotas FastAPI desacoplados que convertem requisições HTTP em chamadas aos Casos de Uso.
"""

from typing import Optional
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query, Request, BackgroundTasks
from pydantic import BaseModel

from web.domain.entities import Comment
from web.application.sync_use_case import SyncKnowledgeUseCase
from web.application.strategy_use_cases import (
    GetStrategiesUseCase, GetStrategyDetailUseCase, ToggleStepUseCase, UpdateStatusUseCase, AddCommentUseCase
)
from web.application.process_use_case import (
    RunPipelineUseCase, RunScraperUseCase, GetProcessStatusUseCase
)
from web.infrastructure.media_service import MediaStreamingService

router = APIRouter()


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


# Injeção de dependências das rotas
sync_use_case: SyncKnowledgeUseCase = None
get_strategies_use_case: GetStrategiesUseCase = None
get_detail_use_case: GetStrategyDetailUseCase = None
toggle_step_use_case: ToggleStepUseCase = None
update_status_use_case: UpdateStatusUseCase = None
add_comment_use_case: AddCommentUseCase = None
run_pipeline_use_case: RunPipelineUseCase = None
run_scraper_use_case: RunScraperUseCase = None
get_process_status_use_case: GetProcessStatusUseCase = None
media_service: MediaStreamingService = None


def init_routes(
    _sync_use_case, _get_strategies_use_case, _get_detail_use_case,
    _toggle_step_use_case, _update_status_use_case, _add_comment_use_case,
    _run_pipeline_use_case, _run_scraper_use_case, _get_process_status_use_case,
    _media_service
):
    global sync_use_case, get_strategies_use_case, get_detail_use_case
    global toggle_step_use_case, update_status_use_case, add_comment_use_case
    global run_pipeline_use_case, run_scraper_use_case, get_process_status_use_case
    global media_service

    sync_use_case = _sync_use_case
    get_strategies_use_case = _get_strategies_use_case
    get_detail_use_case = _get_detail_use_case
    toggle_step_use_case = _toggle_step_use_case
    update_status_use_case = _update_status_use_case
    add_comment_use_case = _add_comment_use_case
    run_pipeline_use_case = _run_pipeline_use_case
    run_scraper_use_case = _run_scraper_use_case
    get_process_status_use_case = _get_process_status_use_case
    media_service = _media_service


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


@router.get("/api/media/input/videos/{filename}")
def stream_video(filename: str, request: Request):
    return media_service.stream_video(filename, request)


@router.get("/api/media/input/images/{filename}")
def serve_input_image(filename: str):
    return media_service.serve_input_image(filename)


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

    background_tasks.add_task(
        run_scraper_use_case.execute,
        payload.target_url, payload.only_videos, payload.only_images, payload.max_scrolls
    )
    return {"status": "started", "message": f"Scraper iniciado para {payload.target_url}"}


@router.get("/api/process-status")
def process_status():
    return get_process_status_use_case.execute()
