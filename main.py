import logging, os, time
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from database       import init_db, save_product_analysis, get_product_analysis, get_recent_analyses
from scraper        import ProductScraper
from review_analyzer import ReviewAnalyzer
from price_compare  import PriceComparator
from price_history  import PriceHistoryTracker
from scoring        import ScoreGenerator
from llm_agent      import LLMAgent

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    log.info("Database ready")
    yield

app = FastAPI(title="AI Product Analyzer", version="1.0.0", lifespan=lifespan)
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

    if not req.force_refresh:
        cached = get_product_analysis(url)
        if cached:
            return {"source": "cache", "data": cached}

    try:
        pd2 = await ProductScraper().scrape(url)
    except Exception as e:
        raise HTTPException(422, f"Could not scrape URL: {e}")

    lr  = await LLMAgent().analyze(pd2)
    rr  = await ReviewAnalyzer().analyze(pd2.get("raw_reviews", []))
    pr  = await PriceComparator().compare(pd2.get("name", ""), pd2.get("price", ""), url)
    hi  = await PriceHistoryTracker().get_history(url, pd2.get("price", ""))
    sc  = ScoreGenerator().generate(pd2, lr, rr, pr)

    result = {
        "url":          url,
        "productName":  pd2.get("name", "Unknown Product"),
        "score":        sc["score"],
        "valueScore":   sc["value_score"],
        "avgRating":    rr.get("avg_rating", 0),
        "reviewCount":  rr.get("review_count", "0"),
        "currentPrice": pd2.get("price", ""),
        "bestPrice":    pr.get("best_price", ""),
        "lowestPrice":  hi.get("lowest", ""),
        "highestPrice": hi.get("highest", ""),
        "summary":      lr.get("summary", ""),
        "pros":         lr.get("pros", []),
        "cons":         lr.get("cons", []),
        "idealBuyer":   lr.get("ideal_buyer", ""),
        "avoidIf":      lr.get("avoid_if", ""),
        "tags":         pd2.get("tags", []),
        "reviews":      rr.get("reviews", []),
        "platforms":    pr.get("platforms", []),
        "priceHistory": hi.get("history", []),
    }

    bg.add_task(save_product_analysis, url, result)
    return {"source": "fresh", "data": result}

@app.get("/api/recent")
def recent():
    return get_recent_analyses(10)

@app.get("/", response_class=HTMLResponse)
def index():
    return open("index.html").read()
