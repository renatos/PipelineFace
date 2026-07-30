#!/usr/bin/env python3
"""
PipelineFace — Pipeline de Extração de Conhecimento 100% Python
===============================================================
Processa vídeos e imagens coletados com telemetria via Webhooks e relatórios de erro.
"""

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import traceback
import urllib.parse
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path

# Configurações do Rich para logs visuais
try:
    from rich.console import Console
    console = Console()
except ImportError:
    class Console:
        def print(self, *args, **kwargs):
            text = args[0] if args else ""
            clean = re.sub(r'\[.*?\]', '', str(text))
            print(clean)
        def log(self, *args, **kwargs):
            self.print(*args, **kwargs)
    console = Console()

DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parent

# Fallbacks padrão — usados quando o MongoDB não está disponível
_ENV_DEFAULTS = {
    "whisper_url":  os.environ.get("WHISPER_URL",  "http://localhost:9000/asr"),
    "ollama_url":   os.environ.get("OLLAMA_URL",   "http://localhost:11434/api/chat"),
    "webhook_url":  os.environ.get("WEBHOOK_URL",  "http://localhost:8000/api/webhooks/execution-event"),
    "vision_model": os.environ.get("VISION_MODEL", "moondream"),
    "text_model":   os.environ.get("TEXT_MODEL",   "qwen2.5:3b"),
    "whisper_model":os.environ.get("WHISPER_MODEL","base"),
    "fps_frame_extraction": "1/10",
    "max_ocr_frames": "3",
}

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".webm", ".mkv"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}


def _get_mongo_config() -> dict:
    """Lê app_config do MongoDB. Retorna dict vazio se não conseguir conectar."""
    try:
        from pymongo import MongoClient
        mongo_uri = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=1500)
        docs = list(client["pipelineface"]["app_config"].find({}, {"_id": 0, "key": 1, "value": 1}))
        return {d["key"]: d["value"] for d in docs}
    except Exception:
        return {}


def send_telemetry_event(
    run_id: str,
    step: str,
    status: str = "info",
    filename: str = None,
    message: str = "",
    metrics: dict = None,
    error_details: str = None,
    webhook_url: str = None
):
    """Envia um evento de telemetria ou log de erro para a API Web (Webhook)."""
    target_url = webhook_url or _ENV_DEFAULTS["webhook_url"]
    try:
        payload = {
            "run_id": run_id,
            "source": "pipeline",
            "step": step,
            "status": status,
            "filename": filename,
            "message": message,
            "metrics": metrics or {},
            "error_details": error_details
        }
        req_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            target_url,
            data=req_data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            pass
    except Exception:
        pass  # Fallback se a Web API não estiver rodando


class KnowledgePipeline:
    def __init__(
        self,
        project_root: Path = DEFAULT_PROJECT_ROOT,
        whisper_url: str = None,
        ollama_url: str = None,
    ):
        self.project_root = Path(project_root)
        self.run_id = str(uuid.uuid4())[:8]

        # Carregar config do MongoDB, com fallback para env/defaults
        cfg = _get_mongo_config()
        self.whisper_url  = whisper_url  or cfg.get("whisper_url",  _ENV_DEFAULTS["whisper_url"])
        self.ollama_url   = ollama_url   or cfg.get("ollama_url",   _ENV_DEFAULTS["ollama_url"])
        self.webhook_url  = cfg.get("webhook_url",  _ENV_DEFAULTS["webhook_url"])
        self.vision_model = cfg.get("vision_model", _ENV_DEFAULTS["vision_model"])
        self.text_model   = cfg.get("text_model",   _ENV_DEFAULTS["text_model"])
        self.whisper_model = cfg.get("whisper_model", _ENV_DEFAULTS["whisper_model"])
        self.fps_extraction = cfg.get("fps_frame_extraction", _ENV_DEFAULTS["fps_frame_extraction"])
        self.max_ocr_frames = int(cfg.get("max_ocr_frames", _ENV_DEFAULTS["max_ocr_frames"]))

        self.input_videos_dir = self.project_root / "data" / "input" / "videos"
        self.input_images_dir = self.project_root / "data" / "input" / "images"
        self.output_dir = self.project_root / "data" / "output"
        self.output_frames_dir = self.output_dir / "frames"
        self.processing_audio_dir = self.project_root / "data" / "processing" / "audio"
        self.processing_frames_dir = self.project_root / "data" / "processing" / "frames"

        for d in [
            self.input_videos_dir,
            self.input_images_dir,
            self.output_dir,
            self.output_frames_dir,
            self.processing_audio_dir,
            self.processing_frames_dir,
        ]:
            d.mkdir(parents=True, exist_ok=True)

    def get_mongo_db(self):
        try:
            from pymongo import MongoClient
            mongo_uri = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
            client = MongoClient(mongo_uri, serverSelectionTimeoutMS=2000)
            return client["pipelineface"]
        except Exception:
            return None

    def get_original_url(self, filename: str, basename: str) -> str:
        # 1. Tentar extrair o post_id diretamente do padrão do arquivo "Vídeo_POSTID.mp4"
        post_id_match = re.search(r'(?:Vídeo_|foto_|post_)?(\d{10,20})', filename)
        target_post_id = post_id_match.group(1) if post_id_match else None

        db = self.get_mongo_db()
        if db is not None:
            try:
                # Buscar na coleção profile_posts por post_id ou mídias contidas nele
                if target_post_id:
                    post_doc = db["profile_posts"].find_one({"post_id": target_post_id})
                    if post_doc and post_doc.get("post_url"):
                        return post_doc["post_url"]

                url_hash = basename.replace("fb_", "")
                doc = db["download_history"].find_one({
                    "$or": [
                        {"filename": filename},
                        {"url_hash": url_hash},
                        {"url_hash": basename}
                    ]
                })
                if doc and doc.get("url"):
                    return doc["url"]
            except Exception:
                pass

        # 2. Fallback: consultar metadados salvos em data/input/metadata
        metadata_dir = self.project_root / "data" / "input" / "metadata"
        if metadata_dir.exists():
            for meta_file in metadata_dir.glob("*.json"):
                if meta_file.name == "download_history.json":
                    continue
                try:
                    with open(meta_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    for item in data.get("videos", []) + data.get("images", []):
                        item_url = item.get("url", "")
                        if item_url:
                            u_hash = hashlib.md5(item_url.encode()).hexdigest()[:12]
                            if filename == f"fb_{u_hash}.jpg" or filename == f"fb_{u_hash}.mp4" or u_hash in basename:
                                return item_url
                except Exception:
                    pass

        # 3. Fallback: se for uma URL/ID numérica direta do Facebook
        if target_post_id:
            return f"https://www.facebook.com/reel/{target_post_id}"

        return None

    def get_processed_basenames(self) -> set[str]:
        processed = set()
        db = self.get_mongo_db()
        if db is not None:
            try:
                for doc in db["seo_knowledge"].find({}, {"basename": 1}):
                    if "basename" in doc:
                        processed.add(doc["basename"])
                if processed:
                    return processed
            except Exception:
                pass

        if self.output_dir.exists():
            for f in self.output_dir.glob("*.json"):
                processed.add(f.stem)
        return processed

    def get_pending_files(self) -> list[dict]:
        processed = self.get_processed_basenames()
        pending = []

        if self.input_videos_dir.exists():
            for f in self.input_videos_dir.iterdir():
                if f.is_file() and f.suffix.lower() in VIDEO_EXTENSIONS:
                    if f.stem not in processed:
                        pending.append({
                            "path": f, "filename": f.name, "basename": f.stem, "type": "video", "ext": f.suffix.lower()
                        })

        if self.input_images_dir.exists():
            for f in self.input_images_dir.iterdir():
                if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS:
                    if f.stem not in processed:
                        pending.append({
                            "path": f, "filename": f.name, "basename": f.stem, "type": "image", "ext": f.suffix.lower()
                        })

        return sorted(pending, key=lambda x: x["filename"])

    def extract_audio_and_frames(self, video_path: Path, basename: str) -> dict:
        audio_path = self.processing_audio_dir / f"{basename}.wav"
        video_frames_dir = self.processing_frames_dir / basename
        video_frames_dir.mkdir(parents=True, exist_ok=True)

        cmd_audio = [
            "ffmpeg", "-y", "-i", str(video_path),
            "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
            str(audio_path)
        ]
        try:
            subprocess.run(cmd_audio, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=300)
        except Exception as e:
            console.print(f"[yellow]⚠️  Falha ao extrair áudio: {e}[/yellow]")
            audio_path = None

        cmd_frames = [
            "ffmpeg", "-y", "-i", str(video_path),
            "-vf", "fps=1/10,scale=720:-1", "-q:v", "3",
            str(video_frames_dir / "frame_%04d.jpg")
        ]
        try:
            subprocess.run(cmd_frames, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=300)
        except Exception as e:
            console.print(f"[red]❌ Erro ao extrair frames: {e}[/red]")

        duration = 0
        cmd_probe = [
            "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
            "-of", "csv=p=0", str(video_path)
        ]
        try:
            res = subprocess.run(cmd_probe, capture_output=True, text=True, timeout=5)
            duration = float(res.stdout.strip()) if res.stdout.strip() else 0
        except Exception:
            pass

        frame_paths = sorted([p for p in video_frames_dir.glob("*.jpg")])

        return {
            "audio_path": audio_path,
            "frames_dir": video_frames_dir,
            "frame_paths": frame_paths,
            "duration_seconds": round(duration)
        }

    def transcribe_audio_whisper(self, audio_path: Path, filename: str) -> str:
        if not audio_path or not audio_path.exists():
            return "[Sem áudio extraído para transcrição]"

        try:
            with open(audio_path, "rb") as f:
                audio_bytes = f.read()

            boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
            body = (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="audio_file"; filename="{filename}.wav"\r\n'
                f"Content-Type: audio/wav\r\n\r\n"
            ).encode("utf-8") + audio_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")

            url = f"{self.whisper_url}?encode=true&task=transcribe&language=pt&output=json"
            req = urllib.request.Request(
                url,
                data=body,
                headers={
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                    "Content-Length": str(len(body))
                },
                method="POST"
            )

            with urllib.request.urlopen(req, timeout=300) as resp:
                res_json = json.loads(resp.read().decode("utf-8"))
                return res_json.get("text", "").strip()
        except Exception as e:
            console.print(f"[red]❌ Erro na transcrição Whisper: {e}[/red]")
            return f"[Erro Whisper: {e}]"

    def query_ollama(self, model: str, prompt: str, image_path: Path = None, system_prompt: str = None, json_format: bool = False) -> str:
        # Se for modelo de visão com imagem, usar o endpoint /api/generate (que funciona confiavelmente com Moondream)
        if image_path and image_path.exists():
            with open(image_path, "rb") as img_f:
                img_b64 = base64.b64encode(img_f.read()).decode("utf-8")
            payload = {
                "model": model,
                "prompt": prompt,
                "images": [img_b64],
                "stream": False,
                "options": {"temperature": 0.2}
            }
            generate_url = self.ollama_url.replace("/api/chat", "/api/generate")
            req_data = json.dumps(payload).encode("utf-8")
            max_retries = 3
            last_error = None
            for attempt in range(1, max_retries + 1):
                try:
                    req = urllib.request.Request(
                        generate_url,
                        data=req_data,
                        headers={"Content-Type": "application/json"},
                        method="POST"
                    )
                    with urllib.request.urlopen(req, timeout=600) as resp:
                        res = json.loads(resp.read().decode("utf-8"))
                        return res.get("response", "").strip()
                except Exception as e:
                    last_error = e
                    time.sleep(3 * attempt)
            console.print(f"[red]❌ Erro na requisição de visão ao Ollama ({model}): {last_error}[/red]")
            return ""

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0.2}
        }
        if json_format:
            payload["format"] = "json"

        req_data = json.dumps(payload).encode("utf-8")
        max_retries = 3
        last_error = None

        for attempt in range(1, max_retries + 1):
            try:
                req = urllib.request.Request(
                    self.ollama_url,
                    data=req_data,
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=600) as resp:
                    res = json.loads(resp.read().decode("utf-8"))
                    return res.get("message", {}).get("content", "").strip()
            except Exception as e:
                last_error = e
                console.print(f"[yellow]⚠️ Tentativa {attempt}/{max_retries} falhou para Ollama ({model}): {e}. Tentando novamente...[/yellow]")
                time.sleep(5 * attempt)

        console.print(f"[red]❌ Erro na requisição ao Ollama ({model}): {last_error}[/red]")
        raise RuntimeError(f"Ollama API ({model}) falhou após {max_retries} tentativas: {last_error}")

    def is_presenter_face(self, image_path: Path) -> bool:
        """Detecta de forma determinística com OpenCV se o frame é um rosto de apresentador em primeiro plano."""
        try:
            import cv2
            img = cv2.imread(str(image_path))
            if img is None: return False
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
            faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(90, 90))
            
            img_area = img.shape[0] * img.shape[1]
            for (x, y, w, h) in faces:
                face_area = w * h
                # Se o rosto ocupa mais de 10% do frame, é uma pessoa/apresentador (talking head)!
                if (face_area / img_area) > 0.10:
                    return True
            return False
        except Exception:
            return False

    def analyze_and_filter_frames(self, frame_paths: list[Path], target_frames_dir: Path) -> tuple[list[dict], list[str]]:
        descriptions = []
        saved_frame_paths = []

        if not frame_paths:
            return descriptions, saved_frame_paths

        max_ocr_frames = 3
        if len(frame_paths) <= max_ocr_frames:
            selected_ocr_frames = set(frame_paths)
        else:
            step = len(frame_paths) // max_ocr_frames
            selected_ocr_frames = set(frame_paths[i * step] for i in range(max_ocr_frames))

        for frame_path in frame_paths:
            frame_filename = frame_path.name

            # 1. Checagem determinística OpenCV (ignora rostos de apresentadores)
            if self.is_presenter_face(frame_path):
                console.print(f"  [yellow]🙈 Frame ignorado (rosto de apresentador detectado via OpenCV): {frame_filename}[/yellow]")
                continue

            # 2. Checagem semântica Moondream (garante que contém tela/slide/sistema/texto)
            prompt_classify = (
                "Describe this image in detail. Is it showing a computer screen, laptop screen, website, slide, graph, or text on screen?"
            )
            desc_classify = self.query_ollama(self.vision_model, prompt_classify, image_path=frame_path).lower()
            
            keywords = [
                "screen", "display", "laptop", "computer", "website", "webpage", "slide",
                "graph", "google", "search", "text", "page", "table", "code", "menu", "list",
                "tela", "grafico", "busca", "sistema", "site", "navegador", "pagina"
            ]
            is_screen = any(kw in desc_classify for kw in keywords)
            if not is_screen:
                console.print(f"  [yellow]🙈 Frame ignorado (sem tela ou gráfico de conteúdo): {frame_filename}[/yellow]")
                continue

            target_frames_dir.mkdir(parents=True, exist_ok=True)
            dest = target_frames_dir / frame_filename
            shutil.copy2(frame_path, dest)
            saved_frame_paths.append(str(dest))

            if frame_path in selected_ocr_frames:
                prompt_ocr = (
                    "Transcreva todo o texto visível nesta imagem. "
                    "Identifique gráficos de SEO, buscas do Google ou telas de sistemas. Responda em português."
                )
                desc = self.query_ollama("moondream", prompt_ocr, image_path=frame_path)
                descriptions.append({
                    "frame": frame_filename,
                    "description": desc
                })

        return descriptions, saved_frame_paths

    def extract_seo_knowledge(self, filename: str, is_video: bool, transcription: str = None, visual_summary: str = None) -> dict:
        if is_video:
            context = f"## Vídeo de SEO: {filename}\n"
            if transcription: context += f"## Transcrição do Áudio:\n{transcription}\n\n"
            if visual_summary: context += f"## Telas/Frames Visuais do Vídeo:\n{visual_summary}\n\n"
        else:
            context = f"## Imagem/Post de SEO: {filename}\n"
            if visual_summary: context += f"## Conteúdo/Texto Transcrito da Imagem:\n{visual_summary}\n\n"

        system_prompt = (
            "Você é um Consultor Especialista em SEO (Search Engine Optimization) e Marketing de Conteúdo.\n"
            "Sua missão principal é extrair um TUTORIAL PASSO A PASSO ULTRA DETALHADO a partir do vídeo/post fornecido, "
            'capturando com EXATIDÃO cada clique, menu, ferramenta e tela demonstrada.\n\n'
            "RETORNE APENAS um JSON válido:\n"
            "{\n"
            '  "titulo_estrategia": "título objetivo da estratégia",\n'
            '  "resumo_executivo": "resumo em 2 frases",\n'
            '  "passo_a_passo_detalhado": ["Passo 1: ...", "Passo 2: ..."],\n'
            '  "ferramentas_e_telas_utilizadas": ["ex: Google Trends, Gemini"],\n'
            '  "termos_e_exemplos_usados": ["palavras-chave usadas"],\n'
            '  "aplicacao_no_negocio": "como aplicar para vender mais",\n'
            '  "conceitos_mencionados": ["ex: Long-tail"]\n'
            "}"
        )

        res_str = self.query_ollama("qwen2.5:3b", prompt=context, system_prompt=system_prompt, json_format=True)
        try:
            return json.loads(res_str)
        except Exception:
            return {"raw_output": res_str}

    def process_item(self, item: dict) -> bool:
        filepath: Path = item["path"]
        basename: str = item["basename"]
        filetype: str = item["type"]
        filename: str = item["filename"]

        console.print(f"\n[bold blue]🚀 Processando ({filetype.upper()}): {filename}[/bold blue]")
        send_telemetry_event(self.run_id, "START_FILE", status="in_progress", filename=filename, message=f"Iniciando {filename}")

        try:
            transcription = None
            visual_summary = ""
            frame_descriptions = []
            saved_frame_paths = []
            duration_seconds = None

            if filetype == "video":
                send_telemetry_event(self.run_id, "FFMPEG_EXTRACT", status="in_progress", filename=filename, message="Extraindo áudio e frames via FFmpeg")
                ext_res = self.extract_audio_and_frames(filepath, basename)
                duration_seconds = ext_res["duration_seconds"]

                send_telemetry_event(self.run_id, "WHISPER_TRANSCRIBE", status="in_progress", filename=filename, message="Transcrevendo fala via Whisper")
                transcription = self.transcribe_audio_whisper(ext_res["audio_path"], basename)

                send_telemetry_event(self.run_id, "VISION_CLASSIFY", status="in_progress", filename=filename, message="Classificando frames e filtrando rosto de apresentadores")
                target_video_frames_dir = self.output_frames_dir / basename
                frame_descriptions, saved_frame_paths = self.analyze_and_filter_frames(
                    ext_res["frame_paths"], target_video_frames_dir
                )
                visual_summary = "\n---\n".join([d["description"] for d in frame_descriptions]) if frame_descriptions else "Sem telas visuais de conteúdo identificadas"

            else:
                send_telemetry_event(self.run_id, "VISION_CLASSIFY", status="in_progress", filename=filename, message="Analisando conteúdo da imagem única")
                prompt_img = (
                    "Transcreva EXATAMENTE todo o texto visível nesta imagem. "
                    "Identifique conceitos de SEO, dicas de busca do Google, palavras-chave e conselhos mostrados na imagem. Responda em português."
                )
                visual_summary = self.query_ollama("moondream", prompt_img, image_path=filepath)

            send_telemetry_event(self.run_id, "LLM_SEO_EXTRACTION", status="in_progress", filename=filename, message="Gerando tutorial e conhecimento em SEO via Qwen2.5:3b")
            seo_knowledge = self.extract_seo_knowledge(filename, is_video=(filetype == "video"), transcription=transcription, visual_summary=visual_summary)

            original_url = self.get_original_url(filename, basename)

            saved_frames = [
                {
                    "filename": Path(fpath).name,
                    "url": f"/api/media/frames/{basename}/{Path(fpath).name}"
                }
                for fpath in saved_frame_paths
            ]

            document = {
                "basename": basename,
                "metadata": {
                    "source": "facebook_profile_seo",
                    "pipeline_version": "3.0.0 (Python Nativo)",
                    "processed_at": datetime.now().isoformat()
                },
                "source_file": {
                    "filename": filename,
                    "type": filetype,
                    "extension": item["ext"],
                    "url": original_url,
                    "path": str(filepath),
                    "duration_seconds": duration_seconds
                },
                "input_file": {
                    "filename": filename,
                    "type": filetype,
                    "extension": item["ext"],
                    "url": original_url,
                    "media_url": f"/api/media/input/{filetype}s/{filename}" if filepath.exists() else None,
                    "duration_seconds": duration_seconds,
                    "size_bytes": filepath.stat().st_size if filepath.exists() else 0
                },
                "content": {
                    "transcription": transcription,
                    "visual_description": visual_summary,
                    "frame_descriptions": frame_descriptions if filetype == "video" else None,
                    "saved_frame_files": saved_frame_paths,
                    "saved_frames": saved_frames
                },
                "seo_knowledge": seo_knowledge,
                "updated_at": datetime.now().isoformat()
            }

            db = self.get_mongo_db()
            saved_to_db = False
            if db is not None:
                try:
                    existing = db["seo_knowledge"].find_one({"basename": basename})
                    if existing and "user_implementation" in existing:
                        document["user_implementation"] = existing["user_implementation"]
                    else:
                        document["user_implementation"] = {
                            "status": "pendente",
                            "completed_steps": [],
                            "comments": []
                        }

                    db["seo_knowledge"].update_one(
                        {"basename": basename},
                        {"$set": document},
                        upsert=True
                    )
                    console.print(f"[bold green]✅ Sucesso! Conhecimento salvo diretamente no MongoDB (coleção: seo_knowledge)[/bold green]")
                    saved_to_db = True
                except Exception as mongo_err:
                    console.print(f"[bold red]❌ Erro ao salvar no MongoDB: {mongo_err}[/bold red]")

            if not saved_to_db:
                output_path = self.output_dir / f"{basename}.json"
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(document, f, ensure_ascii=False, indent=2)
                console.print(f"[bold yellow]⚠️ Salvo em backup JSON local: {output_path}[/bold yellow]")

            # Deletar o arquivo de entrada original para liberar espaço em disco
            try:
                if filepath.exists():
                    filepath.unlink()
                    console.print(f"[green]🗑️  Arquivo de entrada removido para liberar espaço: {filename}[/green]")
            except Exception as del_err:
                console.print(f"[yellow]⚠️  Falha ao remover arquivo de entrada {filename}: {del_err}[/yellow]")

            # Limpar arquivo de áudio temporário se existir
            if filetype == "video":
                audio_tmp = self.processing_audio_dir / f"{basename}.wav"
                if audio_tmp.exists():
                    try:
                        audio_tmp.unlink()
                    except Exception:
                        pass

            send_telemetry_event(self.run_id, "FILE_COMPLETE", status="completed", filename=filename, message=f"Sucesso ao processar {filename}")
            return True

        except Exception as err:
            err_msg = str(err)
            err_trace = traceback.format_exc()
            console.print(f"[bold red]❌ Erro crítico ao processar {filename}: {err_msg}[/bold red]")
            send_telemetry_event(
                self.run_id, "ERROR", status="error", filename=filename,
                message=f"Falha ao processar {filename}: {err_msg}",
                error_details=err_trace
            )
            return False

    def _save_pipeline_run(self, run_data: dict):
        """Cria ou atualiza o documento da execução (run) na coleção pipeline_runs."""
        db = self.get_mongo_db()
        if db is None:
            return
        try:
            db["pipeline_runs"].update_one(
                {"run_id": run_data["run_id"]},
                {"$set": run_data},
                upsert=True
            )
        except Exception as e:
            console.print(f"[yellow]⚠️  Falha ao registrar pipeline_run no MongoDB: {e}[/yellow]")

    def run_once(self):
        pending = self.get_pending_files()
        send_telemetry_event(self.run_id, "PIPELINE_START", status="info", message=f"Pipeline iniciado com {len(pending)} arquivo(s) pendente(s)")

        run_doc = {
            "run_id": self.run_id,
            "source": "pipeline",
            "status": "in_progress",
            "started_at": datetime.now().isoformat(),
            "finished_at": None,
            "total_files": len(pending),
            "success_files": 0,
            "error_files": 0,
            "error_count": 0
        }
        self._save_pipeline_run(run_doc)

        if not pending:
            console.print("[dim]Nenhum arquivo pendente para processar.[/dim]")
            run_doc.update({"status": "completed", "finished_at": datetime.now().isoformat()})
            self._save_pipeline_run(run_doc)
            return 0

        success_count = 0
        error_count = 0
        for item in pending:
            if self.process_item(item):
                success_count += 1
            else:
                error_count += 1

        final_status = "completed" if error_count == 0 else ("error" if success_count == 0 else "completed")
        run_doc.update({
            "status": final_status,
            "finished_at": datetime.now().isoformat(),
            "success_files": success_count,
            "error_files": error_count,
            "error_count": error_count
        })
        self._save_pipeline_run(run_doc)

        event_status = "completed" if final_status == "completed" else "error"
        send_telemetry_event(
            self.run_id,
            "PIPELINE_COMPLETE" if final_status == "completed" else "PIPELINE_ERROR",
            status=event_status,
            message=f"Pipeline finalizado. Éxito: {success_count}/{len(pending)} arquivos, Erros: {error_count}"
        )
        return success_count

    def run_watch(self, interval: int = 30):
        console.print(f"[bold blue]👀 Pipeline Python ativo em modo contínuo (intervalo: {interval}s)...[/bold blue]")
        try:
            while True:
                self.run_once()
                time.sleep(interval)
        except KeyboardInterrupt:
            console.print("\n[yellow]🛑 Monitoramento encerrado pelo usuário.[/yellow]")


def main():
    parser = argparse.ArgumentParser(description="PipelineFace — Extração de Conhecimento em Python Nativo")
    parser.add_argument("--watch", action="store_true", help="Executar em loop contínuo de monitoramento")
    parser.add_argument("--interval", type=int, default=30, help="Intervalo em segundos para o modo --watch (padrão: 30)")
    parser.add_argument("--file", type=str, help="Processar um arquivo específico")
    parser.add_argument("--project-root", type=str, default=str(DEFAULT_PROJECT_ROOT), help="Caminho raiz do projeto")

    args = parser.parse_args()
    pipeline = KnowledgePipeline(project_root=Path(args.project_root))

    if args.file:
        file_path = Path(args.file).resolve()
        if not file_path.exists():
            console.print(f"[bold red]❌ Arquivo não encontrado: {file_path}[/bold red]")
            sys.exit(1)
        ext = file_path.suffix.lower()
        filetype = "video" if ext in VIDEO_EXTENSIONS else ("image" if ext in IMAGE_EXTENSIONS else None)
        if not filetype:
            console.print(f"[bold red]❌ Extensão não suportada: {ext}[/bold red]")
            sys.exit(1)
        item = {
            "path": file_path, "filename": file_path.name, "basename": file_path.stem, "type": filetype, "ext": ext
        }
        pipeline.process_item(item)
    elif args.watch:
        pipeline.run_watch(interval=args.interval)
    else:
        pipeline.run_once()


if __name__ == "__main__":
    main()
