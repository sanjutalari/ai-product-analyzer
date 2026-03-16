import json, logging, os, re
from groq import Groq

log = logging.getLogger(__name__)

class LLMAgent:
    def __init__(self):
        self.client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
        self.model  = "llama-3.3-70b-versatile"

    def _chat(self, prompt, max_tokens=1600):
        r = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=0.3,
        )
        return r.choices[0].message.content

    def _parse_json(self, raw):
        raw = raw.strip()
        if "```" in raw:
            parts = raw.split("```")
            raw = parts[1] if len(parts) > 1 else parts[0]
            if raw.startswith("json"):
                raw = raw[4:]
        s, e = raw.find("{"), raw.rfind("}") + 1
        return json.loads(raw[s:e])

    def _extract_product_from_url(self, url):
        """Use AI to identify product from URL structure alone."""
        prompt = f"""Given this product URL: {url}

Extract the product name. Look at:
- The URL path for product name keywords
- Any ASIN codes (Amazon)
- Product IDs or slugs

Return ONLY a JSON object:
{{"product_name": "Full product name you can identify", "brand": "Brand name", "category": "Product category", "confidence": "high/medium/low"}}

If you recognize an Amazon ASIN, use your knowledge to identify the exact product."""
        try:
            return self._parse_json(self._chat(prompt, max_tokens=200))
        except:
            return {"product_name": "", "brand": "", "category": "", "confidence": "low"}

    async def analyze(self, pd):
        name   = pd.get("name", "")
        price  = pd.get("price", "")
        asin   = pd.get("asin", "")
        url    = pd.get("url", "")
        specs  = pd.get("specifications", {})
        desc   = pd.get("description", "")[:400]
        revs   = json.dumps(pd.get("raw_reviews", [])[:5])
        spec_t = "\n".join(f"  {k}: {v}" for k, v in list(specs.items())[:12]) or "  N/A"

        # If no good product name, extract it from URL first
        if not name or name == "Product" or "ASIN" in name or len(name) < 5:
            url_info = self._extract_product_from_url(url)
            if url_info.get("product_name"):
                name = url_info["product_name"]
                pd["name"] = name

        prompt = f"""You are an expert product analyst. Analyze this product thoroughly.

Product: {name}
{f'Amazon ASIN: {asin}' if asin else ''}
{f'Price: {price}' if price else ''}
{f'URL: {url}' if url else ''}
{f'Description: {desc}' if desc else ''}
Specifications:
{spec_t}
Reviews sample: {revs}

Use your comprehensive knowledge of this product (especially if it is a well-known item).
If you can identify the product from the ASIN or name, provide accurate real-world details.
Research-quality analysis with specific features, real pros/cons, and accurate pricing.

Return ONLY valid JSON, no markdown:
{{
  "productName": "Official full product name",
  "brand": "Brand name",
  "estimatedPrice": "$X.XX",
  "summary": "3 sentence expert verdict covering performance, value, and ideal use case",
  "pros": ["Detailed pro 1", "Detailed pro 2", "Detailed pro 3", "Detailed pro 4", "Detailed pro 5"],
  "cons": ["Real con 1", "Real con 2", "Real con 3"],
  "ideal_buyer": "Specific one-sentence buyer profile",
  "avoid_if": "Specific one-sentence avoid profile",
  "tags": ["tag1","tag2","tag3","tag4","tag5","tag6"],
  "avg_rating": 4.3,
  "review_count": "2,847",
  "category": "Product category",
  "quality_indicators": {{
    "build_quality": 80,
    "performance": 85,
    "value_for_money": 75,
    "reliability": 80
  }},
  "key_specs": [
    {{"label": "Spec name", "value": "Spec value"}},
    {{"label": "Spec name", "value": "Spec value"}},
    {{"label": "Spec name", "value": "Spec value"}},
    {{"label": "Spec name", "value": "Spec value"}}
  ]
}}"""
        try:
            p = self._parse_json(self._chat(prompt))
            if p.get("productName") and (not pd.get("name") or pd.get("name") == "Product" or "ASIN" in pd.get("name", "")):
                pd["name"] = p["productName"]
            if not price and p.get("estimatedPrice"):
                pd["price"] = p["estimatedPrice"]
            return p
        except Exception as e:
            log.error(f"LLMAgent.analyze: {e}")
            return {
                "productName": name or "Product",
                "brand": "",
                "estimatedPrice": price,
                "summary": f"Analysis of {name}. Please try again.",
                "pros": ["Product available for purchase"],
                "cons": ["Could not complete full analysis"],
                "ideal_buyer": "Please verify product details.",
                "avoid_if": "You need detailed specs before buying.",
                "tags": pd.get("tags", []),
                "avg_rating": 0,
                "review_count": "0",
                "category": "",
                "quality_indicators": {"build_quality":50,"performance":50,"value_for_money":50,"reliability":50},
                "key_specs": []
            }
