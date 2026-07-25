"""
Domain Entities — PipelineFace (Clean Architecture)
===================================================
Entidades puras do domínio sem dependências de frameworks (FastAPI/PyMongo).
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class InputFile(BaseModel):
    filename: str
    type: str  # "video" | "image"
    extension: str
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
    step: str    # "SCRAPER_START", "SCROLL_PROGRESS", "VIDEO_DOWNLOAD", "FFMPEG_EXTRACT", "WHISPER_TRANSCRIBE", "VISION_CLASSIFY", "LLM_SEO_EXTRACTION", "COMPLETE", "ERROR"
    status: str  # "info", "in_progress", "completed", "error"
    filename: Optional[str] = None
    target_url: Optional[str] = None
    message: str
    metrics: Dict[str, Any] = Field(default_factory=dict)
    error_details: Optional[str] = None
    created_at: str
