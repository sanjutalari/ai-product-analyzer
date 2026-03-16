"""
image_search.py - Fetch product images from multiple sources.
Uses DuckDuckGo image search + direct Amazon image extraction.
"""
import asyncio, logging, re
from urllib.parse import quote_plus
import httpx

log = logging.getLogger(__name__)

UA  = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
HDR = {
    "User-Agent": UA,
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
}

async def fetch_product_images(product_name: str, max_images: int = 8) -> list[str]:
    if not product_name or product_name in ("Product", "Unknown"):
        return []
    results = await asyncio.gather(
        _ddg_images(product_name),
        _google_images(product_name),
        return_exceptions=True
    )
    images = []
    seen = set()
    for r in results:
        if isinstance(r, list):
            for url in r:
                if url and url not in seen and _is_valid_image(url):
                    seen.add(url)
                    images.append(url)
    log.info(f"Fetched {len(images)} images for '{product_name}'")
    return images[:max_images]


def _is_valid_image(url: str) -> bool:
    if not url.startswith("http"):
        return False
    # Filter out tiny/tracker images
    bad = ["pixel", "transparent", "1x1", "tracking", "analytics", "icon-16", "favicon"]
    return not any(b in url.lower() for b in bad)


async def _ddg_images(product_name: str) -> list[str]:
    """DuckDuckGo image search — free, no API key needed."""
    images = []
    try:
        q = quote_plus(f"{product_name} product")
        # DuckDuckGo image search token endpoint
        async with httpx.AsyncClient(headers=HDR, follow_redirects=True, timeout=12) as c:
            # First get the vqd token
            r = await c.get(f"https://duckduckgo.com/?q={q}&iax=images&ia=images")
            vqd_match = re.search(r'vqd=([\d-]+)', r.text)
            if not vqd_match:
                return []
            vqd = vqd_match.group(1)

            # Now fetch image results JSON
            r2 = await c.get(
                f"https://duckduckgo.com/i.js",
                params={"q": product_name, "o": "json", "p": "1", "vqd": vqd, "f": ",,,,,", "l": "us-en"},
                headers={**HDR, "Referer": "https://duckduckgo.com/"}
            )
            data = r2.json()
            for item in data.get("results", [])[:10]:
                url = item.get("image", "")
                if url and _is_valid_image(url):
                    images.append(url)
    except Exception as e:
        log.warning(f"DDG images failed: {e}")
    return images[:6]


async def _google_images(product_name: str) -> list[str]:
    """Extract images from Google Images HTML (backup)."""
    images = []
    try:
        q = quote_plus(f"{product_name} product official")
        url = f"https://www.google.com/search?q={q}&tbm=isch&tbs=isz:l"
        async with httpx.AsyncClient(headers={**HDR, "Accept": "text/html"}, follow_redirects=True, timeout=12) as c:
            r = await c.get(url)
            # Extract image URLs from JSON embedded in page
            for m in re.finditer(r'"(https://[^"]+\.(?:jpg|jpeg|png|webp))"', r.text):
                img_url = m.group(1)
                if _is_valid_image(img_url) and img_url not in images:
                    images.append(img_url)
                if len(images) >= 6:
                    break
    except Exception as e:
        log.warning(f"Google images failed: {e}")
    return images[:4]
