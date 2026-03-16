import json, logging, os
from urllib.parse import urlparse
from groq import Groq

log = logging.getLogger(__name__)

class PriceComparator:
    def __init__(self):
        self.client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
        self.model  = "llama-3.3-70b-versatile"

    async def compare(self, product_name, current_price, url):
        domain = urlparse(url).netloc.replace("www.", "").split(".")[0].capitalize()

        query = product_name.replace(" ","+")[:60]
        prompt = f"""Generate realistic price comparisons for this product across platforms.

Product: "{product_name}"
Current price: {current_price} on {domain}
Search query for URLs: {query}

Return ONLY this JSON (no markdown, no extra text):
{{
  "platforms": [
    {{"name": "Amazon",   "icon": "🛒", "price": "$X.XX", "current": false, "url": "https://www.amazon.com/s?k={query}"}},
    {{"name": "Best Buy", "icon": "🔵", "price": "$X.XX", "current": false, "url": "https://www.bestbuy.com/site/searchpage.jsp?st={query}"}},
    {{"name": "Walmart",  "icon": "🟡", "price": "$X.XX", "current": false, "url": "https://www.walmart.com/search?q={query}"}},
    {{"name": "Target",   "icon": "🎯", "price": "$X.XX", "current": false, "url": "https://www.target.com/s?searchTerm={query}"}},
    {{"name": "B&H",      "icon": "📷", "price": "$X.XX", "current": false, "url": "https://www.bhphotovideo.com/c/search?q={query}"}},
    {{"name": "Flipkart", "icon": "🛍️", "price": "$X.XX", "current": false, "url": "https://www.flipkart.com/search?q={query}"}},
    {{"name": "eBay",     "icon": "🏷️", "price": "$X.XX", "current": false, "url": "https://www.ebay.com/sch/i.html?_nkw={query}"}}
  ],
  "best_price": "$X.XX",
  "best_platform": "Platform Name"
}}

Rules: mark {domain} as current:true and use {current_price} for it. Vary others by $5-$40. Include all 7 platforms."""

        try:
            raw = self.client.chat.completions.create(
                model=self.model, max_tokens=500, temperature=0.2,
                messages=[{"role": "user", "content": prompt}]
            ).choices[0].message.content.strip()

            if "```" in raw:
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]

            return json.loads(raw[raw.find("{"):raw.rfind("}") + 1])
        except Exception as e:
            log.error(f"PriceComparator: {e}")
            return {"platforms": [{"name": domain, "icon": "🛒",
                                    "price": current_price, "current": True}],
                    "best_price": current_price, "best_platform": domain}
