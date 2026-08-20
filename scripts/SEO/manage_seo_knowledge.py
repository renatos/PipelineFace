#!/usr/bin/env python3
"""
Script auxiliar para consultar e atualizar estratégias no MongoDB seo_knowledge (1 a 1).
Lê as credenciais e URI do .env automaticamente.

Uso:
  Listar todas:        python3 scripts/SEO/manage_seo_knowledge.py --list
  Listar concluídas:   python3 scripts/SEO/manage_seo_knowledge.py --implemented
  Listar pendentes:    python3 scripts/SEO/manage_seo_knowledge.py --pending
  Ver detalhes de uma: python3 scripts/SEO/manage_seo_knowledge.py --detail <basename>
  Marcar concluída:    python3 scripts/SEO/manage_seo_knowledge.py --mark <basename> --steps 0,1,2,3,4 --notes "Página criada"
"""
import os
import sys
import argparse
import pymongo
from datetime import datetime
from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
load_dotenv(os.path.join(BASE_DIR, ".env"))

MONGO_URI = os.getenv("MONGO_URI", os.getenv("MONGODB_URL", "mongodb://localhost:27017"))
DB_NAME = os.getenv("MONGO_DB_NAME", "pipelineface")

def get_db():
    client = pymongo.MongoClient(MONGO_URI)
    return client[DB_NAME]

def list_strategies(status_filter: str = None):
    db = get_db()
    query = {}
    if status_filter:
        if status_filter.lower() in ["completed", "done"]:
            query = {"user_implementation.status": "completed"}
        elif status_filter.lower() in ["pending", "todo"]:
            query = {"$or": [
                {"user_implementation": None},
                {"user_implementation.status": {"$ne": "completed"}}
            ]}

    strategies = list(db.seo_knowledge.find(query, {
        "basename": 1,
        "seo_knowledge.titulo_estrategia": 1,
        "seo_knowledge.quality_score": 1,
        "seo_knowledge.termos_e_exemplos_usados": 1,
        "user_implementation": 1,
        "updated_at": 1
    }))
    
    label = f" (Filtro: {status_filter})" if status_filter else ""
    print(f"Total de estratégias encontradas{label}: {len(strategies)}")
    print("-" * 80)
    for s in strategies:
        basename = s.get("basename", "")
        title = s.get("seo_knowledge", {}).get("titulo_estrategia", "Sem título")
        score = s.get("seo_knowledge", {}).get("quality_score", 0)
        impl = s.get("user_implementation") or {}
        status = impl.get("status", "pending")
        notes = impl.get("comments", "")
        if notes and len(notes) > 40:
            notes = notes[:37] + "..."
        notes_str = f" | Obs: {notes}" if notes else ""
        print(f"[{status.upper():<9}] {basename:<28} | Score: {score:>2}/10 | {title}{notes_str}")

def show_strategy_detail(basename: str):
    db = get_db()
    s = db.seo_knowledge.find_one({"basename": basename})
    if not s:
        print(f"⚠️ Nenhuma estratégia encontrada com basename: {basename}")
        return

    seo = s.get("seo_knowledge", {})
    impl = s.get("user_implementation") or {}
    print("=" * 80)
    print(f"📄 DETALHES DA ESTRATÉGIA: {basename}")
    print("=" * 80)
    print(f"📌 Título: {seo.get('titulo_estrategia', 'Sem título')}")
    print(f"⭐ Quality Score: {seo.get('quality_score', 'N/A')}/10 (Grade: {seo.get('quality_grade', 'N/A')})")
    print(f"📊 Nível Dificuldade: {seo.get('nivel_dificuldade', 'N/A')} | Tempo Estimado: {seo.get('tempo_estimado_implementacao', 'N/A')}")
    print(f"\n📝 Resumo Executivo:\n{seo.get('resumo_executivo', 'N/A')}")
    
    print("\n🪜 Passo a Passo:")
    for idx, step in enumerate(seo.get("passo_a_passo_detalhado", [])):
        print(f"  [{idx}] {step}")
        
    print("\n🛠️ Ferramentas e Telas:")
    for tool in seo.get("ferramentas_e_telas_utilizadas", []):
        print(f"  - {tool}")

    print("\n🔑 Termos e Exemplos:")
    for term in seo.get("termos_e_exemplos_usados", []):
        print(f"  - {term}")

    print("\n⚙️ Estado de Implementação (user_implementation):")
    print(f"  Status: {impl.get('status', 'pending').upper()}")
    print(f"  Passos Concluídos: {impl.get('completed_steps', [])}")
    print(f"  Data de Aplicação: {impl.get('applied_at', 'Não aplicada')}")
    print(f"  Notas / Auditoria: {impl.get('comments', 'Nenhuma nota registrada')}")
    print("=" * 80)

def mark_strategy(basename: str, step_indices: list, notes: str):
    db = get_db()
    res = db.seo_knowledge.update_one(
        {"basename": basename},
        {
            "$set": {
                "user_implementation.status": "completed",
                "user_implementation.completed_steps": step_indices,
                "user_implementation.comments": notes,
                "user_implementation.applied_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
        }
    )
    if res.modified_count > 0:
        print(f"✅ Estratégia {basename} atualizada para COMPLETED com sucesso!")
    else:
        print(f"⚠️ Nenhuma estratégia encontrada ou modificada com basename: {basename}")

def mark_in_progress(basename: str, notes: str = "Iniciando execução da estratégia..."):
    db = get_db()
    res = db.seo_knowledge.update_one(
        {"basename": basename},
        {
            "$set": {
                "user_implementation.status": "in_progress",
                "user_implementation.comments": notes,
                "user_implementation.started_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
        }
    )
    if res.modified_count > 0:
        print(f"🔄 Estratégia {basename} atualizada para IN_PROGRESS (EM_ANDAMENTO) com sucesso!")
    else:
        print(f"⚠️ Nenhuma estratégia encontrada ou modificada com basename: {basename}")

def main():
    parser = argparse.ArgumentParser(description="Gerenciar e auditar estratégias seo_knowledge 1 a 1")
    parser.add_argument("--list", action="store_true", help="Listar todas as estratégias e status")
    parser.add_argument("--implemented", action="store_true", help="Listar apenas estratégias já implementadas (status=completed)")
    parser.add_argument("--pending", action="store_true", help="Listar apenas estratégias pendentes de implementação")
    parser.add_argument("--status", type=str, choices=["completed", "pending", "in_progress"], help="Filtrar estratégias por status")
    parser.add_argument("--detail", type=str, help="Exibir detalhes completos de uma estratégia pelo basename")
    parser.add_argument("--in-progress", type=str, dest="in_progress", help="Basename da estratégia a marcar como EM_ANDAMENTO (in_progress)")
    parser.add_argument("--mark", type=str, help="Basename da estratégia a marcar como concluída")
    parser.add_argument("--steps", type=str, default="0,1,2,3,4", help="Índices dos passos concluídos separados por vírgula (ex: 0,1,2,3)")
    parser.add_argument("--notes", type=str, default="Otimização em andamento.", help="Notas de auditoria da implementação")
    
    args = parser.parse_args()
    if args.list:
        list_strategies()
    elif args.implemented:
        list_strategies(status_filter="completed")
    elif args.pending:
        list_strategies(status_filter="pending")
    elif args.status:
        list_strategies(status_filter=args.status)
    elif args.detail:
        show_strategy_detail(args.detail)
    elif args.in_progress:
        mark_in_progress(args.in_progress, args.notes)
    elif args.mark:
        steps = [int(x.strip()) for x in args.steps.split(",") if x.strip().isdigit()]
        mark_strategy(args.mark, steps, args.notes)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
