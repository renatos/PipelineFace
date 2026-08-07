"""
Sync Knowledge Use Case — PipelineFace (Clean Architecture)
===========================================================
Caso de uso responsável por ler os arquivos JSON gerados em data/output/,
mapear para entidades de domínio e salvar/atualizar no repositório.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

from web.domain.entities import (
    Strategy, InputFile, Content, SavedFrame, SEOKnowledge, UserImplementation
)
from web.domain.repositories import AbstractStrategyRepository


class SyncKnowledgeUseCase:
    def __init__(
        self,
        repository: AbstractStrategyRepository,
        output_dir: Path,
        output_frames_dir: Path
    ):
        self.repository = repository
        self.output_dir = Path(output_dir)
        self.output_frames_dir = Path(output_frames_dir)

    def execute(self) -> Dict[str, Any]:
        if not self.output_dir.exists():
            return {"imported": 0, "total": 0}

        json_files = list(self.output_dir.glob("*.json"))
        imported_count = 0

        for json_file in json_files:
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    raw_data = json.load(f)

                basename = json_file.stem
                source_file = raw_data.get("source_file", {})
                filename = source_file.get("filename", f"{basename}.mp4")
                filetype = source_file.get("type", "video")

                # A UI exibe somente URLs do Facebook — arquivos locais são apenas entrada do pipeline
                size_bytes = source_file.get("size_bytes")
                media_url = None

                # Frames salvos
                saved_frames = []
                frames_subfolder = self.output_frames_dir / basename
                if frames_subfolder.exists():
                    for frame_file in sorted(frames_subfolder.glob("*.jpg")):
                        saved_frames.append(SavedFrame(
                            filename=frame_file.name,
                            url=f"/api/media/frames/{basename}/{frame_file.name}"
                        ))

                # Preservar estado do usuário se já existir
                existing = self.repository.find_by_basename(basename)
                user_impl = existing.user_implementation if existing else UserImplementation()

                seo_data = raw_data.get("seo_knowledge", {})
                strategy = Strategy(
                    basename=basename,
                    input_file=InputFile(
                        filename=filename,
                        type=filetype,
                        extension=source_file.get("extension", ""),
                        url=source_file.get("url"),
                        media_url=media_url,
                        duration_seconds=source_file.get("duration_seconds"),
                        size_bytes=size_bytes
                    ),
                    content=Content(
                        transcription=raw_data.get("content", {}).get("transcription"),
                        visual_description=raw_data.get("content", {}).get("visual_description"),
                        saved_frames=saved_frames
                    ),
                    seo_knowledge=SEOKnowledge(
                        titulo_estrategia=seo_data.get("titulo_estrategia"),
                        resumo_executivo=seo_data.get("resumo_executivo"),
                        passo_a_passo_detalhado=seo_data.get("passo_a_passo_detalhado", []),
                        ferramentas_e_telas_utilizadas=seo_data.get("ferramentas_e_telas_utilizadas", []),
                        termos_e_exemplos_usados=seo_data.get("termos_e_exemplos_usados", []),
                        aplicacao_no_negocio=seo_data.get("aplicacao_no_negocio"),
                        conceitos_mencionados=seo_data.get("conceitos_mencionados", [])
                    ),
                    metadata=raw_data.get("metadata", {}),
                    user_implementation=user_impl,
                    updated_at=datetime.now().isoformat()
                )

                self.repository.save_or_update(strategy)
                imported_count += 1
            except Exception as e:
                print(f"Erro no SyncKnowledgeUseCase para {json_file}: {e}")

        # Se importou estratégias novas de alta qualidade, dispara a consolidação do playbook em segundo plano
        if imported_count > 0:
            try:
                import subprocess
                subprocess.Popen(["python3", "scripts/build_seo_playbook.py"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                print("⚙️  Playbook consolidado disparado automaticamente em segundo plano!")
            except Exception as e:
                print(f"Erro ao disparar build_seo_playbook: {e}")

        return {"imported": imported_count, "total": len(json_files)}
