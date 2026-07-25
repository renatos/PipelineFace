"""
Domain Repositories Interfaces — PipelineFace (Clean Architecture)
==================================================================
Contrato abstrato de persistência para as estratégias de SEO.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Tuple
from web.domain.entities import Strategy, Comment


class AbstractStrategyRepository(ABC):
    
    @abstractmethod
    def save_or_update(self, strategy: Strategy) -> None:
        """Salva ou atualiza uma estratégia no repositório."""
        pass

    @abstractmethod
    def find_by_basename(self, basename: str) -> Optional[Strategy]:
        """Busca uma estratégia pelo seu identificador basename."""
        pass

    @abstractmethod
    def list_all(
        self,
        status: Optional[str] = None,
        search: Optional[str] = None,
        media_type: Optional[str] = None
    ) -> List[Strategy]:
        """Lista todas as estratégias aplicando filtros opcionais."""
        pass

    @abstractmethod
    def toggle_step(self, basename: str, step_index: int) -> Tuple[List[int], str]:
        """Alterna a conclusão de um passo do tutorial e retorna (passos_concluidos, novo_status)."""
        pass

    @abstractmethod
    def update_status(self, basename: str, status: str) -> str:
        """Atualiza o status geral da estratégia."""
        pass

    @abstractmethod
    def add_comment(self, basename: str, comment: Comment) -> Comment:
        """Adiciona um comentário/observação a uma estratégia."""
        pass
