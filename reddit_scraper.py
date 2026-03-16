"""
reddit_scraper.py
Searches Reddit for real product reviews using the public JSON API.
No API key needed — Reddit has a free public JSON endpoint.
"""
import asyncio, logging, re, json
import httpx

log = logging.getLogger(__name__)

HDR = {
    "User-Agent": "Mozilla/5.0 (compatible; ProductAnalyzer/1.0; research)",
    "Accept": "application/json",
}

REVIEW_SUBREDDITS = [
    "reviews", "BuyItForLife", "gadgets", "hardware",
    "headphones", "amazonreviews", "consumer", "product_reviews",
    "tech", "android", "apple",
]

async def search_reddit_reviews(product_name: str, max_results: int = 8) -> list[dict]:
    """
    Search Reddit for product reviews using the public search API.
    Returns list of review dicts with author, rating, text, source fields.
    """
    if not product_name or product_name == "Product":
        return []

    # Clean product name for search
    query = re.sub(r'[^\w\s]', '', product_name)[:60]
    query = f"{query} review"

    reviews = []

    try:
        # Use Reddit's public search JSON endpoint (no auth needed)
        search_url = f"https://www.reddit.com/search.json"
        params = {
            "q":      query,
            "sort":   "relevance",
            "t":      "year",
            "limit":  15,
            "type":   "link",
        }

        async with httpx.AsyncClient(headers=HDR, follow_redirects=True, timeout=15) as c:
            r = await c.get(search_url, params=params)
            if r.status_code != 200:
                log.warning(f"Reddit search returned {r.status_code}")
                return []

            data = r.json()
            posts = data.get("data", {}).get("children", [])

            for post in posts[:6]:
                pd = post.get("data", {})
                title   = pd.get("title", "")
                body    = pd.get("selftext", "")
                author  = pd.get("author", "reddit_user")
                score   = pd.get("score", 0)
                sub     = pd.get("subreddit", "")
                url     = "https://reddit.com" + pd.get("permalink", "")

                # Skip if not relevant
                if not any(w.lower() in title.lower() or w.lower() in body.lower()
                           for w in query.split()[:3]):
                    continue

                # Estimate rating from upvote score and sentiment keywords
                text = (title + " " + body)[:400].strip()
                if not text:
                    continue

                rating = _estimate_rating(text, score)
                sentiment = "positive" if rating >= 4 else "negative" if rating <= 2 else "neutral"

                reviews.append({
                    "author":    f"u/{author}",
                    "rating":    rating,
                    "text":      text[:200],
                    "sentiment": sentiment,
                    "source":    "reddit",
                    "subreddit": sub,
                    "url":       url,
                })

                if len(reviews) >= max_results:
                    break

    except Exception as e:
        log.warning(f"Reddit scrape failed: {e}")
        return []

    log.info(f"Reddit: found {len(reviews)} reviews for '{product_name}'")
    return reviews


def _estimate_rating(text: str, score: int) -> int:
    """Estimate star rating from text sentiment and Reddit score."""
    text_lower = text.lower()

    positive_words = ["great", "excellent", "amazing", "love", "perfect", "best",
                      "fantastic", "awesome", "recommend", "worth", "good", "nice",
                      "impressive", "solid", "happy", "satisfied", "outstanding"]
    negative_words = ["bad", "terrible", "awful", "hate", "worst", "broken",
                      "disappointed", "waste", "poor", "horrible", "avoid",
                      "return", "defective", "cheap", "flimsy", "regret"]

    pos = sum(1 for w in positive_words if w in text_lower)
    neg = sum(1 for w in negative_words if w in text_lower)

    # Base rating from sentiment words
    if pos > neg + 2:    rating = 5
    elif pos > neg:      rating = 4
    elif neg > pos + 2:  rating = 1
    elif neg > pos:      rating = 2
    else:                rating = 3

    # Adjust slightly based on Reddit score
    if score > 100:   rating = min(5, rating + 1)
    elif score < 0:   rating = max(1, rating - 1)

    return rating
