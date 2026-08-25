#!/usr/bin/env python3
"""
GEO-Tagging & Image SEO Optimizer for Studio Githa (Google Business Profile & Web).
Downloads and embeds GPS Coordinates (Latitude, Longitude), Location Metadata, Business Details,
and Copyright into photos for Google Business Profile and Website SEO.

Usage:
  python3 scripts/SEO/geotag_images.py --team-photo
  python3 scripts/SEO/geotag_images.py --download-all
"""
import os
import sys
import argparse
from pathlib import Path
from PIL import Image, ExifTags
import requests

LATITUDE = -19.9327
LONGITUDE = -43.9803
ALTITUDE = 850.0  # meters in BH

BUSINESS_NAME = "Studio Githa"
BUSINESS_ADDRESS = "Rua Juraci, 88 - Sala 102 - Nova Suíça, Belo Horizonte - MG, CEP 30421-181"
WEBSITE_URL = "https://studiogitha.com"

BASE_OUTPUT_DIR = Path("/home/renato/dev/PipelineFace/data/geotagged_images")
GBP_DIR = BASE_OUTPUT_DIR / "google_meu_negocio"

CLINIC_IMAGES = [
    {
        "url": "https://studiogitha.com/wp-content/uploads/2025/10/IMG_3632.jpg",
        "category": "interior",
        "filename": "ambiente-studio-githa-sala-estetica-nova-suica-bh.jpg",
        "title": "Ambiente e Sala de Atendimento Studio Githa",
        "desc": "Espaço privativo, acolhedor e climatizado do Studio Githa na Rua Juraci, 88 - Nova Suíça, Belo Horizonte - MG."
    },
    {
        "url": "https://studiogitha.com/wp-content/uploads/2025/10/Prancheta-5.jpg",
        "category": "servicos",
        "filename": "limpeza-de-pele-bioregenerativa-studio-githa-bh.jpg",
        "title": "Limpeza de Pele Bioregenerativa - Studio Githa",
        "desc": "Protocolo facial de limpeza de pele com extração sem dor, vapor de ozônio e alta frequência no Nova Suíça em BH."
    },
    {
        "url": "https://studiogitha.com/wp-content/uploads/2025/10/Prancheta-3.jpg",
        "category": "servicos",
        "filename": "design-de-sobrancelhas-visagismo-studio-githa-bh.jpg",
        "title": "Design de Sobrancelhas com Visagismo - Studio Githa",
        "desc": "Modelagem anatômica e visagismo personalizado de sobrancelhas no Studio Githa em Belo Horizonte."
    },
    {
        "url": "https://studiogitha.com/wp-content/uploads/2025/10/Prancheta-2.jpg",
        "category": "servicos",
        "filename": "brow-lamination-nutricao-studio-githa-bh.jpg",
        "title": "Brow Lamination e Alinhamento de Fios - Studio Githa",
        "desc": "Procedimento de Brow Lamination com aminoácidos e queratina no Studio Githa, Nova Suíça BH."
    },
    {
        "url": "https://studiogitha.com/wp-content/uploads/2025/10/Prancheta-4.jpg",
        "category": "servicos",
        "filename": "extensao-de-cilios-fio-a-fio-studio-githa-bh.jpg",
        "title": "Extensão de Cílios Fio a Fio - Studio Githa",
        "desc": "Aplicação de extensão de cílios com isolamento seguro e fios ultrafinos de seda no Studio Githa."
    },
    {
        "url": "https://studiogitha.com/wp-content/uploads/2025/10/Prancheta-6.jpg",
        "category": "servicos",
        "filename": "micropigmentacao-labial-sobrancelhas-studio-githa-bh.jpg",
        "title": "Micropigmentação Labial e de Sobrancelhas - Studio Githa",
        "desc": "Harmonização e realce semipermanente com pigmentos orgânicos biocompatíveis no Nova Suíça em BH."
    },
    {
        "url": "https://studiogitha.com/wp-content/uploads/2025/10/Prancheta-7.jpg",
        "category": "servicos",
        "filename": "microagulhamento-drug-delivery-studio-githa-bh.jpg",
        "title": "Microagulhamento e Peeling Facial - Studio Githa",
        "desc": "Estímulo de colágeno e clareamento de melasma com drug delivery e peelings personalizados no Studio Githa."
    },
    {
        "url": "https://studiogitha.com/wp-content/uploads/2025/10/Prancheta-8.jpg",
        "category": "servicos",
        "filename": "massagem-facial-drenagem-lifting-studio-githa-bh.jpg",
        "title": "Massagem Facial e Drenagem Lifting - Studio Githa",
        "desc": "Tônus muscular facial, relaxamento e desintoxicação linfática no Studio Githa em Belo Horizonte."
    }
]

def decimal_to_dms_floats(decimal_val: float) -> tuple[float, float, float]:
    abs_val = abs(decimal_val)
    degrees = int(abs_val)
    minutes_float = (abs_val - degrees) * 60.0
    minutes = int(minutes_float)
    seconds = round((minutes_float - minutes) * 60.0, 3)
    return (float(degrees), float(minutes), float(seconds))

def inject_geotag_metadata(img: Image.Image, title: str, description: str) -> Image.Image:
    if img.mode != "RGB":
        img = img.convert("RGB")
        
    exif = img.getexif()
    artist_info = f"{BUSINESS_NAME} - {BUSINESS_ADDRESS}"
    comment_info = f"{title} | {description} | {WEBSITE_URL}"
    
    exif[0x010e] = comment_info
    exif[0x010f] = "Studio Githa Official Camera"
    exif[0x0110] = "Studio Githa Lens"
    exif[0x0131] = "Studio Githa GEO Optimizer v2.0"
    exif[0x013b] = artist_info
    exif[0x8298] = f"Copyright (c) 2026 {BUSINESS_NAME}. All rights reserved."
    
    gps_ifd = exif.get_ifd(ExifTags.IFD.GPSInfo)
    lat_ref = "S" if LATITUDE < 0 else "N"
    lon_ref = "W" if LONGITUDE < 0 else "E"
    
    gps_ifd[1] = lat_ref
    gps_ifd[2] = decimal_to_dms_floats(LATITUDE)
    gps_ifd[3] = lon_ref
    gps_ifd[4] = decimal_to_dms_floats(LONGITUDE)
    gps_ifd[5] = 0
    gps_ifd[6] = ALTITUDE
    gps_ifd[18] = "WGS-84"
    
    return img, exif

def save_geotagged(img: Image.Image, exif, output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, "jpeg", quality=95, exif=exif, optimize=True)
    print(f"  ✅ Salvo: {output_path.name} ({output_path.stat().st_size / 1024:.1f} KB)")

def process_all_clinic_images():
    print("=" * 70)
    print("🚀 PROCESSANDO PACOTE DE FOTOS PARA O GOOGLE MEU NEGÓCIO")
    print(f"📍 Coordenadas: Lat {LATITUDE}, Lon {LONGITUDE} (Nova Suíça, Belo Horizonte)")
    print("=" * 70)
    
    # 1. Process Team Photo
    team_input = Path("/home/renato/.gemini/antigravity/brain/92d76265-2c62-4789-b27c-b84ff5aecd8b/.user_uploaded/media_1787655431237.png")
    if team_input.exists():
        print("\n👥 1. Categoria: EQUIPE / NO TRABALHO")
        team_out = GBP_DIR / "equipe" / "equipe-studio-githa-estetica-sobrancelhas-bh.jpg"
        img = Image.open(team_input)
        title = "Equipe de Especialistas do Studio Githa"
        desc = "Profissionais de estética facial e design de sobrancelhas em atendimento no Studio Githa, Nova Suíça, Belo Horizonte."
        img_rgb, exif = inject_geotag_metadata(img, title, desc)
        save_geotagged(img_rgb, exif, team_out)
        
    # 2. Download and Process Other Clinic Assets
    print("\n🏢 2. Categorias: INTERIOR & PROCEDIMENTOS / SERVIÇOS")
    headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}
    
    for item in CLINIC_IMAGES:
        category = item["category"]
        filename = item["filename"]
        out_file = GBP_DIR / category / filename
        url = item["url"]
        
        try:
            print(f"⬇️  Baixando: {url.split('/')[-1]}...")
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code == 200:
                from io import BytesIO
                raw_img = Image.open(BytesIO(resp.content))
                img_rgb, exif = inject_geotag_metadata(raw_img, item["title"], item["desc"])
                save_geotagged(img_rgb, exif, out_file)
            else:
                print(f"  ❌ Erro ao baixar {url}: status {resp.status_code}")
        except Exception as e:
            print(f"  ❌ Falha: {e}")
            
    print("\n" + "=" * 70)
    print(f"🎉 PACOTE COMPLETO GERADO EM: {GBP_DIR}")
    print("=" * 70)

def main():
    parser = argparse.ArgumentParser(description="Otimizador de Metadados e GEO-Tagging de Fotos para Studio Githa")
    parser.add_argument("--team-photo", action="store_true", help="Processar apenas a foto da equipe")
    parser.add_argument("--download-all", action="store_true", help="Baixar e processar todas as fotos do estúdio para o Google Meu Negócio")
    
    args = parser.parse_args()
    
    if args.download_all:
        process_all_clinic_images()
    elif args.team_photo:
        team_input = Path("/home/renato/.gemini/antigravity/brain/92d76265-2c62-4789-b27c-b84ff5aecd8b/.user_uploaded/media_1787655431237.png")
        team_out = GBP_DIR / "equipe" / "equipe-studio-githa-estetica-sobrancelhas-bh.jpg"
        img = Image.open(team_input)
        title = "Equipe de Especialistas do Studio Githa"
        desc = "Profissionais de estética facial e design de sobrancelhas em atendimento no Studio Githa, Nova Suíça, Belo Horizonte."
        img_rgb, exif = inject_geotag_metadata(img, title, desc)
        save_geotagged(img_rgb, exif, team_out)
    else:
        process_all_clinic_images()

if __name__ == "__main__":
    main()
