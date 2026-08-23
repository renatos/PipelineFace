#!/usr/bin/env python3
"""
Test script for Google Cloud Natural Language API.
Tests Entity Analysis and Content Classification on sample Studio Githa content.
"""
import os
import sys
import json
import requests
from dotenv import load_dotenv

# Load .env
load_dotenv()

API_KEY = os.getenv("GOOGLE_CLOUD_API_KEY") or os.getenv("GOOGLE_NLP_API_KEY") or os.getenv("GOOGLE_API_KEY")

sample_text = """
Limpeza de Pele em BH: Protocolo Bioregenerativo no Studio Githa.
Se você busca a melhor limpeza de pele em Belo Horizonte, no bairro Nova Suíça,
o Studio Githa oferece um tratamento facial inovador que combina extração minuciosa,
vapor de ozônio, alta frequência e renovação celular para cravos, espinhas e rejuvenescimento.
"""

def test_with_api_key(api_key: str):
    print("=" * 60)
    print("🔍 Testando Google Cloud Natural Language API com API Key...")
    print("=" * 60)
    
    url = f"https://language.googleapis.com/v1/documents:analyzeEntities?key={api_key}"
    payload = {
        "document": {
            "type": "PLAIN_TEXT",
            "content": sample_text.strip(),
            "language": "pt"
        },
        "encodingType": "UTF8"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=15)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            entities = data.get("entities", [])
            print(f"\n✅ SUCESSO! {len(entities)} entidades identificadas pelo Google:\n")
            print(f"{'ENTIDADE':<30} | {'TIPO':<15} | {'SALIÊNCIA (0-1)':<15} | {'KNOWLEDGE GRAPH / WIKIPEDIA'}")
            print("-" * 90)
            
            # Sort by salience descending
            entities_sorted = sorted(entities, key=lambda x: x.get("salience", 0), reverse=True)
            for ent in entities_sorted[:10]:
                name = ent.get("name", "")
                ent_type = ent.get("type", "OTHER")
                salience = ent.get("salience", 0.0)
                metadata = ent.get("metadata", {})
                wiki_url = metadata.get("wikipedia_url", metadata.get("mid", "-"))
                print(f"{name:<30} | {ent_type:<15} | {salience:<15.4f} | {wiki_url}")
            return True
        else:
            print(f"❌ Erro na resposta da API Google:")
            print(json.dumps(response.json(), indent=2, ensure_ascii=False))
            return False
    except Exception as e:
        print(f"❌ Erro na requisição: {e}")
        return False

if __name__ == "__main__":
    if API_KEY:
        test_with_api_key(API_KEY)
    else:
        print("⚠️ GOOGLE_NLP_API_KEY não encontrada no .env!")
        print("As credenciais encontradas no .env foram GOOGLE_CLIENT_ID e GOOGLE_CLIENT_SECRET (OAuth2).")
        sys.exit(1)
