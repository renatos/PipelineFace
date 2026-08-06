"""
Media Streaming Service — PipelineFace (Clean Architecture)
===========================================================
Serviço responsável por servir imagens e realizar o streaming HTTP Range de vídeos de entrada.
"""

import mimetypes
import re
from pathlib import Path
from fastapi import HTTPException, Request, Response
from fastapi.responses import FileResponse, StreamingResponse


class MediaStreamingService:
    def __init__(self, input_videos_dir: Path, input_images_dir: Path, output_frames_dir: Path):
        self.input_videos_dir = Path(input_videos_dir)
        self.input_images_dir = Path(input_images_dir)
        self.output_frames_dir = Path(output_frames_dir)

    def stream_video(self, filename: str, request: Request):
        video_path = self.input_videos_dir / filename
        if not video_path.exists():
            raise HTTPException(status_code=404, detail="Vídeo não encontrado")

        file_size = video_path.stat().st_size
        range_header = request.headers.get("range")

        if range_header:
            bytes_match = re.search(r"bytes=(\d+)-(\d*)", range_header)
            start = int(bytes_match.group(1)) if bytes_match else 0
            end = int(bytes_match.group(2)) if bytes_match and bytes_match.group(2) else file_size - 1
            end = min(end, file_size - 1)
            chunk_size = (end - start) + 1

            def iterfile():
                with open(video_path, "rb") as f:
                    f.seek(start)
                    bytes_left = chunk_size
                    while bytes_left > 0:
                        read_bytes = min(bytes_left, 64 * 1024)
                        data = f.read(read_bytes)
                        if not data:
                            break
                        bytes_left -= len(data)
                        yield data

            headers = {
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(chunk_size),
                "Content-Type": "video/mp4",
            }
            return StreamingResponse(iterfile(), status_code=206, headers=headers)

        return FileResponse(video_path, media_type="video/mp4")

    def serve_input_image(self, filename: str):
        image_path = self.input_images_dir / filename
        if not image_path.exists():
            placeholder_svg = """<svg xmlns="http://www.w3.org/2000/svg" width="400" height="400" viewBox="0 0 400 400" fill="none"><rect width="400" height="400" fill="#0f172a"/><rect x="2" y="2" width="396" height="396" rx="12" stroke="#1e293b" stroke-width="4"/><text x="50%" y="45%" dominant-baseline="middle" text-anchor="middle" fill="#94a3b8" font-family="sans-serif" font-size="14" font-weight="600">Slide / Imagem Indisponível</text><text x="50%" y="55%" dominant-baseline="middle" text-anchor="middle" fill="#64748b" font-family="sans-serif" font-size="11">Arquivo não mantido localmente</text></svg>"""
            return Response(content=placeholder_svg, media_type="image/svg+xml")
        mime, _ = mimetypes.guess_type(str(image_path))
        return FileResponse(image_path, media_type=mime or "image/jpeg")

    def serve_frame_image(self, basename: str, frame_name: str):
        frame_path = self.output_frames_dir / basename / frame_name
        if not frame_path.exists():
            raise HTTPException(status_code=404, detail="Frame não encontrado")
        return FileResponse(frame_path, media_type="image/jpeg")
