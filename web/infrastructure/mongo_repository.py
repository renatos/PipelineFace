"""
Mongo Repositories — PipelineFace (Clean Architecture)
======================================================
Implementação concreta dos repositórios de estratégias, telemetria e perfis alvo usando PyMongo.
"""

import re
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse
from pymongo import MongoClient

from web.domain.entities import (
    AppConfig, Strategy, InputFile, Content, SavedFrame, SEOKnowledge, UserImplementation, Comment,
    ExecutionEvent, PipelineRun, TargetProfile, ProfilePost
)
from web.domain.repositories import (
    AbstractAppConfigRepository, AbstractStrategyRepository, AbstractExecutionEventRepository,
    AbstractPipelineRunRepository, AbstractTargetProfileRepository, AbstractProfilePostRepository
)


# Valores padrão que serão inseridos na coleção app_config na primeira execução
APP_CONFIG_DEFAULTS = [
    # --- Pipeline ---
    {"key": "whisper_url", "group": "pipeline", "value": "http://localhost:9000/asr",
     "value_type": "string", "label": "URL do Whisper",
     "description": "Endpoint do serviço Whisper para transcrição de áudio"},
    {"key": "ollama_url", "group": "pipeline", "value": "http://localhost:11434/api/chat",
     "value_type": "string", "label": "URL do Ollama",
     "description": "Endpoint da API de chat do Ollama"},
    {"key": "webhook_url", "group": "pipeline", "value": "http://localhost:8000/api/webhooks/execution-event",
     "value_type": "string", "label": "URL do Webhook de Telemetria",
     "description": "Endpoint da Web API para receber eventos de execução"},
    # --- Modelos ---
    {"key": "vision_model", "group": "models", "value": "moondream",
     "value_type": "string", "label": "Modelo de Visão (frames)",
     "description": "Modelo Ollama usado para análise visual de frames e imagens"},
    {"key": "text_model", "group": "models", "value": "qwen2.5:3b",
     "value_type": "string", "label": "Modelo de Texto (SEO)",
     "description": "Modelo Ollama usado para extração de conhecimento em SEO"},
    {"key": "whisper_model", "group": "models", "value": "base",
     "value_type": "string", "label": "Modelo Whisper",
     "description": "Tamanho do modelo Whisper: tiny, base, small, medium, large"},
    # --- Scraper ---
    {"key": "scraper_max_scrolls", "group": "scraper", "value": "50",
     "value_type": "int", "label": "Máx. Scrolls do Scraper",
     "description": "Número máximo de scrolls por sessão de coleta"},
    {"key": "scraper_scroll_pause", "group": "scraper", "value": "2.5",
     "value_type": "float", "label": "Pausa entre Scrolls (seg)",
     "description": "Segundos de espera entre cada scroll para carregamento de conteúdo"},
    {"key": "scraper_session_dir", "group": "scraper", "value": "/data/scraper/session",
     "value_type": "string", "label": "Diretório de Sessão",
     "description": "Caminho onde os cookies/sessão do navegador são armazenados"},
    {"key": "scraper_download_batch_size", "group": "scraper", "value": "10",
     "value_type": "int", "label": "Tamanho do Lote de Download",
     "description": "Quantidade padrão de posts pendentes baixados por execução"},
    {"key": "list_posts_interval_minutes", "group": "scraper", "value": "60",
     "value_type": "int", "label": "Intervalo de Re-checagem (min)",
     "description": "Intervalo em minutos para re-checagem de novos posts"},
    {"key": "list_posts_max_scrolls", "group": "scraper", "value": "100",
     "value_type": "int", "label": "Máx. Scrolls na Listagem",
     "description": "Número máximo de scrolls durante a listagem de posts"},
    # --- Sistema ---
    {"key": "pipeline_version", "group": "system", "value": "3.0.0",
     "value_type": "string", "label": "Versão do Pipeline",
     "description": "Versão atual do pipeline de extração", "editable": False},
    {"key": "fps_frame_extraction", "group": "pipeline", "value": "1/10",
     "value_type": "string", "label": "Taxa de Frames (FFmpeg)",
     "description": "Taxa de extração de frames do vídeo (ex: 1/10 = 1 frame a cada 10s)"},
    {"key": "max_ocr_frames", "group": "pipeline", "value": "3",
     "value_type": "int", "label": "Máx. Frames para OCR",
     "description": "Número máximo de frames enviados para análise de texto (OCR) por vídeo"},
]


class MongoStrategyRepository(AbstractStrategyRepository):
    def __init__(self, mongo_uri: str = "mongodb://localhost:27017", db_name: str = "pipelineface", collection_name: str = "seo_knowledge"):
        self.client = MongoClient(mongo_uri, serverSelectionTimeoutMS=3000)
        self.db = self.client[db_name]
        self.collection = self.db[collection_name]

    def save_or_update(self, strategy: Strategy) -> None:
        doc = strategy.model_dump()
        self.collection.update_one(
            {"basename": strategy.basename},
            {"$set": doc},
            upsert=True
        )

    def find_by_basename(self, basename: str) -> Optional[Strategy]:
        doc = self.collection.find_one({"basename": basename}, {"_id": 0})
        if not doc:
            return None
        return Strategy(**doc)

    def list_all(
        self,
        status: Optional[str] = None,
        search: Optional[str] = None,
        media_type: Optional[str] = None
    ) -> List[Strategy]:
        query = {}
        if status:
            query["user_implementation.status"] = status
        if media_type:
            query["input_file.type"] = media_type
        if search:
            regex = re.compile(search, re.IGNORECASE)
            query["$or"] = [
                {"seo_knowledge.titulo_estrategia": regex},
                {"seo_knowledge.resumo_executivo": regex},
                {"seo_knowledge.termos_e_exemplos_usados": regex},
                {"seo_knowledge.ferramentas_e_telas_utilizadas": regex},
                {"basename": regex}
            ]

        docs = list(self.collection.find(query, {"_id": 0}).sort("updated_at", -1))
        return [Strategy(**d) for d in docs]

    def toggle_step(self, basename: str, step_index: int) -> Tuple[List[int], str]:
        doc = self.collection.find_one({"basename": basename})
        if not doc:
            raise KeyError(f"Estratégia {basename} não encontrada")

        user_impl = doc.get("user_implementation", {})
        completed = set(user_impl.get("completed_steps", []))

        if step_index in completed:
            completed.remove(step_index)
        else:
            completed.add(step_index)

        completed_list = sorted(list(completed))
        total_steps = len(doc.get("seo_knowledge", {}).get("passo_a_passo_detalhado", []))

        new_status = user_impl.get("status", "pendente")
        if total_steps > 0 and len(completed_list) == total_steps:
            new_status = "concluido"
        elif len(completed_list) > 0 and new_status == "pendente":
            new_status = "em_andamento"

        self.collection.update_one(
            {"basename": basename},
            {"$set": {
                "user_implementation.completed_steps": completed_list,
                "user_implementation.status": new_status,
                "updated_at": datetime.now().isoformat()
            }}
        )
        return completed_list, new_status

    def update_status(self, basename: str, status: str) -> str:
        res = self.collection.update_one(
            {"basename": basename},
            {"$set": {
                "user_implementation.status": status,
                "updated_at": datetime.now().isoformat()
            }}
        )
        if res.matched_count == 0:
            raise KeyError(f"Estratégia {basename} não encontrada")
        return status

    def add_comment(self, basename: str, comment: Comment) -> Comment:
        comment_dict = comment.model_dump()
        res = self.collection.update_one(
            {"basename": basename},
            {"$push": {"user_implementation.comments": comment_dict},
             "$set": {"updated_at": datetime.now().isoformat()}}
        )
        if res.matched_count == 0:
            raise KeyError(f"Estratégia {basename} não encontrada")
        return comment


class MongoExecutionEventRepository(AbstractExecutionEventRepository):
    def __init__(self, mongo_uri: str = "mongodb://localhost:27017", db_name: str = "pipelineface", collection_name: str = "execution_events"):
        self.client = MongoClient(mongo_uri, serverSelectionTimeoutMS=3000)
        self.db = self.client[db_name]
        self.collection = self.db[collection_name]

    def save_event(self, event: ExecutionEvent) -> ExecutionEvent:
        doc = event.model_dump()
        if not doc.get("id"):
            doc["id"] = str(uuid.uuid4())[:8]
            event.id = doc["id"]

        self.collection.insert_one(doc)
        return event

    def list_events(
        self,
        run_id: Optional[str] = None,
        source: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50
    ) -> List[ExecutionEvent]:
        query = {}
        if run_id:
            query["run_id"] = run_id
        if source:
            query["source"] = source
        if status:
            query["status"] = status

        docs = list(self.collection.find(query, {"_id": 0}).sort("created_at", -1).limit(limit))
        return [ExecutionEvent(**d) for d in docs]


class MongoPipelineRunRepository(AbstractPipelineRunRepository):
    def __init__(self, mongo_uri: str = "mongodb://localhost:27017", db_name: str = "pipelineface", collection_name: str = "pipeline_runs"):
        self.client = MongoClient(mongo_uri, serverSelectionTimeoutMS=3000)
        self.db = self.client[db_name]
        self.collection = self.db[collection_name]
        # Garantir índice único em run_id
        self.collection.create_index("run_id", unique=True, sparse=True)

    def save_or_update(self, run: PipelineRun) -> None:
        doc = run.model_dump()
        self.collection.update_one(
            {"run_id": run.run_id},
            {"$set": doc},
            upsert=True
        )

    def find_by_run_id(self, run_id: str) -> Optional[PipelineRun]:
        doc = self.collection.find_one({"run_id": run_id}, {"_id": 0})
        if not doc:
            return None
        return PipelineRun(**doc)

    def list_runs(self, source: Optional[str] = None, limit: int = 20) -> List[PipelineRun]:
        query = {}
        if source:
            query["source"] = source
        docs = list(self.collection.find(query, {"_id": 0}).sort("started_at", -1).limit(limit))
        return [PipelineRun(**d) for d in docs]


class MongoTargetProfileRepository(AbstractTargetProfileRepository):
    def __init__(self, mongo_uri: str = "mongodb://localhost:27017", db_name: str = "pipelineface", collection_name: str = "target_profiles"):
        self.client = MongoClient(mongo_uri, serverSelectionTimeoutMS=3000)
        self.db = self.client[db_name]
        self.collection = self.db[collection_name]

    def save_or_update_profile(self, target_url: str, max_scrolls: int = 50) -> TargetProfile:
        target_url = target_url.strip()
        parsed = urlparse(target_url)
        profile_name = parsed.path.strip("/").split("/")[-1] if parsed.path else "Perfil"

        existing = self.collection.find_one({"target_url": target_url})
        scrape_count = (existing.get("scrape_count", 0) + 1) if existing else 1
        prof_id = existing.get("id") if existing else str(uuid.uuid4())[:8]

        profile = TargetProfile(
            id=prof_id,
            target_url=target_url,
            profile_name=profile_name or target_url,
            last_scraped_at=datetime.now().isoformat(),
            scrape_count=scrape_count,
            last_max_scrolls=max_scrolls,
            last_videos_count=existing.get("last_videos_count", 0) if existing else 0,
            last_images_count=existing.get("last_images_count", 0) if existing else 0
        )

        doc = profile.model_dump()
        self.collection.update_one(
            {"target_url": target_url},
            {"$set": doc},
            upsert=True
        )
        return profile

    def list_profiles(self, limit: int = 20) -> List[TargetProfile]:
        docs = list(self.collection.find({}, {"_id": 0}).sort("last_scraped_at", -1).limit(limit))
        return [TargetProfile(**d) for d in docs]


class MongoAppConfigRepository(AbstractAppConfigRepository):
    def __init__(self, mongo_uri: str = "mongodb://localhost:27017", db_name: str = "pipelineface", collection_name: str = "app_config"):
        self.client = MongoClient(mongo_uri, serverSelectionTimeoutMS=3000)
        self.db = self.client[db_name]
        self.collection = self.db[collection_name]
        # Índice único por key
        self.collection.create_index("key", unique=True, sparse=True)
        # Popular com valores padrão na primeira inicialização
        self.seed_defaults()

    def seed_defaults(self) -> None:
        """Insere os parâmetros padrão apenas se ainda não existirem na coleção."""
        now = datetime.now().isoformat()
        for cfg in APP_CONFIG_DEFAULTS:
            self.collection.update_one(
                {"key": cfg["key"]},
                {"$setOnInsert": {**cfg, "editable": cfg.get("editable", True), "updated_at": now}},
                upsert=True
            )

    def list_all(self, group: Optional[str] = None) -> List[AppConfig]:
        query = {"group": group} if group else {}
        # Ordenar por grupo e depois label para exibição agrupada
        docs = list(self.collection.find(query, {"_id": 0}).sort([("group", 1), ("label", 1)]))
        return [AppConfig(**d) for d in docs]

    def get(self, key: str) -> Optional[AppConfig]:
        doc = self.collection.find_one({"key": key}, {"_id": 0})
        return AppConfig(**doc) if doc else None

    def update(self, key: str, value: str) -> Optional[AppConfig]:
        result = self.collection.find_one_and_update(
            {"key": key, "editable": True},
            {"$set": {"value": value, "updated_at": datetime.now().isoformat()}},
            return_document=True,
            projection={"_id": 0}
        )
        return AppConfig(**result) if result else None

    def as_dict(self) -> Dict[str, str]:
        """Retorna todos os parâmetros como dicionário key -> value (string bruto)."""
        return {doc["key"]: doc["value"] for doc in self.collection.find({}, {"_id": 0, "key": 1, "value": 1})}


class MongoProfilePostRepository(AbstractProfilePostRepository):
    """Implementação MongoDB para a coleção profile_posts."""

    def __init__(self, mongo_uri: str = "mongodb://localhost:27017", db_name: str = "pipelineface", collection_name: str = "profile_posts"):
        self.client = MongoClient(mongo_uri, serverSelectionTimeoutMS=3000)
        self.db = self.client[db_name]
        self.collection = self.db[collection_name]
        self._ensure_indexes()

    def _ensure_indexes(self):
        self.collection.create_index("post_id", unique=True, sparse=True)
        self.collection.create_index([("profile_url", 1), ("status", 1)])
        self.collection.create_index("media_items.media_id", sparse=True)

    def upsert_post(self, post: ProfilePost) -> bool:
        now = datetime.now().isoformat()
        doc = post.model_dump()

        res = self.collection.update_one(
            {"post_id": post.post_id},
            {
                "$set": {
                    "profile_url": post.profile_url,
                    "profile_name": post.profile_name,
                    "post_url": post.post_url,
                    "post_type": post.post_type,
                    "media_items": doc["media_items"],
                    "post_text_preview": post.post_text_preview,
                    "scroll_position": post.scroll_position,
                    "updated_at": now,
                },
                "$setOnInsert": {
                    "status": post.status or "pending",
                    "discovered_at": now,
                    "error_message": None
                }
            },
            upsert=True
        )
        return res.upserted_id is not None

    def find_by_post_id(self, post_id: str) -> Optional[ProfilePost]:
        doc = self.collection.find_one({"post_id": post_id}, {"_id": 0})
        if not doc:
            return None
        return ProfilePost(**doc)

    def list_posts(self, profile_url: Optional[str] = None, status: Optional[str] = None, limit: int = 500) -> List[ProfilePost]:
        query = {}
        if profile_url:
            query["profile_url"] = profile_url.rstrip("/")
        if status:
            query["status"] = status

        docs = list(self.collection.find(query, {"_id": 0}).sort("discovered_at", -1).limit(limit))
        # Autocorreção: atualizar post_type de posts que contenham URLs de vídeos/reels mas estejam salvos como image ou post
        updated_docs = []
        for d in docs:
            post_url = d.get("post_url", "")
            media_items = d.get("media_items", [])
            has_video_url = any(k in post_url for k in ["/reel/", "/videos/", "/watch/", ".mp4"]) or any(
                m.get("type") == "video" or any(k in (m.get("url") or "") for k in ["/reel/", "/videos/", "/watch/", ".mp4"])
                for m in media_items
            )
            if has_video_url and d.get("post_type") != "video":
                d["post_type"] = "video"
                try:
                    self.collection.update_one({"post_id": d["post_id"]}, {"$set": {"post_type": "video"}})
                except Exception:
                    pass
            updated_docs.append(d)

        return [ProfilePost(**d) for d in updated_docs]

    def delete_post(self, post_id: str) -> bool:
        res = self.collection.delete_one({"post_id": post_id})
        return res.deleted_count > 0

    def get_pending_posts(self, profile_url: Optional[str] = None, limit: int = 10) -> List[ProfilePost]:
        query = {"status": "pending"}
        if profile_url:
            query["profile_url"] = profile_url.rstrip("/")

        docs = list(self.collection.find(query, {"_id": 0}).sort("discovered_at", 1).limit(limit))
        return [ProfilePost(**d) for d in docs]

    def update_status(self, post_id: str, status: str, error_message: Optional[str] = None) -> bool:
        update = {"$set": {"status": status, "updated_at": datetime.now().isoformat()}}
        if error_message is not None:
            update["$set"]["error_message"] = error_message

        res = self.collection.update_one({"post_id": post_id}, update)
        return res.matched_count > 0

    def update_media_status(self, post_id: str, media_id: str, downloaded: bool, filename: Optional[str] = None, error: Optional[str] = None) -> bool:
        update = {
            "$set": {
                "media_items.$.downloaded": downloaded,
                "updated_at": datetime.now().isoformat()
            }
        }
        if filename:
            update["$set"]["media_items.$.filename"] = filename
        if error:
            update["$set"]["media_items.$.download_error"] = error

        res = self.collection.update_one(
            {"post_id": post_id, "media_items.media_id": media_id},
            update
        )
        return res.matched_count > 0

    def get_stats(self, profile_url: Optional[str] = None) -> Dict[str, int]:
        match_stage = {}
        if profile_url:
            match_stage = {"profile_url": profile_url.rstrip("/")}

        pipeline = []
        if match_stage:
            pipeline.append({"$match": match_stage})
        pipeline.append({"$group": {"_id": "$status", "count": {"$sum": 1}}})

        results = list(self.collection.aggregate(pipeline))
        stats = {
            "total": 0,
            "pending": 0,
            "downloading": 0,
            "downloaded": 0,
            "processed": 0,
            "error": 0
        }
        for r in results:
            status_name = r["_id"]
            cnt = r["count"]
            if status_name in stats:
                stats[status_name] = cnt
            stats["total"] += cnt

        return stats



# Valores padrão que serão inseridos na coleção app_config na primeira execução
APP_CONFIG_DEFAULTS = [
    # --- Pipeline ---
    {"key": "whisper_url", "group": "pipeline", "value": "http://localhost:9000/asr",
     "value_type": "string", "label": "URL do Whisper",
     "description": "Endpoint do serviço Whisper para transcrição de áudio"},
    {"key": "ollama_url", "group": "pipeline", "value": "http://localhost:11434/api/chat",
     "value_type": "string", "label": "URL do Ollama",
     "description": "Endpoint da API de chat do Ollama"},
    {"key": "webhook_url", "group": "pipeline", "value": "http://localhost:8000/api/webhooks/execution-event",
     "value_type": "string", "label": "URL do Webhook de Telemetria",
     "description": "Endpoint da Web API para receber eventos de execução"},
    # --- Modelos ---
    {"key": "vision_model", "group": "models", "value": "moondream",
     "value_type": "string", "label": "Modelo de Visão (frames)",
     "description": "Modelo Ollama usado para análise visual de frames e imagens"},
    {"key": "text_model", "group": "models", "value": "qwen2.5:3b",
     "value_type": "string", "label": "Modelo de Texto (SEO)",
     "description": "Modelo Ollama usado para extração de conhecimento em SEO"},
    {"key": "whisper_model", "group": "models", "value": "base",
     "value_type": "string", "label": "Modelo Whisper",
     "description": "Tamanho do modelo Whisper: tiny, base, small, medium, large"},
    # --- Scraper ---
    {"key": "scraper_max_scrolls", "group": "scraper", "value": "50",
     "value_type": "int", "label": "Máx. Scrolls do Scraper",
     "description": "Número máximo de scrolls por sessão de coleta"},
    {"key": "scraper_scroll_pause", "group": "scraper", "value": "2.5",
     "value_type": "float", "label": "Pausa entre Scrolls (seg)",
     "description": "Segundos de espera entre cada scroll para carregamento de conteúdo"},
    {"key": "scraper_session_dir", "group": "scraper", "value": "/data/scraper/session",
     "value_type": "string", "label": "Diretório de Sessão",
     "description": "Caminho onde os cookies/sessão do navegador são armazenados"},
    # --- Sistema ---
    {"key": "pipeline_version", "group": "system", "value": "3.0.0",
     "value_type": "string", "label": "Versão do Pipeline",
     "description": "Versão atual do pipeline de extração", "editable": False},
    {"key": "fps_frame_extraction", "group": "pipeline", "value": "1/10",
     "value_type": "string", "label": "Taxa de Frames (FFmpeg)",
     "description": "Taxa de extração de frames do vídeo (ex: 1/10 = 1 frame a cada 10s)"},
    {"key": "max_ocr_frames", "group": "pipeline", "value": "3",
     "value_type": "int", "label": "Máx. Frames para OCR",
     "description": "Número máximo de frames enviados para análise de texto (OCR) por vídeo"},
]


class MongoStrategyRepository(AbstractStrategyRepository):
    def __init__(self, mongo_uri: str = "mongodb://localhost:27017", db_name: str = "pipelineface", collection_name: str = "seo_knowledge"):
        self.client = MongoClient(mongo_uri, serverSelectionTimeoutMS=3000)
        self.db = self.client[db_name]
        self.collection = self.db[collection_name]

    def save_or_update(self, strategy: Strategy) -> None:
        doc = strategy.model_dump()
        self.collection.update_one(
            {"basename": strategy.basename},
            {"$set": doc},
            upsert=True
        )

    def find_by_basename(self, basename: str) -> Optional[Strategy]:
        doc = self.collection.find_one({"basename": basename}, {"_id": 0})
        if not doc:
            return None
        return Strategy(**doc)

    def list_all(
        self,
        status: Optional[str] = None,
        search: Optional[str] = None,
        media_type: Optional[str] = None
    ) -> List[Strategy]:
        query = {}
        if status:
            query["user_implementation.status"] = status
        if media_type:
            query["input_file.type"] = media_type
        if search:
            regex = re.compile(search, re.IGNORECASE)
            query["$or"] = [
                {"seo_knowledge.titulo_estrategia": regex},
                {"seo_knowledge.resumo_executivo": regex},
                {"seo_knowledge.termos_e_exemplos_usados": regex},
                {"seo_knowledge.ferramentas_e_telas_utilizadas": regex},
                {"basename": regex}
            ]

        docs = list(self.collection.find(query, {"_id": 0}).sort("updated_at", -1))
        return [Strategy(**d) for d in docs]

    def toggle_step(self, basename: str, step_index: int) -> Tuple[List[int], str]:
        doc = self.collection.find_one({"basename": basename})
        if not doc:
            raise KeyError(f"Estratégia {basename} não encontrada")

        user_impl = doc.get("user_implementation", {})
        completed = set(user_impl.get("completed_steps", []))

        if step_index in completed:
            completed.remove(step_index)
        else:
            completed.add(step_index)

        completed_list = sorted(list(completed))
        total_steps = len(doc.get("seo_knowledge", {}).get("passo_a_passo_detalhado", []))

        new_status = user_impl.get("status", "pendente")
        if total_steps > 0 and len(completed_list) == total_steps:
            new_status = "concluido"
        elif len(completed_list) > 0 and new_status == "pendente":
            new_status = "em_andamento"

        self.collection.update_one(
            {"basename": basename},
            {"$set": {
                "user_implementation.completed_steps": completed_list,
                "user_implementation.status": new_status,
                "updated_at": datetime.now().isoformat()
            }}
        )
        return completed_list, new_status

    def update_status(self, basename: str, status: str) -> str:
        res = self.collection.update_one(
            {"basename": basename},
            {"$set": {
                "user_implementation.status": status,
                "updated_at": datetime.now().isoformat()
            }}
        )
        if res.matched_count == 0:
            raise KeyError(f"Estratégia {basename} não encontrada")
        return status

    def add_comment(self, basename: str, comment: Comment) -> Comment:
        comment_dict = comment.model_dump()
        res = self.collection.update_one(
            {"basename": basename},
            {"$push": {"user_implementation.comments": comment_dict},
             "$set": {"updated_at": datetime.now().isoformat()}}
        )
        if res.matched_count == 0:
            raise KeyError(f"Estratégia {basename} não encontrada")
        return comment


class MongoExecutionEventRepository(AbstractExecutionEventRepository):
    def __init__(self, mongo_uri: str = "mongodb://localhost:27017", db_name: str = "pipelineface", collection_name: str = "execution_events"):
        self.client = MongoClient(mongo_uri, serverSelectionTimeoutMS=3000)
        self.db = self.client[db_name]
        self.collection = self.db[collection_name]

    def save_event(self, event: ExecutionEvent) -> ExecutionEvent:
        doc = event.model_dump()
        if not doc.get("id"):
            doc["id"] = str(uuid.uuid4())[:8]
            event.id = doc["id"]

        self.collection.insert_one(doc)
        return event

    def list_events(
        self,
        run_id: Optional[str] = None,
        source: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50
    ) -> List[ExecutionEvent]:
        query = {}
        if run_id:
            query["run_id"] = run_id
        if source:
            query["source"] = source
        if status:
            query["status"] = status

        docs = list(self.collection.find(query, {"_id": 0}).sort("created_at", -1).limit(limit))
        return [ExecutionEvent(**d) for d in docs]


class MongoPipelineRunRepository(AbstractPipelineRunRepository):
    def __init__(self, mongo_uri: str = "mongodb://localhost:27017", db_name: str = "pipelineface", collection_name: str = "pipeline_runs"):
        self.client = MongoClient(mongo_uri, serverSelectionTimeoutMS=3000)
        self.db = self.client[db_name]
        self.collection = self.db[collection_name]
        # Garantir índice único em run_id
        self.collection.create_index("run_id", unique=True, sparse=True)

    def save_or_update(self, run: PipelineRun) -> None:
        doc = run.model_dump()
        self.collection.update_one(
            {"run_id": run.run_id},
            {"$set": doc},
            upsert=True
        )

    def find_by_run_id(self, run_id: str) -> Optional[PipelineRun]:
        doc = self.collection.find_one({"run_id": run_id}, {"_id": 0})
        if not doc:
            return None
        return PipelineRun(**doc)

    def list_runs(self, source: Optional[str] = None, limit: int = 20) -> List[PipelineRun]:
        query = {}
        if source:
            query["source"] = source
        docs = list(self.collection.find(query, {"_id": 0}).sort("started_at", -1).limit(limit))
        return [PipelineRun(**d) for d in docs]


class MongoTargetProfileRepository(AbstractTargetProfileRepository):
    def __init__(self, mongo_uri: str = "mongodb://localhost:27017", db_name: str = "pipelineface", collection_name: str = "target_profiles"):
        self.client = MongoClient(mongo_uri, serverSelectionTimeoutMS=3000)
        self.db = self.client[db_name]
        self.collection = self.db[collection_name]

    def save_or_update_profile(self, target_url: str, max_scrolls: int = 50) -> TargetProfile:
        target_url = target_url.strip()
        parsed = urlparse(target_url)
        profile_name = parsed.path.strip("/").split("/")[-1] if parsed.path else "Perfil"

        existing = self.collection.find_one({"target_url": target_url})
        scrape_count = (existing.get("scrape_count", 0) + 1) if existing else 1
        prof_id = existing.get("id") if existing else str(uuid.uuid4())[:8]

        profile = TargetProfile(
            id=prof_id,
            target_url=target_url,
            profile_name=profile_name or target_url,
            last_scraped_at=datetime.now().isoformat(),
            scrape_count=scrape_count,
            last_max_scrolls=max_scrolls,
            last_videos_count=existing.get("last_videos_count", 0) if existing else 0,
            last_images_count=existing.get("last_images_count", 0) if existing else 0
        )

        doc = profile.model_dump()
        self.collection.update_one(
            {"target_url": target_url},
            {"$set": doc},
            upsert=True
        )
        return profile

    def list_profiles(self, limit: int = 20) -> List[TargetProfile]:
        docs = list(self.collection.find({}, {"_id": 0}).sort("last_scraped_at", -1).limit(limit))
        return [TargetProfile(**d) for d in docs]


class MongoAppConfigRepository(AbstractAppConfigRepository):
    def __init__(self, mongo_uri: str = "mongodb://localhost:27017", db_name: str = "pipelineface", collection_name: str = "app_config"):
        self.client = MongoClient(mongo_uri, serverSelectionTimeoutMS=3000)
        self.db = self.client[db_name]
        self.collection = self.db[collection_name]
        # Índice único por key
        self.collection.create_index("key", unique=True, sparse=True)
        # Popular com valores padrão na primeira inicialização
        self.seed_defaults()

    def seed_defaults(self) -> None:
        """Insere os parâmetros padrão apenas se ainda não existirem na coleção."""
        now = datetime.now().isoformat()
        for cfg in APP_CONFIG_DEFAULTS:
            self.collection.update_one(
                {"key": cfg["key"]},
                {"$setOnInsert": {**cfg, "editable": cfg.get("editable", True), "updated_at": now}},
                upsert=True
            )

    def list_all(self, group: Optional[str] = None) -> List[AppConfig]:
        query = {"group": group} if group else {}
        # Ordenar por grupo e depois label para exibição agrupada
        docs = list(self.collection.find(query, {"_id": 0}).sort([("group", 1), ("label", 1)]))
        return [AppConfig(**d) for d in docs]

    def get(self, key: str) -> Optional[AppConfig]:
        doc = self.collection.find_one({"key": key}, {"_id": 0})
        return AppConfig(**doc) if doc else None

    def update(self, key: str, value: str) -> Optional[AppConfig]:
        result = self.collection.find_one_and_update(
            {"key": key, "editable": True},
            {"$set": {"value": value, "updated_at": datetime.now().isoformat()}},
            return_document=True,
            projection={"_id": 0}
        )
        return AppConfig(**result) if result else None

    def as_dict(self) -> Dict[str, str]:
        """Retorna todos os parâmetros como dicionário key -> value (string bruto)."""
        return {doc["key"]: doc["value"] for doc in self.collection.find({}, {"_id": 0, "key": 1, "value": 1})}
