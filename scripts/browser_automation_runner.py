#!/usr/bin/env python3
"""
Browser Automation Agent — PipelineFace (Browser-Use + Playwright + Ollama)
========================================================================
Executa tarefas de automação de navegador com base na coleção `browser_automation_requirements`.
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime
from pymongo import MongoClient

try:
    from browser_use import Agent
    from langchain_ollama import ChatOllama
except ImportError as e:
    print(f"[!] Faltam pacotes Python para o Browser-Use: {e}")
    print("Certifique-se de que o container foi reconstruído com os pacotes 'browser-use' e 'langchain-ollama'.")
    sys.exit(1)


def get_mongo_db():
    mongo_uri = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
    client = MongoClient(mongo_uri, serverSelectionTimeoutMS=3000)
    return client["pipelineface"]


async def run_automation_task(task_doc: dict, headless: bool = True):
    strategy_title = task_doc.get("titulo_estrategia", "")
    passos = task_doc.get("passos_automacao", [])
    dados_negocio = task_doc.get("dados_negocio_preenchidos", {})

    print(f"\n🚀 Iniciando Automação para: {strategy_title}")
    print(f"📌 Passos a executar: {len(passos)}")

    # Formatar instrução completa para o Agente Browser-Use
    prompt = f"""
Você é um assistente autônomo de navegação focado em SEO Local e Google Meu Negócio.
Sua missão é executar a seguinte estratégia para o negócio "{dados_negocio.get('nome_empresa', 'Githa Studio de Beleza')}":

OBJETIVO DA ESTRATÉGIA:
{strategy_title}

DADOS OFICIAIS DO NEGÓCIO PARA USAR SE NECESSÁRIO:
- Nome: {dados_negocio.get('nome_empresa')}
- Categoria: {dados_negocio.get('categoria_principal')}
- Endereço: {dados_negocio.get('localizacao_e_cobertura', {}).get('endereco_formatado')}
- Telefone: {dados_negocio.get('dados_contato', {}).get('telefone_principal')}
- Website: {dados_negocio.get('dados_contato', {}).get('website_oficial')}
- Instagram: {dados_negocio.get('dados_contato', {}).get('instagram')}
- Descrição: {dados_negocio.get('descricao_oficial')}
- Serviços: {', '.join(dados_negocio.get('servicos_especificos', []))}

PASSO A PASSO DA ESTRATÉGIA:
"""
    for i, p in enumerate(passos, 1):
        prompt += f"{i}. {p}\n"

    prompt += "\nPor favor, acesse as páginas indicadas no passo a passo e execute as etapas necessárias com cuidado."

    # Configurar o LLM Ollama local
    ollama_url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
    # Remover o sufixo /api/chat se presente, pois o ChatOllama usa a URL base
    if "/api/chat" in ollama_url:
        ollama_url = ollama_url.replace("/api/chat", "")

    class BrowserUseChatOllama(ChatOllama):
        provider: str = "ollama"
        
        @property
        def model_name(self) -> str:
            return self.model or "qwen2.5:3b"

    llm = BrowserUseChatOllama(
        model=os.environ.get("TEXT_MODEL", "qwen2.5:3b"),
        base_url=ollama_url,
        temperature=0.1
    )


    agent = Agent(
        task=prompt,
        llm=llm
    )



    try:
        result = await agent.run()
        print(f"✓ Automação concluída com sucesso para [{task_doc.get('basename')}]!")
        return True, str(result)
    except Exception as e:
        print(f"❌ Erro durante a execução do Browser-Use: {e}")
        return False, str(e)


def main():
    parser = argparse.ArgumentParser(description="Executor de Automação de Navegador Browser-Use")
    parser.add_argument("--basename", help="Executar uma estratégia específica pelo basename")
    parser.add_argument("--limit", type=int, default=1, help="Quantidade de estratégias pendentes a executar")
    parser.add_argument("--headless", action="store_true", help="Rodar navegador sem interface gráfica (modo headless)")

    args = parser.parse_args()

    db = get_mongo_db()
    req_coll = db["browser_automation_requirements"]

    if args.basename:
        query = {"basename": args.basename}
    else:
        query = {"status_execucao": "pendente"}

    tasks = list(req_coll.find(query).limit(args.limit))

    if not tasks:
        print("Nenhuma tarefa pendente encontrada na coleção 'browser_automation_requirements'.")
        return

    print(f"=== INICIANDO BROWSER-USE AUTOMATION ({len(tasks)} tarefas) ===")

    for task in tasks:
        doc_id = task["_id"]
        req_coll.update_one({"_id": doc_id}, {"$set": {"status_execucao": "em_execucao", "iniciado_em": datetime.now().isoformat()}})

        success, result_msg = asyncio.run(run_automation_task(task, headless=args.headless))

        status_final = "executado" if success else "erro"
        req_coll.update_one(
            {"_id": doc_id},
            {"$set": {
                "status_execucao": status_final,
                "resultado_execucao": result_msg,
                "finalizado_em": datetime.now().isoformat()
            }}
        )

        # Atualizar também a coleção original seo_knowledge
        db["seo_knowledge"].update_one(
            {"basename": task.get("basename")},
            {"$set": {
                "user_implementation.status": "concluido" if success else "pendente",
                "updated_at": datetime.now().isoformat()
            }}
        )


if __name__ == "__main__":
    main()
