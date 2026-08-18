"""
Strategy Use Cases — PipelineFace (Clean Architecture)
======================================================
Casos de uso para manipulação de estratégias de SEO e acompanhamento do progresso.
"""

import sys
from typing import List, Optional, Tuple
from web.domain.entities import Strategy, Comment
from web.domain.repositories import AbstractStrategyRepository


class GetStrategiesUseCase:
    def __init__(self, repository: AbstractStrategyRepository):
        self.repository = repository

    def execute(self, status: Optional[str] = None, search: Optional[str] = None, media_type: Optional[str] = None) -> List[Strategy]:
        return self.repository.list_all(status=status, search=search, media_type=media_type)


class GetStrategyDetailUseCase:
    def __init__(self, repository: AbstractStrategyRepository):
        self.repository = repository

    def execute(self, basename: str) -> Optional[Strategy]:
        return self.repository.find_by_basename(basename)


class ToggleStepUseCase:
    def __init__(self, repository: AbstractStrategyRepository):
        self.repository = repository

    def execute(self, basename: str, step_index: int) -> Tuple[List[int], str]:
        return self.repository.toggle_step(basename, step_index)


class UpdateStatusUseCase:
    def __init__(self, repository: AbstractStrategyRepository):
        self.repository = repository

    def execute(self, basename: str, status: str) -> str:
        return self.repository.update_status(basename, status)


class AddCommentUseCase:
    def __init__(self, repository: AbstractStrategyRepository):
        self.repository = repository

    def execute(self, basename: str, comment: Comment) -> Comment:
        return self.repository.add_comment(basename, comment)


class RunBrowserAutomationUseCase:
    def __init__(self, run_process_func=None):
        self.run_process_func = run_process_func

    def execute(self, basename: Optional[str] = None, limit: int = 1, interactive: bool = False):
        return {"status": "disabled", "message": "A automação de navegador via LLM local foi descontinuada em favor do Chrome DevTools MCP."}


