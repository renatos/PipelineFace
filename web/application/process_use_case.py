"""
Process Use Cases — PipelineFace (Clean Architecture)
=====================================================
Casos de uso para execução e monitoramento de subprocessos (Pipeline e Scraper).
"""

from typing import Dict, Any, Callable, List


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


class GetProcessStatusUseCase:
    def __init__(self, get_status_func: Callable[[], Dict[str, Any]]):
        self.get_status_func = get_status_func

    def execute(self) -> Dict[str, Any]:
        return self.get_status_func()
