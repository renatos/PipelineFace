"""
Media Streaming Service — PipelineFace (Clean Architecture)
===========================================================
Serviço responsável por servir imagens e realizar o streaming HTTP Range de vídeos de entrada.
"""

import mimetypes
import re
from pathlib import Path
from fastapi import HTTPException, Request
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
            raise HTTPException(status_code=404, detail="Imagem não encontrada")
        mime, _ = mimetypes.guess_type(str(image_path))
        return FileResponse(image_path, media_type=mime or "image/jpeg")

    def serve_frame_image(self, basename: str, frame_name: str):
        frame_path = self.output_frames_dir / basename / frame_name
        if not frame_path.exists():
            raise HTTPException(status_code=404, detail="Frame não encontrado")
        return FileResponse(frame_path, media_type="image/jpeg")
