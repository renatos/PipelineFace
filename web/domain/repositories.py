"""
Domain Repositories Interfaces — PipelineFace (Clean Architecture)
==================================================================
Contrato abstrato de persistência para as estratégias e eventos de telemetria.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Tuple
from web.domain.entities import Strategy, Comment, ExecutionEvent


class AbstractStrategyRepository(ABC):
    @abstractmethod
    def save_or_update(self, strategy: Strategy) -> None:
        pass

    @abstractmethod
    def find_by_basename(self, basename: str) -> Optional[Strategy]:
        pass

    @abstractmethod
    def list_all(
        self,
        status: Optional[str] = None,
        search: Optional[str] = None,
        media_type: Optional[str] = None
    ) -> List[Strategy]:
        pass

    @abstractmethod
    def toggle_step(self, basename: str, step_index: int) -> Tuple[List[int], str]:
        pass

    @abstractmethod
    def update_status(self, basename: str, status: str) -> str:
        pass

    @abstractmethod
    def add_comment(self, basename: str, comment: Comment) -> Comment:
        pass


class AbstractExecutionEventRepository(ABC):
    @abstractmethod
    def save_event(self, event: ExecutionEvent) -> ExecutionEvent:
        """Persiste um evento de telemetria ou erro no repositório."""
        pass

    @abstractmethod
    def list_events(
        self,
        source: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50
    ) -> List[ExecutionEvent]:
        """Lista os eventos de telemetria ordenados pelos mais recentes."""
        pass
