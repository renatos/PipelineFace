#!/usr/bin/env python3
"""
PipelineFace — Pipeline de Extração de Conhecimento 100% Python
===============================================================
Processa vídeos e imagens coletados com telemetria via Webhooks e relatórios de erro.
"""

import argparse
import base64
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
WHISPER_URL = os.environ.get("WHISPER_URL", "http://localhost:9000/asr")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/chat")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "http://localhost:8000/api/webhooks/execution-event")

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".webm", ".mkv"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}


def send_telemetry_event(
    run_id: str,
    step: str,
    status: str = "info",
    filename: str = None,
    message: str = "",
    metrics: dict = None,
    error_details: str = None
):
    """Envia um evento de telemetria ou log de erro para a API Web (Webhook)."""
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
            WEBHOOK_URL,
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
        whisper_url: str = WHISPER_URL,
        ollama_url: str = OLLAMA_URL,
    ):
        self.project_root = Path(project_root)
        self.whisper_url = whisper_url
        self.ollama_url = ollama_url
        self.run_id = str(uuid.uuid4())[:8]

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

    def get_processed_basenames(self) -> set[str]:
        processed = set()
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
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        user_msg = {"role": "user", "content": prompt}
        if image_path and image_path.exists():
            with open(image_path, "rb") as img_f:
                user_msg["images"] = [base64.b64encode(img_f.read()).decode("utf-8")]

        messages.append(user_msg)

        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0.2}
        }
        if json_format:
            payload["format"] = "json"

        req_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.ollama_url,
            data=req_data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                return res.get("message", {}).get("content", "").strip()
        except Exception as e:
            console.print(f"[red]❌ Erro na requisição ao Ollama ({model}): {e}[/red]")
            raise RuntimeError(f"Ollama API ({model}) falhou: {e}")

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

            prompt_classify = (
                "Esta imagem mostra apenas o rosto ou corpo do apresentador (talking head/pessoa falando para a câmera) "
                "sem tela de computador, slides, texto ou gráficos? "
                'Responda APENAS "ROSTO" se for apenas o apresentador, ou "CONTEUDO" se mostrar tela de computador, slides, gráficos, buscas ou texto.'
            )
            classification = self.query_ollama("moondream", prompt_classify, image_path=frame_path).upper()

            is_rosto = ("ROSTO" in classification) and ("CONTEUDO" not in classification)

            if is_rosto:
                console.print(f"  [yellow]🙈 Frame ignorado (apenas rosto): {frame_filename}[/yellow]")
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

            document = {
                "metadata": {
                    "source": "facebook_profile_seo",
                    "pipeline_version": "3.0.0 (Python Nativo)",
                    "processed_at": datetime.now().isoformat()
                },
                "source_file": {
                    "filename": filename,
                    "type": filetype,
                    "extension": item["ext"],
                    "path": str(filepath),
                    "duration_seconds": duration_seconds
                },
                "content": {
                    "transcription": transcription,
                    "visual_description": visual_summary,
                    "frame_descriptions": frame_descriptions if filetype == "video" else None,
                    "saved_frame_files": saved_frame_paths
                },
                "seo_knowledge": seo_knowledge
            }

            output_path = self.output_dir / f"{basename}.json"
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(document, f, ensure_ascii=False, indent=2)

            console.print(f"[bold green]✅ Sucesso! Conhecimento salvo em: {output_path}[/bold green]")
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

    def run_once(self):
        pending = self.get_pending_files()
        send_telemetry_event(self.run_id, "PIPELINE_START", status="info", message=f"Pipeline iniciado com {len(pending)} arquivo(s) pendente(s)")
        if not pending:
            console.print("[dim]Nenhum arquivo pendente para processar.[/dim]")
            return 0

        count = 0
        for item in pending:
            if self.process_item(item):
                count += 1
        return count

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
