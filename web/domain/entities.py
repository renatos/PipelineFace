"""
Domain Entities — PipelineFace (Clean Architecture)
===================================================
Entidades puras do domínio sem dependências de frameworks (FastAPI/PyMongo).
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class AppConfig(BaseModel):
    """Parâmetro de configuração do sistema, armazenado na coleção app_config."""
    key: str
    group: str  # "pipeline" | "models" | "scraper" | "system"
    value: str
    value_type: str = "string"  # "string" | "int" | "float" | "bool"
    label: str
    description: str = ""
    editable: bool = True
    updated_at: Optional[str] = None


class InputFile(BaseModel):
    filename: str
    type: str  # "video" | "image"
    extension: str
    url: Optional[str] = None
    media_url: Optional[str] = None
    duration_seconds: Optional[int] = None
    size_bytes: Optional[int] = None


class SavedFrame(BaseModel):
    filename: str
    url: str


class Content(BaseModel):
    transcription: Optional[str] = None
    visual_description: Optional[str] = None
    saved_frames: List[SavedFrame] = Field(default_factory=list)


class SEOKnowledge(BaseModel):
    titulo_estrategia: Optional[str] = None
    resumo_executivo: Optional[str] = None
    passo_a_passo_detalhado: List[str] = Field(default_factory=list)
    ferramentas_e_telas_utilizadas: List[str] = Field(default_factory=list)
    termos_e_exemplos_usados: List[str] = Field(default_factory=list)
    aplicacao_no_negocio: Optional[str] = None
    conceitos_mencionados: List[str] = Field(default_factory=list)


class Comment(BaseModel):
    id: str
    text: str
    author: str = "Usuário"
    created_at: str


class UserImplementation(BaseModel):
    status: str = "pendente"  # "pendente" | "em_andamento" | "concluido"
    completed_steps: List[int] = Field(default_factory=list)
    comments: List[Comment] = Field(default_factory=list)


class Strategy(BaseModel):
    basename: str
    input_file: InputFile
    content: Content
    seo_knowledge: SEOKnowledge
    metadata: Dict[str, Any] = Field(default_factory=dict)
    user_implementation: UserImplementation = Field(default_factory=UserImplementation)
    updated_at: str


class ExecutionEvent(BaseModel):
    id: Optional[str] = None
    run_id: str
    source: str  # "pipeline" | "scraper"
    step: str
    status: str  # "info", "in_progress", "completed", "error"
    filename: Optional[str] = None
    target_url: Optional[str] = None
    message: str
    metrics: Dict[str, Any] = Field(default_factory=dict)
    error_details: Optional[str] = None
    created_at: str


class PipelineRun(BaseModel):
    """Representa uma execução completa do Pipeline ou Scraper identificada por run_id."""
    run_id: str
    source: str  # "pipeline" | "scraper"
    status: str = "in_progress"  # "in_progress" | "completed" | "error"
    target_url: Optional[str] = None  # Para execuções do scraper
    started_at: str
    finished_at: Optional[str] = None
    total_files: int = 0
    success_files: int = 0
    error_files: int = 0
    error_count: int = 0


class TargetProfile(BaseModel):
    id: Optional[str] = None
    target_url: str
    profile_name: Optional[str] = None
    last_scraped_at: str
    scrape_count: int = 1
    last_max_scrolls: Optional[int] = 50
    last_videos_count: Optional[int] = 0
    last_images_count: Optional[int] = 0
