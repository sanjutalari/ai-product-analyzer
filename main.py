import logging, os, time
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from database        import init_db, save_product_analysis, get_product_analysis, get_recent_analyses
from scraper         import ProductScraper
from review_analyzer import ReviewAnalyzer
from price_compare   import PriceComparator
from price_history   import PriceHistoryTracker
from scoring         import ScoreGenerator
from llm_agent       import LLMAgent
from reddit_scraper  import search_reddit_reviews

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    log.info("Database ready")
    yield

app = FastAPI(title="AI Product Analyzer", version="2.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

class AnalyzeRequest(BaseModel):
    url: str
    force_refresh: bool = False

@app.get("/health")
def health():
    return {"status": "ok", "timestamp": int(time.time())}

@app.post("/api/analyze")
async def analyze(req: AnalyzeRequest, bg: BackgroundTasks):
    url = req.url.strip()
    if not url:
        raise HTTPException(400, "URL is required")

    # Cache check
    if not req.force_refresh:
        cached = get_product_analysis(url)
        if cached:
            return {"source": "cache", "data": cached}

    # ── Step 1: Scrape product page ──────────────────────────
    scraper = ProductScraper()
    pd2     = await scraper.scrape(url)
    pd2["url"] = url

    # ── Step 2: AI analysis (uses product knowledge if scrape failed) ──
    lr           = await LLMAgent().analyze(pd2)
    product_name = lr.get("productName") or pd2.get("name", "Unknown Product")

    # Update price from AI if scraper missed it
    if lr.get("estimatedPrice") and not pd2.get("price"):
        pd2["price"] = lr["estimatedPrice"]

    # ── Step 3: Reddit reviews (runs in parallel with other tasks) ──
    reddit_task = search_reddit_reviews(product_name, max_results=6)

    # ── Step 4: Review analysis from scraped reviews ─────────
    rr_task = ReviewAnalyzer().analyze(pd2.get("raw_reviews", []))

    # ── Step 5: Price comparison ─────────────────────────────
    pr_task = PriceComparator().compare(product_name, pd2.get("price", ""), url)

    # ── Step 6: Price history ─────────────────────────────────
    hi_task = PriceHistoryTracker().get_history(url, pd2.get("price", ""))

    # Run all async tasks in parallel
    import asyncio
    reddit_reviews, rr, pr, hi = await asyncio.gather(
        reddit_task, rr_task, pr_task, hi_task
    )

    # ── Step 7: Merge reviews — Reddit + scraped ─────────────
    scraped_reviews = rr.get("reviews", [])
    all_reviews     = scraped_reviews + reddit_reviews

    # Re-analyze combined reviews if we got Reddit data
    if reddit_reviews:
        all_ratings = [r.get("rating", 3) for r in all_reviews if r.get("rating")]
        combined_avg = round(sum(all_ratings) / len(all_ratings), 1) if all_ratings else rr.get("avg_rating", 0)
        rr["avg_rating"]    = combined_avg
        rr["review_count"]  = f"{len(all_reviews)}+"
        rr["reviews"]       = all_reviews[:10]
        log.info(f"Combined {len(scraped_reviews)} scraped + {len(reddit_reviews)} Reddit reviews")

    # ── Step 8: Score ─────────────────────────────────────────
    sc = ScoreGenerator().generate(pd2, lr, rr, pr)

    result = {
        "url":           url,
        "productName":   product_name,
        "score":         sc["score"],
        "valueScore":    sc["value_score"],
        "avgRating":     lr.get("avg_rating") or rr.get("avg_rating", 0),
        "reviewCount":   rr.get("review_count", "0"),
        "currentPrice":  pd2.get("price", ""),
        "bestPrice":     pr.get("best_price", ""),
        "lowestPrice":   hi.get("lowest", ""),
        "highestPrice":  hi.get("highest", ""),
        "summary":       lr.get("summary", ""),
        "pros":          lr.get("pros", []),
        "cons":          lr.get("cons", []),
        "idealBuyer":    lr.get("ideal_buyer", ""),
        "avoidIf":       lr.get("avoid_if", ""),
        "tags":          lr.get("tags") or pd2.get("tags", []),
        "reviews":       rr.get("reviews", []),
        "platforms":     pr.get("platforms", []),
        "priceHistory":  hi.get("history", []),
        "redditReviews": len(reddit_reviews) > 0,
        "redditCount":   len(reddit_reviews),
    }

    bg.add_task(save_product_analysis, url, result)
    return {"source": "fresh", "data": result}

@app.get("/api/recent")
def recent():
    return get_recent_analyses(10)

@app.get("/", response_class=HTMLResponse)
def index():
    return open("index.html").read()
