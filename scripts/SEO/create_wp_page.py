#!/usr/bin/env python3
"""
Script para criação e gerenciamento de páginas no WordPress (Studio Githa) via REST API.
Lê as credenciais do .env automaticamente.

Uso:
  python3 scripts/SEO/create_wp_page.py \
    --title "Nome da Página" \
    --slug "slug-da-pagina" \
    --status draft \
    --html "<p>Conteúdo HTML</p>"
"""
import os
import re
import sys
import argparse
import requests
from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
load_dotenv(os.path.join(BASE_DIR, ".env"))

WORDPRESS_HOST = os.getenv("WORDPRESS_HOST", "https://studiogitha.com").rstrip("/")
WORDPRESS_USER = os.getenv("WORDPRESS_USER")
WORDPRESS_PASSWORD = os.getenv("WORDPRESS_PASSWORD")

class WordPressAPIClient:
    def __init__(self, host: str = WORDPRESS_HOST, user: str = WORDPRESS_USER, password: str = WORDPRESS_PASSWORD):
        self.host = host
        self.user = user
        self.password = password
        self.session = requests.Session()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        self.nonce = None

    def authenticate(self) -> bool:
        """Autentica no WordPress via sessão web e obtém o REST API nonce."""
        if not self.user or not self.password:
            raise ValueError("WORDPRESS_USER ou WORDPRESS_PASSWORD não definidos no .env")

        login_url = f"{self.host}/wp-login.php"
        self.session.get(login_url, headers=self.headers, timeout=15)

        login_data = {
            "log": self.user,
            "pwd": self.password,
            "wp-submit": "Acessar",
            "redirect_to": f"{self.host}/wp-admin/",
            "testcookie": "1"
        }
        resp = self.session.post(login_url, data=login_data, headers=self.headers, timeout=20)
        
        admin_resp = self.session.get(f"{self.host}/wp-admin/", headers=self.headers, timeout=15)
        if "wp-admin" not in admin_resp.url:
            print("❌ Falha na autenticação. Verifique usuário e senha no .env.")
            return False

        nonce_match = re.search(r"wpApiSettings\s*=\s*\{[^}]*\"nonce\":\"([^\"]+)\"", admin_resp.text)
        if nonce_match:
            self.nonce = nonce_match.group(1)
            return True
        else:
            print("⚠️ Autenticado, mas não foi possível extrair o wpApiSettings nonce.")
            return False

    def create_page(self, title: str, slug: str, content: str, status: str = "draft", template: str = "elementor_canvas") -> dict:
        """Cria uma nova página via REST API."""
        if not self.nonce:
            if not self.authenticate():
                raise RuntimeError("Não foi possível autenticar no WordPress.")

        api_url = f"{self.host}/wp-json/wp/v2/pages"
        payload = {
            "title": title,
            "slug": slug,
            "content": content,
            "status": status,
            "template": template
        }
        headers = {
            **self.headers,
            "X-WP-Nonce": self.nonce,
            "Content-Type": "application/json"
        }
        
        resp = self.session.post(api_url, json=payload, headers=headers, timeout=20)
        if resp.status_code in [200, 201]:
            data = resp.json()
            return data
        else:
            raise RuntimeError(f"Erro na API ({resp.status_code}): {resp.text}")

def main():
    parser = argparse.ArgumentParser(description="Criar página no WordPress via REST API")
    parser.add_argument("--title", required=True, help="Título da página")
    parser.add_argument("--slug", required=True, help="Slug amigável (kebab-case)")
    parser.add_argument("--status", default="draft", choices=["draft", "publish", "pending"], help="Status da página")
    parser.add_argument("--template", default="elementor_canvas", help="Template do WordPress")
    parser.add_argument("--html", help="Conteúdo HTML direto")
    parser.add_argument("--file", help="Caminho para arquivo contendo o HTML")

    args = parser.parse_args()

    content = ""
    if args.file and os.path.exists(args.file):
        with open(args.file, "r", encoding="utf-8") as f:
            content = f.read()
    elif args.html:
        content = args.html
    else:
        content = f"<h1>{args.title}</h1><p>Página gerada automaticamente.</p>"

    client = WordPressAPIClient()
    print(f"🚀 Conectando a {WORDPRESS_HOST}...")
    try:
        page = client.create_page(
            title=args.title,
            slug=args.slug,
            content=content,
            status=args.status,
            template=args.template
        )
        print(f"✅ Página criada com sucesso!")
        print(f"🆔 ID: {page.get('id')}")
        print(f"📌 Título: {page.get('title', {}).get('rendered')}")
        print(f"🔗 Slug: {page.get('slug')}")
        print(f"📝 Status: {page.get('status').upper()}")
        print(f"✏️ Editar no WordPress: {WORDPRESS_HOST}/wp-admin/post.php?post={page.get('id')}&action=edit")
    except Exception as e:
        print(f"❌ Erro: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
