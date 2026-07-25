"""
Domain Repositories Interfaces — PipelineFace (Clean Architecture)
==================================================================
Contrato abstrato de persistência para as estratégias, eventos e histórico de perfis alvo.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Tuple
from web.domain.entities import Strategy, Comment, ExecutionEvent, TargetProfile


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
        pass

    @abstractmethod
    def list_events(
        self,
        source: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50
    ) -> List[ExecutionEvent]:
        pass


class AbstractTargetProfileRepository(ABC):
    @abstractmethod
    def save_or_update_profile(self, target_url: str, max_scrolls: int = 50) -> TargetProfile:
        """Salva ou atualiza um perfil alvo na coleção do MongoDB."""
        pass

    @abstractmethod
    def list_profiles(self, limit: int = 20) -> List[TargetProfile]:
        """Lista os perfis alvo gravados no MongoDB ordenados pela data de raspagem."""
        pass
