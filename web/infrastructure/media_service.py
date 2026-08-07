"""
Media Streaming Service — PipelineFace (Clean Architecture)
===========================================================
Serviço responsável por servir os frames gerados pelo pipeline em data/output/frames.

Imagens e vídeos de entrada (data/input/) são apenas insumo do pipeline e NÃO são
servidos para exibição — a UI utiliza somente as URLs originais do Facebook.
"""

from pathlib import Path
from fastapi import HTTPException
from fastapi.responses import FileResponse


def _validate_path_param(value: str):
    """Bloqueia path traversal sem restringir caracteres Unicode dos basenames do pipeline
    (nomes de pastas podem conter espaços, '·', '｜' etc., vindos dos títulos dos posts)."""
    if not value or value in (".", "..") or "/" in value or "\\" in value or "\x00" in value:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")


class MediaStreamingService:
    def __init__(self, output_frames_dir: Path):
        self.output_frames_dir = Path(output_frames_dir).resolve()

    def serve_frame_image(self, basename: str, frame_name: str):
        _validate_path_param(basename)
        _validate_path_param(frame_name)
        frame_path = (self.output_frames_dir / basename / frame_name).resolve()
        if self.output_frames_dir not in frame_path.parents:
            raise HTTPException(status_code=404, detail="Frame não encontrado")
        if not frame_path.exists():
            raise HTTPException(status_code=404, detail="Frame não encontrado")
        return FileResponse(frame_path, media_type="image/jpeg")
