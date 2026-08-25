#!/usr/bin/env python3
"""
Batch Geotag, Upload to WordPress, and Update Site Pages.
Processes all procedure images, injects GPS coordinates of Nova Suíça/BH,
uploads to WordPress Media Library, and replaces image URLs across all HTML pages.

Usage:
  python3 scripts/SEO/batch_geotag_and_deploy.py
"""
import os
import sys
import json
import re
from pathlib import Path
from io import BytesIO
import requests
from PIL import Image

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from scripts.SEO.geotag_images import inject_geotag_metadata, save_geotagged
from scripts.SEO.upload_wp_media import upload_image_to_wordpress
PAGES_DIR = BASE_DIR / "SiteStudioGitha" / "pages"
OUTPUT_DIR = BASE_DIR / "data" / "geotagged_images"

PROCEDURE_IMAGES = [
    {
        "old_url": "https://studiogitha.com/wp-content/uploads/2025/10/Prancheta-2.jpg",
        "old_pattern": r"https://studiogitha\.com/wp-content/uploads/2025/10/Prancheta-2\.jpg",
        "filename": "brow-lamination-nutricao-studio-githa-bh.jpg",
        "title": "Brow Lamination e Alinhamento de Fios - Studio Githa",
        "alt": "Brow Lamination e alinhamento de sobrancelhas no Studio Githa em Belo Horizonte",
        "desc": "Procedimento de Brow Lamination com aminoácidos e queratina no Studio Githa, Nova Suíça BH."
    },
    {
        "url": "https://studiogitha.com/wp-content/uploads/2025/10/Prancheta-3.jpg",
        "old_pattern": r"https://studiogitha\.com/wp-content/uploads/2025/10/Prancheta-3\.jpg",
        "filename": "design-de-sobrancelhas-visagismo-studio-githa-bh.jpg",
        "title": "Design de Sobrancelhas com Visagismo - Studio Githa",
        "alt": "Design de sobrancelhas com visagismo personalizado no Studio Githa no bairro Nova Suíça",
        "desc": "Modelagem anatômica e visagismo personalizado de sobrancelhas no Studio Githa em Belo Horizonte."
    },
    {
        "url": "https://studiogitha.com/wp-content/uploads/2025/10/Prancheta-4.jpg",
        "old_pattern": r"https://studiogitha\.com/wp-content/uploads/2025/10/Prancheta-4\.jpg",
        "filename": "extensao-de-cilios-fio-a-fio-studio-githa-bh.jpg",
        "title": "Extensão de Cílios Fio a Fio - Studio Githa",
        "alt": "Extensão de cílios fio a fio e volume russo no Studio Githa em Belo Horizonte",
        "desc": "Aplicação de extensão de cílios com isolamento seguro e fios ultrafinos de seda no Studio Githa."
    },
    {
        "url": "https://studiogitha.com/wp-content/uploads/2025/10/Prancheta-5.jpg",
        "old_pattern": r"https://studiogitha\.com/wp-content/uploads/2025/10/Prancheta-5\.jpg",
        "filename": "limpeza-de-pele-bioregenerativa-studio-githa-bh.jpg",
        "title": "Limpeza de Pele Bioregenerativa - Studio Githa",
        "alt": "Limpeza de pele profunda bioregenerativa sem dor no Studio Githa em BH",
        "desc": "Protocolo facial de limpeza de pele com extração sem dor, vapor de ozônio e alta frequência no Nova Suíça em BH."
    },
    {
        "url": "https://studiogitha.com/wp-content/uploads/2025/10/Prancheta-6.jpg",
        "old_pattern": r"https://studiogitha\.com/wp-content/uploads/2025/10/Prancheta-6\.jpg",
        "filename": "micropigmentacao-labial-sobrancelhas-studio-githa-bh.jpg",
        "title": "Micropigmentação Labial e de Sobrancelhas - Studio Githa",
        "alt": "Micropigmentação labial e de sobrancelhas no Studio Githa em Belo Horizonte",
        "desc": "Harmonização e realce semipermanente com pigmentos orgânicos biocompatíveis no Nova Suíça em BH."
    },
    {
        "url": "https://studiogitha.com/wp-content/uploads/2025/10/Prancheta-7.jpg",
        "old_pattern": r"https://studiogitha\.com/wp-content/uploads/2025/10/Prancheta-7\.jpg",
        "filename": "microagulhamento-drug-delivery-studio-githa-bh.jpg",
        "title": "Microagulhamento e Peeling Facial - Studio Githa",
        "alt": "Microagulhamento com drug delivery e peeling químico no Studio Githa em BH",
        "desc": "Estímulo de colágeno e clareamento de melasma com drug delivery e peelings personalizados no Studio Githa."
    },
    {
        "url": "https://studiogitha.com/wp-content/uploads/2025/10/Prancheta-8.jpg",
        "old_pattern": r"https://studiogitha\.com/wp-content/uploads/2025/10/Prancheta-8\.jpg",
        "filename": "massagem-facial-drenagem-lifting-studio-githa-bh.jpg",
        "title": "Massagem Facial e Drenagem Lifting - Studio Githa",
        "alt": "Massagem facial com efeito lifting e drenagem linfática no Studio Githa em BH",
        "desc": "Tônus muscular facial, relaxamento e desintoxicação linfática no Studio Githa em Belo Horizonte."
    },
    {
        "url": "https://studiogitha.com/wp-content/uploads/2025/10/Prancheta-9.jpg",
        "old_pattern": r"https://studiogitha\.com/wp-content/uploads/2025/10/Prancheta-9\.jpg",
        "filename": "lash-lifting-curvatura-cilios-studio-githa-bh.jpg",
        "title": "Lash Lifting e Curvatura Natural de Cílios - Studio Githa",
        "alt": "Lash lifting e nutrição de cílios com queratina no Studio Githa em Belo Horizonte",
        "desc": "Tratamento de curvatura e botox capilar para cílios naturais no Studio Githa em BH."
    }
]

def run_batch():
    headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}
    mapping = {}
    
    print("=" * 70)
    print("🚀 INICIANDO PROCESSAMENTO EM LOTE DE IMAGENS GEOTAGUEADAS")
    print("=" * 70)
    
    for item in PROCEDURE_IMAGES:
        src_url = item.get("url") or item.get("old_url")
        filename = item["filename"]
        out_file = OUTPUT_DIR / filename
        
        print(f"\n📸 [1/3] Baixando e Geotagueando: {filename}...")
        resp = requests.get(src_url, headers=headers, timeout=15)
        if resp.status_code != 200:
            print(f"❌ Erro ao baixar {src_url}")
            continue
            
        img = Image.open(BytesIO(resp.content))
        img_rgb, exif = inject_geotag_metadata(img, item["title"], item["desc"])
        save_geotagged(img_rgb, exif, out_file)
        
        print(f"⬆️  [2/3] Enviando para WordPress Media Library...")
        res = upload_image_to_wordpress(out_file, alt_text=item["alt"], title=item["title"])
        if res and res.get("url"):
            new_url = res["url"]
            mapping[item["old_pattern"]] = new_url
            print(f"✅ Mapeado: {filename} -> {new_url}")
        else:
            print(f"⚠️ Falha no upload de {filename}")

    # Replace URLs in all HTML files
    print("\n" + "=" * 70)
    print("📝 [3/3] Atualizando referências de imagens nas páginas locais...")
    print("=" * 70)
    
    for html_file in PAGES_DIR.glob("*.html"):
        content = html_file.read_text(encoding="utf-8")
        modified = False
        
        for old_pattern, new_url in mapping.items():
            if re.search(old_pattern, content):
                content = re.sub(old_pattern, new_url, content)
                modified = True
                
        if modified:
            html_file.write_text(content, encoding="utf-8")
            print(f"  ✨ {html_file.name} atualizado com novas URLs de imagens!")
            
    print("\n🎉 Todas as imagens foram geotagueadas, enviadas e sincronizadas localmente!")

if __name__ == "__main__":
    run_batch()
