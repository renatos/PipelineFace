#!/usr/bin/env python3
"""
PipelineFace Web App Backend Server
===================================
Servidor FastAPI integrando MongoDB, streaming de mídias de entrada,
galeria de frames extraídos, checklist de implementação e controle do pipeline.
"""

import asyncio
import json
import mimetypes
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from pymongo import MongoClient, ReturnDocument

# ============================================================
# Configurações de Diretórios e MongoDB
# ============================================================
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
INPUT_VIDEOS_DIR = DATA_DIR / "input" / "videos"
INPUT_IMAGES_DIR = DATA_DIR / "input" / "images"
OUTPUT_DIR = DATA_DIR / "output"
OUTPUT_FRAMES_DIR = OUTPUT_DIR / "frames"

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = "pipelineface"
COLLECTION_NAME = "seo_knowledge"

# Conexão MongoDB
client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
db = client[DB_NAME]
collection = db[COLLECTION_NAME]

# FastAPI App
app = FastAPI(title="PipelineFace Web Manager", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TEMPLATES_DIR = PROJECT_ROOT / "web" / "templates"
STATIC_DIR = PROJECT_ROOT / "web" / "static"
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
STATIC_DIR.mkdir(parents=True, exist_ok=True)

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Estado Global de Processos Ativos
active_process = {
    "name": None,  # "pipeline" | "scraper"
    "running": False,
    "started_at": None,
    "logs": []
}


# ============================================================
# Modelos Pydantic
# ============================================================
class CommentCreate(BaseModel):
    text: str
    author: Optional[str] = "Usuário"


class StatusUpdate(BaseModel):
    status: str  # "pendente" | "em_andamento" | "concluido"


class StepToggle(BaseModel):
    step_index: int


class ScraperParams(BaseModel):
    target_url: str
    only_videos: bool = False
    only_images: bool = False
    max_scrolls: int = 50


# ============================================================
# Motor de Sincronização JSON -> MongoDB
# ============================================================
def sync_json_to_mongodb() -> dict:
    """Importa todos os JSONs de data/output/ para o MongoDB presertando dados do usuário."""
    if not OUTPUT_DIR.exists():
        return {"imported": 0, "total": 0}

    json_files = list(OUTPUT_DIR.glob("*.json"))
    imported_count = 0

    for json_file in json_files:
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            basename = json_file.stem
            source_file = data.get("source_file", {})
            filename = source_file.get("filename", f"{basename}.mp4")
            filetype = source_file.get("type", "video")

            # Localizar arquivo original em input
            media_path = None
            if filetype == "video" and (INPUT_VIDEOS_DIR / filename).exists():
                media_path = INPUT_VIDEOS_DIR / filename
            elif filetype == "image" and (INPUT_IMAGES_DIR / filename).exists():
                media_path = INPUT_IMAGES_DIR / filename
            elif (INPUT_VIDEOS_DIR / filename).exists():
                media_path = INPUT_VIDEOS_DIR / filename
                filetype = "video"
            elif (INPUT_IMAGES_DIR / filename).exists():
                media_path = INPUT_IMAGES_DIR / filename
                filetype = "image"

            size_bytes = media_path.stat().st_size if media_path and media_path.exists() else 0
            media_url = f"/api/media/input/{filetype}s/{filename}" if media_path else None

            # Localizar e formatar os frames salvos
            saved_frames = []
            frames_subfolder = OUTPUT_FRAMES_DIR / basename
            if frames_subfolder.exists():
                for frame_file in sorted(frames_subfolder.glob("*.jpg")):
                    saved_frames.append({
                        "filename": frame_file.name,
                        "url": f"/api/media/frames/{basename}/{frame_file.name}"
                    })

            # Checar se já existe no MongoDB para preservar dados do usuário
            existing = collection.find_one({"basename": basename})
            user_implementation = existing.get("user_implementation", {
                "status": "pendente",
                "completed_steps": [],
                "comments": []
            }) if existing else {
                "status": "pendente",
                "completed_steps": [],
                "comments": []
            }

            doc = {
                "basename": basename,
                "input_file": {
                    "filename": filename,
                    "type": filetype,
                    "extension": source_file.get("extension", ""),
                    "media_url": media_url,
                    "duration_seconds": source_file.get("duration_seconds"),
                    "size_bytes": size_bytes
                },
                "content": {
                    "transcription": data.get("content", {}).get("transcription"),
                    "visual_description": data.get("content", {}).get("visual_description"),
                    "saved_frames": saved_frames
                },
                "seo_knowledge": data.get("seo_knowledge", {}),
                "metadata": data.get("metadata", {}),
                "user_implementation": user_implementation,
                "updated_at": datetime.now().isoformat()
            }

            collection.update_one(
                {"basename": basename},
                {"$set": doc},
                upsert=True
            )
            imported_count += 1
        except Exception as e:
            print(f"Erro ao sincronizar {json_file}: {e}")

    return {"imported": imported_count, "total": len(json_files)}


# ============================================================
# API Endpoints
# ============================================================

@app.get("/")
def read_root(request: Request):
    """Página principal da interface web."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/api/sync")
def api_sync():
    """Dispara a sincronização manual dos arquivos JSON para o MongoDB."""
    res = sync_json_to_mongodb()
    return {"status": "success", "data": res}


@app.get("/api/strategies")
def get_strategies(
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    media_type: Optional[str] = Query(None)
):
    """Lista todas as estratégias armazenadas no MongoDB com filtros."""
    query = {}
    if status:
        query["user_implementation.status"] = status
    if media_type:
        query["input_file.type"] = media_type
    if search:
        regex = re.compile(search, re.IGNORECASE)
        query["$or"] = [
            {"seo_knowledge.titulo_estrategia": regex},
            {"seo_knowledge.resumo_executivo": regex},
            {"seo_knowledge.termos_e_exemplos_usados": regex},
            {"seo_knowledge.ferramentas_e_telas_utilizadas": regex},
            {"basename": regex}
        ]

    docs = list(collection.find(query, {"_id": 0}).sort("updated_at", -1))
    return {"count": len(docs), "strategies": docs}


@app.get("/api/strategies/{basename}")
def get_strategy_detail(basename: str):
    """Retorna o detalhamento completo de uma estratégia pelo basename."""
    doc = collection.find_one({"basename": basename}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Estratégia não encontrada")
    return doc


@app.patch("/api/strategies/{basename}/step")
def toggle_step(basename: str, payload: StepToggle):
    """Alterna a marcação de concluído em um passo do tutorial."""
    doc = collection.find_one({"basename": basename})
    if not doc:
        raise HTTPException(status_code=404, detail="Estratégia não encontrada")

    user_impl = doc.get("user_implementation", {"status": "pendente", "completed_steps": [], "comments": []})
    completed = set(user_impl.get("completed_steps", []))

    if payload.step_index in completed:
        completed.remove(payload.step_index)
    else:
        completed.add(payload.step_index)

    completed_list = sorted(list(completed))
    total_steps = len(doc.get("seo_knowledge", {}).get("passo_a_passo_detalhado", []))

    # Atualizar status automaticamente se todos forem marcados
    new_status = user_impl.get("status", "pendente")
    if total_steps > 0 and len(completed_list) == total_steps:
        new_status = "concluido"
    elif len(completed_list) > 0 and new_status == "pendente":
        new_status = "em_andamento"

    collection.update_one(
        {"basename": basename},
        {"$set": {
            "user_implementation.completed_steps": completed_list,
            "user_implementation.status": new_status,
            "updated_at": datetime.now().isoformat()
        }}
    )
    return {"completed_steps": completed_list, "status": new_status}


@app.patch("/api/strategies/{basename}/status")
def update_status(basename: str, payload: StatusUpdate):
    """Atualiza o status geral da estratégia (pendente, em_andamento, concluido)."""
    valid_statuses = {"pendente", "em_andamento", "concluido"}
    if payload.status not in valid_statuses:
        raise HTTPException(status_code=400, detail="Status inválido")

    res = collection.update_one(
        {"basename": basename},
        {"$set": {
            "user_implementation.status": payload.status,
            "updated_at": datetime.now().isoformat()
        }}
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Estratégia não encontrada")

    return {"status": payload.status}


@app.post("/api/strategies/{basename}/comments")
def add_comment(basename: str, payload: CommentCreate):
    """Adiciona uma observação/comentário sobre problemas ou aprendizados na estratégia."""
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="Comentário não pode ser vazio")

    comment = {
        "id": str(uuid.uuid4())[:8],
        "text": payload.text.strip(),
        "author": payload.author or "Usuário",
        "created_at": datetime.now().isoformat()
    }

    res = collection.update_one(
        {"basename": basename},
        {"$push": {"user_implementation.comments": comment},
         "$set": {"updated_at": datetime.now().isoformat()}}
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Estratégia não encontrada")

    return comment


# ============================================================
# Streaming de Mídias de Entrada e Frames
# ============================================================

@app.get("/api/media/input/videos/{filename}")
async def stream_video(filename: str, request: Request):
    """Streaming HTTP Range de arquivos de vídeo de entrada."""
    video_path = INPUT_VIDEOS_DIR / filename
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


@app.get("/api/media/input/images/{filename}")
def serve_input_image(filename: str):
    """Serve imagens de entrada originais."""
    image_path = INPUT_IMAGES_DIR / filename
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Imagem não encontrada")
    mime, _ = mimetypes.guess_type(str(image_path))
    return FileResponse(image_path, media_type=mime or "image/jpeg")


@app.get("/api/media/frames/{basename}/{frame_name}")
def serve_frame_image(basename: str, frame_name: str):
    """Serve os frames de conteúdo extraídos."""
    frame_path = OUTPUT_FRAMES_DIR / basename / frame_name
    if not frame_path.exists():
        raise HTTPException(status_code=404, detail="Frame não encontrado")
    return FileResponse(frame_path, media_type="image/jpeg")


# ============================================================
# Controle de Subprocessos (Pipeline & Scraper)
# ============================================================

def run_process_async(command: list[str], process_name: str):
    """Executa um comando em segundo plano gravando os logs na memória."""
    global active_process
    active_process["name"] = process_name
    active_process["running"] = True
    active_process["started_at"] = datetime.now().isoformat()
    active_process["logs"] = [f"🚀 Iniciando {process_name}: {' '.join(command)}"]

    try:
        proc = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=str(PROJECT_ROOT)
        )
        for line in iter(proc.stdout.readline, ''):
            if line:
                active_process["logs"].append(line.strip())
                if len(active_process["logs"]) > 300:
                    active_process["logs"].pop(0)

        proc.stdout.close()
        proc.wait()
        active_process["logs"].append(f"✅ {process_name} finalizado com código {proc.returncode}")
        # Auto-sincronizar após pipeline rodar
        sync_json_to_mongodb()
    except Exception as e:
        active_process["logs"].append(f"❌ Erro ao executar {process_name}: {e}")
    finally:
        active_process["running"] = False


@app.post("/api/run-pipeline")
def run_pipeline(background_tasks: BackgroundTasks):
    """Dispara a execução do pipeline Python em segundo plano."""
    global active_process
    if active_process["running"]:
        raise HTTPException(status_code=400, detail=f"Processo {active_process['name']} já está em execução.")

    background_tasks.add_task(run_process_async, ["python3", "pipeline.py"], "Pipeline Python")
    return {"status": "started", "message": "Pipeline iniciado em segundo plano"}


@app.post("/api/run-scraper")
def run_scraper(payload: ScraperParams, background_tasks: BackgroundTasks):
    """Dispara a execução do scraper em segundo plano."""
    global active_process
    if active_process["running"]:
        raise HTTPException(status_code=400, detail=f"Processo {active_process['name']} já está em execução.")

    cmd = ["python3", "scraper/facebook_scraper.py", "--target", payload.target_url]
    if payload.only_videos: cmd.append("--only-videos")
    if payload.only_images: cmd.append("--only-images")
    if payload.max_scrolls: cmd.extend(["--max-scrolls", str(payload.max_scrolls)])

    background_tasks.add_task(run_process_async, cmd, "Scraper Facebook")
    return {"status": "started", "message": f"Scraper iniciado para {payload.target_url}"}


@app.get("/api/process-status")
def process_status():
    """Retorna o estado do processo ativo e logs recentes."""
    return active_process


# Executar sincronização inicial ao subir o servidor
sync_json_to_mongodb()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web.server:app", host="0.0.0.0", port=8000, reload=True)
