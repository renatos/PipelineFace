#!/usr/bin/env python3
"""
Sync Google Maps / Places Reviews for Studio Githa.
Fetches real-time rating, total review count, and latest reviews via Google Places API (New),
and automatically updates inicio.html and Schema.org.

Usage:
  python3 scripts/SEO/sync_google_reviews.py --test
  python3 scripts/SEO/sync_google_reviews.py --update
  python3 scripts/SEO/sync_google_reviews.py --update --push
"""
import os
import sys
import json
import re
import subprocess
import argparse
from pathlib import Path
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("GOOGLE_CLOUD_API_KEY") or os.getenv("GOOGLE_NLP_API_KEY") or os.getenv("GOOGLE_API_KEY")
INICIO_HTML_PATH = Path("/home/renato/dev/PipelineFace/SiteStudioGitha/pages/inicio.html")
PLACE_ID_FIXED = "ChIJP58bZQKXpgARb6twJXzbl44"

def find_place_id(query: str, api_key: str) -> str:
    """Finds the Google Place ID using Places API (New)."""
    new_url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress"
    }
    payload = {"textQuery": query, "languageCode": "pt-BR"}
    try:
        new_res = requests.post(new_url, headers=headers, json=payload, timeout=15)
        new_data = new_res.json()
        places = new_data.get("places", [])
        if places:
            p = places[0]
            name = p.get("displayName", {}).get("text", "")
            addr = p.get("formattedAddress", "")
            pid = p.get("id", "")
            print(f"📍 Local encontrado: {name} ({addr})")
            print(f"🔑 Place ID: {pid}")
            return pid
        else:
            print(f"❌ Resposta da Places API (New): {new_data}")
    except Exception as e:
        print(f"❌ Erro na chamada da Places API: {e}")
    return None

def fetch_place_reviews(place_id: str, api_key: str) -> dict:
    """Fetches details & reviews from Google Places API (New)."""
    new_url = f"https://places.googleapis.com/v1/places/{place_id}"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "id,displayName,rating,userRatingCount,reviews,googleMapsUri"
    }
    params = {"languageCode": "pt-BR"}
    
    res = requests.get(new_url, headers=headers, params=params, timeout=15)
    if res.status_code == 200:
        data = res.json()
        rating = data.get("rating", 4.9)
        review_count = data.get("userRatingCount", 55)
        maps_uri = data.get("googleMapsUri", "https://maps.google.com")
        reviews_raw = data.get("reviews", [])
        
        parsed_reviews = []
        for r in reviews_raw:
            author_data = r.get("authorAttribution", {})
            name = author_data.get("displayName", "Cliente Google")
            photo_url = author_data.get("photoUri", "")
            author_uri = author_data.get("uri", "")
            stars = r.get("rating", 5)
            text_obj = r.get("text", {})
            text = text_obj.get("text", "") if isinstance(text_obj, dict) else str(text_obj)
            relative_time = r.get("relativePublishTimeDescription", "")
            
            # Extract initials for avatar fallback
            parts = name.strip().split()
            initials = (parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")).upper()
            
            parsed_reviews.append({
                "name": name,
                "initials": initials,
                "photo_url": photo_url,
                "author_uri": author_uri,
                "rating": stars,
                "text": text,
                "time": relative_time
            })
            
        return {
            "rating": rating,
            "review_count": review_count,
            "maps_uri": maps_uri,
            "reviews": parsed_reviews
        }
    else:
        print(f"❌ Erro ao buscar detalhes da Places API: {res.status_code} - {res.text}")
        return None

def update_inicio_html(data: dict):
    """Updates the reviews section and Schema.org in inicio.html."""
    if not INICIO_HTML_PATH.exists():
        print(f"❌ Arquivo não encontrado: {INICIO_HTML_PATH}")
        return False
        
    html_content = INICIO_HTML_PATH.read_text(encoding="utf-8")
    rating = data["rating"]
    review_count = data["review_count"]
    maps_uri = data["maps_uri"]
    reviews = data.get("reviews", [])
    
    # 1. Generate Cards HTML
    cards_html = []
    for r in reviews[:3]:  # Top 3 display
        stars_span = "★" * int(r['rating']) + "☆" * (5 - int(r['rating']))
        time_tag = f" • {r['time']}" if r['time'] else ""
        escaped_text = r['text'].replace('"', '&quot;').replace("'", "&#039;")
        
        card = f"""      <div class="githa-card" style="position: relative; display: flex; flex-direction: column; justify-content: space-between;">
        <div>
          <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px;">
            <span style="color: #fbbc04; font-size: 16px; letter-spacing: 1px;">{stars_span}</span>
            <span style="color: #a8b0ab; font-size: 12px; background: rgba(255,255,255,0.06); padding: 2px 8px; border-radius: 10px;">Google Review</span>
          </div>
          <p style="font-style: italic; color: #e2e8e5; line-height: 1.6;">&#8220;{escaped_text}&#8221;</p>
        </div>
        <div style="margin-top: 20px; border-top: 1px solid rgba(255,255,255,0.08); padding-top: 12px; display: flex; align-items: center; gap: 10px;">
          <div style="width: 36px; height: 36px; border-radius: 50%; background: linear-gradient(135deg, #fdafe1, #bd7cb5); display: flex; align-items: center; justify-content: center; font-weight: 700; color: #121714; font-size: 14px;">{r['initials']}</div>
          <div>
            <p style="color: #ffffff; font-weight: 700; font-size: 14px; margin: 0;">{r['name']}</p>
            <p style="color: #fdafe1; font-size: 12px; margin: 0;">Avaliação Verificada{time_tag}</p>
          </div>
        </div>
      </div>"""
        cards_html.append(card)
        
    all_cards = "\n".join(cards_html)
    
    # 2. Build New Reviews Section
    new_section = f"""    <!-- Section: Depoimentos & Google Reviews -->
    <div style="text-align: center; margin-top: 50px; margin-bottom: 25px;">
      <span class="githa-badge" style="background: rgba(253, 175, 225, 0.15); color: #fdafe1; border: 1px solid rgba(253, 175, 225, 0.3); padding: 6px 16px; border-radius: 50px; font-size: 13px; font-weight: 700; letter-spacing: 1px; text-transform: uppercase;">⭐ Avaliações no Google</span>
      <h2 class="githa-section-title" style="margin-top: 15px; margin-bottom: 10px;">O que Nossas Clientes Dizem</h2>
      <a href="{maps_uri}" target="_blank" rel="noopener noreferrer" style="text-decoration: none; display: inline-flex; align-items: center; gap: 12px; background: rgba(33, 41, 36, 0.9); border: 1px solid rgba(255, 255, 255, 0.12); padding: 10px 22px; border-radius: 50px; margin-bottom: 30px; transition: transform 0.2s ease;">
        <span style="font-family: 'Outfit', sans-serif; font-size: 24px; font-weight: 800; color: #ffffff;">{rating}</span>
        <span style="color: #fbbc04; font-size: 18px; letter-spacing: 2px;">★★★★★</span>
        <span style="color: #c5c7c5; font-size: 14px; font-weight: 500;">({review_count} avaliações no Google) ↗</span>
      </a>
    </div>
    <div class="githa-grid-3">
{all_cards}
    </div>"""

    # Replace Section in HTML
    section_pattern = re.compile(r'<!-- Section: Depoimentos.*?</div>\s*</div>\s*(?=<p>\s*<!-- Section: Localização|<div class="githa-info-box")', re.DOTALL)
    if section_pattern.search(html_content):
        html_content = section_pattern.sub(new_section + "\n", html_content)
    else:
        print("⚠️ Não foi possível encontrar a seção de depoimentos exata pelo regex padrão.")
        
    # 3. Update Schema.org JSON-LD
    schema_pattern = re.compile(r'"aggregateRating":\s*\{[^}]*\}', re.DOTALL)
    new_agg = f""""aggregateRating": {{
        "@type": "AggregateRating",
        "ratingValue": "{rating}",
        "reviewCount": "{review_count}",
        "bestRating": "5"
      }}"""
    html_content = schema_pattern.sub(new_agg, html_content)
    
    INICIO_HTML_PATH.write_text(html_content, encoding="utf-8")
    print(f"✅ {INICIO_HTML_PATH.name} atualizado com dados oficiais da Places API!")
    return True

def main():
    parser = argparse.ArgumentParser(description="Sincronizador de Avaliações do Google Maps para Studio Githa")
    parser.add_argument("--test", action="store_true", help="Apenas testar a conexão com a API e imprimir as avaliações")
    parser.add_argument("--update", action="store_true", help="Atualizar o arquivo inicio.html local")
    parser.add_argument("--push", action="store_true", help="Enviar para o WordPress após atualizar")
    
    args = parser.parse_args()
    
    if not API_KEY:
        print("❌ GOOGLE_CLOUD_API_KEY não configurada no .env!")
        sys.exit(1)
        
    place_id = PLACE_ID_FIXED
    print(f"📡 Conectando na Places API para o Studio Githa (Place ID: {place_id})...")
    data = fetch_place_reviews(place_id, API_KEY)
    
    if not data:
        sys.exit(1)
        
    print("\n" + "=" * 60)
    print(f"⭐ NOTA MÉDIA: {data['rating']}")
    print(f"💬 TOTAL DE AVALIAÇÕES: {data['review_count']}")
    print(f"🔗 GOOGLE MAPS LINK: {data['maps_uri']}")
    print("=" * 60)
    
    reviews = data.get("reviews", [])
    print(f"\n📝 {len(reviews)} AVALIAÇÕES RETORNADAS PELA API:\n")
    for idx, r in enumerate(reviews, 1):
        stars_str = "⭐" * int(r['rating'])
        print(f"{idx}. {r['name']} ({stars_str} - {r['time']})")
        print(f"   \"{r['text']}\"\n")
        
    if args.update or args.push:
        update_inicio_html(data)
        
    if args.push:
        print("\n🚀 Enviando para o WordPress via push_page.py...")
        subprocess.run([
            sys.executable,
            "SiteStudioGitha/push_page.py",
            "--file",
            str(INICIO_HTML_PATH)
        ], check=True)

if __name__ == "__main__":
    main()
