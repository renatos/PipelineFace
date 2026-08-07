from .base_extractor import BaseExtractor


class ImageFeedExtractor(BaseExtractor):
    """Extrator especializado em posts de imagem/álbum no feed normal da linha do tempo."""

    def extract_feed_units(self, page) -> list[dict]:
        """Extrai unidades de posts do feed agrupadas por container de card (post)."""
        units = page.evaluate("""() => {
            const results = [];
            const mainContainer = document.querySelector('div[role="main"]') || document.querySelector('main') || document.body;
            
            let cards = Array.from(mainContainer.querySelectorAll('div[role="article"], div[data-pagelet*="FeedUnit"]'));
            
            if (cards.length === 0) {
                const anchors = mainContainer.querySelectorAll('a[href*="/posts/"], a[href*="set=pcb."], a[href*="/photo"], a[href*="/videos/"], a[href*="/reel/"]');
                const cardSet = new Set();
                anchors.forEach(a => {
                    let parent = a.parentElement;
                    for (let i = 0; i < 6; i++) {
                        if (parent && parent !== mainContainer) {
                            if (parent.tagName === 'DIV' && parent.children.length > 1) {
                                cardSet.add(parent);
                                break;
                            }
                            parent = parent.parentElement;
                        }
                    }
                });
                cards = Array.from(cardSet);
            }

            cards.forEach(card => {
                const links = [];
                const images = [];
                const videos = [];

                const textEl = card.querySelector('div[dir="auto"]');
                const text = textEl ? textEl.textContent.trim().substring(0, 200) : "";

                const anchors = card.querySelectorAll('a[href*="/posts/"], a[href*="set=pcb."], a[href*="/photo"], a[href*="/videos/"], a[href*="/reel/"], a[href*="fbid="]');
                anchors.forEach(a => {
                    if (a.href && !a.href.includes('notif') && !a.href.includes('ref=bookmarks')) {
                        links.push(a.href);
                    }
                });

                const imgs = card.querySelectorAll('img');
                imgs.forEach(img => {
                    let url = img.src || '';
                    if (url.startsWith('data:')) {
                        const srcset = img.getAttribute('srcset') || '';
                        const candidates = srcset.split(',')
                            .map(s => s.trim().split(/\\s+/)[0])
                            .filter(u => u && !u.startsWith('data:'));
                        if (candidates.length > 0) url = candidates[candidates.length - 1];
                    }
                    if (!url || url.startsWith('data:')) return;
                    if (url.includes('emoji') || url.includes('rsrc.php')) return;
                    if (url.includes('/emg1/')) return;
                    images.push({
                        url: url,
                        alt: img.alt || null
                    });
                });

                const vids = card.querySelectorAll('video');
                vids.forEach(v => {
                    const src = v.src || v.querySelector('source')?.src;
                    if (src && !src.startsWith('blob:')) {
                        videos.push(src);
                    }
                });

                const photoLinks = links.filter(h => h.includes('/photo') || h.includes('fbid='));

                if (links.length > 0 || images.length > 0 || videos.length > 0) {
                    results.push({
                        links: Array.from(new Set(links)),
                        images: images,
                        photo_links: Array.from(new Set(photoLinks)),
                        videos: Array.from(new Set(videos)),
                        text: text
                    });
                }
            });

            return results;
        }""")
        return units

    def extract_image_urls(self, page) -> list[dict]:
        """Extrai URLs de imagens da página atual estritamente do feed do perfil."""
        images = page.evaluate("""() => {
            const results = [];
            const seen = new Set();
            const mainContainer = document.querySelector('div[role="main"]') || document.querySelector('main') || document.body;

            const imgElements = mainContainer.querySelectorAll('img');
            imgElements.forEach(img => {
                const src = img.src;
                if (!src || seen.has(src)) return;
                if (src.startsWith('data:')) return;
                if (src.includes('emoji') || src.includes('rsrc.php')) return;

                seen.add(src);
                results.push({
                    url: src,
                    alt: img.alt || null,
                    width: img.naturalWidth || img.width || 0,
                    height: img.naturalHeight || img.height || 0
                });
            });

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
