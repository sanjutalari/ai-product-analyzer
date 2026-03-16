"""
web_search.py
Searches the entire internet for product reviews using multiple free sources:
- DuckDuckGo (free, no API key)
- Reddit JSON API (free)
- Google via scraping (fallback)
Combines all results and feeds to AI for analysis.
"""
import asyncio, logging, re, json
from urllib.parse import quote_plus, urlparse
import httpx
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

UA  = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
HDR = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9",
       "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"}

# Trusted review sources across the whole internet
TRUSTED_DOMAINS = [
    "reddit.com", "amazon.com", "bestbuy.com", "walmart.com",
    "rtings.com", "techradar.com", "tomsguide.com", "theverge.com",
    "engadget.com", "cnet.com", "pcmag.com", "wired.com",
    "gsmarena.com", "notebookcheck.net", "digitaltrends.com",
    "trustedreviews.com", "expertreviews.co.uk", "91mobiles.com",
    "flipkart.com", "smartprix.com", "ndtvgadgets.com",
]


async def search_web_reviews(product_name: str, max_results: int = 10) -> list[dict]:
    """
    Search the whole web for product reviews.
    Returns enriched review list from multiple sources.
    """
    if not product_name or product_name in ("Product", "Unknown"):
        return []

    # Run all search sources in parallel
    results = await asyncio.gather(
        _search_duckduckgo(product_name),
        _search_reddit(product_name),
        _search_rtings(product_name),
        return_exceptions=True
    )

    all_reviews = []
    for r in results:
        if isinstance(r, list):
            all_reviews.extend(r)

    # Deduplicate by author
    seen = set()
    unique = []
    for rv in all_reviews:
        key = rv.get("author", "") + rv.get("text", "")[:30]
        if key not in seen:
            seen.add(key)
            unique.append(rv)

    # Sort: Reddit + trusted sites first, then by rating confidence
    unique.sort(key=lambda x: (
        0 if x.get("source") in ("reddit", "rtings", "techradar", "theverge", "cnet") else 1,
        -x.get("confidence", 0)
    ))

    log.info(f"Web search: {len(unique)} total reviews for '{product_name}'")
    return unique[:max_results]


async def _search_duckduckgo(product_name: str) -> list[dict]:
    """Search DuckDuckGo for product reviews — completely free, no API key."""
    reviews = []
    query = f"{product_name} review pros cons buy"

    try:
        # DuckDuckGo HTML search (free, no key needed)
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        async with httpx.AsyncClient(headers=HDR, follow_redirects=True, timeout=15) as c:
            r = await c.get(url)
            if r.status_code != 200:
                return []

            soup = BeautifulSoup(r.text, "lxml")
            results = soup.select(".result")[:8]

            for result in results:
                title_el   = result.select_one(".result__title")
                snippet_el = result.select_one(".result__snippet")
                link_el    = result.select_one(".result__url")

                title   = title_el.get_text(strip=True)   if title_el   else ""
                snippet = snippet_el.get_text(strip=True) if snippet_el else ""
                link    = link_el.get_text(strip=True)    if link_el    else ""

                if not snippet or len(snippet) < 30:
                    continue

                # Identify source domain
                source = _extract_domain(link)
                if not _is_review_content(title + " " + snippet):
                    continue

                rating    = _estimate_rating(title + " " + snippet, 0)
                sentiment = "positive" if rating >= 4 else "negative" if rating <= 2 else "neutral"
                confidence = 2 if source in TRUSTED_DOMAINS else 1

                reviews.append({
                    "author":     _source_to_author(source),
                    "rating":     rating,
                    "text":       f"{title} — {snippet}"[:220],
                    "sentiment":  sentiment,
                    "source":     source or "web",
                    "url":        link,
                    "confidence": confidence,
                })

    except Exception as e:
        log.warning(f"DuckDuckGo search failed: {e}")

    log.info(f"DuckDuckGo: {len(reviews)} results")
    return reviews[:5]


async def _search_reddit(product_name: str) -> list[dict]:
    """Search Reddit using public JSON API — no auth needed."""
    reviews = []
    query   = f"{product_name} review"

    try:
        url    = "https://www.reddit.com/search.json"
        params = {"q": query, "sort": "relevance", "t": "year", "limit": 10, "type": "link"}
        reddit_hdrs = {**HDR, "User-Agent": "ProductAnalyzer/2.0 (research tool)"}

        async with httpx.AsyncClient(headers=reddit_hdrs, follow_redirects=True, timeout=12) as c:
            r = await c.get(url, params=params)
            if r.status_code != 200:
                return []

            posts = r.json().get("data", {}).get("children", [])
            query_words = [w.lower() for w in product_name.split()[:4]]

            for post in posts[:8]:
                pd    = post.get("data", {})
                title = pd.get("title", "")
                body  = pd.get("selftext", "")[:300]
                text  = (title + " " + body).strip()

                # Must be relevant to our product
                matches = sum(1 for w in query_words if w.lower() in text.lower())
                if matches < 2:
                    continue

                author  = pd.get("author", "redditor")
                score   = pd.get("score", 0)
                sub     = pd.get("subreddit_name_prefixed", "r/reddit")
                rating    = _estimate_rating(text, score)
                sentiment = "positive" if rating >= 4 else "negative" if rating <= 2 else "neutral"

                reviews.append({
                    "author":     f"u/{author} ({sub})",
                    "rating":     rating,
                    "text":       text[:220],
                    "sentiment":  sentiment,
                    "source":     "reddit",
                    "url":        "https://reddit.com" + pd.get("permalink", ""),
                    "confidence": 3,
                })

    except Exception as e:
        log.warning(f"Reddit search failed: {e}")

    log.info(f"Reddit: {len(reviews)} results")
    return reviews[:4]


async def _search_rtings(product_name: str) -> list[dict]:
    """Try to get expert review snippet from Rtings.com (great for electronics)."""
    reviews = []
    try:
        slug  = re.sub(r'[^a-z0-9]+', '-', product_name.lower()).strip('-')
        url   = f"https://www.rtings.com/{slug}"
        async with httpx.AsyncClient(headers=HDR, follow_redirects=True, timeout=10) as c:
            r = await c.get(url)
            if r.status_code != 200:
                return []
            soup = BeautifulSoup(r.text, "lxml")
            # Try to grab verdict / score text
            verdict = soup.select_one(".test-verdict, .score-verdict, [class*='verdict']")
            if verdict:
                text = verdict.get_text(strip=True)[:200]
                if len(text) > 20:
                    reviews.append({
                        "author":     "Rtings.com Expert",
                        "rating":     4,
                        "text":       text,
                        "sentiment":  "positive",
                        "source":     "rtings.com",
                        "url":        url,
                        "confidence": 5,
                    })
    except Exception:
        pass
    return reviews


# ── Helpers ──────────────────────────────────────────────────────────────────

def _extract_domain(url: str) -> str:
    try:
        return urlparse("https://" + url.lstrip("https://").lstrip("http://")).netloc.replace("www.", "")
    except:
        return "web"


def _source_to_author(domain: str) -> str:
    mapping = {
        "reddit.com":          "Reddit User",
        "rtings.com":          "Rtings.com Expert",
        "techradar.com":       "TechRadar Review",
        "theverge.com":        "The Verge Review",
        "cnet.com":            "CNET Review",
        "pcmag.com":           "PCMag Review",
        "tomsguide.com":       "Tom's Guide Review",
        "wired.com":           "Wired Review",
        "engadget.com":        "Engadget Review",
        "gsmarena.com":        "GSMArena Expert",
        "notebookcheck.net":   "NotebookCheck Expert",
        "digitaltrends.com":   "Digital Trends Review",
        "trustedreviews.com":  "Trusted Reviews Expert",
        "91mobiles.com":       "91Mobiles Review",
        "ndtvgadgets.com":     "NDTV Gadgets Review",
    }
    return mapping.get(domain, f"{domain} Review")


def _is_review_content(text: str) -> bool:
    """Check if text is likely a product review."""
    review_signals = [
        "review", "pros", "cons", "rating", "score", "verdict",
        "buy", "worth", "recommend", "good", "bad", "best", "worst",
        "performance", "quality", "design", "battery", "camera",
        "sound", "display", "price", "value",
    ]
    text_lower = text.lower()
    return sum(1 for s in review_signals if s in text_lower) >= 2


def _estimate_rating(text: str, score: int) -> int:
    """Estimate star rating from text sentiment."""
    t = text.lower()
    pos_words = ["great","excellent","amazing","love","perfect","best","fantastic",
                 "awesome","recommend","worth","good","nice","impressive","solid",
                 "outstanding","superb","wonderful","brilliant","top","quality"]
    neg_words = ["bad","terrible","awful","hate","worst","broken","disappointed",
                 "waste","poor","horrible","avoid","return","defective","cheap",
                 "flimsy","regret","overhyped","mediocre","overpriced","failure"]
    pos = sum(1 for w in pos_words if w in t)
    neg = sum(1 for w in neg_words if w in t)

    if   pos > neg + 3: rating = 5
    elif pos > neg + 1: rating = 4
    elif neg > pos + 3: rating = 1
    elif neg > pos + 1: rating = 2
    else:               rating = 3

    if score > 500:   rating = min(5, rating + 1)
    elif score > 100: rating = min(5, rating)
    elif score < 0:   rating = max(1, rating - 1)

    return rating
