#!/usr/bin/env python3
"""
Script de Consolidação do SEO Playbook — PipelineFace
=====================================================
Lê todos os itens de alta qualidade (Grade A/B) na coleção `seo_knowledge`,
agrupa os tutoriais por pilares estratégicos de SEO e os ordena por prioridade de impacto.
Salva o resultado na coleção `seo_playbook` no MongoDB.
"""

import os
import json
import urllib.request
from datetime import datetime
from pymongo import MongoClient


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


def build_playbook():
    mongo_uri = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
    client = MongoClient(mongo_uri, serverSelectionTimeoutMS=3000)
    db = client["pipelineface"]

    # 1. Buscar apenas estratégias com Grade A ou B (Conhecimento verificado)
    strategies = list(db["seo_knowledge"].find({
        "$or": [
            {"seo_knowledge.quality_grade": "A"},
            {"seo_knowledge.quality_grade": "B"},
            {"seo_knowledge._quality_grade": "A"},
            {"seo_knowledge._quality_grade": "B"}
        ]
    }))

    if not strategies:
        print("⚠️ Nenhum conhecimento com Grade A ou B encontrado em seo_knowledge.")
        return

    print(f"📚 Consolidando {len(strategies)} estratégia(s) validadas...")

    prompt_context = "### DICAS E TUTORIAIS DE SEO EXTRAÍDOS:\n\n"
    for idx, item in enumerate(strategies, 1):
        seo = item.get("seo_knowledge", {})
        prompt_context += f"--- Estratégia {idx} ({item.get('basename')}) ---\n"
        prompt_context += f"Título: {seo.get('titulo_estrategia')}\n"
        prompt_context += f"Resumo: {seo.get('resumo_executivo')}\n"
        prompt_context += f"Passos: {json.dumps(seo.get('passo_a_passo_detalhado'), ensure_ascii=False)}\n"
        prompt_context += f"Ferramentas: {json.dumps(seo.get('ferramentas_e_telas_utilizadas'), ensure_ascii=False)}\n"
        prompt_context += f"Aplicação: {seo.get('aplicacao_no_negocio')}\n\n"

    system_prompt = (
        "Você é um Diretor de SEO e Estrategista de Marketing Digital.\n"
        "Sua missão é agrupar e organizar todas as dicas de SEO fornecidas em um PLAYBOOK PRÁTICO E ESTRUTURADO.\n\n"
        "REGRAS DE ORGANIZAÇÃO:\n"
        "1. Agrupe as dicas em Pilares Estratégicos (Ex: '1. Pesquisa de Palavras-Chave & Demanda', "
        "'2. SEO On-Page & Estrutura HTML', '3. GEO (Otimização para IAs e RAG)', '4. Imagens & Mídia Visual').\n"
        "2. Ordene os pilares por PRIORIDADE DE IMPACTO (Alta, Média, Avançada).\n"
        "3. Em cada pilar, monte um checklist plano de ação passo-a-passo pronto para execução.\n"
        "4. Inclua as ferramentas exatas recomendadas para cada pilar.\n\n"
        "RETORNE APENAS UM JSON VÁLIDO no seguinte formato:\n"
        "{\n"
        '  "titulo_playbook": "Playbook Consolidado de SEO na Prática",\n'
        '  "ultima_atualizacao": "' + datetime.now().isoformat() + '",\n'
        '  "total_dicas_incorporadas": ' + str(len(strategies)) + ',\n'
        '  "topicos_priorizados": [\n'
        '    {\n'
        '      "id_topico": "topico_1",\n'
        '      "titulo_topico": "Nome do Pilar",\n'
        '      "prioridade": "Alta|Media|Avancada",\n'
        '      "descricao_pilar": "Resumo do que este pilar resolve",\n'
        '      "ferramentas_recomendadas": ["Ferramenta A", "Ferramenta B"],\n'
        '      "acoes_praticas": [\n'
        '        "Ação 1: ...",\n'
        '        "Ação 2: ..."\n'
        '      ],\n'
        '      "origem_basenames": ["basename_do_video_ou_imagem"]\n'
        '    }\n'
        '  ]\n'
        "}"
    )

    playbook_json_str = query_ollama(prompt_context, system_prompt=system_prompt)
    try:
        playbook_data = json.loads(playbook_json_str)
        
        # Salvar na coleção seo_playbook no MongoDB
        db["seo_playbook"].replace_one(
            {"id": "playbook_principal"},
            {"id": "playbook_principal", **playbook_data},
            upsert=True
        )
        print("✅ Sucesso! Playbook priorizado consolidado na coleção 'seo_playbook' do MongoDB!")
        print(json.dumps(playbook_data, ensure_ascii=False, indent=2))
    except Exception as e:
        print("❌ Erro ao converter JSON do Playbook:", e)
        print("Raw output:", playbook_json_str)


if __name__ == "__main__":
    build_playbook()
