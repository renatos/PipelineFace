#!/usr/bin/env python3
"""
PipelineFace — Pipeline de Extração de Conhecimento 100% Python
===============================================================
Processa vídeos e imagens coletados, realizando:
  1. Extração de áudio e frames via FFmpeg
  2. Transcrição de áudio via Whisper ASR
  3. Análise visual de frames via Ollama (Moondream)
  4. Filtragem inteligente de rostos (descarta apresentadores/talking head)
  5. Extração de conhecimento em SEO via Ollama (Qwen2.5:3b)
  6. Salvamento do contrato JSON estruturado e frames em data/output/

Uso:
  # Executar uma vez sobre os arquivos pendentes:
  python pipeline.py

  # Modo contínuo (daemon a cada 30 segundos):
  python pipeline.py --watch --interval 30

  # Processar um arquivo específico:
  python pipeline.py --file data/input/videos/exemplo.mp4
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
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

# Configurações do Rich para logs visuais
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
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

# ============================================================
# Configurações de URLs e Diretórios
# ============================================================
DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parent
WHISPER_URL = os.environ.get("WHISPER_URL", "http://localhost:9000/asr")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/chat")

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".webm", ".mkv"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}


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

        self.input_videos_dir = self.project_root / "data" / "input" / "videos"
        self.input_images_dir = self.project_root / "data" / "input" / "images"
        self.output_dir = self.project_root / "data" / "output"
        self.output_frames_dir = self.output_dir / "frames"
        self.processing_audio_dir = self.project_root / "data" / "processing" / "audio"
        self.processing_frames_dir = self.project_root / "data" / "processing" / "frames"

        # Garantir estrutura de diretórios
        for d in [
            self.input_videos_dir,
            self.input_images_dir,
            self.output_dir,
            self.output_frames_dir,
            self.processing_audio_dir,
            self.processing_frames_dir,
        ]:
            d.mkdir(parents=True, exist_ok=True)

    # --------------------------------------------------------
    # Verificação de Mídias Já Processadas
    # --------------------------------------------------------
    def get_processed_basenames(self) -> set[str]:
        """Retorna o conjunto de nomes de arquivos já processados (JSONs em output)."""
        processed = set()
        if self.output_dir.exists():
            for f in self.output_dir.glob("*.json"):
                processed.add(f.stem)
        return processed

    def get_pending_files(self) -> list[dict]:
        """Lista todos os arquivos de entrada pendentes de processamento."""
        processed = self.get_processed_basenames()
        pending = []

        # Vídeos
        if self.input_videos_dir.exists():
            for f in self.input_videos_dir.iterdir():
                if f.is_file() and f.suffix.lower() in VIDEO_EXTENSIONS:
                    if f.stem not in processed:
                        pending.append({
                            "path": f,
                            "filename": f.name,
                            "basename": f.stem,
                            "type": "video",
                            "ext": f.suffix.lower()
                        })

        # Imagens
        if self.input_images_dir.exists():
            for f in self.input_images_dir.iterdir():
                if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS:
                    if f.stem not in processed:
                        pending.append({
                            "path": f,
                            "filename": f.name,
                            "basename": f.stem,
                            "type": "image",
                            "ext": f.suffix.lower()
                        })

        return sorted(pending, key=lambda x: x["filename"])

    # --------------------------------------------------------
    # Processamento de Áudio & Vídeo com FFmpeg
    # --------------------------------------------------------
    def extract_audio_and_frames(self, video_path: Path, basename: str) -> dict:
        """Extrai áudio WAV e frames JPG de um arquivo de vídeo usando FFmpeg."""
        audio_path = self.processing_audio_dir / f"{basename}.wav"
        video_frames_dir = self.processing_frames_dir / basename
        video_frames_dir.mkdir(parents=True, exist_ok=True)

        # 1. Extração de Áudio
        cmd_audio = [
            "ffmpeg", "-y", "-i", str(video_path),
            "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
            str(audio_path)
        ]
        try:
            subprocess.run(cmd_audio, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=300)
        except Exception as e:
            console.print(f"[yellow]⚠️  Falha ao extrair áudio ({e}). O vídeo continuará sem áudio.[/yellow]")
            audio_path = None

        # 2. Extração de Frames (1 frame a cada 10s)
        cmd_frames = [
            "ffmpeg", "-y", "-i", str(video_path),
            "-vf", "fps=1/10,scale=720:-1", "-q:v", "3",
            str(video_frames_dir / "frame_%04d.jpg")
        ]
        try:
            subprocess.run(cmd_frames, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=300)
        except Exception as e:
            console.print(f"[red]❌ Erro ao extrair frames: {e}[/red]")

        # 3. Duração via FFprobe
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

    # --------------------------------------------------------
    # Chamadas de API (Whisper & Ollama)
    # --------------------------------------------------------
    def transcribe_audio_whisper(self, audio_path: Path, filename: str) -> str:
        """Envia o arquivo WAV para a API do Whisper via multipart request."""
        if not audio_path or not audio_path.exists():
            return "[Sem áudio extraído para transcrição]"

        try:
            with open(audio_path, "rb") as f:
                audio_bytes = f.read()

            boundary = "----WebKitFormBoundary" + os.urllib_parse_hash() if hasattr(os, 'urllib_parse_hash') else "----WebKitFormBoundary7MA4YWxkTrZu0gW"
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
        """Envia uma requisição de chat para a API do Ollama (local/host)."""
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
            return f"[Erro Ollama: {e}]"

    # --------------------------------------------------------
    # Análise Visual & Filtro de Apresentador (Moondream)
    # --------------------------------------------------------
    def analyze_and_filter_frames(self, frame_paths: list[Path], target_frames_dir: Path) -> tuple[list[dict], list[str]]:
        """
        Analisa os frames com o modelo Moondream:
          - Classifica e descarta frames que contêm APENAS o rosto do apresentador (talking head).
          - Copia e salva apenas os frames com CONTEÚDO (telas, slides, gráficos, buscas, texto).
        """
        descriptions = []
        saved_frame_paths = []

        if not frame_paths:
            return descriptions, saved_frame_paths

        # Selecionar até 3-5 frames para descrição OCR detalhada
        max_ocr_frames = 3
        if len(frame_paths) <= max_ocr_frames:
            selected_ocr_frames = set(frame_paths)
        else:
            step = len(frame_paths) // max_ocr_frames
            selected_ocr_frames = set(frame_paths[i * step] for i in range(max_ocr_frames))

        for frame_path in frame_paths:
            frame_filename = frame_path.name

            # 1. Classificação ROSTO vs CONTEUDO
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

            # 2. Se for CONTEÚDO, copia para a pasta de saída persistente
            target_frames_dir.mkdir(parents=True, exist_ok=True)
            dest = target_frames_dir / frame_filename
            shutil.copy2(frame_path, dest)
            saved_frame_paths.append(str(dest))

            # 3. Se selecionado para OCR detalhado, faz transcrição do texto visível
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

    # --------------------------------------------------------
    # Extração de Conhecimento em SEO (Qwen2.5:3b)
    # --------------------------------------------------------
    def extract_seo_knowledge(self, filename: str, is_video: bool, transcription: str = None, visual_summary: str = None) -> dict:
        """Gera a estrutura JSON com a estratégia de SEO usando Qwen2.5:3b."""
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
            'capturando com EXATIDÃO cada clique, menu, ferramenta e tela demonstrada (ex: "Entre no Google Trends", "Clique em Explorar", "Abra o Gemini", "Abra o Semrush", etc.).\n\n'
            "NÃO RESUMA OU SINTETIZE DEMAIS. Descreva cada ação prática de forma acionável para que qualquer pessoa possa replicar exatamente os mesmos cliques no próprio negócio.\n\n"
            "RETORNE APENAS um JSON válido no seguinte formato:\n"
            "{\n"
            '  "titulo_estrategia": "título objetivo da estratégia ou tutorial de SEO",\n'
            '  "resumo_executivo": "resumo da técnica ensinada em 2 frases",\n'
            '  "passo_a_passo_detalhado": [\n'
            '    "Passo 1: [Ação exata] Acesse o site/ferramenta X...",\n'
            '    "Passo 2: [Clique/Digite] Clique no menu Y ou digite o termo Z...",\n'
            '    "Passo N: ..."\n'
            "  ],\n"
            '  "ferramentas_e_telas_utilizadas": ["ex: Google Trends, Gemini, Semrush"],\n'
            '  "termos_e_exemplos_usados": ["termos de busca ou palavras-chave usadas como exemplo"],\n'
            '  "aplicacao_no_negocio": "como utilizar essa estratégia para ranquear melhor",\n'
            '  "conceitos_mencionados": ["ex: Long-tail, Volume de busca"]\n'
            "}"
        )

        res_str = self.query_ollama("qwen2.5:3b", prompt=context, system_prompt=system_prompt, json_format=True)
        try:
            return json.loads(res_str)
        except Exception:
            return {"raw_output": res_str}

    # --------------------------------------------------------
    # Processador Principal por Item
    # --------------------------------------------------------
    def process_item(self, item: dict) -> bool:
        """Processa um arquivo individual (vídeo ou imagem)."""
        filepath: Path = item["path"]
        basename: str = item["basename"]
        filetype: str = item["type"]
        filename: str = item["filename"]

        console.print(f"\n[bold blue]🚀 Processando ({filetype.upper()}): {filename}[/bold blue]")

        transcription = None
        visual_summary = ""
        frame_descriptions = []
        saved_frame_paths = []
        duration_seconds = None

        if filetype == "video":
            # 1. FFmpeg Extração
            console.print("  [cyan]1/4 Extraindo áudio e frames com FFmpeg...[/cyan]")
            ext_res = self.extract_audio_and_frames(filepath, basename)
            duration_seconds = ext_res["duration_seconds"]

            # 2. Whisper Transcrição
            console.print("  [cyan]2/4 Transcrevendo áudio com Whisper...[/cyan]")
            transcription = self.transcribe_audio_whisper(ext_res["audio_path"], basename)

            # 3. Moondream Visão e Filtro de Apresentador
            console.print("  [cyan]3/4 Analisando visivelmente e filtrando rostos dos apresentadores...[/cyan]")
            target_video_frames_dir = self.output_frames_dir / basename
            frame_descriptions, saved_frame_paths = self.analyze_and_filter_frames(
                ext_res["frame_paths"], target_video_frames_dir
            )
            visual_summary = "\n---\n".join([d["description"] for d in frame_descriptions]) if frame_descriptions else "Sem telas visuais de conteúdo identificadas"

        else:
            # Imagem única
            console.print("  [cyan]1/2 Analisando imagem única com Moondream...[/cyan]")
            prompt_img = (
                "Transcreva EXATAMENTE todo o texto visível nesta imagem. "
                "Identifique conceitos de SEO, dicas de busca do Google, palavras-chave e conselhos mostrados na imagem. Responda em português."
            )
            visual_summary = self.query_ollama("moondream", prompt_img, image_path=filepath)

        # 4. LLM Extração Estruturada
        console.print("  [cyan]4/4 Extraindo conhecimento em SEO com Qwen2.5:3b...[/cyan]")
        seo_knowledge = self.extract_seo_knowledge(filename, is_video=(filetype == "video"), transcription=transcription, visual_summary=visual_summary)

        # 5. Montagem do Documento JSON Final
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
        return True

    # --------------------------------------------------------
    # Execução do Ciclo
    # --------------------------------------------------------
    def run_once(self):
        """Varre e processa todos os arquivos pendentes."""
        pending = self.get_pending_files()
        if not pending:
            console.print("[dim]Nenhum arquivo pendente para processar.[/dim]")
            return 0

        console.print(f"[bold green]📦 {len(pending)} arquivo(s) pendente(s) encontrado(s).[/bold green]")
        count = 0
        for item in pending:
            try:
                if self.process_item(item):
                    count += 1
            except Exception as e:
                console.print(f"[bold red]❌ Falha ao processar {item['filename']}: {e}[/bold red]")
        return count

    def run_watch(self, interval: int = 30):
        """Roda continuamente checando novos arquivos a cada N segundos."""
        console.print(f"[bold blue]👀 Pipeline Python ativo em modo contínuo (intervalo: {interval}s)...[/bold blue]")
        try:
            while True:
                self.run_once()
                time.sleep(interval)
        except KeyboardInterrupt:
            console.print("\n[yellow]🛑 Monitoramento encerrado pelo usuário.[/yellow]")


# Helper para hash no boundary
if not hasattr(os, 'urllib_parse_hash'):
    import hashlib
    os.urllib_parse_hash = lambda: hashlib.md5(str(time.time()).encode()).hexdigest()[:12]


# ============================================================
# Main CLI
# ============================================================
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
            "path": file_path,
            "filename": file_path.name,
            "basename": file_path.stem,
            "type": filetype,
            "ext": ext
        }
        pipeline.process_item(item)
    elif args.watch:
        pipeline.run_watch(interval=args.interval)
    else:
        pipeline.run_once()


if __name__ == "__main__":
    main()
