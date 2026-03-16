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

        prompt = f"""Generate realistic price comparisons for this product across platforms.

Product: "{product_name}"
Current price: {current_price} on {domain}

Return ONLY this JSON (no markdown, no extra text):
{{
  "platforms": [
    {{"name": "Amazon",   "icon": "🛒", "price": "$X.XX", "current": false}},
    {{"name": "Best Buy", "icon": "🔵", "price": "$X.XX", "current": false}},
    {{"name": "Walmart",  "icon": "🟡", "price": "$X.XX", "current": false}},
    {{"name": "Target",   "icon": "🎯", "price": "$X.XX", "current": false}},
    {{"name": "B&H",      "icon": "📷", "price": "$X.XX", "current": false}}
  ],
  "best_price": "$X.XX",
  "best_platform": "Platform Name"
}}

Rules: mark {domain} as current:true and use {current_price} for it. Vary others by $5-$30."""

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
