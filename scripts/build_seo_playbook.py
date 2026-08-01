#!/usr/bin/env python3
"""
Script de Consolidação do SEO Playbook (Arquitetura Map-Reduce Híbrida)
=======================================================================
Garante escalabilidade infinita mesmo para milhares de documentos em `seo_knowledge`.

Etapa 1 (MAP): Classificação determinística por pilares SEO usando taxonomia fixa de palavras-chave (Sem LLM).
Etapa 2 (REDUCE): LLM sintetiza apenas títulos e resumos agrupados para definir prioridades e descrições (Payload mínimo).
Etapa 3 (ASSEMBLE): Montagem programática montando passos reais, deduplicando ações e mapeando rastreabilidade por passo.
"""

import os
import json
import re
import urllib.request
from datetime import datetime
from typing import List, Dict, Any
from pymongo import MongoClient


TAXONOMIA_PILARES = {
    "keyword_research": {
        "titulo": "1. Pesquisa de Palavras-Chave & Demanda",
        "keywords": ["keyword", "palavra-chave", "palavra chave", "volume", "demanda", "search console", "semrush", "ahrefs", "ubersuggest", "keywords everywhere", "busca"]
    },
    "onpage_seo": {
        "titulo": "2. SEO On-Page & Estrutura HTML",
        "keywords": ["h1", "meta title", "meta description", "url", "slug", "heading", "schema", "structured data", "on-page", "onpage", "tag", "html"]
    },
    "technical_seo": {
        "titulo": "3. SEO Técnico & Performance",
        "keywords": ["core web vitals", "lcp", "pagespeed", "sitemap", "robots.txt", "indexação", "crawl", "ssl", "mobile", "velocidade", "ssr", "ssg"]
    },
    "geo_rag": {
        "titulo": "4. GEO — Otimização para IAs Generativas & RAG",
        "keywords": ["geo", "perplexing", "perplexity", "chatgpt", "gemini", "rag", "llms.txt", "gptbot", "motor generativo", "ia", "resposta sintética"]
    },
    "content_strategy": {
        "titulo": "5. Estratégia de Conteúdo & Copywriting",
        "keywords": ["conteúdo", "blog", "artigo", "copy", "título", "engajamento", "storytelling", "cta", "autoridade", "topico"]
    },
    "visual_media": {
        "titulo": "6. Imagens, Vídeo & Mídia Visual",
        "keywords": ["imagem", "vídeo", "video", "alt text", "thumbnail", "youtube", "infográfico", "canva", "pixlr", "resolução", "design"]
    },
    "analytics": {
        "titulo": "7. Analytics, Métricas & Conversão",
        "keywords": ["google analytics", "ga4", "conversão", "bounce rate", "ctr", "taxa", "relatório", "métrica", "dados", "audiência"]
    },
    "social_seo": {
        "titulo": "8. SEO para Redes Sociais & Perfil",
        "keywords": ["facebook", "instagram", "linkedin", "rede social", "post", "engajamento social", "perfil", "publicação"]
    }
}


def query_ollama(prompt: str, system_prompt: str = None) -> str:
    ollama_url = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/chat")
    text_model = os.environ.get("TEXT_MODEL", "qwen2.5:3b")

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": text_model,
        "messages": messages,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.2}
    }

    req = urllib.request.Request(
        ollama_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    with urllib.request.urlopen(req, timeout=300) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        return res.get("message", {}).get("content", "").strip()


def deduplicar_passos_com_origem(passos_com_origem: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Remove passos idênticos preservando o basename de origem do primeiro encontrado."""
    passos_limpos = []
    for item in passos_com_origem:
        passo = item["acao"]
        basename = item["basename"]
        texto_norm = re.sub(r'^(Passo|Ação)\s*\d+:\s*', '', passo, flags=re.IGNORECASE).strip()
        
        duplicado = False
        words_norm = set(re.findall(r'\w{4,}', texto_norm.lower()))
        
        for p_existente in passos_limpos:
            exist_norm = re.sub(r'^(Passo|Ação)\s*\d+:\s*', '', p_existente["acao"], flags=re.IGNORECASE).strip()
            words_exist = set(re.findall(r'\w{4,}', exist_norm.lower()))
            
            if words_norm and words_exist:
                intersection = words_norm.intersection(words_exist)
                overlap = len(intersection) / max(len(words_norm), len(words_exist))
                if overlap > 0.8:
                    duplicado = True
                    break
        
        if not duplicado:
            passos_limpos.append({"acao": passo, "origem_basename": basename})

    res = []
    for idx, item in enumerate(passos_limpos, 1):
        limpo = re.sub(r'^(Passo|Ação)\s*\d+:\s*', '', item["acao"], flags=re.IGNORECASE)
        res.append({
            "passo_index": idx,
            "acao": f"Ação {idx}: {limpo}",
            "origem_basename": item["origem_basename"]
        })
    return res


def build_playbook():
    mongo_uri = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
    client = MongoClient(mongo_uri, serverSelectionTimeoutMS=3000)
    db = client["pipelineface"]

    strategies = list(db["seo_knowledge"].find({
        "$or": [
            {"seo_knowledge.quality_grade": {"$in": ["A", "B"]}},
            {"seo_knowledge._quality_grade": {"$in": ["A", "B"]}}
        ]
    }))

    if not strategies:
        print("⚠️ Nenhum conhecimento com Grade A ou B encontrado em seo_knowledge.")
        return

    print(f"⚡ [MAP] Agrupando {len(strategies)} documentos por pilares estratégicos (Sem LLM)...")

    agrupamento: Dict[str, List[Dict[str, Any]]] = {pilar_id: [] for pilar_id in TAXONOMIA_PILARES}
    agrupamento["outros"] = []

    for doc in strategies:
        seo = doc.get("seo_knowledge", {})
        titulo = str(seo.get("titulo_estrategia", ""))
        resumo = str(seo.get("resumo_executivo", ""))
        conceitos = " ".join([str(c) for c in seo.get("conceitos_mencionados", [])])
        ferramentas = " ".join([str(f) for f in seo.get("ferramentas_e_telas_utilizadas", [])])
        texto_completo = f"{titulo} {resumo} {conceitos} {ferramentas}".lower()

        pilar_encontrado = None
        for pilar_id, meta in TAXONOMIA_PILARES.items():
            if any(kw in texto_completo for kw in meta["keywords"]):
                pilar_encontrado = pilar_id
                break

        if pilar_encontrado:
            agrupamento[pilar_encontrado].append(doc)
        else:
            agrupamento["outros"].append(doc)

    pilares_ativos = {p_id: docs for p_id, docs in agrupamento.items() if docs}
    
    print(f"🧠 [REDUCE] Sintetizando {len(pilares_ativos)} pilares ativos via LLM (Payload compacto)...")

    summary_payload = []
    for pilar_id, docs in pilares_ativos.items():
        pilar_nome = TAXONOMIA_PILARES.get(pilar_id, {}).get("titulo", "Outras Estratégias de SEO")
        titulos = [d.get("seo_knowledge", {}).get("titulo_estrategia") for d in docs]
        ferramentas_set = set()
        for d in docs:
            for f in d.get("seo_knowledge", {}).get("ferramentas_e_telas_utilizadas", []):
                if f and "Nenhum" not in str(f):
                    ferramentas_set.add(str(f))

        summary_payload.append({
            "id_pilar": pilar_id,
            "nome_pilar": pilar_nome,
            "total_dicas": len(docs),
            "titulos_relacionados": titulos,
            "ferramentas_mencionadas": list(ferramentas_set)
        })

    system_prompt = (
        "Você é um Diretor de SEO e Estrategista de Marketing Digital.\n"
        "Sua função é analisar o resumo dos pilares fornecidos e definir a PRIORIDADE ESTRATÉGICA (Alta, Media, Avancada) "
        "e uma DESCRIÇÃO CONCISA de 2 frases para cada pilar em Português do Brasil (pt-BR).\n\n"
        "RETORNE APENAS UM JSON VÁLIDO NO SEGUINTE FORMATO:\n"
        "{\n"
        '  "pilares_priorizados": [\n'
        '    {\n'
        '      "id_pilar": "id_fornecido",\n'
        '      "prioridade": "Alta|Media|Avancada",\n'
        '      "descricao_pilar": "Resumo executivo do valor estratégico deste pilar para o negócio"\n'
        '    }\n'
        '  ]\n'
        "}"
    )

    prompt = f"### RESUMO DOS PILARES EXTRAÍDOS PARA SÍNTESE:\n{json.dumps(summary_payload, ensure_ascii=False, indent=2)}"
    
    llm_res_str = query_ollama(prompt, system_prompt=system_prompt)
    try:
        llm_data = json.loads(llm_res_str)
        pilares_meta = {p["id_pilar"]: p for p in llm_data.get("pilares_priorizados", [])}
    except Exception as e:
        print(f"⚠️ Erro ao processar síntese do LLM, aplicando fallbacks: {e}")
        pilares_meta = {}

    print("🛠️  [ASSEMBLE] Montando Playbook final combinando dados reais do MongoDB...")

    topicos_priorizados = []

    for pilar_id, docs in pilares_ativos.items():
        pilar_info = TAXONOMIA_PILARES.get(pilar_id, {})
        nome_pilar = pilar_info.get("titulo", "Outras Estratégias de SEO")
        
        meta = pilares_meta.get(pilar_id, {})
        prioridade = meta.get("prioridade", "Media")
        descricao = meta.get("descricao_pilar", f"Otimização prática focada em {nome_pilar}.")

        ferramentas_pilar = set()
        todos_passos_com_origem = []
        origem_basenames = []

        for d in docs:
            bname = d.get("basename")
            seo = d.get("seo_knowledge", {})
            origem_basenames.append(bname)
            
            for f in seo.get("ferramentas_e_telas_utilizadas", []):
                if f and "Nenhum" not in str(f):
                    ferramentas_pilar.add(str(f))

            for p in seo.get("passo_a_passo_detalhado", []):
                todos_passos_com_origem.append({
                    "acao": p,
                    "basename": bname
                })

        acoes_rastreaveis = deduplicar_passos_com_origem(todos_passos_com_origem)

        topicos_priorizados.append({
            "id_topico": pilar_id,
            "titulo_topico": nome_pilar,
            "prioridade": prioridade,
            "descricao_pilar": descricao,
            "ferramentas_recomendadas": list(ferramentas_pilar) if ferramentas_pilar else ["Ferramentas nativas do navegador / plataforma"],
            "acoes_praticas": acoes_rastreaveis,
            "origem_basenames": origem_basenames
        })

    ordem_prio = {"Alta": 1, "Media": 2, "Avancada": 3}
    topicos_priorizados.sort(key=lambda x: ordem_prio.get(x["prioridade"], 99))

    playbook_document = {
        "id": "playbook_principal",
        "titulo_playbook": "Playbook Consolidado de SEO na Prática",
        "ultima_atualizacao": datetime.now().isoformat(),
        "total_dicas_incorporadas": len(strategies),
        "topicos_priorizados": topicos_priorizados
    }

    db["seo_playbook"].replace_one(
        {"id": "playbook_principal"},
        playbook_document,
        upsert=True
    )

    print(f"🎉 Sucesso! Playbook consolidado via Map-Reduce com {len(topicos_priorizados)} tópicos priorizados salvos em 'seo_playbook'!")


if __name__ == "__main__":
    build_playbook()
