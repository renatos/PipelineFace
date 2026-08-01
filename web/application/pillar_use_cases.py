"""
SEO Pillar Use Cases — PipelineFace (Clean Architecture)
=========================================================
Casos de uso para listagem, criação, edição e exclusão de pilares de SEO no MongoDB.
"""

from typing import List, Optional
from web.domain.entities import SEOPillar
from web.domain.repositories import AbstractSEOPillarRepository


class ListSEOPillarsUseCase:
    def __init__(self, repository: AbstractSEOPillarRepository):
        self.repository = repository

    def execute(self, apenas_ativos: bool = False) -> List[SEOPillar]:
        return self.repository.list_all(apenas_ativos=apenas_ativos)


class SaveSEOPillarUseCase:
    def __init__(self, repository: AbstractSEOPillarRepository):
        self.repository = repository

    def execute(self, pilar_id: str, titulo: str, keywords: List[str], ordem: int = 1, ativo: bool = True) -> SEOPillar:
        clean_keywords = [k.strip() for k in keywords if k and k.strip()]
        pilar = SEOPillar(
            id=pilar_id.strip().lower().replace(" ", "_"),
            titulo=titulo.strip(),
            keywords=clean_keywords,
            ordem=ordem,
            ativo=ativo
        )
        return self.repository.save_or_update(pilar)


class DeleteSEOPillarUseCase:
    def __init__(self, repository: AbstractSEOPillarRepository):
        self.repository = repository

    def execute(self, pilar_id: str) -> bool:
        return self.repository.delete(pilar_id)
