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
            db = self.get_mongo_db()
            image_files = [f for f in self.input_images_dir.iterdir() if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS]
            
            post_groups = {}
            unmatched_files = []

            for f in image_files:
                target_post_id = None
                if db is not None:
                    try:
                        pdoc = db["profile_posts"].find_one({"media_items.filename": f.name})
                        if pdoc:
                            target_post_id = pdoc.get("post_id")
                    except Exception:
                        pass
                
                if not target_post_id:
                    clean = re.sub(r'^(?:foto_|post_|Vídeo_)', '', f.stem, flags=re.IGNORECASE)
                    clean = re.sub(r'_slide_\d+.*$', '', clean, flags=re.IGNORECASE)
                    clean = re.sub(r'_[a-f0-9]{6,12}$', '', clean, flags=re.IGNORECASE)
                    if clean and len(clean) >= 6:
                        target_post_id = clean

                if target_post_id:
                    if target_post_id not in post_groups:
                        post_groups[target_post_id] = []
                    post_groups[target_post_id].append(f)
                else:
                    unmatched_files.append(f)

            for post_id, f_list in post_groups.items():
                sorted_files = sorted(f_list, key=lambda x: x.name)
                primary_file = sorted_files[0]
                basename = f"post_{post_id}"
                if basename not in processed and primary_file.stem not in processed:
                    pending.append({
                        "path": primary_file,
                        "carousel_paths": sorted_files,
                        "filename": primary_file.name,
                        "basename": basename,
                        "type": "album" if len(sorted_files) > 1 else "image",
                        "ext": primary_file.suffix.lower(),
                        "post_id": post_id
                    })

            # Agrupar unmatched_files via busca por relação de carrossel
            visited_unmatched = set()
            for f in unmatched_files:
                if f in visited_unmatched:
                    continue
                related = self.get_carousel_related_images(f)
                for r in related:
                    visited_unmatched.add(r)
                
                sorted_rel = sorted(related, key=lambda x: x.name)
                prim = sorted_rel[0]
                if prim.stem not in processed:
                    pending.append({
                        "path": prim,
                        "carousel_paths": sorted_rel,
                        "filename": prim.name,
                        "basename": prim.stem,
                        "type": "album" if len(sorted_rel) > 1 else "image",
                        "ext": prim.suffix.lower()
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

        fps_param = f"fps={self.fps_extraction},scale=720:-1" if hasattr(self, 'fps_extraction') and self.fps_extraction != "1/10" else "fps=1/8,scale=720:-1"
        cmd_frames = [
            "ffmpeg", "-y", "-i", str(video_path),
            "-vf", fps_param, "-q:v", "3",
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

    def correct_transcription(self, raw_transcription: str, filename: str) -> str:
        """Pós-corrige erros de transcrição Whisper em conteúdo de SEO."""
        if not raw_transcription or raw_transcription.startswith("["):
            return raw_transcription

        system = (
            "Você é um corretor de transcrições de vídeos de SEO/Marketing Digital em português brasileiro.\n"
            "Corrija APENAS erros óbvios de transcrição automática, mantendo fidelidade ao original:\n"
            "- Nomes de ferramentas de SEO (ex: 'Bessojeste' → 'Keywords Everywhere', 'Semrash' → 'Semrush', 'Arefs' → 'Ahrefs')\n"
            "- Termos técnicos (H1, meta title, URL, bounce rate, CTR, SERP, backlink, etc.)\n"
            "- Nomes de plataformas (Google, YouTube, Facebook, Instagram, etc.)\n"
            "- Siglas e acrônimos comuns de marketing (SEO, SEM, CPC, ROI, KPI, etc.)\n"
            "NÃO altere o conteúdo semântico. NÃO adicione informação nova.\n"
            "Retorne APENAS a transcrição corrigida, sem comentários."
        )
        try:
            corrected = self.query_ollama(self.text_model, raw_transcription, system_prompt=system)
            return corrected if corrected else raw_transcription
        except Exception:
            return raw_transcription

    def analyze_and_filter_frames(self, frame_paths: list[Path], output_dir: Path) -> tuple[list[dict], list[str]]:
        """Analisa frames de vídeo via visão (Moondream) e filtra frames úteis (telas, ferramentas, não rostos)."""
        import shutil
        output_dir.mkdir(parents=True, exist_ok=True)
        descriptions = []
        saved_paths = []

        for frame_path in frame_paths:
            prompt = (
                "Classify this video frame: Is it a SCREEN/TOOL (showing a website, app, dashboard, search engine, or tool interface) "
                "or a FACE/PERSON (just showing a person talking to camera)? "
                "If SCREEN/TOOL: transcribe ALL text visible. If FACE/PERSON: respond only 'FACE'. "
                "Respond in Portuguese."
            )
            response = self.query_ollama(self.vision_model, prompt, image_path=frame_path)

            if not response or response.strip().upper() in ["FACE", "ROSTO", "PESSOA"]:
                continue

            # Frame contém conteúdo visual útil — salvar e registrar
            dest_path = output_dir / frame_path.name
            try:
                shutil.copy2(frame_path, dest_path)
                saved_paths.append(str(dest_path))
                descriptions.append({
                    "frame": frame_path.name,
                    "description": response.strip()
                })
            except Exception:
                pass

        # Se nenhum frame foi classificado como tela, usar OCR Tesseract nos frames
        if not descriptions:
            for frame_path in frame_paths[:5]:  # limitar a 5 frames
                try:
                    import pytesseract
                    prep_img = self.preprocess_image_for_ocr(frame_path)
                    if prep_img:
                        text = pytesseract.image_to_string(prep_img, lang='por+eng', config='--psm 6')
                        if text and len(text.strip()) > 30:
                            dest_path = output_dir / frame_path.name
                            shutil.copy2(frame_path, dest_path)
                            saved_paths.append(str(dest_path))
                            descriptions.append({
                                "frame": frame_path.name,
                                "description": f"[OCR Tesseract]:\n{text.strip()}"
                            })
                except Exception:
                    pass

        return descriptions, saved_paths

    def get_post_metadata(self, filename: str, basename: str) -> dict:
        """Busca metadados enriquecidos do post original em profile_posts."""
        db = self.get_mongo_db()
        if db is None:
            return {}

        try:
            post_id_match = re.search(r'(?:Vídeo_|foto_|post_)?(\d{10,20})', filename)
            target_post_id = post_id_match.group(1) if post_id_match else None

            post_doc = None
            if target_post_id:
                post_doc = db["profile_posts"].find_one({"post_id": target_post_id})

            if not post_doc:
                post_doc = db["profile_posts"].find_one({"media_items.filename": filename})

            if not post_doc:
                url_hash = basename.replace("fb_", "")
                dl_doc = db["download_history"].find_one({"url_hash": url_hash})
                if dl_doc and dl_doc.get("post_id"):
                    post_doc = db["profile_posts"].find_one({"post_id": dl_doc["post_id"]})

            if post_doc:
                return {
                    "author": post_doc.get("profile_name", "Desconhecido"),
                    "author_url": post_doc.get("profile_url"),
                    "post_text_preview": post_doc.get("post_text_preview"),
                    "post_type": post_doc.get("post_type"),
                    "discovered_at": post_doc.get("discovered_at"),
                }
        except Exception:
            pass

        return {}

    def preprocess_image_for_ocr(self, image_path: Path):
        """Aplica escala de cinza, ampliação e contraste para maximizar acurácia de OCR em infográficos."""
        try:
            import cv2
            from PIL import Image, ImageEnhance, ImageFilter

            img = cv2.imread(str(image_path))
            if img is None:
                return Image.open(image_path)

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

            # Ampliar imagem se a resolução for baixa (melhora muito leitura de fontes de infográficos)
            h, w = gray.shape
            if w < 1200:
                scale = 1200 / w
                gray = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)

            pil_img = Image.fromarray(gray)
            
            # Aumentar contraste e nitidez
            enhancer = ImageEnhance.Contrast(pil_img)
            pil_img = enhancer.enhance(2.0)
            sharpener = ImageEnhance.Sharpness(pil_img)
            pil_img = sharpener.enhance(1.5)

            return pil_img
        except Exception:
            try:
                from PIL import Image
                return Image.open(image_path)
            except Exception:
                return None

    def ocr_image(self, image_path: Path, carousel_paths: list[Path] = None) -> str:
        """OCR dedicado com suporte a carrossel de imagens (slides)."""
        all_paths = carousel_paths if carousel_paths else [image_path]
        texts = []

        for idx, p in enumerate(all_paths, 1):
            slide_text = ""
            try:
                import pytesseract
                prep_img = self.preprocess_image_for_ocr(p)
                if prep_img:
                    t = pytesseract.image_to_string(prep_img, lang='por+eng', config='--psm 6')
                    if not t or len(t.strip()) < 15:
                        t = pytesseract.image_to_string(prep_img, lang='por+eng', config='--psm 3')
                    if t and len(t.strip()) > 15:
                        slide_text = t.strip()
            except Exception:
                pass

            if not slide_text:
                try:
                    prompt_ocr = (
                        "Read and transcribe ALL text visible in this image. "
                        "Output ONLY the transcribed text in portuguese. Do not output coordinates or numbers in brackets."
                    )
                    vision_text = self.query_ollama(self.vision_model, prompt_ocr, image_path=p)
                    if vision_text and not re.search(r'^\s*\[\s*\d+\.\d+,\s*\d+\.\d+', vision_text):
                        slide_text = vision_text.strip()
                except Exception:
                    pass  # Moondream pode retornar 400 em certas imagens — Tesseract já é o primário

            if slide_text:
                header = f"--- Slide {idx}/{len(all_paths)} ({p.name}) ---" if len(all_paths) > 1 else "[OCR Conteúdo Visual]:"
                texts.append(f"{header}\n{slide_text}")

        return "\n\n".join(texts) if texts else ""

    def get_carousel_related_images(self, target_filepath: Path) -> list[Path]:
        """Localiza imagens no mesmo diretório de input que pertençam ao mesmo post/carrossel."""
        if not target_filepath.parent.exists():
            return [target_filepath]

        db = self.get_mongo_db()
        if db is not None:
            try:
                post_id_match = re.search(r'(?:Vídeo_|foto_|post_)?([a-f0-9]{8,32})', target_filepath.name, re.IGNORECASE)
                target_post_id = post_id_match.group(1) if post_id_match else None
                
                # Se encontrou o post_id no nome, buscar todas as mídias daquele post_id
                if target_post_id:
                    post_doc = db["profile_posts"].find_one({"post_id": target_post_id})
                    if post_doc:
                        related_paths = []
                        for item in post_doc.get("media_items", []):
                            fname = item.get("filename")
                            if fname:
                                fpath = target_filepath.parent / fname
                                if fpath.exists() and fpath not in related_paths:
                                    related_paths.append(fpath)
                        if len(related_paths) > 1:
                            return sorted(related_paths)

                    # Fallback: buscar arquivos no disco com o mesmo prefixo de post_id
                    prefix = f"foto_{target_post_id}"
                    disk_related = [f for f in target_filepath.parent.glob(f"{prefix}*") if f.is_file()]
                    if len(disk_related) > 1:
                        return sorted(disk_related)
            except Exception:
                pass

        return [target_filepath]

    def validate_seo_knowledge(self, knowledge: dict, has_transcription: bool, has_visual: bool) -> dict:
        """Valida qualidade do conhecimento extraído e atribui score."""
        issues = []
        score = 100

        if "raw_output" in knowledge:
            issues.append("LLM não retornou JSON válido")
            score -= 50

        steps = knowledge.get("passo_a_passo_detalhado", [])
        if len(steps) == 0:
            issues.append("Nenhum passo extraído")
            score -= 30
        else:
            for i, step in enumerate(steps):
                if len(step) < 30:
                    issues.append(f"Passo {i+1} muito curto ({len(step)} chars)")
                    score -= 5

        # Se não há transcrição nem texto visual lido, o resultado é invenção/alucinação!
        if not has_transcription and not has_visual:
            issues.append("Sem fonte real de dados: OCR/Visão e Áudio falharam — conhecimento alucinado pelo LLM")
            score = 0

        placeholder_patterns = [
            "palavras-chave usadas", "ex: Long-tail", "ex: Google Trends",
            "ex: Gemini", "título objetivo", "resumo em 2 frases"
        ]
        for field_name in ["termos_e_exemplos_usados", "conceitos_mencionados", "ferramentas_e_telas_utilizadas"]:
            values = knowledge.get(field_name, [])
            for v in (values if isinstance(values, list) else [values]):
                v_lower = str(v).lower()
                for p in placeholder_patterns:
                    if p.lower() in v_lower:
                        issues.append(f"Placeholder em '{field_name}': '{v}'")
                        score -= 15

        titulo = knowledge.get("titulo_estrategia", "")
        generic_titles = ["otimização de seo", "melhorar seo", "estratégia de seo", "seo para melhorar", "como criar e otimizar posts"]
        if any(g in titulo.lower() for g in generic_titles):
            issues.append(f"Título genérico: '{titulo}'")
            score -= 15

        knowledge["quality_score"] = max(0, score)
        knowledge["quality_issues"] = issues
        knowledge["quality_grade"] = (
            "A" if score >= 80 else
            "B" if score >= 60 else
            "C" if score >= 40 else
            "D"
        )
        return knowledge

    def extract_seo_knowledge(self, filename: str, is_video: bool, transcription: str = None, visual_summary: str = None) -> dict:
        if is_video:
            context = f"## Vídeo de SEO: {filename}\n"
            if transcription: context += f"## Transcrição do Áudio:\n{transcription}\n\n"
            if visual_summary: context += f"## Telas/Frames Visuais do Vídeo:\n{visual_summary}\n\n"

            system_prompt = (
                "Você é um Consultor Especialista em SEO (Search Engine Optimization) e Marketing de Conteúdo.\n"
                "Sua missão é extrair um TUTORIAL PASSO A PASSO ULTRA DETALHADO a partir do conteúdo fornecido, "
                "capturando com EXATIDÃO cada clique, menu, ferramenta e tela demonstrada.\n\n"
                "IDIOMA OBRIGATÓRIO: Escreva TODAS as respostas EXCLUSIVAMENTE em Português do Brasil (pt-BR). "
                "Nunca responda em espanhol, inglês ou qualquer outro idioma.\n\n"
                "REGRAS CRÍTICAS — SIGA RIGOROSAMENTE:\n"
                "1. EXTRAIA apenas informações PRESENTES no conteúdo. NUNCA invente dados.\n"
                "2. Se um campo não pode ser preenchido com dados reais, use \"Não identificado no conteúdo\".\n"
                "3. Cada passo DEVE conter uma AÇÃO CONCRETA (ex: 'Acesse google.com e digite...', 'Clique no menu...').\n"
                "4. Os termos em 'termos_e_exemplos_usados' devem ser LITERALMENTE do conteúdo.\n"
                "5. Se a transcrição contiver erros prováveis, interprete pelo contexto.\n"
                "6. Inclua URLs e nomes EXATOS de ferramentas quando mencionados.\n"
                "7. O campo 'nivel_dificuldade' deve ser: 'iniciante', 'intermediario' ou 'avancado'.\n"
                "8. O campo 'tempo_estimado_implementacao' deve ser realista (ex: '15 minutos', '1 hora').\n\n"
                "RETORNE APENAS um JSON válido:\n"
                "{\n"
                '  "titulo_estrategia": "título objetivo e descritivo da estratégia/dica",\n'
                '  "resumo_executivo": "resumo em 2-3 frases do que o conteúdo ensina",\n'
                '  "passo_a_passo_detalhado": ["Passo 1: Ação concreta...", "Passo 2: ..."],\n'
                '  "ferramentas_e_telas_utilizadas": ["Nome exato da ferramenta mencionada"],\n'
                '  "termos_e_exemplos_usados": ["termo literal extraído do conteúdo"],\n'
                '  "aplicacao_no_negocio": "como aplicar esta dica para gerar resultados concretos",\n'
                '  "conceitos_mencionados": ["conceito de SEO/marketing mencionado"],\n'
                '  "nivel_dificuldade": "iniciante|intermediario|avancado",\n'
                '  "tempo_estimado_implementacao": "estimativa de tempo para implementar",\n'
                '  "pre_requisitos": ["o que o usuário precisa ter/saber antes de começar"],\n'
                '  "resultado_esperado": "o que o usuário obterá ao implementar esta dica"\n'
                "}"
            )
        else:
            context = f"## Post de Imagem/Carrossel de SEO: {filename}\n"
            if visual_summary: context += f"## Transcrição e Análise dos Slides do Carrossel/Infográfico:\n{visual_summary}\n\n"

            system_prompt = (
                "Você é um Consultor Especialista em SEO (Search Engine Optimization) e Marketing de Conteúdo.\n"
                "Sua missão é sintetizar este CARROSSEL / INFOGRÁFICO VISUAL DE SEO em um guia de conhecimento altamente estruturado e prático.\n"
                "Sua análise deve consolidar TODAS as lições, conceitos, dicas e checklists apresentados ao longo de TODOS os slides da imagem/carrossel em um único ensinamento coeso.\n\n"
                "IDIOMA OBRIGATÓRIO: Escreva TODAS as respostas EXCLUSIVAMENTE em Português do Brasil (pt-BR).\n\n"
                "REGRAS CRÍTICAS — SIGA RIGOROSAMENTE:\n"
                "1. SINTETIZE as informações presentes nos slides sem inventar dados adicionais.\n"
                "2. No campo 'passo_a_passo_detalhado', consolide a sequência lógica das dicas ensinadas nos slides (ex: 'Passo 1: Definir a palavra-chave principal...', 'Passo 2: Otimizar a estrutura...').\n"
                "3. Os termos em 'termos_e_exemplos_usados' devem ser extraídos literalmente dos slides.\n"
                "4. Inclua ferramentas e conceitos mencionados visualmente.\n"
                "5. O campo 'nivel_dificuldade' deve ser: 'iniciante', 'intermediario' ou 'avancado'.\n"
                "6. O campo 'tempo_estimado_implementacao' deve ser realista (ex: '15 minutos', '30 minutos').\n\n"
                "RETORNE APENAS um JSON válido:\n"
                "{\n"
                '  "titulo_estrategia": "título claro e atraente resumindo a dica do carrossel/infográfico",\n'
                '  "resumo_executivo": "resumo em 2-3 frases do objetivo e ensinamento principal do carrossel",\n'
                '  "passo_a_passo_detalhado": ["Recomendação/Passo 1 extraído dos slides", "Recomendação/Passo 2..."],\n'
                '  "ferramentas_e_telas_utilizadas": ["Ferramenta ou plataforma mencionada nos slides"],\n'
                '  "termos_e_exemplos_usados": ["termo ou exemplo literal extraído do carrossel"],\n'
                '  "aplicacao_no_negocio": "como aplicar esta dica para obter resultados em SEO",\n'
                '  "conceitos_mencionados": ["conceito de SEO/marketing presente no carrossel"],\n'
                '  "nivel_dificuldade": "iniciante|intermediario|avancado",\n'
                '  "tempo_estimado_implementacao": "estimativa de tempo para aplicar",\n'
                '  "pre_requisitos": ["o que o usuário precisa antes de aplicar"],\n'
                '  "resultado_esperado": "resultado concreto esperado ao aplicar a dica"\n'
                "}"
            )

        res_str = self.query_ollama(self.text_model, prompt=context, system_prompt=system_prompt, json_format=True)
        try:
            data = json.loads(res_str)
        except Exception:
            data = {"raw_output": res_str}

        # Pós-processamento de tradução: se detectar termos em espanhol comuns, força a tradução do JSON para pt-BR
        espanhol_indicators = [" el ", " los ", " del ", " para mejorar ", " esta ", " con ", " como ", " paso ", " optimización ", " en "]
        str_data = json.dumps(data, ensure_ascii=False).lower()
        if any(ind in str_data for ind in espanhol_indicators):
            translate_prompt = (
                "Você é um tradutor especialista. Traduza o seguinte objeto JSON do espanhol para Português do Brasil (pt-BR).\n"
                "Mantenha a estrutura JSON e todas as chaves intactas. Traduza apenas os valores de texto para um português natural do Brasil.\n\n"
                f"Objeto JSON para traduzir:\n{json.dumps(data, ensure_ascii=False)}"
            )
            try:
                translated_str = self.query_ollama(self.text_model, prompt=translate_prompt, system_prompt="Retorne apenas o JSON traduzido, sem explicações.", json_format=True)
                translated_data = json.loads(translated_str)
                if "titulo_estrategia" in translated_data:
                    data = translated_data
            except Exception:
                pass

        return data

    def process_item(self, item: dict) -> bool:
        filepath: Path = item["path"]
        basename: str = item["basename"]
        filetype: str = item["type"]
        filename: str = item["filename"]
        carousel_paths: list[Path] = item.get("carousel_paths") or [filepath]

        console.print(f"\n[bold blue]🚀 Processando ({filetype.upper()}): {filename} ({len(carousel_paths)} slide(s))[/bold blue]")
        send_telemetry_event(self.run_id, "START_FILE", status="in_progress", filename=filename, message=f"Iniciando {filename}")

        try:
            transcription = None
            transcription_raw = None
            visual_summary = ""
            frame_descriptions = []
            saved_frame_paths = []
            duration_seconds = None

            if filetype == "video":
                send_telemetry_event(self.run_id, "FFMPEG_EXTRACT", status="in_progress", filename=filename, message="Extraindo áudio e frames via FFmpeg")
                ext_res = self.extract_audio_and_frames(filepath, basename)
                duration_seconds = ext_res["duration_seconds"]

                send_telemetry_event(self.run_id, "WHISPER_TRANSCRIBE", status="in_progress", filename=filename, message="Transcrevendo fala via Whisper")
                transcription_raw = self.transcribe_audio_whisper(ext_res["audio_path"], basename)

                send_telemetry_event(self.run_id, "CORRECT_TRANSCRIPTION", status="in_progress", filename=filename, message="Corrigindo erros de transcrição via LLM")
                transcription = self.correct_transcription(transcription_raw, filename)

                send_telemetry_event(self.run_id, "VISION_CLASSIFY", status="in_progress", filename=filename, message="Classificando frames e filtrando rosto de apresentadores")
                target_video_frames_dir = self.output_frames_dir / basename
                frame_descriptions, saved_frame_paths = self.analyze_and_filter_frames(
                    ext_res["frame_paths"], target_video_frames_dir
                )
                visual_summary = "\n---\n".join([d["description"] for d in frame_descriptions]) if frame_descriptions else "Sem telas visuais de conteúdo identificadas"

            else:
                send_telemetry_event(self.run_id, "VISION_CLASSIFY", status="in_progress", filename=filename, message="Analisando conteúdo da imagem/carrossel")
                if len(carousel_paths) > 1:
                    console.print(f"  [bold cyan]🎠 Carrossel unificado com {len(carousel_paths)} slides![/bold cyan]")
                visual_summary = self.ocr_image(filepath, carousel_paths=carousel_paths)
                saved_frame_paths = [str(p) for p in carousel_paths]

            send_telemetry_event(self.run_id, "LLM_SEO_EXTRACTION", status="in_progress", filename=filename, message="Gerando síntese em SEO via LLM")
            seo_knowledge = self.extract_seo_knowledge(filename, is_video=(filetype == "video"), transcription=transcription, visual_summary=visual_summary)
            
            seo_knowledge = self.validate_seo_knowledge(
                seo_knowledge,
                has_transcription=bool(transcription and not transcription.startswith("[")),
                has_visual=bool(visual_summary and visual_summary != "Sem telas visuais de conteúdo identificadas" and "Nenhum texto identificado" not in visual_summary)
            )
            quality = seo_knowledge.get("quality_grade", "?")
            score = seo_knowledge.get("quality_score", 0)
            console.print(f"  [bold]📊 Qualidade: Grade {quality} (Score: {score}/100)[/bold]")

            original_url = self.get_original_url(filename, basename)
            post_meta = self.get_post_metadata(filename, basename)

            saved_frames = [
                {
                    "filename": Path(fpath).name,
                    "url": f"/api/media/input/images/{Path(fpath).name}" if filetype != "video" else f"/api/media/frames/{basename}/{Path(fpath).name}"
                }
                for fpath in saved_frame_paths
            ]

            document = {
                "basename": basename,
                "metadata": {
                    "source": "facebook_profile_seo",
                    "pipeline_version": "3.2.0 (Carrossel Unificado com OCR e Prompt Dedicado)",
                    "processed_at": datetime.now().isoformat(),
                    "author": post_meta.get("author"),
                    "author_url": post_meta.get("author_url"),
                    "post_text_preview": post_meta.get("post_text_preview")
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
                    "media_url": f"/api/media/input/{filetype}s/{filename}" if (filepath.exists() and filetype == "video") else None,
                    "duration_seconds": duration_seconds,
                    "size_bytes": filepath.stat().st_size if filepath.exists() else 0
                },
                "content": {
                    "transcription": transcription,
                    "transcription_raw": transcription_raw,
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
                    console.print(f"[bold green]✅ Sucesso! Conhecimento do carrossel salvo no MongoDB (coleção: seo_knowledge)[/bold green]")
                    saved_to_db = True
                except Exception as mongo_err:
                    console.print(f"[bold red]❌ Erro ao salvar no MongoDB: {mongo_err}[/bold red]")

            if not saved_to_db:
                output_path = self.output_dir / f"{basename}.json"
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(document, f, ensure_ascii=False, indent=2)
                console.print(f"[bold yellow]⚠️ Salvo em backup JSON local: {output_path}[/bold yellow]")

            # Deletar todos os arquivos de entrada do carrossel para liberar espaço em disco
            for c_path in carousel_paths:
                try:
                    if c_path.exists():
                        c_path.unlink()
                        console.print(f"[green]🗑️  Arquivo de entrada removido: {c_path.name}[/green]")
                except Exception as del_err:
                    console.print(f"[yellow]⚠️  Falha ao remover arquivo {c_path.name}: {del_err}[/yellow]")

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
