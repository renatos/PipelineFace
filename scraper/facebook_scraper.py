#!/usr/bin/env python3
"""
Facebook Profile Scraper — PipelineFace
=========================================
Coleta automatizada de vídeos e imagens de perfis de terceiros
no Facebook, utilizando uma sessão autenticada do próprio usuário.

Fluxo:
  1. Login interativo (primeira vez) → salva sessão
  2. Navegação ao perfil-alvo
  3. Scroll e coleta de URLs de mídia (vídeos e imagens)
  4. Download de vídeos com yt-dlp
  5. Download de imagens com requests
  6. Salva metadados em JSON

Uso:
  # Primeira vez (login interativo):
  python facebook_scraper.py --target https://www.facebook.com/perfil.alvo --login

  # Execuções subsequentes (usa sessão salva):
  python facebook_scraper.py --target https://www.facebook.com/perfil.alvo

  # Coletar apenas vídeos:
  python facebook_scraper.py --target https://www.facebook.com/perfil.alvo --only-videos

  # Limitar quantidade de scrolls:
  python facebook_scraper.py --target https://www.facebook.com/perfil.alvo --max-scrolls 100
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import hashlib
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, urljoin

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
except ImportError:
    print("❌ Playwright não instalado. Execute: pip install playwright && playwright install chromium")
    sys.exit(1)

try:
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
    from rich.table import Table
    from rich.panel import Panel
    console = Console()
except ImportError:
    # Fallback simples sem rich
    class Console:
        def print(self, *args, **kwargs):
            text = args[0] if args else ""
            # Remover markup do rich
            clean = re.sub(r'\[.*?\]', '', str(text))
            print(clean)
        def log(self, *args, **kwargs):
            self.print(*args, **kwargs)
    console = Console()

# ============================================================
# Configuração
# ============================================================

DEFAULT_OUTPUT_VIDEOS = "/data/input/videos"
DEFAULT_OUTPUT_IMAGES = "/data/input/images"
DEFAULT_OUTPUT_METADATA = "/data/input/metadata"
DEFAULT_SESSION_DIR = "/data/scraper/session"
DEFAULT_MAX_SCROLLS = 50
SCROLL_PAUSE = 2.5  # segundos entre scrolls
PAGE_LOAD_TIMEOUT = 30000  # ms



def send_telemetry_event(
    run_id: str,
    step: str,
    status: str = "info",
    target_url: str = None,
    filename: str = None,
    message: str = "",
    metrics: dict = None,
    error_details: str = None,
    webhook_url: str = "http://localhost:8000/api/webhooks/execution-event"
):
    try:
        import urllib.request, json
        payload = {
            "run_id": run_id,
            "source": "scraper",
            "step": step,
            "status": status,
            "filename": filename,
            "target_url": target_url,
            "message": message,
            "metrics": metrics or {},
            "error_details": error_details
        }
        req_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            webhook_url,
            data=req_data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            pass
    except Exception:
        pass


class FacebookScraper:
    """Scraper de perfis do Facebook com sessão autenticada."""

    import uuid
    def __init__(
        self,
        target_url: str,
        session_dir: str = DEFAULT_SESSION_DIR,
        output_videos: str = DEFAULT_OUTPUT_VIDEOS,
        output_images: str = DEFAULT_OUTPUT_IMAGES,
        output_metadata: str = DEFAULT_OUTPUT_METADATA,
        max_scrolls: int = DEFAULT_MAX_SCROLLS,
        only_videos: bool = False,
        only_images: bool = False,
        headless: bool = True,
    ):
        self.target_url = target_url.rstrip("/")
        self.session_dir = Path(session_dir)
        self.output_videos = Path(output_videos)
        self.output_images = Path(output_images)
        self.output_metadata = Path(output_metadata)
        self.max_scrolls = max_scrolls
        self.only_videos = only_videos
        self.only_images = only_images
        self.headless = headless

        # Criar diretórios
        for d in [self.session_dir, self.output_videos, self.output_images, self.output_metadata]:
            d.mkdir(parents=True, exist_ok=True)

        # Estado de coleta
        self.collected_videos: list[dict] = []
        self.collected_images: list[dict] = []
        self.profile_info: dict = {}
        self.errors: list[str] = []
        self.run_id = str(uuid.uuid4())[:8]
        
        # Histórico persistente de downloads para evitar re-download
        self.history_file = self.output_metadata / "download_history.json"
        self.downloaded_history = self._load_download_history()

    def _init_mongo_client(self):
        try:
            from pymongo import MongoClient
            mongo_uri = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
            client = MongoClient(mongo_uri, serverSelectionTimeoutMS=2000)
            db = client["pipelineface"]
            return db["download_history"]
        except Exception:
            return None

    def _load_download_history(self) -> set:
        """Carrega o histórico de URLs e hashes já baixados do MongoDB."""
        history = set()
        mongo_col = self._init_mongo_client()
        if mongo_col is not None:
            try:
                for doc in mongo_col.find({}, {"url": 1, "url_hash": 1}):
                    if "url" in doc: history.add(doc["url"])
                    if "url_hash" in doc: history.add(doc["url_hash"])
                if history:
                    return history
            except Exception:
                pass

        if self.history_file.exists():
            try:
                data = json.loads(self.history_file.read_text(encoding="utf-8"))
                return set(data.get("downloaded_urls", []))
            except Exception:
                return set()
        return history

    def _save_download_history(self):
        """Salva o histórico atualizado de downloads."""
        data = {
            "updated_at": datetime.now().isoformat(),
            "total_items": len(self.downloaded_history),
            "downloaded_urls": list(self.downloaded_history)
        }
        self.history_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _mark_as_downloaded(self, url: str, filename: str = None, media_type: str = None):
        """Marca uma URL/Mídia como baixada no MongoDB e no histórico local."""
        url_hash = self._url_hash(url)
        self.downloaded_history.add(url)
        self.downloaded_history.add(url_hash)

        mongo_col = self._init_mongo_client()
        if mongo_col is not None:
            try:
                mongo_col.update_one(
                    {"url_hash": url_hash},
                    {"$set": {
                        "url": url,
                        "url_hash": url_hash,
                        "filename": filename,
                        "media_type": media_type,
                        "downloaded_at": datetime.now().isoformat()
                    }},
                    upsert=True
                )
            except Exception:
                pass

        self._save_download_history()

    def _is_already_downloaded(self, url: str, target_filepath: Path = None) -> bool:
        """Verifica se a URL ou arquivo já foi baixado anteriormente."""
        if target_filepath and target_filepath.exists() and target_filepath.stat().st_size > 0:
            return True
        if url in self.downloaded_history or self._url_hash(url) in self.downloaded_history:
            return True
        return False

    def _url_hash(self, url: str) -> str:
        """Gera hash único de identificação da URL."""
        return hashlib.md5(url.encode()).hexdigest()[:16]

    def _session_path(self) -> Path:
        return self.session_dir / "facebook_session.json"

    def _has_session(self) -> bool:
        """Verifica e converte os cookies para o formato Playwright se necessário."""
        session_path = self._session_path()
        if not session_path.exists():
            return False

        # Tentar ler a sessão e verificar se precisa de conversão
        try:
            data = json.loads(session_path.read_text(encoding="utf-8"))
            
            # Se for uma lista simples (cookies brutos do navegador), converte
            if isinstance(data, list):
                console.print("[yellow]🔄 Convertendo cookies exportados do navegador para o formato Playwright...[/yellow]")
                formatted_cookies = []
                for c in data:
                    cookie = {
                        "name": c.get("name"),
                        "value": c.get("value"),
                        "domain": c.get("domain"),
                        "path": c.get("path", "/"),
                        "secure": c.get("secure", True),
                        "httpOnly": c.get("httpOnly", True),
                        "sameSite": "None" if c.get("sameSite") == "no_restriction" else c.get("sameSite", "Lax")
                    }
                    # Traduzir expirationDate para expires (unix timestamp)
                    if "expirationDate" in c:
                        cookie["expires"] = int(c["expirationDate"])
                    
                    # Limpar sameSite caso seja inválido
                    if cookie["sameSite"] not in ["Strict", "Lax", "None"]:
                        cookie["sameSite"] = "Lax"
                        
                    formatted_cookies.append(cookie)
                
                playwright_state = {
                    "cookies": formatted_cookies,
                    "origins": []
                }
                
                # Sobrescreve com o formato correto do Playwright
                session_path.write_text(json.dumps(playwright_state, ensure_ascii=False, indent=2))
                console.print("[green]✅ Cookies convertidos com sucesso![/green]")
            return True
        except Exception as e:
            console.print(f"[red]❌ Erro ao ler/converter sessão: {e}[/red]")
            return False



    # --------------------------------------------------------
    # Login
    # --------------------------------------------------------

    def login_interactive(self):
        """Abre o navegador para login. Tenta GUI (Headed) primeiro, cai para terminal se falhar."""
        self.session_dir.mkdir(parents=True, exist_ok=True)
        session_path = self._session_path()

        console.print("[bold blue]🔐 Iniciando assistente de autenticação do Facebook...[/bold blue]")

        with sync_playwright() as p:
            # Lança o Chromium local visível (headed) se DISPLAY estiver presente
            browser = None
            try:
                if not os.environ.get("DISPLAY"):
                    raise RuntimeError("Variável $DISPLAY ausente (sem ambiente gráfico)")

                console.print("ℹ️  Tentando abrir navegador com interface visual (headed)...")
                browser = p.chromium.launch(
                    headless=False,
                    args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
                )
                context = browser.new_context()
                page = context.new_page()
                page.goto("https://www.facebook.com")

                console.print("[bold yellow]👉 Faça login na janela do navegador que foi aberta.[/bold yellow]")
                input("\nPressione [ENTER] após ter feito login com sucesso no navegador para salvar...")

                context.storage_state(path=str(session_path))
                console.print(f"[bold green]✅ Login concluído! Sessão salva em {session_path}[/bold green]")
                return True
            except Exception as e:
                console.print(f"[yellow]⚠️  Navegador visual indisponível (Erro: {str(e)[:80]}).[/yellow]")
                console.print("[bold blue]💻 Iniciando login seguro via terminal (Modo Headless)...[/bold blue]")
                if browser:
                    try: browser.close()
                    except: pass

            # Fallback: Login interativo diretamente no prompt do terminal (Headless)
            try:
                import getpass
                browser = p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
                )
                context = browser.new_context(
                    viewport={"width": 1280, "height": 800},
                    user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
                page = context.new_page()
                page.goto("https://www.facebook.com")

                # Aceitar banner de cookies se visível
                try:
                    page.click('button[data-cookiebanner="accept_button"]', timeout=3000)
                except:
                    pass

                # Solicitar dados de login de forma interativa no terminal
                email = input("\n📧 Digite seu E-mail ou Telefone do Facebook: ")
                password = getpass.getpass("🔑 Digite sua Senha: ")

                console.print("⏳ Enviando credenciais...")
                page.fill('input[id="email"]', email)
                page.fill('input[id="pass"]', password)
                page.click('button[name="login"]')

                page.wait_for_timeout(6000)

                # Checar se pede Código 2FA (Checkpoint)
                if "checkpoint" in page.url or page.locator('input[id="approvals_code"]').is_visible() or page.locator('input[type="text"]').is_visible():
                    console.print("[bold yellow]🔑 Autenticação de 2 Fatores (2FA) detectada![/bold yellow]")
                    code = input("Digite o código de verificação enviado/gerado do 2FA: ")

                    if page.locator('input[id="approvals_code"]').is_visible():
                        page.fill('input[id="approvals_code"]', code)
                        page.click('button[id="checkpointSubmitButton"]')
                    else:
                        # Tentar input padrão
                        try:
                            page.locator('input[type="text"]').fill(code)
                            page.locator('button[type="submit"]').click()
                        except:
                            page.fill('input', code)
                            page.click('button')

                    page.wait_for_timeout(6000)

                # Validar sucesso do login
                cookies = context.cookies()
                has_user_cookie = any(c['name'] == 'c_user' for c in cookies)

                if has_user_cookie or "feed" in page.url or page.locator('a[href*="/me/"]').is_visible():
                    context.storage_state(path=str(session_path))
                    console.print(f"[bold green]✅ Login realizado com sucesso! Sessão salva em {session_path}[/bold green]")
                    return True
                else:
                    console.print("[bold red]❌ Falha na autenticação. Verifique suas credenciais e tente novamente.[/bold red]")
                    # Salvar imagem da tela do erro para auditoria
                    self.session_dir.mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(self.session_dir / "login_error.png"))
                    console.print("📷 Imagem do erro salva em: data/scraper/session/login_error.png")
                    return False
            except Exception as ex:
                console.print(f"[bold red]❌ Erro crítico no login do terminal: {ex}[/bold red]")
                return False
            finally:
                if browser:
                    browser.close()


    # --------------------------------------------------------
    # Coleta de URLs
    # --------------------------------------------------------

    def _extract_video_urls(self, page) -> list[dict]:
        """Extrai URLs de vídeos da página atual."""
        videos = page.evaluate("""() => {
            const results = [];
            
            // Buscar elementos de vídeo
            const videoElements = document.querySelectorAll('video');
            videoElements.forEach(video => {
                const src = video.src || video.querySelector('source')?.src;
                if (src && !src.startsWith('blob:')) {
                    results.push({
                        url: src,
                        type: 'video_element',
                        poster: video.poster || null
                    });
                }
            });

            // Buscar links para vídeos do Facebook
            const links = document.querySelectorAll('a[href*="/videos/"], a[href*="/watch/"], a[href*="/reel/"]');
            links.forEach(link => {
                const href = link.href;
                if (href && !results.some(r => r.url === href)) {
                    results.push({
                        url: href,
                        type: 'video_link',
                        text: link.textContent?.trim()?.substring(0, 100) || null
                    });
                }
            });

            return results;
        }""")
        return videos

    def _extract_image_urls(self, page) -> list[dict]:
        """Extrai URLs de imagens da página atual."""
        images = page.evaluate("""() => {
            const results = [];
            const seen = new Set();

            // Buscar imagens em posts (exclui ícones, avatares pequenos)
            const imgElements = document.querySelectorAll('img');
            imgElements.forEach(img => {
                const src = img.src;
                if (!src || seen.has(src)) return;

                // Filtrar imagens muito pequenas (ícones, emojis)
                const width = img.naturalWidth || img.width || 0;
                const height = img.naturalHeight || img.height || 0;
                if (width < 200 && height < 200) return;

                // Filtrar imagens de perfil/sistema do Facebook
                if (src.includes('emoji') || src.includes('rsrc.php')) return;

                seen.add(src);
                results.push({
                    url: src,
                    alt: img.alt || null,
                    width: width,
                    height: height
                });
            });

            // Buscar links para fotos de alta resolução
            const photoLinks = document.querySelectorAll('a[href*="/photo"], a[href*="fbid="]');
            photoLinks.forEach(link => {
                const href = link.href;
                if (href && !seen.has(href)) {
                    seen.add(href);
                    results.push({
                        url: href,
                        type: 'photo_link',
                        text: link.textContent?.trim()?.substring(0, 100) || null
                    });
                }
            });

            return results;
        }""")
        return images

    def _extract_profile_info(self, page) -> dict:
        """Extrai informações básicas do perfil."""
        info = page.evaluate("""() => {
            const result = {};

            // Nome do perfil (h1 geralmente contém o nome)
            const h1 = document.querySelector('h1');
            if (h1) result.name = h1.textContent.trim();

            // URL atual
            result.url = window.location.href;

            // Título da página
            result.page_title = document.title;

            return result;
        }""")
        return info

    # --------------------------------------------------------
    # Scroll e Coleta
    # --------------------------------------------------------

    def collect_media(self):
        """Navega ao perfil-alvo e coleta URLs de mídia via scroll."""
        if not self._has_session():
            console.print("[bold red]❌ Nenhuma sessão encontrada. Execute com --login primeiro.[/bold red]")
            sys.exit(1)

        console.print(f"\n[bold blue]🔍 Coletando mídia de:[/bold blue] {self.target_url}")

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=self.headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ]
            )

            context = browser.new_context(
                storage_state=str(self._session_path()),
                viewport={"width": 1366, "height": 768},
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                locale="pt-BR",
                timezone_id="America/Sao_Paulo",
            )

            page = context.new_page()

            try:
                # Navegar ao perfil
                console.print("[yellow]⏳ Carregando perfil...[/yellow]")
                page.goto(self.target_url, timeout=PAGE_LOAD_TIMEOUT)
                time.sleep(3)

                # Fechar popups/modais que podem aparecer
                self._dismiss_popups(page)

                # Extrair info do perfil
                self.profile_info = self._extract_profile_info(page)
                console.print(f"[green]✅ Perfil carregado:[/green] {self.profile_info.get('name', 'N/A')}")

                # Scroll e coleta progressiva
                seen_video_urls = set()
                seen_image_urls = set()
                last_height = 0
                no_change_count = 0

                console.print(f"\n[bold]📜 Iniciando scroll (máx {self.max_scrolls} iterações)...[/bold]\n")

                for scroll_num in range(1, self.max_scrolls + 1):
                    # Scroll para baixo
                    page.evaluate("window.scrollBy(0, window.innerHeight * 2)")
                    time.sleep(SCROLL_PAUSE)

                    # Coletar vídeos
                    if not self.only_images:
                        videos = self._extract_video_urls(page)
                        for v in videos:
                            url = v.get("url", "")
                            if url and url not in seen_video_urls:
                                seen_video_urls.add(url)
                                v["collected_at"] = datetime.now().isoformat()
                                v["scroll_position"] = scroll_num
                                self.collected_videos.append(v)

                    # Coletar imagens
                    if not self.only_videos:
                        images = self._extract_image_urls(page)
                        for img in images:
                            url = img.get("url", "")
                            if url and url not in seen_image_urls:
                                seen_image_urls.add(url)
                                img["collected_at"] = datetime.now().isoformat()
                                img["scroll_position"] = scroll_num
                                self.collected_images.append(img)

                    # Verificar se chegamos ao fim
                    new_height = page.evaluate("document.documentElement.scrollHeight")
                    if new_height == last_height:
                        no_change_count += 1
                        if no_change_count >= 5:
                            console.print(f"[yellow]⚠️  Fim do conteúdo detectado no scroll {scroll_num}[/yellow]")
                            break
                    else:
                        no_change_count = 0
                    last_height = new_height

                    # Progresso
                    if scroll_num % 5 == 0:
                        console.print(
                            f"  📊 Scroll {scroll_num}/{self.max_scrolls} — "
                            f"Vídeos: {len(self.collected_videos)}, "
                            f"Imagens: {len(self.collected_images)}"
                        )

                    # Fechar popups que podem aparecer durante scroll
                    if scroll_num % 10 == 0:
                        self._dismiss_popups(page)

                # Atualizar sessão
                context.storage_state(path=str(self._session_path()))

            except PlaywrightTimeout:
                console.print("[bold red]❌ Timeout ao carregar o perfil[/bold red]")
                self.errors.append("Timeout ao carregar perfil")
            except Exception as e:
                console.print(f"[bold red]❌ Erro: {e}[/bold red]")
                self.errors.append(str(e))
            finally:
                browser.close()

        # Resumo da coleta
        console.print(f"\n[bold green]📦 Coleta concluída![/bold green]")
        console.print(f"  • Vídeos encontrados: {len(self.collected_videos)}")
        console.print(f"  • Imagens encontradas: {len(self.collected_images)}")

    def _dismiss_popups(self, page):
        """Tenta fechar popups/modais comuns do Facebook."""
        selectors = [
            # Botão "Fechar" de modais
            '[aria-label="Fechar"]',
            '[aria-label="Close"]',
            # Cookie consent
            'button[data-cookiebanner="accept_button"]',
            'button[data-testid="cookie-policy-manage-dialog-accept-button"]',
            # Login wall
            '[role="dialog"] [aria-label="Fechar"]',
        ]
        for selector in selectors:
            try:
                el = page.query_selector(selector)
                if el and el.is_visible():
                    el.click()
                    time.sleep(0.5)
            except Exception:
                pass

    # --------------------------------------------------------
    # Download
    # --------------------------------------------------------

    def download_videos(self):
        """Baixa vídeos coletados usando yt-dlp sem duplicar downloads."""
        if not self.collected_videos:
            console.print("[yellow]⚠️  Nenhum vídeo para baixar[/yellow]")
            return

        console.print(f"\n[bold blue]⬇️  Baixando vídeos (com desduplicação ativada)...[/bold blue]")

        # Exportar cookies para yt-dlp
        cookies_path = self.session_dir / "cookies.txt"
        self._export_cookies_for_ytdlp(cookies_path)

        downloaded = 0
        skipped = 0
        for i, video in enumerate(self.collected_videos, 1):
            url = video.get("url", "")
            if not url:
                continue

            # Checar se já foi baixado anteriormente
            if self._is_already_downloaded(url):
                skipped += 1
                video["downloaded"] = True
                video["download_method"] = "skipped (histórico)"
                continue

            # Se é um link de página de vídeo do Facebook (não URL direta)
            if "facebook.com" in url and ("/videos/" in url or "/watch/" in url or "/reel/" in url):
                try:
                    console.print(f"  [{i}/{len(self.collected_videos)}] Baixando vídeo: {url[:80]}...")
                    result = subprocess.run(
                        [
                            "yt-dlp",
                            "--cookies", str(cookies_path),
                            "--output", str(self.output_videos / "%(title).80s_%(id)s.%(ext)s"),
                            "--format", "best[ext=mp4]/best",
                            "--no-overwrites",
                            "--write-info-json",
                            "--socket-timeout", "30",
                            "--retries", "3",
                            url,
                        ],
                        capture_output=True,
                        text=True,
                        timeout=300,
                    )
                    if result.returncode == 0:
                        downloaded += 1
                        video["downloaded"] = True
                        video["download_method"] = "yt-dlp"
                        self._mark_as_downloaded(url)
                        console.print(f"  [green]✅ Sucesso[/green]")
                    else:
                        video["downloaded"] = False
                        video["error"] = result.stderr[:200]
                        console.print(f"  [red]❌ Falha: {result.stderr[:100]}[/red]")
                except subprocess.TimeoutExpired:
                    video["downloaded"] = False
                    video["error"] = "Timeout (5 min)"
                    console.print(f"  [red]❌ Timeout[/red]")
                except FileNotFoundError:
                    console.print("[bold red]❌ yt-dlp não encontrado. Instale com: pip install yt-dlp[/bold red]")
                    break

            elif url.startswith("http") and not url.startswith("blob:"):
                # URL direta de vídeo — baixar com requests
                try:
                    import requests
                    filename = self._url_to_filename(url, "mp4")
                    filepath = self.output_videos / filename

                    if self._is_already_downloaded(url, filepath):
                        skipped += 1
                        video["downloaded"] = True
                        video["download_method"] = "skipped (existente)"
                        self._mark_as_downloaded(url)
                        continue

                    console.print(f"  [{i}/{len(self.collected_videos)}] Baixando vídeo direto: {filename}")
                    resp = requests.get(url, timeout=120, stream=True)
                    if resp.status_code == 200:
                        with open(filepath, "wb") as f:
                            for chunk in resp.iter_content(chunk_size=8192):
                                f.write(chunk)
                        downloaded += 1
                        video["downloaded"] = True
                        video["download_method"] = "direct"
                        self._mark_as_downloaded(url)
                        console.print(f"  [green]✅ Sucesso[/green]")
                    else:
                        video["downloaded"] = False
                        video["error"] = f"HTTP {resp.status_code}"
                except Exception as e:
                    video["downloaded"] = False
                    video["error"] = str(e)

        console.print(f"\n[bold green]✅ Vídeos: {downloaded} novos baixados, {skipped} pulados (já existentes)[/bold green]")

    def download_images(self):
        """Baixa imagens coletadas sem duplicar downloads."""
        if not self.collected_images:
            console.print("[yellow]⚠️  Nenhuma imagem para baixar[/yellow]")
            return

        # Filtrar apenas URLs diretas de imagem (não links para páginas de foto)
        direct_images = [
            img for img in self.collected_images
            if img.get("url", "").startswith("http")
            and not "/photo" in img.get("url", "")
            and not "fbid=" in img.get("url", "")
        ]

        console.print(f"\n[bold blue]⬇️  Baixando imagens (com desduplicação ativada)...[/bold blue]")

        import requests

        downloaded = 0
        skipped = 0
        for i, img in enumerate(direct_images, 1):
            url = img.get("url", "")
            if not url:
                continue

            filename = self._url_to_filename(url, "jpg")
            filepath = self.output_images / filename

            if self._is_already_downloaded(url, filepath):
                skipped += 1
                img["downloaded"] = True
                img["download_method"] = "skipped (existente)"
                self._mark_as_downloaded(url)
                continue

            try:
                resp = requests.get(url, timeout=60, stream=True)
                if resp.status_code == 200:
                    with open(filepath, "wb") as f:
                        for chunk in resp.iter_content(chunk_size=8192):
                            f.write(chunk)
                    downloaded += 1
                    img["downloaded"] = True
                    img["download_method"] = "direct"
                    self._mark_as_downloaded(url)
                else:
                    img["downloaded"] = False
                    img["error"] = f"HTTP {resp.status_code}"
            except Exception as e:
                img["downloaded"] = False
                img["error"] = str(e)

            # Progresso a cada 20
            if i % 20 == 0:
                console.print(f"  📊 {i}/{len(direct_images)} processadas ({skipped} puladas)...")

        console.print(f"\n[bold green]✅ Imagens: {downloaded} novas baixadas, {skipped} puladas (já existentes)[/bold green]")


    # --------------------------------------------------------
    # Utilitários
    # --------------------------------------------------------

    def _url_to_filename(self, url: str, default_ext: str) -> str:
        """Gera nome de arquivo a partir de uma URL."""
        url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
        parsed = urlparse(url)
        path = parsed.path
        ext = Path(path).suffix.lower()

        valid_exts = {".mp4", ".mov", ".avi", ".webm", ".mkv", ".jpg", ".jpeg", ".png", ".gif", ".webp"}
        if ext not in valid_exts:
            ext = f".{default_ext}"

        return f"fb_{url_hash}{ext}"

    def _export_cookies_for_ytdlp(self, output_path: Path):
        """Converte a sessão do Playwright para formato Netscape cookies.txt."""
        if not self._session_path().exists():
            return
 
        session_data = json.loads(self._session_path().read_text())
        cookies = session_data.get("cookies", [])
 
        lines = ["# Netscape HTTP Cookie File", "# Generated by PipelineFace scraper", ""]
        
        # timestamp futuro padrão (daqui a 1 ano) para cookies sem data válida (-1)
        future_expiration = str(int(time.time() + 31536000))

        for cookie in cookies:
            domain = cookie.get("domain", "")
            if "facebook" not in domain and "fbcdn" not in domain:
                continue
 
            flag = "TRUE" if domain.startswith(".") else "FALSE"
            path = cookie.get("path", "/")
            secure = "TRUE" if cookie.get("secure", False) else "FALSE"
            
            # Ajustar expirações inválidas
            expires_val = cookie.get("expires", 0)
            if expires_val == -1 or expires_val <= 0:
                expires = future_expiration
            else:
                expires = str(int(expires_val))
                
            name = cookie.get("name", "")
            value = cookie.get("value", "")
 
            lines.append(f"{domain}\t{flag}\t{path}\t{secure}\t{expires}\t{name}\t{value}")
 
        output_path.write_text("\n".join(lines))


    def save_metadata(self):
        """Salva metadados da coleta em JSON."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        profile_name = self.profile_info.get("name", "unknown").replace(" ", "_")

        metadata = {
            "scrape_info": {
                "target_url": self.target_url,
                "profile_name": self.profile_info.get("name"),
                "scraped_at": datetime.now().isoformat(),
                "max_scrolls": self.max_scrolls,
                "errors": self.errors,
            },
            "statistics": {
                "total_videos_found": len(self.collected_videos),
                "total_images_found": len(self.collected_images),
                "videos_downloaded": sum(1 for v in self.collected_videos if v.get("downloaded")),
                "images_downloaded": sum(1 for i in self.collected_images if i.get("downloaded")),
            },
            "videos": self.collected_videos,
            "images": self.collected_images,
        }

        filename = f"scrape_{profile_name}_{timestamp}.json"
        filepath = self.output_metadata / filename
        filepath.write_text(json.dumps(metadata, ensure_ascii=False, indent=2))
        console.print(f"\n[bold green]📋 Metadados salvos em:[/bold green] {filepath}")

    def print_summary(self):
        """Exibe resumo final formatado."""
        console.print("\n" + "=" * 60)
        console.print("[bold]📊 RESUMO DA COLETA[/bold]")
        console.print("=" * 60)
        console.print(f"  Perfil:   {self.profile_info.get('name', 'N/A')}")
        console.print(f"  URL:      {self.target_url}")
        console.print(f"  Vídeos:   {len(self.collected_videos)} encontrados")
        console.print(f"  Imagens:  {len(self.collected_images)} encontradas")

        if self.errors:
            console.print(f"\n  [red]⚠️  {len(self.errors)} erro(s) durante a coleta[/red]")
            for err in self.errors[:5]:
                console.print(f"     • {err}")

        console.print("")
        console.print(f"  📂 Vídeos em:    {self.output_videos}")
        console.print(f"  📂 Imagens em:   {self.output_images}")
        console.print(f"  📂 Metadados em: {self.output_metadata}")
        console.print("=" * 60 + "\n")


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="🧠 PipelineFace — Scraper de perfis do Facebook",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  # Primeira vez (login interativo):
  python facebook_scraper.py --target https://www.facebook.com/usuario --login

  # Coleta com sessão salva:
  python facebook_scraper.py --target https://www.facebook.com/usuario

  # Apenas vídeos, com mais scroll:
  python facebook_scraper.py --target https://www.facebook.com/usuario --only-videos --max-scrolls 100
        """,
    )

    parser.add_argument(
        "--target",
        type=str,
        help="URL do perfil-alvo no Facebook",
    )
    parser.add_argument(
        "--login",
        action="store_true",
        help="Abrir navegador para login interativo (primeira vez)",
    )
    parser.add_argument(
        "--max-scrolls",
        type=int,
        default=int(os.environ.get("SCRAPER_MAX_SCROLLS", DEFAULT_MAX_SCROLLS)),
        help=f"Número máximo de scrolls (padrão: {DEFAULT_MAX_SCROLLS})",
    )
    parser.add_argument(
        "--only-videos",
        action="store_true",
        help="Coletar apenas vídeos",
    )
    parser.add_argument(
        "--only-images",
        action="store_true",
        help="Coletar apenas imagens",
    )
    parser.add_argument(
        "--no-download",
        action="store_true",
        help="Apenas coletar URLs, não baixar arquivos",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=True,
        help="Executar navegador sem interface gráfica (padrão: True)",
    )
    parser.add_argument(
        "--visible",
        action="store_true",
        help="Executar navegador com interface gráfica visível",
    )
    parser.add_argument(
        "--session-dir",
        type=str,
        default=os.environ.get("SCRAPER_SESSION_DIR", DEFAULT_SESSION_DIR),
        help="Diretório para sessão salva",
    )
    parser.add_argument(
        "--output-videos",
        type=str,
        default=DEFAULT_OUTPUT_VIDEOS,
        help="Diretório de saída para vídeos",
    )
    parser.add_argument(
        "--output-images",
        type=str,
        default=DEFAULT_OUTPUT_IMAGES,
        help="Diretório de saída para imagens",
    )

    args = parser.parse_args()

    # Banner
    console.print("\n[bold blue]" + "=" * 50 + "[/bold blue]")
    console.print("[bold blue]  🧠 PipelineFace — Facebook Scraper[/bold blue]")
    console.print("[bold blue]" + "=" * 50 + "[/bold blue]")

    headless = args.headless and not args.visible

    scraper = FacebookScraper(
        target_url=args.target or "",
        session_dir=args.session_dir,
        output_videos=args.output_videos,
        output_images=args.output_images,
        max_scrolls=args.max_scrolls,
        only_videos=args.only_videos,
        only_images=args.only_images,
        headless=headless,
    )

    # Fluxo de execução
    if args.login:
        scraper.login_interactive()
        if not args.target:
            console.print("\n[green]✅ Login salvo! Agora execute novamente com --target para coletar dados.[/green]")
            return

    if not args.target:
        parser.print_help()
        console.print("\n[red]❌ É necessário especificar --target com a URL do perfil.[/red]")
        sys.exit(1)

    # Coletar URLs
    scraper.collect_media()

    # Download
    if not args.no_download:
        if not args.only_images:
            scraper.download_videos()
        if not args.only_videos:
            scraper.download_images()

    # Salvar metadados e resumo
    scraper.save_metadata()
    scraper.print_summary()


if __name__ == "__main__":
    main()
