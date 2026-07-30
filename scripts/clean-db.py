#!/usr/bin/env python3
"""
PipelineFace — Script de Limpeza do MongoDB
=============================================
Apaga o conteúdo de todas as coleções de execuções, posts e telemetria,
preservando unicamente as coleções `target_profiles` e `app_config`.
"""

import os
import sys
from pymongo import MongoClient

def clean_database():
    mongo_uri = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
    print(f"🔌 Conectando ao MongoDB em: {mongo_uri}")
    
    try:
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=3000)
        db = client["pipelineface"]
        
        # Coleções a serem mantidas intactas
        keep_collections = {"target_profiles", "app_config"}
        
        # Listar todas as coleções existentes
        all_collections = set(db.list_collection_names())
        to_clean = all_collections - keep_collections
        
        print("\n📋 Resumo da Operação:")
        print(f"  • Coleções Mantidas: {', '.join(keep_collections)}")
        if to_clean:
            print(f"  • Coleções a Serem Limpas: {', '.join(to_clean)}")
        else:
            print("  • Nenhuma coleção adicional para limpar.")
            return

        print("\n🧹 Limpando dados...")
        for col_name in to_clean:
            count = db[col_name].count_documents({})
            db[col_name].delete_many({})
            print(f"  ✅ Coleção '{col_name}': {count} documentos removidos.")

        print("\n✨ Limpeza concluída com sucesso! O banco de dados está pronto para uma execução limpa.")

    except Exception as e:
        print(f"❌ Erro ao conectar ou limpar o MongoDB: {e}")
        sys.exit(1)

if __name__ == "__main__":
    clean_database()
