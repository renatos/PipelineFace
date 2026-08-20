#!/usr/bin/env python3
"""
Script para baixar todas as páginas do WordPress (Studio Githa) via REST API.
Salva arquivos HTML editáveis, JSONs completos e um índice Markdown.
"""
import os
import re
import json
import requests
from datetime import datetime
from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../"))
load_dotenv(os.path.join(BASE_DIR, ".env"))

OUTPUT_DIR = os.path.abspath(os.path.dirname(__file__))
PAGES_DIR = os.path.join(OUTPUT_DIR, "pages")
JSON_DIR = os.path.join(OUTPUT_DIR, "json")

os.makedirs(PAGES_DIR, exist_ok=True)
os.makedirs(JSON_DIR, exist_ok=True)

WORDPRESS_HOST = os.getenv("WORDPRESS_HOST", "https://studiogitha.com").rstrip("/")
WORDPRESS_USER = os.getenv("WORDPRESS_USER")
WORDPRESS_PASSWORD = os.getenv("WORDPRESS_PASSWORD")

session = requests.Session()
headers = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

print(f"🚀 Conectando a {WORDPRESS_HOST}...")

# 1. Login no WordPress para obter acesso a rascunhos e páginas privadas
login_url = f"{WORDPRESS_HOST}/wp-login.php"
session.get(login_url, headers=headers, timeout=15)
login_data = {
    "log": WORDPRESS_USER,
    "pwd": WORDPRESS_PASSWORD,
    "wp-submit": "Acessar",
    "redirect_to": f"{WORDPRESS_HOST}/wp-admin/",
    "testcookie": "1"
}
session.post(login_url, data=login_data, headers=headers, timeout=20)
admin_resp = session.get(f"{WORDPRESS_HOST}/wp-admin/", headers=headers, timeout=15)

nonce_match = re.search(r"wpApiSettings\s*=\s*\{[^}]*\"nonce\":\"([^\"]+)\"", admin_resp.text)
nonce = nonce_match.group(1) if nonce_match else None

req_headers = {**headers}
if nonce:
    req_headers["X-WP-Nonce"] = nonce
    print("🔑 Autenticado com sucesso (REST Nonce obtido).")
else:
    print("⚠️ Não foi possível obter o nonce de admin, consultando páginas públicas.")

# 2. Buscar páginas (paginadas)
page_num = 1
all_pages = []

while True:
    api_url = f"{WORDPRESS_HOST}/wp-json/wp/v2/pages?per_page=100&page={page_num}&status=any"
    resp = session.get(api_url, headers=req_headers, timeout=20)
    if resp.status_code != 200:
        break
    items = resp.json()
    if not items or not isinstance(items, list):
        break
    all_pages.extend(items)
    total_pages_hdr = resp.headers.get("X-WP-TotalPages", "1")
    if page_num >= int(total_pages_hdr):
        break
    page_num += 1

print(f"📄 Total de páginas encontradas: {len(all_pages)}")

# 3. Salvar cada página
manifest = []
for p in all_pages:
    pid = p.get("id")
    slug = p.get("slug") or f"page-{pid}"
    title = p.get("title", {}).get("rendered", "Sem Título")
    raw_title = p.get("title", {}).get("raw", title)
    status = p.get("status", "publish")
    link = p.get("link", "")
    template = p.get("template", "")
    modified = p.get("modified", "")
    
    content_rendered = p.get("content", {}).get("rendered", "")
    content_raw = p.get("content", {}).get("raw", content_rendered)
    
    # Salvar JSON completo
    json_path = os.path.join(JSON_DIR, f"{slug}_{pid}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(p, f, ensure_ascii=False, indent=2)
        
    # Salvar arquivo HTML
    html_filename = f"{slug}.html"
    html_path = os.path.join(PAGES_DIR, html_filename)
    
    # Montar HTML amigável para visualização e edição local
    html_content = f"""<!--
ID: {pid}
Slug: {slug}
Title: {raw_title}
Status: {status}
Template: {template}
Modified: {modified}
Link: {link}
WP-Admin Edit: {WORDPRESS_HOST}/wp-admin/post.php?post={pid}&action=edit
-->
{content_rendered}
"""
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
        
    manifest.append({
        "id": pid,
        "title": raw_title,
        "slug": slug,
        "status": status,
        "template": template,
        "modified": modified,
        "link": link,
        "edit_link": f"{WORDPRESS_HOST}/wp-admin/post.php?post={pid}&action=edit",
        "html_file": f"pages/{html_filename}",
        "json_file": f"json/{slug}_{pid}.json"
    })
    print(f"  • [{status.upper():<7}] ID {pid:<4} | {slug:<30} -> pages/{html_filename}")

# 4. Salvar manifesto JSON e README.md
manifest_path = os.path.join(OUTPUT_DIR, "manifest.json")
with open(manifest_path, "w", encoding="utf-8") as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2)

readme_path = os.path.join(OUTPUT_DIR, "README.md")
with open(readme_path, "w", encoding="utf-8") as f:
    f.write(f"# 🌐 Páginas do Site Studio Githa (`{WORDPRESS_HOST}`)\n\n")
    f.write(f"> **Última sincronização:** {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}  \n")
    f.write(f"> **Total de Páginas:** {len(manifest)}\n\n")
    f.write("## 📋 Índice de Páginas\n\n")
    f.write("| ID | Status | Título | Slug | Arquivo HTML | Link no WP-Admin |\n")
    f.write("| :--- | :--- | :--- | :--- | :--- | :--- |\n")
    for item in manifest:
        f.write(f"| `{item['id']}` | **{item['status'].upper()}** | {item['title']} | `{item['slug']}` | [`{item['html_file']}`]({item['html_file']}) | [Editar]({item['edit_link']}) |\n")

print(f"\n✅ Concluído com sucesso! Manifesto e páginas salvos em {OUTPUT_DIR}")
