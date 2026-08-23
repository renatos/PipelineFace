#!/usr/bin/env python3
"""
Google Cloud Natural Language SEO Auditor for Studio Githa.
Audits landing pages, calculates entity salience, taxonomy categories, and suggests Schema.org enrichments.

Usage:
  python3 scripts/SEO/analyze_nlp.py --page limpeza-de-pele-em-bh
  python3 scripts/SEO/analyze_nlp.py --all
  python3 scripts/SEO/analyze_nlp.py --text "Seu texto aqui..."
"""
import os
import re
import sys
import json
import argparse
from pathlib import Path
from html.parser import HTMLParser
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("GOOGLE_CLOUD_API_KEY") or os.getenv("GOOGLE_NLP_API_KEY") or os.getenv("GOOGLE_API_KEY")
PAGES_DIR = Path("/home/renato/dev/PipelineFace/SiteStudioGitha/pages")

class HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text_chunks = []
        self.skip_tags = {"script", "style", "head", "title", "meta", "noscript", "svg"}
        self.current_skip = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self.skip_tags:
            self.current_skip += 1

    def handle_endtag(self, tag):
        if tag.lower() in self.skip_tags and self.current_skip > 0:
            self.current_skip -= 1

    def handle_data(self, data):
        if self.current_skip == 0:
            text = data.strip()
            if text:
                self.text_chunks.append(text)

    def get_text(self):
        return " ".join(self.text_chunks)

def extract_text_from_html(html_content: str) -> str:
    """Extracts clean human-readable text from HTML content, removing scripts/styles/comments."""
    # First remove comments and script blocks
    clean_html = re.sub(r'<!--.*?-->', '', html_content, flags=re.DOTALL)
    clean_html = re.sub(r'<script.*?>.*?</script>', '', clean_html, flags=re.DOTALL | re.IGNORECASE)
    clean_html = re.sub(r'<style.*?>.*?</style>', '', clean_html, flags=re.DOTALL | re.IGNORECASE)
    
    parser = HTMLTextExtractor()
    parser.feed(clean_html)
    text = parser.get_text()
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def analyze_document_nlp(text: str, api_key: str):
    """Calls Google Cloud Natural Language API for Entity Analysis and Content Classification."""
    base_url = "https://language.googleapis.com/v1/documents"
    
    # 1. Analyze Entities
    entities_url = f"{base_url}:analyzeEntities?key={api_key}"
    payload = {
        "document": {
            "type": "PLAIN_TEXT",
            "content": text,
            "language": "pt"
        },
        "encodingType": "UTF8"
    }
    
    entities_res = requests.post(entities_url, json=payload, timeout=20)
    entities_data = entities_res.json() if entities_res.status_code == 200 else {}
    
    # 2. Classify Text (Requires minimum ~20 words in PT)
    classify_url = f"{base_url}:classifyText?key={api_key}"
    classify_res = requests.post(classify_url, json=payload, timeout=20)
    classify_data = classify_res.json() if classify_res.status_code == 200 else {}
    
    return {
        "status_code": entities_res.status_code,
        "entities": entities_data.get("entities", []),
        "categories": classify_data.get("categories", []),
        "error": entities_data.get("error") or classify_data.get("error")
    }

def audit_page(page_slug: str):
    html_file = PAGES_DIR / f"{page_slug}.html"
    if not html_file.exists():
        # Try finding by partial name
        matches = list(PAGES_DIR.glob(f"*{page_slug}*.html"))
        if matches:
            html_file = matches[0]
        else:
            print(f"❌ Página não encontrada: {page_slug} em {PAGES_DIR}")
            return
            
    print("\n" + "=" * 80)
    print(f"📑 AUDITORIA GOOGLE NLP: {html_file.name}")
    print("=" * 80)
    
    html_content = html_file.read_text(encoding="utf-8")
    clean_text = extract_text_from_html(html_content)
    word_count = len(clean_text.split())
    
    print(f"📊 Total de Palavras no Conteúdo: {word_count}")
    
    if not API_KEY:
        print("❌ GOOGLE_CLOUD_API_KEY não configurada no .env!")
        return

    result = analyze_document_nlp(clean_text, API_KEY)
    
    if result["status_code"] != 200:
        print(f"❌ Erro na API do Google: {result.get('error')}")
        return
        
    entities = result["entities"]
    categories = result["categories"]
    
    # Classifications
    print("\n🏷️  CATEGORIZAÇÃO OFICIAL DO GOOGLE:")
    if categories:
        for cat in categories:
            name = cat.get("name", "")
            confidence = cat.get("confidence", 0.0) * 100
            print(f"  • {name} (Confiança: {confidence:.1f}%)")
    else:
        print("  (Categoria não atribuída automaticamente ou texto sem classificação prévia)")
        
    # Entities sorted by Salience
    print("\n🧠 TOP 15 ENTIDADES & SALIÊNCIA (Peso no Algoritmo do Google):")
    print(f"{'ENTIDADE':<30} | {'TIPO':<15} | {'SALIÊNCIA':<10} | {'WIKIPEDIA / KNOWLEDGE GRAPH'}")
    print("-" * 85)
    
    entities_sorted = sorted(entities, key=lambda x: x.get("salience", 0), reverse=True)
    
    knowledge_graph_links = []
    
    for ent in entities_sorted[:15]:
        name = ent.get("name", "")
        ent_type = ent.get("type", "OTHER")
        salience = ent.get("salience", 0.0)
        metadata = ent.get("metadata", {})
        wiki = metadata.get("wikipedia_url", "")
        
        if wiki:
            knowledge_graph_links.append((name, wiki))
            wiki_display = wiki
        else:
            wiki_display = "-"
            
        print(f"{name:<30} | {ent_type:<15} | {salience:<10.4f} | {wiki_display}")
        
    # Local & Service Entities Summary
    print("\n📍 ENTIDADES GEOGRÁFICAS DETECTADAS (SEO Local):")
    locations = [e for e in entities if e.get("type") == "LOCATION"]
    if locations:
        for loc in locations:
            meta = loc.get("metadata", {})
            wiki = f" ({meta.get('wikipedia_url')})" if meta.get("wikipedia_url") else ""
            print(f"  • {loc.get('name')} - Saliência: {loc.get('salience', 0):.4f}{wiki}")
    else:
        print("  ⚠️ Nenhuma entidade de localização explícita com alta saliência!")
        
    # Schema.org Recommendations
    print("\n💡 RECOMENDAÇÕES PARA SCHEMA.ORG (JSON-LD 'about' e 'mentions'):")
    if knowledge_graph_links:
        print("  Adicione ao Schema.org da página para conectar ao Knowledge Graph:")
        print("  \"about\": [")
        for name, link in knowledge_graph_links[:3]:
            print(f'    {{ "@type": "Thing", "name": "{name}", "sameAs": "{link}" }},')
        print("  ]")
    else:
        print("  Nenhum link da Wikipedia retornado automaticamente. Mantenha os termos locais e do serviço em destaque.")
    print("=" * 80 + "\n")

def main():
    parser = argparse.ArgumentParser(description="Auditor SEO Google Cloud NLP para Studio Githa")
    parser.add_argument("--page", type=str, help="Slug da página para auditar (ex: limpeza-de-pele-em-bh)")
    parser.add_argument("--text", type=str, help="Texto arbitrário para auditar")
    parser.add_argument("--all", action="store_true", help="Auditar todas as páginas de serviços em SiteStudioGitha/pages/")
    
    args = parser.parse_args()
    
    if args.page:
        audit_page(args.page)
    elif args.all:
        for p in PAGES_DIR.glob("*.html"):
            if "privacy" in p.name or "teste" in p.name:
                continue
            audit_page(p.stem)
    elif args.text:
        res = analyze_document_nlp(args.text, API_KEY)
        print(json.dumps(res, indent=2, ensure_ascii=False))
    else:
        # Default test page
        audit_page("limpeza-de-pele-em-bh")

if __name__ == "__main__":
    main()
