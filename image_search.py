"""
image_search.py
Fetches product images from multiple free sources.
No API key needed.
"""
import asyncio, logging, re
from urllib.parse import quote_plus
import httpx
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)
UA  = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
HDR = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9",
       "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"}

async def fetch_product_images(product_name: str, max_images: int = 8) -> list[str]:
    """Fetch product images from Bing Image Search and DuckDuckGo."""
    if not product_name or product_name in ("Product", "Unknown"):
        return []
    results = await asyncio.gather(
        _bing_images(product_name, max_images),
        _ddg_images(product_name, max_images),
        return_exceptions=True
    )
    images = []
    seen = set()
    for r in results:
        if isinstance(r, list):
            for url in r:
                if url and url not in seen and url.startswith("http"):
                    seen.add(url)
                    images.append(url)
    log.info(f"Images fetched: {len(images)} for '{product_name}'")
    return images[:max_images]

async def _bing_images(product_name: str, limit: int) -> list[str]:
    images = []
    try:
        q   = quote_plus(f"{product_name} product official")
        url = f"https://www.bing.com/images/search?q={q}&form=HDRSC2&first=1"
        async with httpx.AsyncClient(headers=HDR, follow_redirects=True, timeout=12) as c:
            r = await c.get(url)
            if r.status_code != 200:
                return []
            soup = BeautifulSoup(r.text, "lxml")
            for img in soup.select("img.mimg, img.rms_img, .iusc img, .imgpt img")[:12]:
                src = img.get("src") or img.get("data-src") or ""
                if src.startswith("http") and not "microsoft" in src and len(src) > 30:
                    images.append(src)
            # Also try JSON embedded data
            for m in re.finditer(r'"murl":"(https[^"]+?\.(?:jpg|jpeg|png|webp))"', r.text):
                url2 = m.group(1)
                if url2 not in images:
                    images.append(url2)
    except Exception as e:
        log.warning(f"Bing images: {e}")
    return images[:limit]

async def _ddg_images(product_name: str, limit: int) -> list[str]:
    images = []
    try:
        q   = quote_plus(f"{product_name} buy product image")
        url = f"https://duckduckgo.com/?q={q}&iax=images&ia=images"
        async with httpx.AsyncClient(headers={**HDR, "Referer":"https://duckduckgo.com"}, follow_redirects=True, timeout=12) as c:
            r = await c.get(url)
            for m in re.finditer(r'"thumbnail":"(https[^"]+?)"', r.text):
                u = m.group(1)
                if u.startswith("http") and u not in images:
                    images.append(u)
    except Exception as e:
        log.warning(f"DDG images: {e}")
    return images[:limit]
