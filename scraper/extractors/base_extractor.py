import re
import hashlib
from urllib.parse import urlparse, parse_qs, urlencode


class BaseExtractor:
    """Classe base para extratores de conteúdo do Facebook."""

    def __init__(self, scraper_instance=None):
        self.scraper = scraper_instance

    def clean_facebook_url(self, url: str) -> str:
        """Limpa parâmetros de rastreamento mantendo a URL direta do post/reel/foto."""
        if self.scraper and hasattr(self.scraper, "_clean_facebook_url"):
            return self.scraper._clean_facebook_url(url)
        if not url:
            return url
        try:
            parsed = urlparse(url)
            if "/reel/" in parsed.path or "/posts/" in parsed.path or "/videos/" in parsed.path:
                return f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
            if "/photo" in parsed.path:
                params = parse_qs(parsed.query)
                kept = {k: v[0] for k, v in params.items() if k in ("fbid", "set")}
                new_query = urlencode(kept)
                return f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{new_query}" if new_query else f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            return url
        except Exception:
            return url

    def extract_post_and_media_ids(self, url: str) -> tuple[str | None, str | None]:
        """Extrai um identificador único de post (post_id) e de mídia a partir da URL do Facebook."""
        if self.scraper and hasattr(self.scraper, "_extract_post_and_media_ids"):
            return self.scraper._extract_post_and_media_ids(url)
        if not url:
            return None, None
        
        url_clean = self.clean_facebook_url(url)
        
        post_match = re.search(r'/(?:posts|videos|reel)/([A-Za-z0-9_-]+)', url_clean)
        if post_match:
            pid = post_match.group(1)
            return pid, pid

        photo_fbid = re.search(r'[?&]fbid=(\d+)', url_clean)
        if photo_fbid:
            fbid = photo_fbid.group(1)
            set_pcb = re.search(r'set=pcb\.(\d+)', url_clean)
            pid = set_pcb.group(1) if set_pcb else fbid
            return pid, fbid

        fbid_match = re.search(r'fbid=(\d+)', url_clean)
        if fbid_match:
            fbid = fbid_match.group(1)
            return fbid, fbid

        hash_id = hashlib.md5(url_clean.encode()).hexdigest()[:16]
        return f"post_{hash_id}", None
