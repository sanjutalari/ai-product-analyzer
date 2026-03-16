import json, logging, os
from groq import Groq

log = logging.getLogger(__name__)

class LLMAgent:
    def __init__(self):
        self.client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
        self.model  = "llama-3.3-70b-versatile"

    def _chat(self, prompt, max_tokens=1400):
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
        start = raw.find("{")
        end   = raw.rfind("}") + 1
        return json.loads(raw[start:end])

    async def analyze(self, pd):
        name   = pd.get("name", "Unknown")
        price  = pd.get("price", "")
        asin   = pd.get("asin", "")
        url    = pd.get("url", "")
        specs  = pd.get("specifications", {})
        desc   = pd.get("description", "")[:400]
        revs   = json.dumps(pd.get("raw_reviews", [])[:5])
        spec_t = "\n".join(f"  {k}: {v}" for k, v in list(specs.items())[:12]) or "  N/A"

        # Build context — use ASIN if we have it so AI can identify the product
        product_ref = ""
        if asin:
            product_ref = f"Amazon ASIN: {asin} (use your knowledge to identify this product)"
        elif name and name != "Product" and "ASIN" not in name:
            product_ref = f"Product name: {name}"
        else:
            product_ref = f"Product URL: {url}"

        prompt = f"""You are an expert product analyst with deep knowledge of consumer electronics, 
gadgets, and products sold on Amazon and other retailers.

{product_ref}
{f'Price: {price}' if price else ''}
{f'Description: {desc}' if desc else ''}
Specifications:
{spec_t}
Customer reviews sample: {revs}

IMPORTANT: If this is a well-known product (identified by ASIN or name), use your full knowledge 
of this product to provide accurate, detailed analysis. Do not make up information.

Return ONLY a valid JSON object, no markdown, no explanation:
{{
  "productName": "Full official product name",
  "estimatedPrice": "$X.XX",
  "summary": "2-3 sentence expert analysis covering key strengths, weaknesses, and ideal use case",
  "pros": [
    "Specific pro with real detail",
    "Specific pro 2",
    "Specific pro 3",
    "Specific pro 4"
  ],
  "cons": [
    "Specific con with real detail",
    "Specific con 2",
    "Specific con 3"
  ],
  "ideal_buyer": "One sentence: who should buy this product",
  "avoid_if": "One sentence: who should NOT buy this",
  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5"],
  "avg_rating": 4.3,
  "review_count": "2,500+",
  "quality_indicators": {{
    "build_quality": 80,
    "performance": 85,
    "value_for_money": 75,
    "reliability": 80
  }}
}}"""

        try:
            p = self._parse_json(self._chat(prompt))
            # Merge AI-identified name back if scraper didn't get one
            if p.get("productName") and (not pd.get("name") or
               pd.get("name") == "Product" or "ASIN" in pd.get("name", "")):
                pd["name"] = p["productName"]
            # Fill in price if scraper missed it
            if not price and p.get("estimatedPrice"):
                pd["price"] = p["estimatedPrice"]
            if len(p.get("tags", [])) < 3 and pd.get("tags"):
                p["tags"] = list(set(p.get("tags", []) + pd["tags"]))[:8]
            return p
        except Exception as e:
            log.error(f"LLMAgent.analyze: {e}")
            return {
                "productName": name,
                "estimatedPrice": price,
                "summary": f"Analysis of {name}. Please try again.",
                "pros":  ["Product available for purchase"],
                "cons":  ["Could not complete full analysis — please retry"],
                "ideal_buyer": "Please verify product details before purchasing.",
                "avoid_if":    "You need detailed specs before buying.",
                "tags":  pd.get("tags", []),
                "avg_rating": 0,
                "review_count": "0",
                "quality_indicators": {"build_quality": 50, "performance": 50,
                                        "value_for_money": 50, "reliability": 50}
            }
