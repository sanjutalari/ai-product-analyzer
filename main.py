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

app = FastAPI(title="AI Product Analyzer v3", version="3.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class AnalyzeRequest(BaseModel):
    url: str
    force_refresh: bool = False

class ChatRequest(BaseModel):
    message: str
    product: str = ""

@app.get("/health")
def health():
    return {"status": "ok", "version": "3.0.0", "timestamp": int(time.time())}

@app.post("/api/analyze")
async def analyze(req: AnalyzeRequest, bg: BackgroundTasks):
    url = req.url.strip()
    if not url:
        raise HTTPException(400, "URL is required")

    if not req.force_refresh:
        cached = get_product_analysis(url)
        if cached:
            return {"source": "cache", "data": cached}

    # ── Step 1: Scrape product page ──────────────────────────────────────
    pd2 = await ProductScraper().scrape(url)
    pd2["url"] = url

    # ── Step 2: Multi-model AI analysis (3 models in parallel) ───────────
    lr = await LLMAgent().analyze(pd2)
    product_name = lr.get("productName") or pd2.get("name", "Unknown Product")

    if lr.get("estimatedPrice") and not pd2.get("price"):
        pd2["price"] = lr["estimatedPrice"]

    # ── Step 3: All remaining tasks in parallel ───────────────────────────
    web_reviews_task = search_web_reviews(product_name, max_results=10)
    rr_task          = ReviewAnalyzer().analyze(pd2.get("raw_reviews", []))
    pr_task          = PriceComparator().compare(product_name, pd2.get("price", ""), url)
    hi_task          = PriceHistoryTracker().get_history(url, pd2.get("price", ""))
    images_task      = fetch_product_images(product_name, max_images=8)

    web_reviews, rr, pr, hi, extra_images = await asyncio.gather(
        web_reviews_task, rr_task, pr_task, hi_task, images_task
    )

    # ── Step 4: Merge reviews (scraped + web) ────────────────────────────
    scraped_reviews = rr.get("reviews", [])
    all_reviews     = scraped_reviews + web_reviews

    if web_reviews:
        all_ratings  = [r.get("rating", 3) for r in all_reviews if r.get("rating")]
        combined_avg = round(sum(all_ratings) / len(all_ratings), 1) if all_ratings else rr.get("avg_rating", 0)
        rr["avg_rating"]   = combined_avg
        rr["review_count"] = f"{len(all_reviews):,}+"
        rr["reviews"]      = all_reviews[:12]

    # Count sources
    sources = {}
    for rv in all_reviews:
        src = rv.get("source", "web")
        sources[src] = sources.get(src, 0) + 1

    # ── Step 5: Category-aware scoring ──────────────────────────────────
    sc = ScoreGenerator().generate(pd2, lr, rr, pr)

    # ── Step 6: Build result ────────────────────────────────────────────
    result = {
        "url":                  url,
        "productName":          product_name,
        "score":                sc["score"],
        "valueScore":           sc["value_score"],
        "category":             sc.get("category", "default"),
        "avgRating":            lr.get("avg_rating") or rr.get("avg_rating", 0),
        "recencyWeightedRating":rr.get("recency_weighted_rating", 0),
        "reviewCount":          rr.get("review_count", "0"),
        "currentPrice":         pd2.get("price", ""),
        "bestPrice":            pr.get("best_price", ""),
        "lowestPrice":          hi.get("lowest", ""),
        "highestPrice":         hi.get("highest", ""),
        "summary":              lr.get("summary", ""),
        "pros":                 lr.get("pros", []),
        "cons":                 lr.get("cons", []),
        "idealBuyer":           lr.get("ideal_buyer", ""),
        "avoidIf":              lr.get("avoid_if", ""),
        "competitors":          lr.get("competitors", []),
        "tags":                 lr.get("tags") or pd2.get("tags", []),
        "reviews":              rr.get("reviews", []),
        "sentimentBreakdown":   rr.get("sentiment_breakdown", {}),
        "commonThemes":         rr.get("common_themes", []),
        "mostPraised":          rr.get("most_praised", ""),
        "mostCriticized":       rr.get("most_criticized", ""),
        "platforms":            pr.get("platforms", []),
        "priceHistory":         hi.get("history", []),
        "images":               list(dict.fromkeys(pd2.get("images", []) + extra_images))[:8],
        "webSources":           sources,
        "hasWebReviews":        len(web_reviews) > 0,
        "qualityIndicators":    lr.get("quality_indicators", {}),
        "modelsUsed":           lr.get("models_used", 1),
        "consensusConfidence":  lr.get("consensus_confidence", 50),
        "scoreBreakdown":       sc.get("breakdown", {}),
    }

    bg.add_task(save_product_analysis, url, result)
    return {"source": "fresh", "data": result}

@app.post("/api/chat")
async def chat(req: ChatRequest):
    try:
        from groq import Groq
        client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are a helpful product advisor. Answer concisely in 2-4 sentences. Be specific and actionable. Never recommend seeking professional advice for product questions."},
                {"role": "user", "content": req.message}
            ],
            max_tokens=300, temperature=0.4,
        )
        return {"reply": resp.choices[0].message.content.strip()}
    except Exception as e:
        log.error(f"Chat error: {e}")
        return {"reply": "Sorry, I couldn't process that. Please try again."}

@app.get("/api/imgproxy")
async def img_proxy(url: str):
    import httpx
    from fastapi.responses import Response
    try:
        hdrs = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"}
        async with httpx.AsyncClient(headers=hdrs, follow_redirects=True, timeout=10) as c:
            r = await c.get(url)
            ct = r.headers.get("content-type", "image/jpeg")
            return Response(content=r.content, media_type=ct,
                          headers={"Cache-Control": "public, max-age=86400",
                                   "Access-Control-Allow-Origin": "*"})
    except:
        raise HTTPException(404, "Image not found")

@app.get("/api/recent")
def recent():
    return get_recent_analyses(10)

@app.get("/", response_class=HTMLResponse)
def index():
    return open("index.html").read()
