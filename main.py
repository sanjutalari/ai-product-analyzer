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
from image_search    import fetch_product_images

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
    images_task      = fetch_product_images(product_name, max_images=8)
    rr_task          = ReviewAnalyzer().analyze(pd2.get("raw_reviews", []))
    pr_task          = PriceComparator().compare(product_name, pd2.get("price", ""), url)
    hi_task          = PriceHistoryTracker().get_history(url, pd2.get("price", ""))

    web_reviews, rr, pr, hi, extra_images = await asyncio.gather(
        web_reviews_task, rr_task, pr_task, hi_task, images_task
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
        "images": list(dict.fromkeys(pd2.get("images", []) + extra_images))[:8],
        "qualityIndicators": lr.get("quality_indicators", {}),
    }

    bg.add_task(save_product_analysis, url, result)
    return {"source": "fresh", "data": result}

@app.get("/api/recent")
def recent():
    return get_recent_analyses(10)

@app.get("/", response_class=HTMLResponse)
def index():
    return open("index.html").read()


class ChatRequest(BaseModel):
    message: str
    product: str = ""

@app.post("/api/chat")
async def chat(req: ChatRequest):
    """AI chat about a specific product."""
    try:
        from groq import Groq
        client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
        prompt = f"""You are a helpful product advisor. Answer the user's question concisely and helpfully.
Context: {req.message}
Give a clear, direct answer in 2-4 sentences. Be specific and actionable."""
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role":"user","content":prompt}],
            max_tokens=300, temperature=0.4,
        )
        return {"reply": resp.choices[0].message.content.strip()}
    except Exception as e:
        log.error(f"Chat error: {e}")
        return {"reply": "Sorry, I couldn't process that question. Please try again."}


@app.get("/api/imgproxy")
async def img_proxy(url: str):
    """Proxy product images to avoid CORS issues in browser."""
    import httpx
    from fastapi.responses import Response
    try:
        hdrs = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"}
        async with httpx.AsyncClient(headers=hdrs, follow_redirects=True, timeout=10) as c:
            r = await c.get(url)
            content_type = r.headers.get("content-type", "image/jpeg")
            return Response(content=r.content, media_type=content_type,
                          headers={"Cache-Control": "public, max-age=86400",
                                   "Access-Control-Allow-Origin": "*"})
    except Exception as e:
        log.error(f"Image proxy error: {e}")
        from fastapi import HTTPException
        raise HTTPException(404, "Image not found")
