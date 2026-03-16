import asyncio, logging, os, time
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
from web_search      import search_web_reviews

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

    # ── 1. Scrape product page ─────────────────────────────
    pd2        = await ProductScraper().scrape(url)
    pd2["url"] = url

    # ── 2. AI analysis ─────────────────────────────────────
    lr           = await LLMAgent().analyze(pd2)
    product_name = lr.get("productName") or pd2.get("name", "Unknown Product")

    if lr.get("estimatedPrice") and not pd2.get("price"):
        pd2["price"] = lr["estimatedPrice"]

    # ── 3. Web search for reviews (whole internet) ─────────
    # Runs in parallel with price/history tasks
    web_reviews_task = search_web_reviews(product_name, max_results=10)
    rr_task          = ReviewAnalyzer().analyze(pd2.get("raw_reviews", []))
    pr_task          = PriceComparator().compare(product_name, pd2.get("price", ""), url)
    hi_task          = PriceHistoryTracker().get_history(url, pd2.get("price", ""))

    web_reviews, rr, pr, hi = await asyncio.gather(
        web_reviews_task, rr_task, pr_task, hi_task
    )

    # ── 4. Merge all reviews ───────────────────────────────
    scraped_reviews = rr.get("reviews", [])
    all_reviews     = scraped_reviews + web_reviews

    if web_reviews:
        all_ratings     = [r.get("rating", 3) for r in all_reviews if r.get("rating")]
        combined_avg    = round(sum(all_ratings) / len(all_ratings), 1) if all_ratings else rr.get("avg_rating", 0)
        rr["avg_rating"]   = combined_avg
        rr["review_count"] = f"{len(all_reviews)}+"
        rr["reviews"]      = all_reviews[:12]

    # Count sources
    sources = {}
    for rv in all_reviews:
        src = rv.get("source", "web")
        sources[src] = sources.get(src, 0) + 1

    # ── 5. Score ───────────────────────────────────────────
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
        "webSources":    sources,
        "hasWebReviews": len(web_reviews) > 0,
    }

    bg.add_task(save_product_analysis, url, result)
    return {"source": "fresh", "data": result}

@app.get("/api/recent")
def recent():
    return get_recent_analyses(10)

@app.get("/", response_class=HTMLResponse)
def index():
    return open("index.html").read()
