import json, logging, os
from groq import Groq

log = logging.getLogger(__name__)

class LLMAgent:
    def __init__(self):
        self.client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
        self.model  = "llama-3.3-70b-versatile"

    def _chat(self, prompt, max_tokens=1200):
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
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw[raw.find("{"):raw.rfind("}") + 1])

    async def analyze(self, pd):
        name   = pd.get("name", "Unknown")
        price  = pd.get("price", "N/A")
        specs  = pd.get("specifications", {})
        desc   = pd.get("description", "")[:400]
        revs   = json.dumps(pd.get("raw_reviews", [])[:5])
        spec_t = "\n".join(f"  {k}: {v}" for k, v in list(specs.items())[:12]) or "  N/A"

        prompt = f"""You are an expert product analyst. Analyze this product carefully.

PRODUCT: {name}
PRICE: {price}
DESCRIPTION: {desc}
SPECIFICATIONS:
{spec_t}
CUSTOMER REVIEWS: {revs}

Return ONLY a valid JSON object. No markdown. No explanation. Just the JSON.

{{
  "summary": "2-3 sentence expert summary of this specific product and whether it is worth buying",
  "pros": ["specific pro 1", "specific pro 2", "specific pro 3", "specific pro 4"],
  "cons": ["specific con 1", "specific con 2", "specific con 3"],
  "ideal_buyer": "one sentence describing who should buy this",
  "avoid_if": "one sentence describing who should NOT buy this",
  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5"],
  "quality_indicators": {{
    "build_quality": 75,
    "performance": 80,
    "value_for_money": 70,
    "reliability": 75
  }}
}}"""
        try:
            p = self._parse_json(self._chat(prompt))
            if len(p.get("tags", [])) < 3 and pd.get("tags"):
                p["tags"] = list(set(p.get("tags", []) + pd["tags"]))[:8]
            return p
        except Exception as e:
            log.error(f"LLMAgent.analyze: {e}")
            return {
                "summary": f"{name} at {price}. Analysis could not be completed.",
                "pros": ["Product is available for purchase"],
                "cons": ["Could not complete full analysis"],
                "ideal_buyer": "Please verify product details before purchasing.",
                "avoid_if": "You need detailed specifications before buying.",
                "tags": pd.get("tags", []),
                "quality_indicators": {"build_quality": 50, "performance": 50,
                                        "value_for_money": 50, "reliability": 50}
            }
