#!/usr/bin/env python3
"""
Script para enviar/atualizar uma página editada localmente de volta para o WordPress via REST API.
Lê o ID ou Slug do cabeçalho do arquivo HTML ou via argumento.

Uso:
  python3 SiteStudioGitha/push_page.py --file SiteStudioGitha/pages/limpeza-de-pele-em-bh.html
  python3 SiteStudioGitha/push_page.py --id 214 --file SiteStudioGitha/pages/limpeza-de-pele-em-bh.html
"""
import os
import re
import sys
import json
import argparse
import requests
from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../"))
load_dotenv(os.path.join(BASE_DIR, ".env"))

WORDPRESS_HOST = os.getenv("WORDPRESS_HOST", "https://studiogitha.com").rstrip("/")
WORDPRESS_USER = os.getenv("WORDPRESS_USER")
WORDPRESS_PASSWORD = os.getenv("WORDPRESS_PASSWORD")

def extract_meta_from_html(content: str):
    meta = {}
    comment_match = re.match(r"^<!--\s*(.*?)\s*-->", content, re.DOTALL)
    if comment_match:
        for line in comment_match.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip().lower()] = v.strip()
    return meta

def validate_scripts_in_html(content: str) -> tuple[bool, str]:
    """Validates all <script> tags for unclosed braces and valid JSON-LD."""
    script_pattern = re.compile(r'<script(.*?)>(.*?)</script>', re.DOTALL | re.IGNORECASE)
    for match in script_pattern.finditer(content):
        attrs = match.group(1).lower()
        script_body = match.group(2).strip()
        if not script_body:
            continue
            
        if "application/ld+json" in attrs:
            try:
                json.loads(script_body)
            except json.JSONDecodeError as e:
                return False, f"JSON-LD inválido (erro de sintaxe/chaves não fechadas): {e}"
        else:
            # Check balanced curly braces and parentheses
            stack = []
            pairs = {'}': '{', ')': '(', ']': '['}
            in_single = False
            in_double = False
            escaped = False
            for idx, c in enumerate(script_body):
                if escaped:
                    escaped = False
                    continue
                if c == '\\':
                    escaped = True
                    continue
                if c == "'" and not in_double:
                    in_single = not in_single
                    continue
                if c == '"' and not in_single:
                    in_double = not in_double
                    continue
                if in_single or in_double:
                    continue
                if c in '{[(':
                    stack.append((c, idx))
                elif c in '}])':
                    if not stack or pairs[c] != stack.pop()[0]:
                        return False, f"Chave ou parêntese desbalanceado em tag <script> na posição {idx}"
            if stack:
                return False, f"Tag <script> possui chave ou parêntese não fechado: '{stack[-1][0]}'"
    return True, "OK"

def main():
    parser = argparse.ArgumentParser(description="Atualizar página no WordPress a partir do arquivo HTML local")
    parser.add_argument("--file", required=True, help="Caminho para o arquivo .html local")
    parser.add_argument("--id", type=int, help="ID da página no WordPress (se não informado, tenta extrair do cabeçalho)")
    parser.add_argument("--status", choices=["draft", "publish"], help="Alterar status de publicação")
    parser.add_argument("--title", help="Alterar título da página")
    
    args = parser.parse_args()

    if not os.path.exists(args.file):
        print(f"❌ Arquivo não encontrado: {args.file}")
        sys.exit(1)

    with open(args.file, "r", encoding="utf-8") as f:
        file_content = f.read()

    # Pre-flight Lint Check
    is_valid, err_msg = validate_scripts_in_html(file_content)
    if not is_valid:
        print(f"🛑 BLOQUEADO: Erro no Lint de Scripts/JSON-LD: {err_msg}")
        print("Corrija o arquivo antes de enviar para o WordPress.")
        sys.exit(1)
    else:
        print("✅ Pre-flight Lint OK: Todos os <script> e JSON-LD estão 100% balanceados e válidos.")

    header_meta = extract_meta_from_html(file_content)
    page_id = args.id or (int(header_meta.get("id")) if header_meta.get("id") else None)

    if not page_id:
        print("❌ ID da página não informado e não encontrado no cabeçalho do arquivo.")
        sys.exit(1)

    # Remover comentário de cabeçalho para enviar apenas o HTML limpo
    clean_html = re.sub(r"^<!--\s*.*?\s*-->\s*", "", file_content, flags=re.DOTALL)

    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
    }

    print(f"🚀 Conectando a {WORDPRESS_HOST} para atualizar página ID {page_id}...")
    login_url = f"{WORDPRESS_HOST}/wp-login.php"
    session.get(login_url, headers=headers, timeout=15)
    session.post(login_url, data={
        "log": WORDPRESS_USER,
        "pwd": WORDPRESS_PASSWORD,
        "wp-submit": "Acessar",
        "redirect_to": f"{WORDPRESS_HOST}/wp-admin/",
        "testcookie": "1"
    }, headers=headers, timeout=20)
    
    admin_resp = session.get(f"{WORDPRESS_HOST}/wp-admin/", headers=headers, timeout=15)
    nonce_match = re.search(r"wpApiSettings\s*=\s*\{[^}]*\"nonce\":\"([^\"]+)\"", admin_resp.text)
    if not nonce_match:
        print("❌ Falha na autenticação.")
        sys.exit(1)

    nonce = nonce_match.group(1)

    payload = {
        "content": clean_html
    }
    if header_meta.get("template"):
        payload["template"] = header_meta.get("template")
    if args.status:
        payload["status"] = args.status
    if args.title:
        payload["title"] = args.title

    api_url = f"{WORDPRESS_HOST}/wp-json/wp/v2/pages/{page_id}"
    req_headers = {
        **headers,
        "X-WP-Nonce": nonce,
        "Content-Type": "application/json"
    }

    resp = session.post(api_url, json=payload, headers=req_headers, timeout=20)
    if resp.status_code == 200:
        data = resp.json()
        print(f"✅ Página ID {page_id} atualizada com sucesso no WordPress!")
        print(f"📌 Título: {data.get('title', {}).get('rendered')}")
        print(f"📝 Status: {data.get('status').upper()}")
        print(f"🔗 Link: {data.get('link')}")
        print(f"🕒 Modificado em: {data.get('modified')}")
    else:
        print(f"❌ Erro ao atualizar ({resp.status_code}): {resp.text}")
        sys.exit(1)

if __name__ == "__main__":
    main()
