import time
from .base_extractor import BaseExtractor


class ReelVideoExtractor(BaseExtractor):
    """Extrator especializado em Reels e vídeos nas abas dedicadas /reels/ e /videos/."""

    def extract_reels_and_videos(self, page, sub_url: str, scroll_pause: float = 1.5, max_scrolls: int = 40) -> list[dict]:
        """Navega para a aba de mídia (/reels/ ou /videos/) e extrai todas as mídias da grade."""
        items = []
        try:
            page.goto(sub_url, timeout=30000)
            time.sleep(3)

            last_h = 0
            no_chg = 0
            seen_urls = set()

            for sub_scroll in range(1, max_scrolls + 1):
                page.evaluate("window.scrollBy(0, window.innerHeight * 3)")
                time.sleep(scroll_pause)

                sub_anchors = page.evaluate("""() => {
                    const links = Array.from(document.querySelectorAll('a'));
                    return links.map(a => ({ url: a.href, text: a.textContent?.trim() || '' }))
                                .filter(item => item.url && (item.url.includes('/reel/') || item.url.includes('/videos/') || item.url.includes('/watch/')));
                }""")

                for sa in sub_anchors:
                    item_url = self.clean_facebook_url(sa["url"])
                    if item_url in seen_urls:
                        continue
                    seen_urls.add(item_url)

                    post_id, media_fbid = self.extract_post_and_media_ids(item_url)
                    if not post_id:
                        continue

                    unique_sub_id = media_fbid or post_id[:16]
                    media_id = f"m_{unique_sub_id}_v0"
                    
                    items.append({
                        "post_id": post_id,
                        "media_id": media_id,
                        "item_url": item_url,
                        "text": sa.get("text"),
                        "scroll_position": sub_scroll
                    })

                new_h = page.evaluate("Math.max(document.documentElement.scrollHeight || 0, document.body.scrollHeight || 0)")
                if new_h == last_h:
                    no_chg += 1
                    if no_chg >= 6:
                        break
                else:
                    no_chg = 0
                last_h = new_h
        except Exception as e:
            if hasattr(self.scraper, "errors"):
                self.scraper.errors.append(f"Erro ao extrair mídias de {sub_url}: {e}")

        return items
