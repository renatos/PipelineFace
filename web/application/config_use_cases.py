"""
App Config Use Cases — PipelineFace (Clean Architecture)
=========================================================
Casos de uso para leitura e edição dos parâmetros de configuração do sistema.
"""

from typing import Dict, List, Optional
from web.domain.entities import AppConfig
from web.domain.repositories import AbstractAppConfigRepository


class GetAllConfigsUseCase:
    def __init__(self, repository: AbstractAppConfigRepository):
        self.repository = repository

    def execute(self, group: Optional[str] = None) -> List[AppConfig]:
        return self.repository.list_all(group=group)


class GetConfigUseCase:
    def __init__(self, repository: AbstractAppConfigRepository):
        self.repository = repository

    def execute(self, key: str) -> Optional[AppConfig]:
        return self.repository.get(key)


class UpdateConfigUseCase:
    def __init__(self, repository: AbstractAppConfigRepository):
        self.repository = repository

    def execute(self, key: str, value: str) -> Optional[AppConfig]:
        return self.repository.update(key, value)


class GetConfigAsDictUseCase:
    """Retorna todos os parâmetros como dict key->value — para uso no pipeline/scraper."""
    def __init__(self, repository: AbstractAppConfigRepository):
        self.repository = repository

    def execute(self) -> Dict[str, str]:
        return self.repository.as_dict()
