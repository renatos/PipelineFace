"""
Process & Telemetry Use Cases — PipelineFace (Clean Architecture)
=================================================================
Casos de uso para execução, interrupção, telemetria e gestão de histórico de perfis alvo.
"""

from typing import Dict, Any, Callable, List, Optional
from web.domain.entities import ExecutionEvent, PipelineRun, TargetProfile
from web.domain.repositories import AbstractExecutionEventRepository, AbstractPipelineRunRepository, AbstractTargetProfileRepository


class RecordExecutionEventUseCase:
    def __init__(self, repository: AbstractExecutionEventRepository):
        self.repository = repository

    def execute(self, event: ExecutionEvent) -> ExecutionEvent:
        return self.repository.save_event(event)


class GetExecutionEventsUseCase:
    def __init__(self, repository: AbstractExecutionEventRepository):
        self.repository = repository

    def execute(self, run_id: Optional[str] = None, source: Optional[str] = None, status: Optional[str] = None, limit: int = 50) -> List[ExecutionEvent]:
        return self.repository.list_events(run_id=run_id, source=source, status=status, limit=limit)


class SavePipelineRunUseCase:
    def __init__(self, repository: AbstractPipelineRunRepository):
        self.repository = repository

    def execute(self, run: PipelineRun) -> None:
        self.repository.save_or_update(run)


class GetPipelineRunUseCase:
    def __init__(self, repository: AbstractPipelineRunRepository):
        self.repository = repository

    def execute(self, run_id: str) -> Optional[PipelineRun]:
        return self.repository.find_by_run_id(run_id)


class ListPipelineRunsUseCase:
    def __init__(self, repository: AbstractPipelineRunRepository):
        self.repository = repository

    def execute(self, source: Optional[str] = None, limit: int = 20) -> List[PipelineRun]:
        return self.repository.list_runs(source=source, limit=limit)


class SaveTargetProfileUseCase:
    def __init__(self, repository: AbstractTargetProfileRepository):
        self.repository = repository

    def execute(self, target_url: str, max_scrolls: int = 50) -> TargetProfile:
        return self.repository.save_or_update_profile(target_url=target_url, max_scrolls=max_scrolls)


class GetTargetProfilesUseCase:
    def __init__(self, repository: AbstractTargetProfileRepository):
        self.repository = repository

    def execute(self, limit: int = 20) -> List[TargetProfile]:
        return self.repository.list_profiles(limit=limit)


class RunPipelineUseCase:
    def __init__(self, run_process_func: Callable[[List[str], str], None]):
        self.run_process_func = run_process_func

    def execute(self) -> Dict[str, str]:
        self.run_process_func(["python3", "pipeline.py"], "Pipeline Python")
        return {"status": "started", "message": "Pipeline iniciado em segundo plano"}


class RunScraperUseCase:
    def __init__(self, run_process_func: Callable[[List[str], str], None]):
        self.run_process_func = run_process_func

    def execute(self, target_url: str, only_videos: bool = False, only_images: bool = False, max_scrolls: int = 50) -> Dict[str, str]:
        cmd = ["python3", "scraper/facebook_scraper.py", "--target", target_url]
        if only_videos: cmd.append("--only-videos")
        if only_images: cmd.append("--only-images")
        if max_scrolls: cmd.extend(["--max-scrolls", str(max_scrolls)])

        self.run_process_func(cmd, "Scraper Facebook")
        return {"status": "started", "message": f"Scraper iniciado para {target_url}"}


class StopProcessUseCase:
    def __init__(self, stop_process_func: Callable[[], Dict[str, str]]):
        self.stop_process_func = stop_process_func

    def execute(self) -> Dict[str, str]:
        return self.stop_process_func()


class GetProcessStatusUseCase:
    def __init__(self, get_status_func: Callable[[], Dict[str, Any]]):
        self.get_status_func = get_status_func

    def execute(self) -> Dict[str, Any]:
        return self.get_status_func()
