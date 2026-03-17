"""
youtube_scraper.py
Scrapes YouTube review data via DuckDuckGo search — no API key needed.
Extracts video titles, descriptions, channel names for sentiment analysis.
"""
import asyncio, logging, re
from urllib.parse import quote_plus
import httpx
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)
UA  = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
HDR = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}

TRUSTED_CHANNELS = [
    "mkbhd", "linus tech tips", "dave2d", "unbox therapy", "mrwhosetheboss",
    "the verge", "techradar", "rtings", "jon rettinger", "david imel",
    "technical guruji", "trakin tech", "geekyranjit", "c4etech", "review prime",
]

async def get_youtube_reviews(product_name: str, max_results: int = 6) -> list[dict]:
    """Search YouTube for product reviews via DuckDuckGo."""
    if not product_name or product_name in ("Product", "Unknown"):
        return []

    reviews = []
    queries = [
        f"{product_name} review site:youtube.com",
        f"{product_name} honest review youtube",
    ]

    for query in queries:
        try:
            async with httpx.AsyncClient(headers=HDR, follow_redirects=True, timeout=12) as c:
                url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
                r = await c.get(url)
                if r.status_code != 200:
                    continue

                soup = BeautifulSoup(r.text, "lxml")
                for result in soup.select(".result")[:6]:
                    title_el   = result.select_one(".result__title")
                    snippet_el = result.select_one(".result__snippet")
                    url_el     = result.select_one(".result__url")

                    title   = title_el.get_text(strip=True)   if title_el   else ""
                    snippet = snippet_el.get_text(strip=True) if snippet_el else ""
                    url_txt = url_el.get_text(strip=True)     if url_el     else ""

                    if "youtube" not in url_txt.lower() and "youtube" not in title.lower():
                        continue
                    if not snippet or len(snippet) < 30:
                        continue

                    # Extract channel name from title pattern "Title - Channel"
                    channel = "YouTube Reviewer"
                    if " - " in title:
                        parts   = title.rsplit(" - ", 1)
                        channel = parts[-1].strip()[:40]

                    # Detect if trusted reviewer
                    is_trusted = any(tc in (channel + title).lower() for tc in TRUSTED_CHANNELS)

                    text = f"{title}: {snippet}"[:220]
                    rating   = _estimate_rating(text)
                    sentiment = "positive" if rating >= 4 else "negative" if rating <= 2 else "neutral"

                    reviews.append({
                        "author":     f"📺 {channel}",
                        "rating":     rating,
                        "text":       text,
                        "sentiment":  sentiment,
                        "source":     "youtube",
                        "url":        url_txt,
                        "is_trusted": is_trusted,
                        "confidence": 4 if is_trusted else 2,
                    })

                if len(reviews) >= max_results:
                    break

        except Exception as e:
            log.warning(f"YouTube scrape failed for query '{query}': {e}")

    # Sort trusted reviewers first
    reviews.sort(key=lambda x: -x.get("confidence", 0))
    log.info(f"YouTube: {len(reviews)} reviews for '{product_name}'")
    return reviews[:max_results]


def _estimate_rating(text: str) -> int:
    t = text.lower()
    pos = ["great","excellent","amazing","love","best","fantastic","awesome",
           "recommend","worth","impressive","solid","outstanding","perfect",
           "brilliant","superb","5 star","must buy","good value","top pick"]
    neg = ["bad","terrible","awful","hate","worst","broken","disappointed",
           "waste","poor","avoid","return","defective","overpriced","regret",
           "1 star","not worth","skip","mediocre","fail","disappointing"]
    neutral = ["okay","decent","average","mixed","depends","middle","so-so"]

    p = sum(1 for w in pos if w in t)
    n = sum(1 for w in neg if w in t)
    u = sum(1 for w in neutral if w in t)

    if p > n + 2:   return 5
    if p > n + 1:   return 4
    if n > p + 2:   return 1
    if n > p + 1:   return 2
    if u > 0:       return 3
    return 3
