#!/usr/bin/env python3
"""
Uploads a media file (with EXIF/GPS geotags) to WordPress Media Library via REST API.

Usage:
  python3 scripts/SEO/upload_wp_media.py --file data/geotagged_images/ambiente-studio-githa-sala-estetica-nova-suica-bh.jpg
"""
import os
import re
import sys
import argparse
from pathlib import Path
import requests
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")

WORDPRESS_HOST = os.getenv("WORDPRESS_HOST", "https://studiogitha.com").rstrip("/")
WORDPRESS_USER = os.getenv("WORDPRESS_USER")
WORDPRESS_PASSWORD = os.getenv("WORDPRESS_PASSWORD")

def upload_image_to_wordpress(file_path: Path, alt_text: str = "", title: str = "") -> dict:
    if not file_path.exists():
        print(f"❌ Arquivo não encontrado: {file_path}")
        return None
        
    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
    }

    print(f"🚀 Conectando a {WORDPRESS_HOST} para autenticação...")
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
        print("❌ Falha na autenticação WordPress.")
        return None

    nonce = nonce_match.group(1)
    
    filename = file_path.name
    content_type = "image/jpeg" if file_path.suffix.lower() in [".jpg", ".jpeg"] else "image/png"
    
    print(f"⬆️  Fazendo upload de '{filename}' para a biblioteca de mídia do WordPress...")
    
    with open(file_path, "rb") as f:
        file_bytes = f.read()

    upload_headers = {
        **headers,
        "X-WP-Nonce": nonce,
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Content-Type": content_type
    }
    
    media_url = f"{WORDPRESS_HOST}/wp-json/wp/v2/media"
    res = session.post(media_url, headers=upload_headers, data=file_bytes, timeout=30)
    
    if res.status_code in [200, 201]:
        data = res.json()
        source_url = data.get("source_url")
        media_id = data.get("id")
        print(f"\n✅ Upload concluído com sucesso!")
        print(f"🆔 Media ID: {media_id}")
        print(f"🔗 URL Pública no WordPress: {source_url}")
        
        # Optionally update alt text and title
        if alt_text or title:
            update_payload = {}
            if alt_text:
                update_payload["alt_text"] = alt_text
            if title:
                update_payload["title"] = title
            session.post(f"{media_url}/{media_id}", headers={**headers, "X-WP-Nonce": nonce}, json=update_payload)
            
        return {
            "id": media_id,
            "url": source_url,
            "filename": filename
        }
    else:
        print(f"❌ Falha no upload: Status {res.status_code}")
        print(res.text)
        return None

def main():
    parser = argparse.ArgumentParser(description="Upload de imagem para biblioteca de mídia do WordPress")
    parser.add_argument("--file", required=True, help="Caminho do arquivo local para upload")
    parser.add_argument("--alt", default="", help="Texto alternativo (alt text)")
    parser.add_argument("--title", default="", help="Título da mídia no WordPress")
    
    args = parser.parse_args()
    upload_image_to_wordpress(Path(args.file), args.alt, args.title)

if __name__ == "__main__":
    main()
