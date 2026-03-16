import logging, re
from urllib.parse import urlparse
import httpx
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)
UA  = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
HDR = {
    "User-Agent": UA,
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

class ProductScraper:
    async def scrape(self, url):
        """Try to scrape, but always fall back to URL-based analysis."""
        domain = urlparse(url).netloc.lower()
        product_info = self._extract_from_url(url)

        try:
            async with httpx.AsyncClient(
                headers=HDR, follow_redirects=True, timeout=20
            ) as c:
                r = await c.get(url)
                if r.status_code == 200:
                    scraped = self._parse(r.text, url)
                    # Only use scraped data if we got a real product name
                    if scraped.get("name") and len(scraped["name"]) > 5 and scraped["name"] != "Product":
                        return scraped
        except Exception as e:
            log.warning(f"Scrape failed ({e}), using URL analysis")

        # Fall back to URL-based product info for AI to analyze
        return product_info

    def _extract_from_url(self, url):
        """Extract product info from URL structure for AI fallback."""
        domain = urlparse(url).netloc.lower().replace("www.", "")
        path   = urlparse(url).path

        # Try to get ASIN from Amazon URL
        asin_match = re.search(r'/dp/([A-Z0-9]{10})', url)
        asin = asin_match.group(1) if asin_match else ""

        # Build a useful product description for the AI
        source = domain.split(".")[0]
        name   = f"Product from {domain}"
        if asin:
            name = f"Amazon product ASIN {asin}"

        return {
            "name":          name,
            "price":         "",
            "avg_rating":    0,
            "category":      "",
            "images":        [],
            "specifications": {},
            "raw_reviews":   [],
            "tags":          [source],
            "source":        source,
            "url":           url,
            "asin":          asin,
        }

    def _parse(self, html, url):
        s      = BeautifulSoup(html, "lxml")
        domain = urlparse(url).netloc.lower()
        if "amazon"  in domain: return self._amz(s)
        if "bestbuy" in domain: return self._bb(s)
        if "walmart" in domain: return self._wm(s)
        if "flipkart" in domain: return self._fk(s)
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

    def _fk(self, s):
        name  = self._t(s, "span.B_NuCI") or self._t(s, "h1.yhB1nd")
        price = self._t(s, "div._30jeq3") or self._t(s, "div._16Jk6d")
        return {"name": (name or "Product").strip(), "price": (price or "").strip(),
                "avg_rating": 0, "category": "", "images": [],
                "specifications": {}, "raw_reviews": [], "tags": [], "source": "flipkart"}

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
