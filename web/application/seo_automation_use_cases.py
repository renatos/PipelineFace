"""
SEO Automation Use Cases — PipelineFace (Clean Architecture)
============================================================
Casos de uso para priorização de estratégias, enriquecimento com dados
reais do Githa e montagem de planos de execução para o Chrome DevTools MCP.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
import re

from web.domain.entities import (
    GithaContext, StrategyExecutionPlan, EnrichedStep, PrioritizedStrategyItem,
    Strategy, Comment
)
from web.infrastructure.githa_repository import GithaContextRepository
from web.domain.repositories import AbstractStrategyRepository, AbstractSEOPillarRepository



class GetGithaContextUseCase:
    """Retorna o contexto completo de negócio da clínica Studio Githa."""

    def __init__(self, githa_repo: GithaContextRepository):
        self.githa_repo = githa_repo

    def execute(self) -> GithaContext:
        return self.githa_repo.get_full_context()


class PrioritizeStrategiesUseCase:
    """
    Ranqueia as estratégias SEO do PipelineFace pelo impacto no negócio do Studio Githa.
    Cruza catálogo de serviços populares, pilares de SEO local/on-page e score de qualidade.
    """

    def __init__(
        self,
        strategy_repo: AbstractStrategyRepository,
        githa_repo: GithaContextRepository,
        pillar_repo: Optional[AbstractSEOPillarRepository] = None
    ):
        self.strategy_repo = strategy_repo
        self.githa_repo = githa_repo
        self.pillar_repo = pillar_repo

    def execute(self, status_filter: Optional[str] = None, limit: int = 50) -> List[PrioritizedStrategyItem]:
        strategies: List[Strategy] = self.strategy_repo.list_all()
        githa_ctx = self.githa_repo.get_full_context()


        # Extrair palavras-chave dos serviços populares do Githa
        service_keywords = set()
        for s in githa_ctx.popular_services[:10]:
            words = [w.lower() for w in re.split(r"[\s,\-/]+", s.name) if len(w) > 3]
            service_keywords.update(words)

        # Palavras-chave de alto valor para estética & SEO local
        high_value_seo_terms = {
            "local", "google", "search console", "maps", "business", "gmb", "ranking",
            "palavra-chave", "pesquisa", "indexação", "on-page", "h1", "meta", "schema",
            "bing", "chatgpt", "geolocalização", "cidade", "bairro", "serviço", "página",
            "conversão", "tráfego", "artigo", "blog", "visagismo", "estética", "pele", "sobrancelha"
        }

        prioritized_items = []

        for strat in strategies:
            # Filtro por status
            user_status = strat.user_implementation.status if strat.user_implementation else "pendente"
            if status_filter and user_status != status_filter:
                continue

            seo = strat.seo_knowledge
            title = (seo.titulo_estrategia or strat.basename).strip()
            summary = seo.resumo_executivo or ""
            concepts = " ".join(seo.conceitos_mencionados or [])
            tools = " ".join(seo.ferramentas_e_telas_utilizadas or [])
            full_text = f"{title} {summary} {concepts} {tools}".lower()

            # 1. Match com serviços reais do Githa
            matched_services = []
            service_score = 0.0
            for s in githa_ctx.popular_services:
                s_name_lower = s.name.lower()
                # Verifica se parte relevante do nome do serviço aparece
                s_tokens = [w for w in re.split(r"[\s,\-/]+", s_name_lower) if len(w) > 3]
                if any(token in full_text for token in s_tokens):
                    matched_services.append(s.name)
                    service_score += 10.0

            service_score = min(service_score, 30.0)

            # 2. Match com termos de SEO Local & Alto Impacto
            term_matches = [term for term in high_value_seo_terms if term in full_text]
            term_score = min(len(term_matches) * 4.0, 30.0)

            # 3. Quality Score da Estratégia
            q_score = seo.quality_score or 0
            quality_component = (q_score / 100.0) * 25.0

            # 4. Status de Implementação (Pendente priorizado sobre concluído)
            status_score = 10.0 if user_status == "pendente" else (5.0 if user_status == "em_andamento" else 0.0)

            # 5. Facilidade de Ação (passos bem definidos)
            steps_count = len(seo.passo_a_passo_detalhado or [])
            steps_score = 5.0 if (3 <= steps_count <= 8) else 2.0

            total_priority = round(service_score + term_score + quality_component + status_score + steps_score, 1)

            if total_priority >= 70.0:
                priority_level = "critica"
            elif total_priority >= 50.0:
                priority_level = "alta"
            elif total_priority >= 30.0:
                priority_level = "media"
            else:
                priority_level = "baixa"

            completed_count = len(strat.user_implementation.completed_steps) if strat.user_implementation else 0

            prioritized_items.append(
                PrioritizedStrategyItem(
                    basename=strat.basename,
                    titulo_estrategia=title,
                    resumo_executivo=summary,
                    quality_score=q_score,
                    quality_grade=seo.quality_grade or "D",
                    status=user_status,
                    priority_score=total_priority,
                    priority_level=priority_level,
                    matched_services=matched_services[:5],
                    matched_pillars=term_matches[:4],
                    completed_steps_count=completed_count,
                    total_steps_count=steps_count,
                    media_type=strat.input_file.type if strat.input_file else "video"
                )
            )

        # Ordenar por prioridade decrescente e quality_score
        prioritized_items.sort(key=lambda x: (x.priority_score, x.quality_score), reverse=True)
        return prioritized_items[:limit]


class BuildExecutionPlanUseCase:
    """
    Constrói um plano de execução detalhado para uma estratégia específica,
    classificando cada passo e injetando as variáveis do Studio Githa.
    """

    def __init__(self, strategy_repo: AbstractStrategyRepository, githa_repo: GithaContextRepository):
        self.strategy_repo = strategy_repo
        self.githa_repo = githa_repo

    def execute(self, basename: str) -> StrategyExecutionPlan:
        strat = self.strategy_repo.find_by_basename(basename)
        if not strat:
            raise KeyError(f"Estratégia '{basename}' não encontrada.")

        githa_ctx = self.githa_repo.get_full_context()
        seo = strat.seo_knowledge
        raw_steps = seo.passo_a_passo_detalhado or []
        completed_steps = strat.user_implementation.completed_steps if strat.user_implementation else []

        enriched_steps: List[EnrichedStep] = []

        for idx, step_text in enumerate(raw_steps):
            step_lower = step_text.lower()

            # Classificação da ferramenta alvo
            target_tool = "general_browser"
            if any(w in step_lower for w in ["wordpress", "wp-admin", "página", "post", "publicar", "rank math", "yoast", "slug", "h1", "h2", "h3", "editor"]):
                target_tool = "wordpress_wpadmin"
            elif any(w in step_lower for w in ["search console", "indexação", "desempenho", "consultas", "sitemap", "solicitar indexação", "inspeção de url"]):
                target_tool = "google_search_console"
            elif any(w in step_lower for w in ["google meu negócio", "google business", "perfil da empresa", "gmb", "google maps"]):
                target_tool = "google_my_business"
            elif any(w in step_lower for w in ["google analytics", "ga4", "aquisição", "origem da sessão"]):
                target_tool = "ga4"
            elif any(w in step_lower for w in ["bing", "bing places", "bing webmaster"]):
                target_tool = "bing_webmaster"
            elif any(w in step_lower for w in ["google cloud", "console.cloud", "conta de serviço", "api instant"]):
                target_tool = "google_cloud_console"

            # Classificação do tipo de ação
            action_type = "browser_action"
            githa_source = "clinic_info"
            suggested_inputs: Dict[str, Any] = {
                "clinic_name": githa_ctx.clinic_name,
                "site_url": githa_ctx.site_url,
                "address": githa_ctx.address,
                "phone": githa_ctx.phone
            }

            if any(w in step_lower for w in ["serviço", "procedimento", "tratamento", "preço", "catálogo"]):
                githa_source = "services"
                suggested_inputs["top_services"] = [
                    {"name": s.name, "price": s.price, "duration": s.duration_minutes}
                    for s in githa_ctx.popular_services[:5]
                ]
            elif any(w in step_lower for w in ["profissional", "equipe", "especialista"]):
                githa_source = "professionals"
                suggested_inputs["professionals"] = [p.name for p in githa_ctx.professionals]

            if any(w in step_lower for w in ["crie um texto", "escreva", "gere", "descrição", "resumo", "redija"]):
                action_type = "llm_generatable"
            elif any(w in step_lower for w in ["liste", "selecione os serviços", "identifique seus procedimentos"]):
                action_type = "data_enrichable"
            elif any(w in step_lower for w in ["autentique", "faça login com 2fa", "insira sms", "cartão de crédito"]):
                action_type = "manual_only"

            enriched_steps.append(
                EnrichedStep(
                    step_index=idx,
                    raw_action=step_text,
                    action_type=action_type,
                    target_tool=target_tool,
                    githa_data_source=githa_source,
                    suggested_inputs=suggested_inputs,
                    is_completed=(idx in completed_steps)
                )
            )

        githa_summary = {
            "clinic_name": githa_ctx.clinic_name,
            "site_url": githa_ctx.site_url,
            "top_popular_services": [s.name for s in githa_ctx.popular_services[:5]],
            "total_clients": githa_ctx.total_clients,
            "total_services": githa_ctx.total_services
        }

        return StrategyExecutionPlan(
            basename=strat.basename,
            titulo_estrategia=seo.titulo_estrategia or strat.basename,
            resumo_executivo=seo.resumo_executivo,
            quality_score=seo.quality_score,
            quality_grade=seo.quality_grade,
            status=strat.user_implementation.status if strat.user_implementation else "pendente",
            completed_steps=completed_steps,
            total_steps=len(raw_steps),
            enriched_steps=enriched_steps,
            githa_context_summary=githa_summary,
            generated_at=datetime.now().isoformat()
        )


class MarkStrategyAppliedUseCase:
    """Registra a conclusão de passos ou estratégia via automação com logs."""

    def __init__(self, strategy_repo: AbstractStrategyRepository):
        self.strategy_repo = strategy_repo

    def execute(self, basename: str, step_indices: Optional[List[int]] = None, notes: Optional[str] = None) -> Strategy:
        strat = self.strategy_repo.find_by_basename(basename)
        if not strat:
            raise KeyError(f"Estratégia '{basename}' não encontrada.")

        # Marcar passos
        if step_indices:
            for step_idx in step_indices:
                self.strategy_repo.toggle_step(basename, step_idx)

        # Adicionar comentário de automação
        if notes:
            import uuid
            comment = Comment(
                id=str(uuid.uuid4())[:8],
                text=f"[Automação Chrome MCP] {notes}",
                author="Agente Antigravity",
                created_at=datetime.now().isoformat()
            )
            self.strategy_repo.add_comment(basename, comment)

        return self.strategy_repo.find_by_basename(basename)

