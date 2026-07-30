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
import uuid
from typing import Optional, List, Dict
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

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_VIDEOS = str(PROJECT_ROOT / "data" / "input" / "videos")
DEFAULT_OUTPUT_IMAGES = str(PROJECT_ROOT / "data" / "input" / "images")
DEFAULT_OUTPUT_METADATA = str(PROJECT_ROOT / "data" / "input" / "metadata")
DEFAULT_SESSION_DIR = str(PROJECT_ROOT / "data" / "scraper" / "session")
DEFAULT_MAX_SCROLLS = 50
DEFAULT_SCROLL_PAUSE = 2.5  # segundos entre scrolls
SCROLL_PAUSE = DEFAULT_SCROLL_PAUSE  # compat backward
PAGE_LOAD_TIMEOUT = 30000  # ms


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
        session_dir: str = None,
        output_videos: str = DEFAULT_OUTPUT_VIDEOS,
        output_images: str = DEFAULT_OUTPUT_IMAGES,
        output_metadata: str = DEFAULT_OUTPUT_METADATA,
        max_scrolls: int = None,
        only_videos: bool = False,
        only_images: bool = False,
        headless: bool = True,
    ):
        # Carregar config do MongoDB com fallback para defaults
        cfg = _get_mongo_config()
        resolved_max_scrolls = max_scrolls if max_scrolls is not None else int(cfg.get("scraper_max_scrolls", DEFAULT_MAX_SCROLLS))
        resolved_session_dir = session_dir or cfg.get("scraper_session_dir", DEFAULT_SESSION_DIR)
        self.scroll_pause = float(cfg.get("scraper_scroll_pause", DEFAULT_SCROLL_PAUSE))
        self.webhook_url = cfg.get("webhook_url", "http://localhost:8000/api/webhooks/execution-event")

        self.target_url = target_url.rstrip("/")
        self.session_dir = Path(resolved_session_dir)
        self.output_videos = Path(output_videos)
        self.output_images = Path(output_images)
        self.output_metadata = Path(output_metadata)
        self.max_scrolls = resolved_max_scrolls
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
            return client["pipelineface"]
        except Exception:
            return None

    def _save_pipeline_run(self, run_data: dict):
        """Cria ou atualiza a execução na coleção pipeline_runs do MongoDB."""
        db = self._init_mongo_client()
        if db is None:
            return
        try:
            db["pipeline_runs"].update_one(
                {"run_id": run_data["run_id"]},
                {"$set": run_data},
                upsert=True
            )
        except Exception as e:
            console.print(f"[yellow]⚠️ Falha ao registrar pipeline_run do scraper no MongoDB: {e}[/yellow]")

    def _load_download_history(self) -> set:
        """Carrega o histórico de URLs e hashes já baixados do MongoDB."""
        history = set()
        db = self._init_mongo_client()
        if db is not None:
            try:
                for doc in db["download_history"].find({}, {"url": 1, "url_hash": 1}):
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

    def _mark_as_downloaded(self, url: str, filename: str = None, media_type: str = None, post_id: str = None, media_id: str = None):
        """Marca uma URL/Mídia como baixada no MongoDB e no histórico local."""
        url_hash = self._url_hash(url)
        self.downloaded_history.add(url)
        self.downloaded_history.add(url_hash)

        db = self._init_mongo_client()
        if db is not None:
            try:
                update_data = {
                    "url": url,
                    "url_hash": url_hash,
                    "filename": filename,
                    "media_type": media_type,
                    "downloaded_at": datetime.now().isoformat()
                }
                if post_id:
                    update_data["post_id"] = post_id
                if media_id:
                    update_data["media_id"] = media_id

                db["download_history"].update_one(
                    {"url_hash": url_hash},
                    {"$set": update_data},
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

    def _extract_post_id(self, url: str) -> Optional[str]:
        """Extrai um identificador único de post a partir da URL do Facebook."""
        if not url:
            return None

        # Rejeitar links genéricos de navegação do Facebook (abas/menus/bens do sistema)
        url_lower = url.lower()
        ignored_substrings = [
            "/reel/?", "/reel/tab", "/watch/", "/stories/", "/gaming/",
            "/marketplace/", "/groups/", "/friends/", "/bookmarks/",
            "/messages/", "/notifications", "/home.php", "/login"
        ]
        for ign in ignored_substrings:
            if ign in url_lower and not re.search(r'/reel/\w{8,}', url):
                return None

        patterns = [
            r'/posts/(pfbid\w+)',
            r'/posts/(\d+)',
            r'/videos/(\d+)',
            r'/reel/(\w+)',
            r'/photo/?\?fbid=(\d+)',
            r'/photos/[^/]+/(\d+)',
            r'story_fbid=(\d+)',
            r'fbid=(\d+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                extracted_id = match.group(1)
                if extracted_id not in ["tab", "index", "feed", "watch"]:
                    return extracted_id

        # Se for uma URL direta de imagem CDN ou mídia sem id explicito no FB
        if "scontent" in url or "fbcdn" in url:
            return hashlib.md5(url.encode()).hexdigest()[:16]

        return None



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

        """Extrai URLs de vídeos da página atual estritamente do feed do perfil."""
        videos = page.evaluate("""() => {
            const results = [];
            const mainContainer = document.querySelector('div[role="main"]') || document.querySelector('main') || document.body;
            
            // Buscar elementos de vídeo
            const videoElements = mainContainer.querySelectorAll('video');
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

            // Buscar links para vídeos/reels específicos do Facebook no feed
            const links = mainContainer.querySelectorAll('a[href*="/videos/"], a[href*="/watch/"], a[href*="/reel/"]');
            links.forEach(link => {
                const href = link.href;
                if (!href) return;
                
                // Descartar links genéricos e notificações
                if (href.includes('/reel/?') || href.endsWith('/reel/') || href.endsWith('/watch/') || href.includes('notif')) return;

                if (!results.some(r => r.url === href)) {
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
        """Extrai URLs de imagens da página atual estritamente do feed do perfil."""
        images = page.evaluate("""() => {
            const results = [];
            const seen = new Set();
            const mainContainer = document.querySelector('div[role="main"]') || document.querySelector('main') || document.body;

            // Buscar imagens em posts no feed
            const imgElements = mainContainer.querySelectorAll('img');
            imgElements.forEach(img => {
                const src = img.src;
                if (!src || seen.has(src)) return;

                // Filtrar imagens de perfil/sistema/emojis do Facebook
                if (src.includes('emoji') || src.includes('rsrc.php')) return;

                seen.add(src);
                results.push({
                    url: src,
                    alt: img.alt || null,
                    width: img.naturalWidth || img.width || 0,
                    height: img.naturalHeight || img.height || 0
                });
            });

            // Buscar links para fotos no feed
            const photoLinks = mainContainer.querySelectorAll('a[href*="/photo"], a[href*="fbid="]');
            photoLinks.forEach(link => {
                const href = link.href;
                if (!href || href.includes('notif')) return;

                if (!seen.has(href)) {
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

    def _extract_post_links(self, page) -> list[dict]:
        """Extrai todas as URLs de posts/mídias diretamente do feed principal ([role=main])."""
        links = page.evaluate("""() => {
            const results = [];
            const seen = new Set();
            const mainContainer = document.querySelector('div[role="main"]') || document.querySelector('main') || document.body;
            
            const anchors = mainContainer.querySelectorAll('a[href*="/posts/"], a[href*="/videos/"], a[href*="/reel/"], a[href*="fbid="], a[href*="story_fbid="], a[href*="/photo"]');
            anchors.forEach(a => {
                const href = a.href;
                if (!href || seen.has(href)) return;
                
                // Descartar links de notificações, menus laterais e comentários de terceiros
                if (href.includes('notif') || href.includes('/reel/?') || href.includes('ref=bookmarks')) return;

                seen.add(href);
                const text = a.textContent ? a.textContent.trim().substring(0, 150) : "";
                results.push({ url: href, text: text });
            });
            
            return results;
        }""")
        return links

    def _clean_facebook_url(self, url: str) -> str:
        """Limpa parâmetros de rastreamento (notif, comment_id, __cft__, __tn__) mantendo a URL direta do post/reel/foto."""
        if not url:
            return url
        try:
            parsed = urlparse(url)
            if "/reel/" in parsed.path or "/posts/" in parsed.path or "/videos/" in parsed.path:
                return f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
        except Exception:
            pass
        return url

    def _extract_profile_info(self, page) -> dict:
        """Extrai informações básicas do perfil a partir do container principal."""
        info = page.evaluate("""() => {
            const result = {};
            const mainContainer = document.querySelector('div[role="main"]') || document.querySelector('main') || document;

            const h1s = mainContainer.querySelectorAll('h1');
            for (const h1 of h1s) {
                const txt = h1.textContent.trim();
                if (txt && txt !== "Notificações" && txt !== "Facebook" && txt !== "Menu" && txt !== "Feed") {
                    result.name = txt;
                    break;
                }
            }

            result.url = window.location.href;
            result.page_title = document.title;
            return result;
        }""")

        # Fallback de nome de perfil baseado no slug da URL
        if not info.get("name") or info.get("name") in ["Notificações", "Facebook", "Menu", "Feed"]:
            slug = self.target_url.rstrip("/").split("/")[-1]
            info["name"] = slug.replace(".", " ").title()

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
    # Step 1: Listagem e Catalogação de Posts no MongoDB
    # --------------------------------------------------------

    def list_posts(self):
        """Navega pelo perfil-alvo, cataloga todos os posts na coleção profile_posts do MongoDB e gera eventos de telemetria."""
        if not self._has_session():
            console.print("[bold red]❌ Nenhuma sessão encontrada. Execute com --login primeiro.[/bold red]")
            sys.exit(1)

        console.print(f"\n[bold blue]📋 Catalogando posts de:[/bold blue] {self.target_url}")
        send_telemetry_event(self.run_id, "LIST_POSTS_START", status="in_progress", target_url=self.target_url, message=f"Iniciando catalogação de posts em {self.target_url}")

        db = self._init_mongo_client()
        cataloged_count = 0
        new_posts_count = 0

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=self.headless,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-dev-shm-usage"]
            )
            context = browser.new_context(
                storage_state=str(self._session_path()),
                viewport={"width": 1366, "height": 768},
                user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale="pt-BR",
                timezone_id="America/Sao_Paulo",
            )
            page = context.new_page()

            try:
                page.goto(self.target_url, timeout=PAGE_LOAD_TIMEOUT)
                time.sleep(3)
                self._dismiss_popups(page)
                self.profile_info = self._extract_profile_info(page)

                profile_name = self.profile_info.get("name")
                if not profile_name or profile_name in ["Notificações", "Facebook", "Menu", "Feed"]:
                    slug = self.target_url.rstrip("/").split("/")[-1]
                    profile_name = slug.replace(".", " ").title()

                console.print(f"[green]✅ Perfil carregado:[/green] {profile_name}")


                seen_post_ids = set()
                last_height = 0
                no_change_count = 0

                # Para o Step 1 (catalogar todos os posts), garante limite alto de scrolls ate o fim da pagina
                max_list_scrolls = max(self.max_scrolls, 200)

                console.print(f"\n[bold]📜 Iniciando scroll contínuo para catalogar TODOS os posts (até {max_list_scrolls} iterações ou fim do feed)...[/bold]\n")

                for scroll_num in range(1, max_list_scrolls + 1):
                    page.evaluate("window.scrollBy(0, window.innerHeight * 2)")
                    time.sleep(self.scroll_pause)


                    # Extrair elementos de mídia e links de post da página
                    page_videos = self._extract_video_urls(page)
                    page_images = self._extract_image_urls(page)
                    page_post_links = self._extract_post_links(page)

                    # Agrupar mídias por post (usando URL do link ou hash da mídia)
                    raw_items = []
                    for pl in page_post_links:
                        url = pl.get("url", "")
                        if url:
                            raw_items.append({"url": url, "type": "post", "text": pl.get("text")})
                    for v in page_videos:
                        url = v.get("url", "")
                        if url:
                            raw_items.append({"url": url, "type": "video", "text": v.get("text")})
                    for img in page_images:
                        url = img.get("url", "")
                        if url:
                            raw_items.append({"url": url, "type": "image", "text": img.get("alt")})


                    for item in raw_items:
                        item_url = self._clean_facebook_url(item["url"])
                        post_id = self._extract_post_id(item_url)
                        if not post_id or post_id in seen_post_ids:
                            continue

                        seen_post_ids.add(post_id)

                        # Gerar media_id único
                        media_id = f"m_{post_id[:16]}_0"
                        media_item = {
                            "media_id": media_id,
                            "url": item_url,
                            "type": item["type"],
                            "filename": None,
                            "downloaded": False,
                            "download_error": None
                        }


                        post_type = item["type"]
                        post_doc = {
                            "post_id": post_id,
                            "profile_url": self.target_url,
                            "profile_name": profile_name,
                            "post_url": item_url if ("facebook.com" in item_url and ("/posts/" in item_url or "/videos/" in item_url or "/reel/" in item_url)) else f"{self.target_url}/posts/{post_id}",
                            "post_type": post_type,
                            "status": "pending",
                            "media_items": [media_item],
                            "post_text_preview": item_url[:100],
                            "scroll_position": scroll_num,
                            "discovered_at": datetime.now().isoformat(),
                            "updated_at": datetime.now().isoformat(),
                            "error_message": None
                        }

                        if db is not None:
                            try:
                                res = db["profile_posts"].update_one(
                                    {"post_id": post_id},
                                    {
                                        "$set": {
                                            "profile_url": self.target_url,
                                            "profile_name": profile_name,
                                            "post_url": post_doc["post_url"],
                                            "post_type": post_type,
                                            "media_items": post_doc["media_items"],
                                            "scroll_position": scroll_num,
                                            "updated_at": datetime.now().isoformat()
                                        },
                                        "$setOnInsert": {
                                            "status": "pending",
                                            "discovered_at": datetime.now().isoformat(),
                                            "error_message": None
                                        }
                                    },
                                    upsert=True
                                )
                                if res.upserted_id:
                                    new_posts_count += 1
                                cataloged_count += 1
                            except Exception as mongo_err:
                                console.print(f"[yellow]⚠️ Erro ao salvar post no MongoDB: {mongo_err}[/yellow]")

                        send_telemetry_event(
                            self.run_id, "POST_DISCOVERED", status="info", target_url=self.target_url,
                            message=f"Post descoberto: {post_id}",
                            metrics={"post_id": post_id, "post_type": post_type, "scroll": scroll_num}
                        )

                    # Log de progresso a cada 5 iterações
                    if scroll_num % 5 == 0 or scroll_num == 1:
                        console.print(f"  📊 Scroll {scroll_num}/{max_list_scrolls} — {len(seen_post_ids)} posts descobertos até o momento...")

                    # Checar fim do conteúdo
                    new_height = page.evaluate("document.documentElement.scrollHeight")
                    if new_height == last_height:
                        no_change_count += 1
                        if no_change_count >= 5:
                            console.print(f"[yellow]⚠️ Fim do feed de posts detectado no scroll {scroll_num}.[/yellow]")
                            break
                    else:
                        no_change_count = 0
                    last_height = new_height


                    if scroll_num % 10 == 0:
                        self._dismiss_popups(page)

                context.storage_state(path=str(self._session_path()))

            except Exception as e:
                console.print(f"[bold red]❌ Erro durante listagem de posts: {e}[/bold red]")
                send_telemetry_event(self.run_id, "LIST_POSTS_ERROR", status="error", target_url=self.target_url, message=f"Erro na listagem: {e}")
                self.errors.append(str(e))
            finally:
                browser.close()

        console.print(f"\n[bold green]✅ Catalogação concluída! Total catalogados: {cataloged_count} ({new_posts_count} novos)[/bold green]")
        send_telemetry_event(
            self.run_id, "LIST_POSTS_COMPLETE", status="completed", target_url=self.target_url,
            message=f"Listagem concluída. {new_posts_count} novos posts catalogados.",
            metrics={"new_posts_count": new_posts_count, "cataloged_count": cataloged_count}
        )

    # --------------------------------------------------------
    # Step 2: Download em Lotes de Posts Pendentes
    # --------------------------------------------------------

    def download_pending(self, batch_size: int = 10):
        """Busca até N posts pendentes na coleção profile_posts e realiza o download das mídias em lote."""
        db = self._init_mongo_client()
        if db is None:
            console.print("[bold red]❌ Conexão com MongoDB necessária para download de pendentes.[/bold red]")
            return

        pending_docs = list(db["profile_posts"].find(
            {"profile_url": self.target_url, "status": "pending"},
            {"_id": 0}
        ).sort("discovered_at", 1).limit(batch_size))

        if not pending_docs:
            # Fallback: buscar qualquer pending sem filtro de profile_url exato
            pending_docs = list(db["profile_posts"].find(
                {"status": "pending"},
                {"_id": 0}
            ).sort("discovered_at", 1).limit(batch_size))

        if not pending_docs:
            console.print("[yellow]⚠️ Nenhum post pendente encontrado para download.[/yellow]")
            return

        total_pending = db["profile_posts"].count_documents({"status": "pending"})
        console.print(f"\n[bold blue]⬇️ Iniciando download em lote: {len(pending_docs)} posts (total pendentes no banco: {total_pending})[/bold blue]")

        send_telemetry_event(
            self.run_id, "DOWNLOAD_BATCH_START", status="in_progress", target_url=self.target_url,
            message=f"Iniciando lote de download ({len(pending_docs)} posts)",
            metrics={"batch_size": len(pending_docs), "total_pending": total_pending}
        )

        cookies_path = self.session_dir / "cookies.txt"
        self._export_cookies_for_ytdlp(cookies_path)

        success_count = 0
        error_count = 0

        for i, post in enumerate(pending_docs, 1):
            post_id = post["post_id"]
            media_items = post.get("media_items", [])
            console.print(f"\n[{i}/{len(pending_docs)}] 📦 Baixando post {post_id} ({len(media_items)} mídia(s))...")

            # Atualizar status para downloading
            db["profile_posts"].update_one({"post_id": post_id}, {"$set": {"status": "downloading", "updated_at": datetime.now().isoformat()}})
            send_telemetry_event(self.run_id, "POST_DOWNLOAD_START", status="in_progress", message=f"Baixando post {post_id}", metrics={"post_id": post_id})

            post_success = True
            downloaded_files = []

            for media in media_items:
                media_id = media.get("media_id", f"m_{post_id[:16]}_0")
                url = media.get("url", "")
                media_type = media.get("type", "image")

                if not url:
                    continue

                if self._is_already_downloaded(url):
                    console.print(f"  [yellow]⏭️ Mídia já baixada (histórico): {media_id}[/yellow]")
                    db["profile_posts"].update_one(
                        {"post_id": post_id, "media_items.media_id": media_id},
                        {"$set": {"media_items.$.downloaded": True, "updated_at": datetime.now().isoformat()}}
                    )
                    continue

                if media_type == "video":
                    if "facebook.com" in url and ("/videos/" in url or "/watch/" in url or "/reel/" in url):
                        try:
                            res = subprocess.run(
                                [
                                    "yt-dlp",
                                    "--cookies", str(cookies_path),
                                    "--output", str(self.output_videos / "%(title).80s_%(id)s.%(ext)s"),
                                    "--format", "best[ext=mp4]/best",
                                    "--no-overwrites",
                                    "--socket-timeout", "30",
                                    "--retries", "3",
                                    url,
                                ],
                                capture_output=True, text=True, timeout=300
                            )
                            if res.returncode == 0:
                                filename = f"fb_{self._url_hash(url)}.mp4"
                                self._mark_as_downloaded(url, filename=filename, media_type="video", post_id=post_id, media_id=media_id)
                                downloaded_files.append(filename)
                                db["profile_posts"].update_one(
                                    {"post_id": post_id, "media_items.media_id": media_id},
                                    {"$set": {"media_items.$.downloaded": True, "media_items.$.filename": filename, "updated_at": datetime.now().isoformat()}}
                                )
                                console.print(f"  [green]✅ Vídeo baixado com sucesso via yt-dlp[/green]")
                            else:
                                post_success = False
                                db["profile_posts"].update_one(
                                    {"post_id": post_id, "media_items.media_id": media_id},
                                    {"$set": {"media_items.$.download_error": res.stderr[:150], "updated_at": datetime.now().isoformat()}}
                                )
                        except Exception as ex:
                            post_success = False
                            console.print(f"  [red]❌ Erro ao baixar vídeo: {ex}[/red]")
                    else:
                        try:
                            import requests
                            filename = self._url_to_filename(url, "mp4")
                            filepath = self.output_videos / filename
                            resp = requests.get(url, timeout=120, stream=True)
                            if resp.status_code == 200:
                                with open(filepath, "wb") as f:
                                    for chunk in resp.iter_content(chunk_size=8192): f.write(chunk)
                                self._mark_as_downloaded(url, filename=filename, media_type="video", post_id=post_id, media_id=media_id)
                                downloaded_files.append(filename)
                                db["profile_posts"].update_one(
                                    {"post_id": post_id, "media_items.media_id": media_id},
                                    {"$set": {"media_items.$.downloaded": True, "media_items.$.filename": filename, "updated_at": datetime.now().isoformat()}}
                                )
                                console.print(f"  [green]✅ Vídeo direto baixado com sucesso[/green]")
                            else:
                                post_success = False
                        except Exception as ex:
                            post_success = False
                            console.print(f"  [red]❌ Erro HTTP vídeo: {ex}[/red]")
                else:
                    # Imagem
                    try:
                        import requests
                        filename = self._url_to_filename(url, "jpg")
                        filepath = self.output_images / filename
                        resp = requests.get(url, timeout=60, stream=True)
                        if resp.status_code == 200:
                            with open(filepath, "wb") as f:
                                for chunk in resp.iter_content(chunk_size=8192): f.write(chunk)
                            self._mark_as_downloaded(url, filename=filename, media_type="image", post_id=post_id, media_id=media_id)
                            downloaded_files.append(filename)
                            db["profile_posts"].update_one(
                                {"post_id": post_id, "media_items.media_id": media_id},
                                {"$set": {"media_items.$.downloaded": True, "media_items.$.filename": filename, "updated_at": datetime.now().isoformat()}}
                            )
                            console.print(f"  [green]✅ Imagem baixada com sucesso[/green]")
                        else:
                            post_success = False
                    except Exception as ex:
                        post_success = False
                        console.print(f"  [red]❌ Erro ao baixar imagem: {ex}[/red]")

            if post_success:
                success_count += 1
                db["profile_posts"].update_one({"post_id": post_id}, {"$set": {"status": "downloaded", "updated_at": datetime.now().isoformat()}})
                send_telemetry_event(self.run_id, "POST_DOWNLOAD_COMPLETE", status="completed", message=f"Sucesso no download do post {post_id}", metrics={"post_id": post_id, "files": downloaded_files})
            else:
                error_count += 1
                db["profile_posts"].update_one({"post_id": post_id}, {"$set": {"status": "error", "error_message": "Falha no download de mídias", "updated_at": datetime.now().isoformat()}})
                send_telemetry_event(self.run_id, "POST_DOWNLOAD_ERROR", status="error", message=f"Falha no download do post {post_id}", metrics={"post_id": post_id})

        remaining_pending = db["profile_posts"].count_documents({"status": "pending"})
        console.print(f"\n[bold green]✅ Lote finalizado! Sucessos: {success_count}, Erros: {error_count}. Restantes pendentes no banco: {remaining_pending}[/bold green]")
        send_telemetry_event(
            self.run_id, "DOWNLOAD_BATCH_COMPLETE", status="completed", target_url=self.target_url,
            message=f"Lote de download finalizado. Sucessos: {success_count}, Erros: {error_count}, Restantes: {remaining_pending}",
            metrics={"processed_in_batch": len(pending_docs), "success_count": success_count, "error_count": error_count, "remaining_pending": remaining_pending}
        )


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
        "--list-posts",
        action="store_true",
        help="Step 1: Apenas catalogar posts do perfil-alvo no MongoDB, sem realizar download",
    )
    parser.add_argument(
        "--download-pending",
        action="store_true",
        help="Step 2: Baixar mídias dos posts com status 'pending' em lote",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=int(os.environ.get("SCRAPER_DOWNLOAD_BATCH_SIZE", 10)),
        help="Quantidade máxima de posts pendentes a baixar no Step 2 (padrão: 10)",
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

    # Modo Step 1: Apenas Listar Posts
    if args.list_posts:
        scraper.list_posts()
        return

    # Modo Step 2: Download em Lote de Posts Pendentes
    if args.download_pending:
        scraper.download_pending(batch_size=args.batch_size)
        return

    # Modo legado / direto: Coleta e Download na mesma sessão
    send_telemetry_event(scraper.run_id, "SCRAPE_START", status="in_progress", target_url=args.target, message=f"Iniciando coleta para {args.target}")

    run_doc = {
        "run_id": scraper.run_id,
        "source": "scraper",
        "status": "in_progress",
        "target_url": args.target,
        "started_at": datetime.now().isoformat(),
        "finished_at": None,
        "total_files": 0,
        "success_files": 0,
        "error_files": 0,
        "error_count": 0
    }
    scraper._save_pipeline_run(run_doc)

    try:
        # Coletar URLs
        send_telemetry_event(scraper.run_id, "COLLECT_MEDIA", status="in_progress", target_url=args.target, message=f"Coletando mídia em {args.target}")
        scraper.collect_media()

        # Download
        if not args.no_download:
            if not args.only_images:
                send_telemetry_event(scraper.run_id, "DOWNLOAD_VIDEOS", status="in_progress", target_url=args.target, message="Baixando vídeos coletados")
                scraper.download_videos()
            if not args.only_videos:
                send_telemetry_event(scraper.run_id, "DOWNLOAD_IMAGES", status="in_progress", target_url=args.target, message="Baixando imagens coletadas")
                scraper.download_images()

        # Salvar metadados e resumo
        scraper.save_metadata()
        scraper.print_summary()

        v_down = sum(1 for v in scraper.collected_videos if v.get("downloaded"))
        i_down = sum(1 for i in scraper.collected_images if i.get("downloaded"))
        total_down = v_down + i_down
        err_len = len(scraper.errors)

        run_doc.update({
            "status": "completed" if err_len == 0 else "completed",
            "finished_at": datetime.now().isoformat(),
            "total_files": len(scraper.collected_videos) + len(scraper.collected_images),
            "success_files": total_down,
            "error_files": err_len,
            "error_count": err_len
        })
        scraper._save_pipeline_run(run_doc)

        send_telemetry_event(scraper.run_id, "SCRAPE_COMPLETE", status="completed", target_url=args.target, message=f"Coleta e download concluídos para {args.target}")

    except Exception as e:
        import traceback
        err_msg = str(e)
        err_trace = traceback.format_exc()

        run_doc.update({
            "status": "error",
            "finished_at": datetime.now().isoformat(),
            "error_count": run_doc.get("error_count", 0) + 1
        })
        scraper._save_pipeline_run(run_doc)

        send_telemetry_event(scraper.run_id, "ERROR", status="error", target_url=args.target, message=f"Falha na raspagem: {err_msg}", error_details=err_trace)
        raise e


if __name__ == "__main__":
    main()

