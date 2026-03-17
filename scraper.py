import re
import logging, re, asyncio
from urllib.parse import urlparse, unquote
import httpx
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)
UA  = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
HDR = {
    "User-Agent": UA,
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

class ProductScraper:
    async def scrape(self, url):
        # Step 1: resolve redirects / short URLs
        resolved_url = await self._resolve_url(url)

        # Step 2: extract info from URL structure
        product_info = self._extract_from_url(resolved_url)

        # Step 3: try to scrape the page
        try:
            async with httpx.AsyncClient(
                headers=HDR, follow_redirects=True, timeout=20
            ) as c:
                r = await c.get(resolved_url)
                if r.status_code == 200:
                    scraped = self._parse(r.text, resolved_url)
                    if scraped.get("name") and len(scraped["name"]) > 5 and scraped["name"] != "Product":
                        scraped["url"] = resolved_url
                        scraped["original_url"] = url
                        return scraped
        except Exception as e:
            log.warning(f"Scrape failed: {e}")

        product_info["url"] = resolved_url
        product_info["original_url"] = url
        return product_info

    async def _resolve_url(self, url):
        """Follow redirects to get the final URL (handles short links)."""
        try:
            async with httpx.AsyncClient(headers=HDR, follow_redirects=True, timeout=10) as c:
                r = await c.head(url)
                return str(r.url)
        except:
            try:
                async with httpx.AsyncClient(headers=HDR, follow_redirects=True, timeout=10) as c:
                    r = await c.get(url, timeout=10)
                    return str(r.url)
            except:
                return url

    def _extract_from_url(self, url):
        domain = urlparse(url).netloc.lower().replace("www.", "")
        path   = urlparse(url).path

        # Extract ASIN from Amazon URLs
        asin_match = re.search(r'/dp/([A-Z0-9]{10})', url)
        asin = asin_match.group(1) if asin_match else ""

        # Try to extract product name from URL path
        name = self._name_from_path(path, domain, asin)
        source = domain.split(".")[0]

        return {
            "name":           name,
            "price":          "",
            "avg_rating":     0,
            "category":       "",
            "images":         [],
            "specifications": {},
            "raw_reviews":    [],
            "tags":           [source],
            "source":         source,
            "asin":           asin,
            "domain":         domain,
        }

    def _name_from_path(self, path, domain, asin):
        """Extract readable product name from URL path."""
        if asin:
            return f"Amazon product (ASIN: {asin})"

        # Flipkart: /product-name-here/p/itemID
        if "flipkart" in domain:
            parts = [p for p in path.split("/") if p and p != "p"]
            if parts:
                name = parts[0].replace("-", " ").replace("_", " ")
                return name[:100].title()

        # Generic: get meaningful path segments
        parts = [p for p in path.split("/") if len(p) > 3 and not re.match(r'^[a-f0-9-]{8,}$', p)]
        if parts:
            name = parts[-1].replace("-", " ").replace("_", " ")
            name = re.sub(r'\.[a-z]{2,4}$', '', name)
            return unquote(name)[:100].title()

        return f"Product from {domain}"

    def _parse(self, html, url):
        s = BeautifulSoup(html, "lxml")
        d = urlparse(url).netloc.lower()
        if "amazon"   in d: return self._amz(s)
        if "flipkart" in d: return self._fk(s)
        if "bestbuy"  in d: return self._bb(s)
        if "walmart"  in d: return self._wm(s)
        if "meesho"   in d: return self._gen(s)
        if "myntra"   in d: return self._gen(s)
        if "snapdeal" in d: return self._gen(s)
        return self._gen(s)

    def _amz(self, s):
        name  = self._t(s, "#productTitle") or self._t(s, "h1.a-size-large")
        price = self._t(s, ".a-price .a-offscreen") or self._t(s, "#priceblock_ourprice")
        specs = {}
        for row in s.select("#productDetails_techSpec_section_1 tr, #productDetails_detailBullets_sections1 tr"):
            th, td = row.find("th"), row.find("td")
            if th and td: specs[th.get_text(strip=True)] = td.get_text(strip=True)
        revs = []
        for rv in s.select(".review")[:8]:
            b = self._t(rv, ".review-text-content")
            st = self._f(self._t(rv, ".review-rating")) or 3
            a = self._t(rv, ".a-profile-name")
            if b: revs.append({"author": a or "Customer", "rating": int(st), "text": b[:250]})
        tags = [c.get_text(strip=True) for c in s.select("#wayfinding-breadcrumbs_feature_div a")][:6]
        return {"name":(name or "Product").strip(), "price":(price or "").strip(),
                "avg_rating":0, "category":"", "images":[], "specifications":specs,
                "raw_reviews":revs, "tags":tags, "source":"amazon"}

    def _fk(self, s):
        name  = self._t(s, "span.B_NuCI") or self._t(s, "h1.yhB1nd") or self._t(s, "h1")
        price = self._t(s, "div._30jeq3") or self._t(s, "div._16Jk6d") or self._t(s, "div._25b18c")
        rating_t = self._t(s, "div._3LWZlK")
        rating = self._f(rating_t)
        specs = {}
        for row in s.select("._14cfVK tr, .rzPiMe tr"):
            cells = row.find_all("td")
            if len(cells) >= 2: specs[cells[0].get_text(strip=True)] = cells[1].get_text(strip=True)
        revs = []
        for rv in s.select("._27M-vq, .t-ZTKy")[:8]:
            body = rv.get_text(strip=True)
            if body: revs.append({"author":"Flipkart Customer","rating":4,"text":body[:250]})
        return {"name":(name or "Product").strip(), "price":(price or "").strip(),
                "avg_rating":rating or 0, "category":"", "images":[],
                "specifications":specs, "raw_reviews":revs, "tags":[], "source":"flipkart"}

    def _bb(self, s):
        return {"name":(self._t(s,"h1.heading-5") or "Product").strip(),
                "price":self._t(s,".priceView-customer-price span"),
                "avg_rating":0,"category":"","images":[],"specifications":{},"raw_reviews":[],"tags":[],"source":"bestbuy"}

    def _wm(self, s):
        return {"name":(self._t(s,"h1.prod-ProductTitle") or "Product").strip(),
                "price":self._t(s,".price-characteristic"),
                "avg_rating":0,"category":"","images":[],"specifications":{},"raw_reviews":[],"tags":[],"source":"walmart"}

    def _gen(self, s):
        name  = self._og(s,"og:title") or self._t(s,"h1") or "Product"
        price = self._og(s,"product:price:amount") or self._t(s,"[itemprop='price']") or ""
        desc  = self._og(s,"og:description") or ""
        rating_t = self._t(s,"[itemprop='ratingValue']")
        rating = self._f(rating_t)
        og_img = self._og(s,'og:image')
        return {"name":name.strip()[:200], "price":price.strip(), "images":[og_img] if og_img else [],
                "avg_rating":rating or 0, "category":"", "images":[],
                "specifications":{}, "raw_reviews":[], "tags":[], "description":desc, "source":"generic"}

    @staticmethod
    def _t(n, sel):
        el = n.select_one(sel); return el.get_text(strip=True) if el else ""

    @staticmethod
    def _og(s, p):
        el = s.find("meta",attrs={"property":p}) or s.find("meta",attrs={"name":p})
        return (el.get("content","") if el else "").strip()

    @staticmethod
    def _f(t):
        if not t: return 0.0
        m = re.search(r"[\d.]+", t.replace(",","")); return float(m.group()) if m else 0.0
