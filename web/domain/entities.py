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


class SEOPillar(BaseModel):
    """Pilar de SEO utilizado para agrupamento e consolidação do Playbook."""
    id: str
    titulo: str
    keywords: List[str] = Field(default_factory=list)
    ativo: bool = True
    ordem: int = 1
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class CoreSEOStandard(BaseModel):
    """Diretriz ou Padrão Canônico Permanente de SEO armazenado na coleção core_seo_standards."""
    id: str  # slug único (ex: "h1-h2-h3-headings-hierarchy")
    title: str
    category: str = "on_page_structure"  # "on_page_structure" | "schema_org" | "geo_local" | "ai_search" | "technical"
    description: str
    source_strategy_id: Optional[str] = None  # Basename da estratégia no seo_knowledge (ex: "fb_72db9d049c3689c7")
    rule_scope: List[str] = Field(default_factory=lambda: ["all_pages"])
    checklist_items: List[str] = Field(default_factory=list)
    validation_rules: List[str] = Field(default_factory=list)
    applied_instances: List[Dict[str, Any]] = Field(default_factory=list)
    is_active: bool = True
    created_at: Optional[str] = None
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
    transcription_raw: Optional[str] = None
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
    nivel_dificuldade: Optional[str] = None
    tempo_estimado_implementacao: Optional[str] = None
    pre_requisitos: List[str] = Field(default_factory=list)
    resultado_esperado: Optional[str] = None
    quality_score: Optional[int] = None
    quality_grade: Optional[str] = None
    quality_issues: List[str] = Field(default_factory=list)


class Comment(BaseModel):
    id: str
    text: str
    author: str = "Usuário"
    created_at: str


class UserImplementation(BaseModel):
    status: str = "pendente"  # "pendente" | "em_andamento" | "concluido" | "core_standard"
    is_core_rule: bool = False
    rule_scope: List[str] = Field(default_factory=list)  # ex: ["all_pages", "on_page_structure", "schema_org"]
    applied_instances: List[Dict[str, Any]] = Field(default_factory=list)  # [{"page_slug": "...", "applied_at": "...", "notes": "..."}]
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
    status: str = "in_progress"  # "in_progress" | "completed" | "completed_with_errors" | "error"
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


class PostMediaItem(BaseModel):
    """Mídia individual dentro de um post. O media_id permite referência cruzada."""
    media_id: str
    url: str
    type: str  # "video" | "image"
    filename: Optional[str] = None
    downloaded: bool = False
    download_error: Optional[str] = None


class ProfilePost(BaseModel):
    """Post catalogado de um perfil-alvo do Facebook."""
    post_id: str
    profile_url: str
    profile_name: Optional[str] = None
    post_url: str
    post_type: str  # "video" | "image" | "album" | "text" | "reel"
    status: str = "pending"  # "pending" | "downloading" | "downloaded" | "processed" | "error"
    media_items: List[PostMediaItem] = Field(default_factory=list)
    post_text_preview: Optional[str] = None
    scroll_position: Optional[int] = None
    discovered_at: Optional[str] = None
    updated_at: Optional[str] = None
    error_message: Optional[str] = None


# --- Githa Context & SEO Automation Domain Entities ---

class GithaService(BaseModel):
    id: Optional[int] = None
    name: str
    price: Optional[float] = None
    duration_minutes: Optional[int] = None
    description: Optional[str] = None
    service_group: Optional[str] = None
    active: bool = True
    appointment_count: int = 0
    total_revenue: float = 0.0


class GithaProfessional(BaseModel):
    id: Optional[int] = None
    name: str
    phone: Optional[str] = None
    active: bool = True


class GithaContext(BaseModel):
    clinic_name: str = "Studio Githa"
    site_url: str = "https://studiogitha.com"
    wp_admin_url: str = "https://studiogitha.com/wp-admin"
    address: str = "Rua Juraci, 88 - Sala 102 - Nova Suíça, Belo Horizonte - MG, CEP 30421-181"
    phone: str = "(31) 9 9169-6979"
    instagram_url: str = "https://www.instagram.com/studiogitha"
    whatsapp_url: str = "https://api.whatsapp.com/send?phone=5531991696979"
    total_services: int = 0
    total_clients: int = 0
    total_appointments: int = 0
    services: List[GithaService] = Field(default_factory=list)
    popular_services: List[GithaService] = Field(default_factory=list)
    professionals: List[GithaProfessional] = Field(default_factory=list)
    seasonal_trends: List[Dict[str, Any]] = Field(default_factory=list)
    extracted_at: Optional[str] = None


class EnrichedStep(BaseModel):
    step_index: int
    raw_action: str
    action_type: str  # "browser_action" | "data_enrichable" | "llm_generatable" | "manual_only"
    target_tool: Optional[str] = None  # "wordpress_wpadmin" | "google_search_console" | "google_my_business" | "ga4" | "bing_webmaster" | "general_browser"
    githa_data_source: Optional[str] = None  # "services" | "popular_services" | "clinic_info" | "professionals"
    suggested_inputs: Dict[str, Any] = Field(default_factory=dict)
    is_completed: bool = False


class StrategyExecutionPlan(BaseModel):
    basename: str
    titulo_estrategia: str
    resumo_executivo: Optional[str] = None
    quality_score: Optional[int] = None
    quality_grade: Optional[str] = None
    status: str = "pendente"
    completed_steps: List[int] = Field(default_factory=list)
    total_steps: int = 0
    enriched_steps: List[EnrichedStep] = Field(default_factory=list)
    githa_context_summary: Dict[str, Any] = Field(default_factory=dict)
    generated_at: str


class PrioritizedStrategyItem(BaseModel):
    basename: str
    titulo_estrategia: str
    resumo_executivo: Optional[str] = None
    quality_score: int = 0
    quality_grade: str = "D"
    status: str = "pendente"
    priority_score: float = 0.0  # 0 to 100
    priority_level: str = "baixa"  # "critica" | "alta" | "media" | "baixa"
    matched_services: List[str] = Field(default_factory=list)
    matched_pillars: List[str] = Field(default_factory=list)
    completed_steps_count: int = 0
    total_steps_count: int = 0
    media_type: str = "video"


