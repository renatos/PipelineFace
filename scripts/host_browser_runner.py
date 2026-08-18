#!/usr/bin/env python3
"""
Browser Automation Agent — Hospedeiro Nativo (Linux)
====================================================
Executa o Browser-Use diretamente no seu sistema operacional hospedeiro,
conectando-se ao MongoDB local (porta 27017) e abrindo a janela do seu navegador Chrome.
"""

import argparse
import atexit
import asyncio
import os
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pymongo import MongoClient

try:
    from browser_use import Agent, Browser, BrowserProfile
    from browser_use.llm.ollama.chat import ChatOllama
except Exception as e:
    print(f"\n[!] Erro ao carregar dependências no ambiente hospedeiro: {e}")
    sys.exit(1)


def get_mongo_db():
    mongo_uri = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
    client = MongoClient(mongo_uri, serverSelectionTimeoutMS=3000)
    return client["pipelineface"]


def check_ollama_health(ollama_url: str) -> bool:
    """Verifica se o servidor Ollama está respondendo."""
    try:
        req = urllib.request.urlopen(f"{ollama_url}/api/tags", timeout=3)
        return req.status == 200
    except Exception:
        return False


def is_port_open(port: int = 9222) -> bool:
    """Verifica se uma porta de rede local está aberta."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1.0)
            return s.connect_ex(('127.0.0.1', port)) == 0
    except Exception:
        return False


def sync_user_chrome_profile(src_base: str, target_base: str, profile_name: str = "Default"):
    """Sincroniza cookies, logins e dados de sessão do perfil real para o diretório de depuração CDP."""
    import shutil
    try:
        os.makedirs(target_base, exist_ok=True)
        local_state_src = os.path.join(src_base, "Local State")
        local_state_tgt = os.path.join(target_base, "Local State")
        if os.path.exists(local_state_src):
            try:
                shutil.copy2(local_state_src, local_state_tgt)
            except Exception:
                pass

        src_prof = os.path.join(src_base, profile_name)
        target_prof = os.path.join(target_base, profile_name)
        os.makedirs(target_prof, exist_ok=True)

        items_to_sync = [
            'Cookies', 'Network', 'Login Data', 'Web Data', 'Preferences',
            'Secure Preferences', 'Local Storage', 'IndexedDB', 'History', 'Extensions', 'Extension State'
        ]

        for item in items_to_sync:
            s = os.path.join(src_prof, item)
            t = os.path.join(target_prof, item)
            if os.path.exists(s):
                try:
                    if os.path.isdir(s):
                        shutil.copytree(s, t, symlinks=True, dirs_exist_ok=True)
                    else:
                        shutil.copy2(s, t)
                except Exception:
                    pass
    except Exception as e:
        print(f"⚠️ Aviso ao sincronizar perfil do Chrome: {e}")


def ensure_chrome_cdp(cdp_port: int = 9222, user_data_dir: str = None, profile_name: str = "Default") -> bool:
    """Garante que o Chrome esteja rodando com a porta de depuração CDP aberta usando os dados do perfil do usuário."""
    if is_port_open(cdp_port):
        return True

    real_user_dir = user_data_dir or os.environ.get("CHROME_USER_DATA_DIR", os.path.expanduser("~/.config/google-chrome"))
    auto_user_dir = os.path.expanduser("~/.config/google-chrome-automation")

    print(f"🔄 Sincronizando credenciais e logins do perfil '{profile_name}'...")
    sync_user_chrome_profile(real_user_dir, auto_user_dir, profile_name)

    print(f"🌐 Iniciando Google Chrome com seu perfil ativo na porta CDP ({cdp_port})...")
    chrome_bin = "google-chrome"
    for p in ["/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/usr/bin/chromium", "/usr/bin/chromium-browser"]:
        if os.path.exists(p):
            chrome_bin = p
            break

    cmd = [
        chrome_bin,
        f"--remote-debugging-port={cdp_port}",
        f"--user-data-dir={auto_user_dir}",
    ]
    if profile_name:
        cmd.append(f"--profile-directory={profile_name}")

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    atexit.register(lambda: proc.terminate() if proc.poll() is None else None)

    for _ in range(20):
        if is_port_open(cdp_port):
            return True
        time.sleep(0.5)

    return is_port_open(cdp_port)


def build_system_prompt(dados_negocio: dict, strategy_title: str) -> str:
    """Gera o cabeçalho base do contexto da empresa para o prompt."""
    return f"""Você é um agente autônomo de automação de navegador (Browser Automation Agent) com controle direto sobre a janela do Google Chrome.
Sua única função é executar as ações requeridas no navegador. Você possui ferramentas nativas para navegar, clicar em botões e preencher formulários.
NUNCA responda dizendo que é um modelo de linguagem ou que não pode acessar a web. Você DEVE obrigatoriamente executar ações no navegador (como navigate, click_element, input_text).

EMPRESA ALVO: "{dados_negocio.get('nome_empresa', 'Githa Studio de Beleza')}"
OBJETIVO DA ESTRATÉGIA:
{strategy_title}

DADOS OFICIAIS DO NEGÓCIO PARA PREENCHIMENTO SE NECESSÁRIO:
- Nome: {dados_negocio.get('nome_empresa')}
- Categoria: {dados_negocio.get('categoria_principal')}
- Endereço: {dados_negocio.get('localizacao_e_cobertura', {}).get('endereco_formatado')}
- Telefone: {dados_negocio.get('dados_contato', {}).get('telefone_principal')}
- Website: {dados_negocio.get('dados_contato', {}).get('website_oficial')}
- Instagram: {dados_negocio.get('dados_contato', {}).get('instagram')}
- Descrição: {dados_negocio.get('descricao_oficial')}
- Serviços: {', '.join(dados_negocio.get('servicos_especificos', []))}
"""




async def execute_agent_with_timeout(agent: Agent, timeout_seconds: int = 300) -> tuple[bool, str]:
    """Executa o agente com timeout e validação rigorosa dos resultados."""
    try:
        history = await asyncio.wait_for(agent.run(), timeout=timeout_seconds)
        
        # Validar histórico de ações do AgentHistoryList
        is_successful = True
        error_reasons = []

        if hasattr(history, 'is_done') and not history.is_done():
            is_successful = False
            error_reasons.append("Agente encerrou sem concluir o objetivo final.")

        # Checar lista de resultados das ações
        if hasattr(history, 'all_results'):
            results = history.all_results
            if results:
                # Contar falhas consecutivas ou erros reportados
                failed_actions = [r for r in results if getattr(r, 'error', None) is not None or getattr(r, 'success', True) is False]
                if len(failed_actions) == len(results) or len(failed_actions) >= 5:
                    is_successful = False
                    error_reasons.append(f"Múltiplas falhas de ação detectadas ({len(failed_actions)}/{len(results)}).")

        result_summary = str(history)
        if not is_successful:
            full_error = " | ".join(error_reasons)
            print(f"⚠️ Execução concluída com falhas: {full_error}")
            return False, f"FALHA: {full_error}\nDetalhes: {result_summary[:2000]}"

        return True, result_summary[:2000]

    except asyncio.TimeoutError:
        msg = f"Timeout de execução ({timeout_seconds}s) atingido."
        print(f"⏱️ {msg}")
        return False, msg
    except Exception as e:
        msg = f"Erro fatal no agente: {e}"
        print(f"❌ {msg}")
        return False, msg


async def run_automation_task(
    task_doc: dict,
    visible: bool = True,
    interactive: bool = False,
    timeout_seconds: int = 300,
    profile_name: str = "Default",
    user_data_dir: str = None
):
    strategy_title = task_doc.get("titulo_estrategia", "")
    passos = task_doc.get("passos_automacao", [])
    dados_negocio = task_doc.get("dados_negocio_preenchidos", {})
    basename = task_doc.get("basename", "desconhecido")

    print(f"\n🚀 [HOST] Iniciando Automação para: {strategy_title}")
    print(f"📌 Total de passos: {len(passos)} | Modo: {'INTERATIVO (Pausa entre passos)' if interactive else 'AUTOMÁTICO'}")

    ollama_url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
    if not check_ollama_health(ollama_url):
        msg = f"Ollama não está respondendo em {ollama_url}. Verifique se o serviço está ativo."
        print(f"❌ {msg}")
        return False, msg

    llm = ChatOllama(
        model=os.environ.get("TEXT_MODEL", "qwen2.5:7b"),
        host=ollama_url,
    )

    cdp_url = os.environ.get("CHROME_CDP_URL", "http://127.0.0.1:9222")

    if ensure_chrome_cdp(9222, user_data_dir=user_data_dir, profile_name=profile_name):
        print(f"🔗 Conectado ao Google Chrome com perfil ativo '{profile_name}' via CDP (porta 9222)!")
        profile = BrowserProfile(cdp_url=cdp_url)
    else:
        print("🖥️ Abrindo janela visível do navegador para a automação...")
        profile = BrowserProfile(
            headless=not visible,
            disable_security=True
        )

    browser = Browser(browser_profile=profile)
    context_header = build_system_prompt(dados_negocio, strategy_title)

    if interactive:
        overall_success = True
        logs = []

        for idx, passo in enumerate(passos, 1):
            print(f"\n" + "="*60)
            print(f"📌 [PASSO {idx}/{len(passos)}] {passo}")
            print("="*60)

            step_prompt = f"{context_header}\n\nSUA TAREFA ATUAL (Execute APENAS este passo agora):\n{passo}\n\nNavegue e execute as ações necessárias no navegador com calma."

            agent = Agent(
                task=step_prompt,
                llm=llm,
                browser=browser,
                use_vision=False,
                max_failures=5,
                max_actions_per_step=3,
            )

            success, log_msg = await execute_agent_with_timeout(agent, timeout_seconds=timeout_seconds)
            logs.append(f"Passo {idx}: {'OK' if success else 'FALHA'} - {log_msg}")

            if not success:
                overall_success = False
                print(f"⚠️ O passo {idx} falhou ou não pôde ser completado.")

            if idx < len(passos):
                print(f"\n⏸️  Passo {idx} concluído. Ações disponíveis:")
                user_choice = input("    [ENTER] Continuar para o próximo passo | [S] Pular próximo | [Q] Sair da automação: ").strip().lower()
                if user_choice == 'q':
                    print("🛑 Automação interrompida pelo usuário.")
                    logs.append("Interrompido pelo usuário.")
                    break
                elif user_choice == 's':
                    print("⏩ Próximo passo pulado pelo usuário.")
                    continue

        return overall_success, "\n".join(logs)

    else:
        full_prompt = context_header + "\nPASSO A PASSO DA ESTRATÉGIA:\n"
        for i, p in enumerate(passos, 1):
            full_prompt += f"{i}. {p}\n"
        full_prompt += "\nPor favor, acesse os sites indicados e execute as ações no navegador com calma."

        agent = Agent(
            task=full_prompt,
            llm=llm,
            browser=browser,
            use_vision=False,
            max_failures=5,
            max_actions_per_step=3,
        )

        return await execute_agent_with_timeout(agent, timeout_seconds=timeout_seconds)


def log_execution_event(db, basename: str, step: str, status: str, message: str):
    """Registra telemetria na collection execution_events."""
    try:
        db["execution_events"].insert_one({
            "run_id": f"browser_{basename}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "source": "browser_automation",
            "step": step,
            "status": status,
            "filename": basename,
            "message": message,
            "created_at": datetime.now().isoformat()
        })
    except Exception as e:
        print(f"⚠️ Falha ao gravar evento de execução: {e}")


def main():
    parser = argparse.ArgumentParser(description="Executor de Automação de Navegador no Hospedeiro")
    parser.add_argument("--basename", help="Executar uma estratégia específica pelo basename")
    parser.add_argument("--limit", type=int, default=1, help="Quantidade de estratégias a executar")
    parser.add_argument("--headless", action="store_true", help="Rodar navegador de forma oculta (sem janela)")
    parser.add_argument("--interactive", "-i", action="store_true", help="Modo interativo: pausa e aguarda confirmação a cada passo")
    parser.add_argument("--timeout", type=int, default=300, help="Timeout em segundos por tarefa (padrão: 300s)")
    parser.add_argument("--profile", default=os.environ.get("CHROME_PROFILE", "Default"), help="Nome da pasta do perfil do Chrome (padrão: Default, ex: 'Profile 3')")
    parser.add_argument("--user-data-dir", default=os.environ.get("CHROME_USER_DATA_DIR", None), help="Diretório de dados do Chrome (padrão: ~/.config/google-chrome)")

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

    print(f"=== INICIANDO BROWSER-USE NO HOSPEDEIRO ({len(tasks)} tarefas) ===")
    print(f"👤 Perfil Chrome selecionado: {args.profile}")

    for task in tasks:
        doc_id = task["_id"]
        basename = task.get("basename", "desconhecido")

        req_coll.update_one({"_id": doc_id}, {"$set": {"status_execucao": "em_execucao", "iniciado_em": datetime.now().isoformat()}})
        log_execution_event(db, basename, "start", "in_progress", f"Iniciando automação: {task.get('titulo_estrategia')}")

        success, result_msg = asyncio.run(run_automation_task(
            task,
            visible=not args.headless,
            interactive=args.interactive,
            timeout_seconds=args.timeout,
            profile_name=args.profile,
            user_data_dir=args.user_data_dir
        ))

        status_final = "executado" if success else "erro"
        req_coll.update_one(
            {"_id": doc_id},
            {"$set": {
                "status_execucao": status_final,
                "resultado_execucao": result_msg[:5000],
                "finalizado_em": datetime.now().isoformat()
            }}
        )

        db["seo_knowledge"].update_one(
            {"basename": basename},
            {"$set": {
                "user_implementation.status": "concluido" if success else "pendente",
                "updated_at": datetime.now().isoformat()
            }}
        )

        log_execution_event(
            db,
            basename,
            "finish",
            "completed" if success else "error",
            f"Automação finalizada com status: {status_final}"
        )


if __name__ == "__main__":
    main()
