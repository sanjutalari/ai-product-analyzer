"""
llm_agent.py
Multi-model consensus AI analysis.
- Works with product URLs AND plain product names
- Generates alternative/recommended products
- Chain-of-thought prompting for accuracy
"""
import asyncio, json, logging, os, re
from groq import Groq

log = logging.getLogger(__name__)

MODELS = [
    "llama-3.3-70b-versatile",
    "mixtral-8x7b-32768",
    "gemma2-9b-it",
]

CATEGORY_WEIGHTS = {
    "headphones":  {"quality":0.25,"value":0.20,"reviews":0.30,"features":0.25},
    "earbuds":     {"quality":0.25,"value":0.20,"reviews":0.30,"features":0.25},
    "smartphone":  {"quality":0.30,"value":0.20,"reviews":0.25,"features":0.25},
    "laptop":      {"quality":0.30,"value":0.25,"reviews":0.20,"features":0.25},
    "tablet":      {"quality":0.28,"value":0.25,"reviews":0.22,"features":0.25},
    "smartwatch":  {"quality":0.25,"value":0.25,"reviews":0.25,"features":0.25},
    "camera":      {"quality":0.35,"value":0.20,"reviews":0.25,"features":0.20},
    "tv":          {"quality":0.35,"value":0.20,"reviews":0.25,"features":0.20},
    "speaker":     {"quality":0.30,"value":0.20,"reviews":0.30,"features":0.20},
    "default":     {"quality":0.30,"value":0.25,"reviews":0.25,"features":0.20},
}

CATEGORY_KW = {
    "headphones": ["headphone","headset","over-ear","on-ear","wh-","xm","qc"],
    "earbuds":    ["earbud","airpod","tws","in-ear","buds","pod","freebuds"],
    "smartphone": ["phone","iphone","galaxy","pixel","redmi","oneplus","realme","poco","vivo","oppo","motorola"],
    "laptop":     ["laptop","macbook","notebook","thinkpad","chromebook","zenbook","vivobook"],
    "tablet":     ["tablet","ipad","galaxy tab","fire hd"],
    "smartwatch": ["watch","band","fitbit","garmin","amazfit","mi band","fire-boltt"],
    "camera":     ["camera","dslr","mirrorless","gopro","lens"],
    "tv":         ["tv","television","oled","qled","monitor","display"],
    "speaker":    ["speaker","echo","soundbar","bluetooth speaker","homepod"],
    "default":    [],
}


class LLMAgent:
    def __init__(self):
        self.client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

    def _detect_category(self, pd: dict) -> str:
        text = f"{pd.get('name','')} {pd.get('description','')} {' '.join(pd.get('tags',[]))}".lower()
        for cat, kws in CATEGORY_KW.items():
            if kws and any(kw in text for kw in kws):
                return cat
        return "default"

    def _chat(self, prompt: str, model: str, max_tokens: int = 1500) -> str:
        try:
            r = self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are an expert product analyst. Always respond with valid JSON only. No markdown. No extra text. Just the JSON."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=max_tokens,
                temperature=0.15,
            )
            return r.choices[0].message.content
        except Exception as e:
            log.error(f"Model {model} error: {e}")
            return ""

    def _parse(self, raw: str) -> dict:
        if not raw: return {}
        raw = raw.strip()
        if "```" in raw:
            parts = raw.split("```")
            raw = parts[1] if len(parts) > 1 else parts[0]
            if raw.startswith("json"): raw = raw[4:]
        s, e = raw.find("{"), raw.rfind("}") + 1
        if s < 0 or e <= s: return {}
        try:    return json.loads(raw[s:e])
        except: return {}

    def _build_prompt(self, pd: dict, category: str) -> str:
        name  = pd.get("name", "Unknown")
        price = pd.get("price", "")
        asin  = pd.get("asin", "")
        url   = pd.get("url", "")
        specs = pd.get("specifications", {})
        desc  = pd.get("description", "")[:400]
        revs  = pd.get("raw_reviews", [])[:6]
        spec_t = "\n".join(f"  {k}: {v}" for k, v in list(specs.items())[:15]) or "  N/A"
        rev_t  = "\n".join(f"  [{r.get('rating',3)}★] {r.get('text','')[:120]}" for r in revs) or "  None"

        ref = f"ASIN: {asin}" if asin else f"Product: {name}"
        if url: ref += f"\nURL: {url}"

        return f"""Analyze this product as a world-class product expert. Use ALL your knowledge.

PRODUCT IDENTIFICATION:
{ref}
Price: {price}
Category: {category}
Description: {desc}

SPECIFICATIONS:
{spec_t}

CUSTOMER REVIEWS SAMPLE:
{rev_t}

INSTRUCTIONS:
1. If you recognize this product (by ASIN, name, or model number), use your FULL knowledge
2. Be honest and critical — do NOT give inflated scores
3. Score weights for {category}: {json.dumps(CATEGORY_WEIGHTS.get(category, CATEGORY_WEIGHTS["default"]))}
4. Alternatives must be REAL products that are actually better in some way
5. For alternatives: include products from same price range AND premium tier

Return ONLY this JSON (no markdown):
{{
  "productName": "Full official product name with model number and variant",
  "estimatedPrice": "$X.XX or ₹X,XXX",
  "category": "{category}",
  "summary": "3 sentences: real-world performance, key strength, key weakness, verdict",
  "pros": [
    "Specific measurable pro (e.g. 30hr battery, not just good battery)",
    "Specific pro 2",
    "Specific pro 3",
    "Specific pro 4"
  ],
  "cons": [
    "Specific measurable con with context",
    "Specific con 2",
    "Specific con 3"
  ],
  "ideal_buyer": "Precise 1-sentence description of ideal buyer",
  "avoid_if": "Precise 1-sentence description of who should avoid",
  "competitors": [
    {{"name": "Competitor 1", "vs": "better", "reason": "specific reason why", "price": "approx price"}},
    {{"name": "Competitor 2", "vs": "similar", "reason": "how they compare", "price": "approx price"}},
    {{"name": "Competitor 3", "vs": "worse", "reason": "why this product wins", "price": "approx price"}}
  ],
  "alternatives": [
    {{
      "name": "Product Name with Model",
      "reason": "Why this is a good alternative — specific advantage",
      "price": "₹X,XXX or $XX",
      "rating": 4.5,
      "why_better": "What it does better than the analyzed product",
      "search_url": "https://www.amazon.in/s?k=product+name+model",
      "tier": "same_price"
    }},
    {{
      "name": "Premium Alternative Name",
      "reason": "Why worth the extra cost",
      "price": "₹X,XXX or $XX",
      "rating": 4.7,
      "why_better": "Specific improvement over analyzed product",
      "search_url": "https://www.amazon.in/s?k=premium+product+name",
      "tier": "premium"
    }},
    {{
      "name": "Budget Alternative Name",
      "reason": "Best value option",
      "price": "₹X,XXX or $XX",
      "rating": 4.2,
      "why_better": "Good enough for most people at lower cost",
      "search_url": "https://www.amazon.in/s?k=budget+product+name",
      "tier": "budget"
    }}
  ],
  "avg_rating": 4.2,
  "review_count": "2,500+",
  "tags": ["tag1","tag2","tag3","tag4","tag5"],
  "quality_indicators": {{
    "build_quality": 75,
    "performance": 80,
    "value_for_money": 70,
    "reliability": 78
  }},
  "confidence": 85
}}"""

    def _merge(self, results: list[dict], category: str) -> dict:
        valid = [r for r in results if r and r.get("productName")]
        if not valid: return results[0] if results else {}
        if len(valid) == 1: return valid[0]

        base = max(valid, key=lambda x: x.get("confidence", 50))

        # Average quality indicators
        qi_keys = ["build_quality", "performance", "value_for_money", "reliability"]
        merged_qi = {}
        for k in qi_keys:
            vals = [r.get("quality_indicators", {}).get(k, 70) for r in valid if r.get("quality_indicators")]
            merged_qi[k] = int(sum(vals) / len(vals)) if vals else 70

        # Average ratings
        ratings = [r.get("avg_rating", 0) for r in valid if r.get("avg_rating", 0) > 0]
        if ratings: base["avg_rating"] = round(sum(ratings) / len(ratings), 1)

        base["quality_indicators"] = merged_qi
        base["models_used"] = len(valid)
        base["consensus_confidence"] = int(sum(r.get("confidence", 50) for r in valid) / len(valid))

        # Use alternatives from highest-confidence model (they need to be specific)
        for r in valid:
            if r.get("alternatives") and len(r["alternatives"]) >= 2:
                base["alternatives"] = r["alternatives"]
                break

        return base

    async def analyze(self, pd: dict) -> dict:
        category = self._detect_category(pd)
        prompt   = self._build_prompt(pd, category)

        loop = asyncio.get_event_loop()
        tasks = [
            loop.run_in_executor(None, self._chat, prompt, model, 1500)
            for model in MODELS
        ]
        raws = await asyncio.gather(*tasks, return_exceptions=True)

        parsed = []
        for i, raw in enumerate(raws):
            if isinstance(raw, Exception):
                log.warning(f"Model {MODELS[i]}: {raw}")
                continue
            p = self._parse(raw)
            if p:
                parsed.append(p)
                log.info(f"Model {MODELS[i]}: conf={p.get('confidence','?')} name={p.get('productName','?')}")

        if not parsed:
            return self._fallback(pd, category)

        merged = self._merge(parsed, category)

        # Enrich scraped data
        if not pd.get("price") and merged.get("estimatedPrice"):
            pd["price"] = merged["estimatedPrice"]
        if merged.get("tags") and pd.get("tags"):
            merged["tags"] = list(set(merged["tags"] + pd["tags"]))[:8]

        merged["detected_category"] = category
        return merged

    def _fallback(self, pd: dict, category: str) -> dict:
        name = pd.get("name", "Product")
        return {
            "productName": name,
            "estimatedPrice": pd.get("price", ""),
            "category": category,
            "summary": f"Could not complete analysis for {name}. Please try again.",
            "pros": ["Product available for purchase"],
            "cons": ["Analysis incomplete — please retry"],
            "ideal_buyer": "Verify product details before purchasing.",
            "avoid_if": "You need a complete analysis before deciding.",
            "competitors": [],
            "alternatives": [],
            "tags": pd.get("tags", []),
            "avg_rating": 0,
            "review_count": "0",
            "quality_indicators": {"build_quality":50,"performance":50,"value_for_money":50,"reliability":50},
            "confidence": 0,
        }
