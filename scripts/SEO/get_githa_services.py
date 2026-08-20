#!/usr/bin/env python3
"""
Script auxiliar para consultar serviços e preços reais do Studio Githa (PostgreSQL).
Lê as credenciais do .env automaticamente.

Uso:
  python3 scripts/SEO/get_githa_services.py
"""
import os
import sys
from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
load_dotenv(os.path.join(BASE_DIR, ".env"))
sys.path.insert(0, BASE_DIR)

from web.infrastructure.githa_repository import GithaContextRepository

def main():
    repo = GithaContextRepository()
    ctx = repo.get_full_context()
    
    print(f"==================================================")
    print(f"💈 STUDIO GITHA — Catálogo de Serviços (Githa DB)")
    print(f"==================================================")
    print(f"Total de Serviços: {ctx.total_services}")
    print(f"Total de Clientes: {ctx.total_clients}")
    print(f"Total de Agendamentos: {ctx.total_appointments}")
    print(f"\n--- Serviços Mais Populares e Rentáveis ---")
    for s in ctx.popular_services:
        desc = f" ({s.description})" if s.description else ""
        rev = f" | R$ {s.total_revenue:,.2f}" if s.total_revenue else ""
        print(f"• {s.name:<35} | R$ {s.price:>6.2f} | {s.duration_minutes:>3} min | {s.appointment_count:>3} agendamentos{rev}{desc}")

if __name__ == "__main__":
    main()
