"""
Domain Repositories Interfaces — PipelineFace (Clean Architecture)
==================================================================
Contrato abstrato de persistência para as estratégias, eventos e histórico de perfis alvo.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple
from web.domain.entities import AppConfig, Strategy, Comment, ExecutionEvent, PipelineRun, TargetProfile, ProfilePost


class AbstractAppConfigRepository(ABC):
    @abstractmethod
    def seed_defaults(self) -> None:
        """Garante que os parâmetros padrão existam na coleção."""
        pass

    @abstractmethod
    def list_all(self, group: Optional[str] = None) -> List[AppConfig]:
        pass

    @abstractmethod
    def get(self, key: str) -> Optional[AppConfig]:
        pass

    @abstractmethod
    def update(self, key: str, value: str) -> Optional[AppConfig]:
        pass

    @abstractmethod
    def as_dict(self) -> Dict[str, str]:
        """Retorna dicionário key -> value para uso interno no pipeline/scraper."""
        pass


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
        run_id: Optional[str] = None,
        source: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50
    ) -> List[ExecutionEvent]:
        pass


class AbstractPipelineRunRepository(ABC):
    @abstractmethod
    def save_or_update(self, run: PipelineRun) -> None:
        pass

    @abstractmethod
    def find_by_run_id(self, run_id: str) -> Optional[PipelineRun]:
        pass

    @abstractmethod
    def list_runs(self, source: Optional[str] = None, limit: int = 20) -> List[PipelineRun]:
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


class AbstractProfilePostRepository(ABC):
    @abstractmethod
    def upsert_post(self, post: ProfilePost) -> bool:
        """Insere ou atualiza um post. Retorna True se inseriu novo documento."""
        pass

    @abstractmethod
    def find_by_post_id(self, post_id: str) -> Optional[ProfilePost]:
        """Busca um post pelo ID único."""
        pass

    @abstractmethod
    def list_posts(self, profile_url: Optional[str] = None, status: Optional[str] = None, limit: int = 500) -> List[ProfilePost]:
        """Lista os posts catalogados com filtros opcionais."""
        pass

    @abstractmethod
    def get_pending_posts(self, profile_url: Optional[str] = None, limit: int = 10) -> List[ProfilePost]:
        """Retorna até N posts pendentes de download."""
        pass

    @abstractmethod
    def update_status(self, post_id: str, status: str, error_message: Optional[str] = None) -> bool:
        """Atualiza o status de processamento do post."""
        pass

    @abstractmethod
    def update_media_status(self, post_id: str, media_id: str, downloaded: bool, filename: Optional[str] = None, error: Optional[str] = None) -> bool:
        """Atualiza o status de uma mídia específica dentro do post."""
        pass

    @abstractmethod
    def get_stats(self, profile_url: Optional[str] = None) -> Dict[str, int]:
        """Retorna estatísticas dos posts (total, pending, downloading, downloaded, processed, error)."""
        pass

