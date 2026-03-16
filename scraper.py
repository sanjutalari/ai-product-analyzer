import asyncio, logging, re
from urllib.parse import urlparse
import httpx
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

log = logging.getLogger(__name__)
UA  = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
HDR = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}

class ProductScraper:
    # Render free tier has no Playwright support — use httpx only
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=6))
    async def scrape(self, url):
        async with httpx.AsyncClient(headers=HDR, follow_redirects=True, timeout=30) as c:
            r = await c.get(url)
            r.raise_for_status()
            return self._parse(r.text, url)

    def _parse(self, html, url):
        s = BeautifulSoup(html, "lxml")
        d = urlparse(url).netloc.lower()
        if "amazon"  in d: return self._amz(s)
        if "bestbuy" in d: return self._bb(s)
        if "walmart" in d: return self._wm(s)
        return self._gen(s)

    def _amz(self, s):
        name  = self._t(s, "#productTitle") or self._t(s, "h1.a-size-large")
        price = self._t(s, ".a-price .a-offscreen") or self._t(s, "#priceblock_ourprice")
        specs = {}
        for row in s.select("#productDetails_techSpec_section_1 tr"):
            th, td = row.find("th"), row.find("td")
            if th and td:
                specs[th.get_text(strip=True)] = td.get_text(strip=True)
        revs = []
        for rv in s.select(".review")[:8]:
            b  = self._t(rv, ".review-text-content")
            st = self._f(self._t(rv, ".review-rating")) or 3
            a  = self._t(rv, ".a-profile-name")
            if b:
                revs.append({"author": a or "Customer", "rating": int(st), "text": b[:250]})
        tags = [c.get_text(strip=True) for c in
                s.select("#wayfinding-breadcrumbs_feature_div a")][:6]
        return {"name": (name or "Product").strip(), "price": (price or "").strip(),
                "avg_rating": 0, "category": "", "images": [],
                "specifications": specs, "raw_reviews": revs, "tags": tags, "source": "amazon"}

    def _bb(self, s):
        return {"name": (self._t(s, "h1.heading-5") or "Product").strip(),
                "price": self._t(s, ".priceView-customer-price span"),
                "avg_rating": 0, "category": "", "images": [],
                "specifications": {}, "raw_reviews": [], "tags": [], "source": "bestbuy"}

    def _wm(self, s):
        return {"name": (self._t(s, "h1.prod-ProductTitle") or "Product").strip(),
                "price": self._t(s, ".price-characteristic"),
                "avg_rating": 0, "category": "", "images": [],
                "specifications": {}, "raw_reviews": [], "tags": [], "source": "walmart"}

    def _gen(self, s):
        name  = self._og(s, "og:title") or self._t(s, "h1") or "Product"
        price = self._og(s, "product:price:amount") or ""
        desc  = self._og(s, "og:description") or ""
        return {"name": name.strip()[:200], "price": price.strip(),
                "avg_rating": 0, "category": "", "images": [],
                "specifications": {}, "raw_reviews": [], "tags": [],
                "description": desc, "source": "generic"}

    @staticmethod
    def _t(n, sel):
        el = n.select_one(sel)
        return el.get_text(strip=True) if el else ""

    @staticmethod
    def _og(s, p):
        el = s.find("meta", attrs={"property": p}) or s.find("meta", attrs={"name": p})
        return (el.get("content", "") if el else "").strip()

    @staticmethod
    def _f(t):
        if not t: return 0.0
        m = re.search(r"[\d.]+", t.replace(",", ""))
        return float(m.group()) if m else 0.0
