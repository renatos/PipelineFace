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
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
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
        s_low = status_filter.lower().strip()
        if s_low in ["completed", "done", "concluido", "concluído"]:
            query = {"user_implementation.status": {"$in": ["completed", "concluido", "concluído"]}}
        elif s_low in ["in_progress", "em_andamento", "andamento"]:
            query = {"user_implementation.status": {"$in": ["in_progress", "em_andamento"]}}
        elif s_low in ["pending", "todo", "pendente"]:
            query = {"$or": [
                {"user_implementation": None},
                {"user_implementation.status": {"$in": ["pending", "pendente", None]}},
                {"user_implementation.status": {"$nin": ["completed", "concluido", "concluído", "in_progress", "em_andamento"]}}
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
                "user_implementation.status": "concluido",
                "user_implementation.completed_steps": step_indices,
                "user_implementation.comments": notes,
                "user_implementation.applied_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
        }
    )
    if res.modified_count > 0:
        print(f"✅ Estratégia {basename} atualizada para CONCLUIDO com sucesso!")
    else:
        print(f"⚠️ Nenhuma estratégia encontrada ou modificada com basename: {basename}")

def mark_in_progress(basename: str, notes: str = "Iniciando execução da estratégia..."):
    db = get_db()
    res = db.seo_knowledge.update_one(
        {"basename": basename},
        {
            "$set": {
                "user_implementation.status": "em_andamento",
                "user_implementation.comments": notes,
                "user_implementation.started_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
        }
    )
    if res.modified_count > 0:
        print(f"🔄 Estratégia {basename} atualizada para EM_ANDAMENTO com sucesso!")
    else:
        print(f"⚠️ Nenhuma estratégia encontrada ou modificada com basename: {basename}")

def get_core_repo():
    from web.infrastructure.mongo_repository import MongoCoreSEOStandardRepository
    client = pymongo.MongoClient(MONGO_URI)
    repo = MongoCoreSEOStandardRepository(client, DB_NAME)
    repo.seed_defaults()
    return repo

def list_core_rules():
    repo = get_core_repo()
    standards = repo.list_all(apenas_ativos=False)

    print(f"⭐ Total de Core Standards (Padrões Permanentes de SEO): {len(standards)}")
    print("=" * 90)
    for s in standards:
        status_label = "ATIVO" if s.is_active else "INATIVO"
        scope = ", ".join(s.rule_scope)
        instances = s.applied_instances or []
        
        print(f"📌 [{status_label}] ID: {s.id:<28} | Cat: {s.category:<16} | Escopo: [{scope}]")
        print(f"   Título: {s.title}")
        print(f"   Descrição: {s.description}")
        if s.checklist_items:
            print(f"   Checklist de Aceite ({len(s.checklist_items)}):")
            for item in s.checklist_items:
                print(f"     [✓] {item}")
        print(f"   Aplicações Registradas ({len(instances)}):")
        if instances:
            for inst in instances:
                slug = inst.get("page_slug", "N/A")
                dt = str(inst.get("applied_at", ""))[:10]
                inst_notes = inst.get("notes", "")
                pid = f" (ID {inst.get('page_id')})" if inst.get('page_id') else ""
                print(f"     • /{slug}/{pid} ({dt}) — {inst_notes}")
        else:
            print("     • (Nenhuma página registrada ainda)")
        print("-" * 90)

def set_core_rule(basename_or_id: str, scope: list = None, title: str = None, category: str = "on_page_structure", notes: str = ""):
    db = get_db()
    repo = get_core_repo()
    if scope is None:
        scope = ["all_pages", "on_page_structure"]
    
    # 1. Verificar se existe estratégia com esse basename
    strat = db.seo_knowledge.find_one({"basename": basename_or_id})
    strat_title = strat.get("seo_knowledge", {}).get("titulo_estrategia") if strat else None
    strat_desc = strat.get("seo_knowledge", {}).get("resumo_executivo") if strat else None

    standard_id = basename_or_id.replace("post_", "").replace("fb_", "").replace("_", "-")
    std_title = title or strat_title or basename_or_id
    std_desc = notes or strat_desc or "Diretriz permanente de SEO."

    from web.domain.entities import CoreSEOStandard
    standard = CoreSEOStandard(
        id=standard_id,
        title=std_title,
        category=category,
        description=std_desc,
        source_strategy_id=basename_or_id if strat else None,
        rule_scope=scope,
        checklist_items=strat.get("seo_knowledge", {}).get("passo_a_passo_detalhado", []) if strat else []
    )
    repo.save_or_update(standard)

    # 2. Atualizar no seo_knowledge se for uma estratégia existente
    if strat:
        db.seo_knowledge.update_one(
            {"basename": basename_or_id},
            {
                "$set": {
                    "user_implementation.is_core_rule": True,
                    "user_implementation.status": "core_standard",
                    "user_implementation.rule_scope": scope,
                    "updated_at": datetime.now().isoformat()
                }
            }
        )

    print(f"⭐ Padrão Permanente '{standard_id}' salvo com sucesso na collection core_seo_standards!")
    print(f"   Título: {std_title}")
    print(f"   Escopo: {scope}")

def apply_core_rule(standard_id_or_basename: str, page_slug: str, page_id: int = None, notes: str = ""):
    db = get_db()
    repo = get_core_repo()
    
    # Resolver ID na collection core_seo_standards
    std = repo.get_by_id(standard_id_or_basename)
    if not std:
        # Tentar buscar por source_strategy_id
        doc = db.core_seo_standards.find_one({"source_strategy_id": standard_id_or_basename})
        if doc:
            std_id = doc["id"]
        else:
            std_id = standard_id_or_basename
    else:
        std_id = std.id

    repo.record_application(std_id, page_slug=page_slug, page_id=page_id, notes=notes)

    # Sincronizar no seo_knowledge caso exista a estratégia de origem
    db.seo_knowledge.update_one(
        {"$or": [{"basename": standard_id_or_basename}, {"basename": f"fb_{standard_id_or_basename}"}]},
        {
            "$set": {
                "user_implementation.is_core_rule": True,
                "user_implementation.status": "core_standard",
                "updated_at": datetime.now().isoformat()
            },
            "$push": {
                "user_implementation.applied_instances": {
                    "page_slug": page_slug,
                    "page_id": page_id,
                    "applied_at": datetime.now().isoformat(),
                    "notes": notes
                }
            }
        }
    )
    print(f"✅ Aplicação do Core Standard '{std_id}' registrada na collection core_seo_standards (Página: /{page_slug}/)!")

def main():
    parser = argparse.ArgumentParser(description="Gerenciar e auditar estratégias seo_knowledge 1 a 1 e Core Standards")
    parser.add_argument("--list", action="store_true", help="Listar todas as estratégias e status")
    parser.add_argument("--implemented", action="store_true", help="Listar apenas estratégias já implementadas (status=completed)")
    parser.add_argument("--pending", action="store_true", help="Listar apenas estratégias pendentes de implementação")
    parser.add_argument("--core", "--core-rules", action="store_true", dest="core_rules", help="Listar todas as Core Rules (Padrões Permanentes de SEO)")
    parser.add_argument("--status", type=str, choices=["completed", "pending", "in_progress", "core_standard"], help="Filtrar estratégias por status")
    parser.add_argument("--detail", type=str, help="Exibir detalhes completos de uma estratégia pelo basename")
    parser.add_argument("--in-progress", type=str, dest="in_progress", help="Basename da estratégia a marcar como EM_ANDAMENTO (in_progress)")
    parser.add_argument("--set-core", type=str, dest="set_core", help="Promover estratégia para Core Standard (Padrão Permanente)")
    parser.add_argument("--apply-core", type=str, dest="apply_core", help="Registrar aplicação de uma Core Rule em uma página específica")
    parser.add_argument("--page", type=str, help="Slug da página (ex: lash-lifting-em-bh)")
    parser.add_argument("--page-id", type=int, help="ID da página no WordPress (ex: 334)")
    parser.add_argument("--scope", type=str, default="all_pages,on_page_structure", help="Escopos separados por vírgula para Core Rule")
    parser.add_argument("--mark", type=str, help="Basename da estratégia a marcar como concluída (tarefa pontual)")
    parser.add_argument("--steps", type=str, default="0,1,2,3,4", help="Índices dos passos concluídos separados por vírgula (ex: 0,1,2,3)")
    parser.add_argument("--notes", type=str, default="Otimização em andamento.", help="Notas de auditoria da implementação")
    
    args = parser.parse_args()
    if args.core_rules:
        list_core_rules()
    elif args.set_core:
        scopes = [s.strip() for s in args.scope.split(",") if s.strip()]
        set_core_rule(args.set_core, scope=scopes, notes=args.notes)
    elif args.apply_core:
        if not args.page:
            print("❌ Erro: --page é obrigatório para registrar a aplicação de uma Core Rule.")
            sys.exit(1)
        apply_core_rule(args.apply_core, page_slug=args.page, page_id=args.page_id, notes=args.notes)
    elif args.list:
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
