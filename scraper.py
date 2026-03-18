"""
scraper.py
Scrapes product pages OR accepts plain product names.
Falls back gracefully — AI analysis works even without scraped data.
"""
import logging, re
from urllib.parse import urlparse, quote_plus
import httpx
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

log = logging.getLogger(__name__)
UA  = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
HDR = {
    "User-Agent": UA,
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate",
}

def is_url(s: str) -> bool:
    """Check if input is a URL or a plain product name."""
    s = s.strip()
    return (s.startswith("http://") or s.startswith("https://") or
            s.startswith("www.") or "/" in s[:50])

def name_to_search_url(name: str) -> str:
    """Convert product name to Amazon India search URL."""
    q = quote_plus(name.strip())
    return f"https://www.amazon.in/s?k={q}"


class ProductScraper:

    async def scrape(self, url_or_name: str) -> dict:
        """Accepts a URL or a plain product name."""
        raw = url_or_name.strip()

        # Plain product name — search Amazon India
        if not is_url(raw):
            log.info(f"Product name input (not URL): '{raw}'")
            return await self._from_name(raw)

        # Normalize URL
        url = raw
        if url.startswith("www."):
            url = "https://" + url

        try:
            async with httpx.AsyncClient(
                headers=HDR, follow_redirects=True,
                timeout=20, verify=False
            ) as c:
                r = await c.get(url)
                if r.status_code == 200:
                    parsed = self._parse(r.text, url)
                    if parsed.get("name") and len(parsed["name"]) > 4 and parsed["name"] != "Product":
                        return parsed
        except Exception as e:
            log.warning(f"Scrape failed for {url}: {e}")

        return self._from_url(url)

    async def _from_name(self, name: str) -> dict:
        """Build product data from a plain product name — AI will fill in the rest."""
        return {
            "name":           name,
            "price":          "",
            "avg_rating":     0,
            "category":       "",
            "images":         [],
            "specifications": {},
            "raw_reviews":    [],
            "tags":           name.lower().split()[:5],
            "description":    f"Product analysis for: {name}",
            "source":         "name_search",
            "url":            name_to_search_url(name),
            "is_name_input":  True,
        }

    def _from_url(self, url: str) -> dict:
        """Fallback: extract info from URL structure."""
        domain = urlparse(url).netloc.replace("www.", "").split(".")[0]
        asin_m = re.search(r"/dp/([A-Z0-9]{10})", url)
        asin   = asin_m.group(1) if asin_m else ""
        name   = f"Amazon product {asin}" if asin else f"Product from {domain}"
        return {
            "name": name, "price": "", "avg_rating": 0,
            "category": "", "images": [], "specifications": {},
            "raw_reviews": [], "tags": [domain],
            "source": domain, "url": url, "asin": asin,
        }

    def _parse(self, html: str, url: str) -> dict:
        s = BeautifulSoup(html, "lxml")
        d = urlparse(url).netloc.lower()
        if "amazon"   in d: return self._amz(s, url)
        if "flipkart" in d: return self._fk(s)
        if "bestbuy"  in d: return self._bb(s)
        if "walmart"  in d: return self._wm(s)
        return self._gen(s)

    def _amz(self, s, url=""):
        name  = self._t(s, "#productTitle") or self._t(s, "h1.a-size-large")
        price = (self._t(s, ".a-price .a-offscreen") or
                 self._t(s, "#priceblock_ourprice") or
                 self._t(s, "#price_inside_buybox") or
                 self._t(s, ".apexPriceToPay .a-offscreen"))
        asin_m = re.search(r"/dp/([A-Z0-9]{10})", url)
        asin   = asin_m.group(1) if asin_m else ""
        specs  = {}
        for row in s.select("#productDetails_techSpec_section_1 tr, #productDetails_db_sections tr"):
            th, td = row.find("th"), row.find("td")
            if th and td: specs[th.get_text(strip=True)] = td.get_text(strip=True)[:120]
        revs = []
        for rv in s.select(".review")[:10]:
            b  = self._t(rv, ".review-text-content span")
            rt = self._t(rv, ".review-rating")
            st = self._f(rt) or 3
            a  = self._t(rv, ".a-profile-name")
            dt = self._t(rv, ".review-date")
            if b:
                revs.append({"author": a or "Customer", "rating": int(st),
                             "text": b[:250], "date": dt})
        imgs = []
        for img in s.select("#altImages img, #imgTagWrapperId img")[:8]:
            u = img.get("data-old-hires") or img.get("src", "")
            if u and "transparent" not in u and u.startswith("http"):
                u = re.sub(r"\._[A-Z]{2}\d+_\.", "._SL500_.", u)
                imgs.append(u)
        tags = [c.get_text(strip=True) for c in s.select("#wayfinding-breadcrumbs_feature_div a")][:6]
        return {"name": (name or "Product").strip(), "price": (price or "").strip(),
                "avg_rating": 0, "category": "", "images": imgs,
                "specifications": specs, "raw_reviews": revs,
                "tags": tags, "source": "amazon", "asin": asin}

    def _fk(self, s):
        name  = (self._t(s, "span.B_NuCI") or self._t(s, "h1.yhB1nd") or
                 self._t(s, "span.VU-ZEz"))
        price = (self._t(s, "div._30jeq3") or self._t(s, "div._16Jk6d") or
                 self._t(s, "div.Nx9bqj"))
        try:    avg_rating = float(self._t(s, "div._3LWZlK").split()[0])
        except: avg_rating = 0
        specs = {}
        for row in s.select("._14cfVK, tr.WJdYP6"):
            cells = row.find_all(["td","li"])
            if len(cells) >= 2:
                specs[cells[0].get_text(strip=True)] = cells[1].get_text(strip=True)[:100]
        revs = []
        for rv in s.select("div.col._2wzgFH")[:8]:
            body = rv.get_text(strip=True)
            if len(body) > 30:
                revs.append({"author":"Flipkart User","rating":int(avg_rating) or 3,
                             "text":body[:200],"sentiment":"neutral"})
        imgs = []
        for img in s.select("img._396cs4, img._2r_T1I")[:6]:
            u = img.get("src","")
            if u.startswith("http"):
                u = re.sub(r"/\d+/\d+/", "/832/832/", u)
                imgs.append(u)
        tags = [c.get_text(strip=True) for c in s.select("div._2kHMtA a")][:6]
        return {"name": (name or "Product").strip(), "price": (price or "").strip(),
                "avg_rating": avg_rating, "category": "", "images": imgs,
                "specifications": specs, "raw_reviews": revs,
                "tags": tags, "source": "flipkart"}

    def _bb(self, s):
        return {"name": (self._t(s,"h1.heading-5") or "Product").strip(),
                "price": self._t(s,".priceView-customer-price span"),
                "avg_rating":0,"category":"","images":[],"specifications":{},
                "raw_reviews":[],"tags":[],"source":"bestbuy"}

    def _wm(self, s):
        return {"name": (self._t(s,"h1.prod-ProductTitle") or "Product").strip(),
                "price": self._t(s,".price-characteristic"),
                "avg_rating":0,"category":"","images":[],"specifications":{},
                "raw_reviews":[],"tags":[],"source":"walmart"}

    def _gen(self, s):
        name  = self._og(s,"og:title") or self._t(s,"h1") or "Product"
        price = self._og(s,"product:price:amount") or ""
        desc  = self._og(s,"og:description") or ""
        imgs  = []
        og_img = self._og(s,"og:image")
        if og_img: imgs.append(og_img)
        return {"name":name.strip()[:200],"price":price.strip(),
                "avg_rating":0,"category":"","images":imgs,
                "specifications":{},"raw_reviews":[],"tags":[],
                "description":desc,"source":"generic"}

    @staticmethod
    def _t(n, sel):
        el = n.select_one(sel)
        return el.get_text(strip=True) if el else ""

    @staticmethod
    def _og(s, p):
        el = s.find("meta", attrs={"property":p}) or s.find("meta",attrs={"name":p})
        return (el.get("content","") if el else "").strip()

    @staticmethod
    def _f(t):
        if not t: return 0.0
        m = re.search(r"[\d.]+", t.replace(",",""))
        return float(m.group()) if m else 0.0
