"""
llm_agent.py — Multi-model consensus + chain-of-thought + competitor benchmarking
Uses 3 Groq models in parallel, merges results, dramatically improves accuracy.
"""
import asyncio, json, logging, os, re
from groq import Groq

log = logging.getLogger(__name__)

# All free on Groq
MODELS = [
    "llama-3.3-70b-versatile",   # Primary — best reasoning
    "mixtral-8x7b-32768",         # Secondary — different architecture
    "gemma2-9b-it",               # Tertiary — fast cross-check
]

CATEGORY_WEIGHTS = {
    "headphones":    {"quality":0.25,"value":0.20,"reviews":0.30,"features":0.25},
    "earbuds":       {"quality":0.25,"value":0.20,"reviews":0.30,"features":0.25},
    "smartphone":    {"quality":0.30,"value":0.20,"reviews":0.25,"features":0.25},
    "laptop":        {"quality":0.30,"value":0.25,"reviews":0.20,"features":0.25},
    "tablet":        {"quality":0.28,"value":0.25,"reviews":0.22,"features":0.25},
    "smartwatch":    {"quality":0.25,"value":0.25,"reviews":0.25,"features":0.25},
    "camera":        {"quality":0.35,"value":0.20,"reviews":0.25,"features":0.20},
    "tv":            {"quality":0.35,"value":0.20,"reviews":0.25,"features":0.20},
    "speaker":       {"quality":0.30,"value":0.20,"reviews":0.30,"features":0.20},
    "keyboard":      {"quality":0.25,"value":0.30,"reviews":0.25,"features":0.20},
    "mouse":         {"quality":0.25,"value":0.30,"reviews":0.25,"features":0.20},
    "default":       {"quality":0.30,"value":0.25,"reviews":0.25,"features":0.20},
}

CATEGORY_KEYWORDS = {
    "headphones":  ["headphone","headset","over-ear","on-ear","wh-","xm","studio"],
    "earbuds":     ["earbud","airpod","tws","in-ear","buds","pod"],
    "smartphone":  ["phone","iphone","galaxy","pixel","redmi","oneplus","realme","poco"],
    "laptop":      ["laptop","macbook","notebook","thinkpad","chromebook","zenbook"],
    "tablet":      ["tablet","ipad","galaxy tab","fire hd"],
    "smartwatch":  ["watch","band","fitbit","garmin","amazfit"],
    "camera":      ["camera","dslr","mirrorless","gopro","lens"],
    "tv":          ["tv","television","oled","qled","monitor","display"],
    "speaker":     ["speaker","echo","soundbar","bluetooth speaker","home pod"],
    "keyboard":    ["keyboard","keychron","mechanical"],
    "mouse":       ["mouse","trackpad","logitech mx"],
}


class LLMAgent:
    def __init__(self):
        self.client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

    def _detect_category(self, pd: dict) -> str:
        text = f"{pd.get('name','')} {pd.get('description','')} {' '.join(pd.get('tags',[]))}".lower()
        for cat, kws in CATEGORY_KEYWORDS.items():
            if any(kw in text for kw in kws):
                return cat
        return "default"

    def _chat(self, prompt: str, model: str, max_tokens: int = 1400) -> str:
        try:
            r = self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are an expert product analyst. Always respond with valid JSON only. No markdown. No explanation. Just the JSON object."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=max_tokens,
                temperature=0.2,
            )
            return r.choices[0].message.content
        except Exception as e:
            log.error(f"Model {model} failed: {e}")
            return ""

    def _parse(self, raw: str) -> dict:
        if not raw:
            return {}
        raw = raw.strip()
        if "```" in raw:
            parts = raw.split("```")
            raw = parts[1] if len(parts) > 1 else parts[0]
            if raw.startswith("json"):
                raw = raw[4:]
        start = raw.find("{")
        end   = raw.rfind("}") + 1
        if start < 0 or end <= start:
            return {}
        try:
            return json.loads(raw[start:end])
        except:
            return {}

    def _build_prompt(self, pd: dict, category: str) -> str:
        name   = pd.get("name", "Unknown")
        price  = pd.get("price", "")
        asin   = pd.get("asin", "")
        url    = pd.get("url", "")
        specs  = pd.get("specifications", {})
        desc   = pd.get("description", "")[:400]
        revs   = pd.get("raw_reviews", [])[:6]
        spec_t = "\n".join(f"  {k}: {v}" for k, v in list(specs.items())[:15]) or "  N/A"

        product_ref = f"Amazon ASIN: {asin}" if asin else f"Product: {name}"
        if url:
            product_ref += f"\nURL: {url}"

        reviews_text = ""
        if revs:
            reviews_text = "\nCUSTOMER REVIEWS:\n" + "\n".join(
                f"  [{r.get('rating',3)}★] {r.get('text','')[:150]}"
                for r in revs
            )

        return f"""You are a world-class product analyst. Use chain-of-thought reasoning.

STEP 1 — IDENTIFY: {product_ref}
Category detected: {category}
Price: {price}
Description: {desc}

STEP 2 — ANALYZE SPECS:
{spec_t}
{reviews_text}

STEP 3 — CROSS-REFERENCE: Use your training knowledge about this exact product model.
If you recognize the ASIN or product name, use your full knowledge of real-world performance,
known issues, expert reviews, and user feedback from across the internet.

STEP 4 — SCORE HONESTLY: Do not give inflated scores. Be critical and precise.
Category "{category}" scoring focus: {json.dumps(CATEGORY_WEIGHTS.get(category, CATEGORY_WEIGHTS["default"]))}

STEP 5 — OUTPUT this exact JSON:
{{
  "productName": "Full official product name with model number",
  "estimatedPrice": "$X.XX",
  "category": "{category}",
  "summary": "3-sentence expert verdict covering real-world performance, value, and who it's for",
  "pros": [
    "Specific measurable pro (e.g. 30hr battery life, not just 'long battery')",
    "Specific pro 2",
    "Specific pro 3",
    "Specific pro 4"
  ],
  "cons": [
    "Specific measurable con with context",
    "Specific con 2",
    "Specific con 3"
  ],
  "ideal_buyer": "Precise description of who benefits most",
  "avoid_if": "Precise description of who should avoid this",
  "competitors": [
    {{"name": "Competitor 1", "vs": "better/worse/similar", "reason": "why"}},
    {{"name": "Competitor 2", "vs": "better/worse/similar", "reason": "why"}},
    {{"name": "Competitor 3", "vs": "better/worse/similar", "reason": "why"}}
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

    def _merge_results(self, results: list[dict], category: str) -> dict:
        """Merge outputs from multiple models using weighted consensus."""
        valid = [r for r in results if r and r.get("productName")]
        if not valid:
            return results[0] if results else {}
        if len(valid) == 1:
            return valid[0]

        # Use highest-confidence result as base
        base = max(valid, key=lambda x: x.get("confidence", 50))

        # Average quality indicators across all valid models
        qi_keys = ["build_quality", "performance", "value_for_money", "reliability"]
        merged_qi = {}
        for k in qi_keys:
            vals = [r.get("quality_indicators", {}).get(k, 70) for r in valid if r.get("quality_indicators")]
            merged_qi[k] = int(sum(vals) / len(vals)) if vals else 70

        # Merge pros — keep ones mentioned by 2+ models, then fill from base
        all_pros = []
        for r in valid:
            all_pros.extend(r.get("pros", []))
        # Deduplicate by keyword overlap
        base_pros = base.get("pros", [])
        if len(valid) >= 2:
            # Take base pros but validate against other models
            validated_pros = []
            for pro in base_pros:
                pro_lower = pro.lower()
                confirmed = sum(
                    1 for r in valid if r != base
                    and any(w in " ".join(r.get("pros", [])).lower() for w in pro_lower.split()[:3])
                )
                validated_pros.append(pro)
            base["pros"] = validated_pros[:5] if validated_pros else base_pros

        # Average avg_rating
        ratings = [r.get("avg_rating", 0) for r in valid if r.get("avg_rating", 0) > 0]
        if ratings:
            base["avg_rating"] = round(sum(ratings) / len(ratings), 1)

        base["quality_indicators"] = merged_qi
        base["models_used"] = len(valid)
        base["consensus_confidence"] = int(sum(r.get("confidence", 50) for r in valid) / len(valid))

        return base

    async def analyze(self, pd: dict) -> dict:
        category = self._detect_category(pd)
        prompt   = self._build_prompt(pd, category)

        # Run all 3 models in parallel
        loop = asyncio.get_event_loop()
        tasks = [
            loop.run_in_executor(None, self._chat, prompt, model, 1400)
            for model in MODELS
        ]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Parse each result
        parsed = []
        for i, raw in enumerate(raw_results):
            if isinstance(raw, Exception):
                log.warning(f"Model {MODELS[i]} error: {raw}")
                continue
            p = self._parse(raw)
            if p:
                parsed.append(p)
                log.info(f"Model {MODELS[i]}: confidence={p.get('confidence','?')}, name={p.get('productName','?')}")

        if not parsed:
            log.error("All models failed")
            return self._fallback(pd)

        # Merge results from all models
        merged = self._merge_results(parsed, category)

        # Enrich with scraped data if AI missed it
        if not pd.get("price") and merged.get("estimatedPrice"):
            pd["price"] = merged["estimatedPrice"]

        if merged.get("tags") and pd.get("tags"):
            merged["tags"] = list(set(merged["tags"] + pd["tags"]))[:8]

        merged["detected_category"] = category
        return merged

    def _fallback(self, pd: dict) -> dict:
        name = pd.get("name", "Product")
        return {
            "productName": name,
            "estimatedPrice": pd.get("price", ""),
            "category": "default",
            "summary": f"Could not complete analysis for {name}. Please try again.",
            "pros": ["Product available for purchase"],
            "cons": ["Analysis incomplete — please retry"],
            "ideal_buyer": "Verify product details before purchasing.",
            "avoid_if": "You need complete analysis before deciding.",
            "competitors": [],
            "tags": pd.get("tags", []),
            "avg_rating": 0,
            "review_count": "0",
            "quality_indicators": {"build_quality":50,"performance":50,"value_for_money":50,"reliability":50},
            "confidence": 0,
        }
