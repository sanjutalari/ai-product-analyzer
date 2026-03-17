"""
review_analyzer.py — Recency-weighted review analysis.
Recent reviews count more than old ones.
"""
import json, logging, os, re
from groq import Groq

log = logging.getLogger(__name__)

# Recency multipliers (by months ago)
def recency_weight(months_ago: int) -> float:
    if months_ago <= 1:   return 3.0
    if months_ago <= 3:   return 2.5
    if months_ago <= 6:   return 2.0
    if months_ago <= 12:  return 1.5
    if months_ago <= 24:  return 1.0
    return 0.6  # old reviews count less

class ReviewAnalyzer:
    def __init__(self):
        self.client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
        self.model  = "llama-3.3-70b-versatile"

    def _weighted_rating(self, reviews: list) -> float:
        """Calculate recency-weighted average rating."""
        total_weight = 0
        weighted_sum = 0
        for r in reviews:
            rating = r.get("rating", 3)
            # Try to extract date info if available
            months_ago = r.get("months_ago", 12)  # default 12 months if unknown
            w = recency_weight(months_ago)
            weighted_sum += rating * w
            total_weight += w
        return round(weighted_sum / total_weight, 1) if total_weight > 0 else 0

    async def analyze(self, raw: list) -> dict:
        if not raw:
            return {
                "avg_rating": 0, "review_count": "0", "reviews": [],
                "sentiment_breakdown": {"positive": 0, "neutral": 0, "negative": 0},
                "common_themes": [], "recency_weighted_rating": 0
            }

        # Calculate both simple and weighted ratings
        ratings = [r.get("rating", 3) for r in raw if r.get("rating")]
        simple_avg = round(sum(ratings) / len(ratings), 1) if ratings else 0
        weighted_avg = self._weighted_rating(raw)

        prompt = f"""Analyze these product reviews carefully. Apply critical thinking.

Reviews: {json.dumps(raw[:10])}

INSTRUCTIONS:
1. Identify genuine sentiment — ignore fake/incentivized reviews (too perfect, generic language)
2. Weight recent reviews more than old ones
3. Look for patterns — repeated complaints = real issue
4. Separate emotional reactions from factual feedback

Return ONLY valid JSON:
{{
  "reviews": [
    {{
      "author": "name",
      "rating": 4,
      "text": "cleaned meaningful review under 120 chars",
      "sentiment": "positive",
      "is_verified": true,
      "key_point": "what this review specifically says about the product"
    }}
  ],
  "sentiment_breakdown": {{"positive": 60, "neutral": 25, "negative": 15}},
  "common_themes": [
    {{"theme": "sound quality", "sentiment": "positive", "count": 8}},
    {{"theme": "battery life", "sentiment": "negative", "count": 5}}
  ],
  "fake_review_percentage": 5,
  "most_praised": "what users love most",
  "most_criticized": "what users complain about most"
}}

Sentiment: positive=4-5★, neutral=3★, negative=1-2★"""

        try:
            raw_r = self.client.chat.completions.create(
                model=self.model, max_tokens=900, temperature=0.1,
                messages=[
                    {"role": "system", "content": "You are a review analysis expert. Return only valid JSON."},
                    {"role": "user", "content": prompt}
                ]
            ).choices[0].message.content.strip()

            if "```" in raw_r:
                parts = raw_r.split("```")
                raw_r = parts[1] if len(parts) > 1 else parts[0]
                if raw_r.startswith("json"):
                    raw_r = raw_r[4:]

            p = json.loads(raw_r[raw_r.find("{"):raw_r.rfind("}") + 1])

            # Use weighted rating for display
            final_avg = weighted_avg if weighted_avg > 0 else simple_avg

            return {
                "avg_rating": final_avg,
                "simple_avg_rating": simple_avg,
                "recency_weighted_rating": weighted_avg,
                "review_count": f"{len(raw):,}",
                "reviews": p.get("reviews", [])[:10],
                "sentiment_breakdown": p.get("sentiment_breakdown", {}),
                "common_themes": p.get("common_themes", []),
                "most_praised": p.get("most_praised", ""),
                "most_criticized": p.get("most_criticized", ""),
                "fake_review_percentage": p.get("fake_review_percentage", 0),
            }
        except Exception as e:
            log.error(f"ReviewAnalyzer: {e}")
            return {
                "avg_rating": simple_avg,
                "recency_weighted_rating": weighted_avg,
                "review_count": str(len(raw)),
                "reviews": raw[:8],
                "sentiment_breakdown": {"positive": 50, "neutral": 30, "negative": 20},
                "common_themes": [],
                "most_praised": "",
                "most_criticized": "",
            }
