"""
Mongo Strategy Repository — PipelineFace (Clean Architecture)
=============================================================
Implementação concreta do repositório de estratégias usando PyMongo.
"""

import re
from datetime import datetime
from typing import List, Optional, Tuple
from pymongo import MongoClient

from web.domain.entities import (
    Strategy, InputFile, Content, SavedFrame, SEOKnowledge, UserImplementation, Comment
)
from web.domain.repositories import AbstractStrategyRepository


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
