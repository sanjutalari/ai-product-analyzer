import json, logging, os
from groq import Groq

log = logging.getLogger(__name__)

class ReviewAnalyzer:
    def __init__(self):
        self.client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
        self.model  = "llama-3.3-70b-versatile"

    async def analyze(self, raw):
        if not raw:
            return {"avg_rating": 0, "review_count": "0", "reviews": [],
                    "sentiment_breakdown": {"positive": 0, "neutral": 0, "negative": 0},
                    "common_themes": []}

        ratings = [r.get("rating", 3) for r in raw if r.get("rating")]
        avg     = round(sum(ratings) / len(ratings), 1) if ratings else 0

        prompt = f"""Analyze these product reviews. Return ONLY valid JSON, no markdown.

Reviews: {json.dumps(raw[:8])}

Return this exact structure:
{{
  "reviews": [
    {{"author": "name", "rating": 4, "text": "cleaned review under 100 chars", "sentiment": "positive"}}
  ],
  "sentiment_breakdown": {{"positive": 60, "neutral": 25, "negative": 15}},
  "common_themes": ["theme1", "theme2", "theme3"]
}}

sentiment must be: positive (4-5 stars), neutral (3 stars), negative (1-2 stars)."""

        try:
            raw_r = self.client.chat.completions.create(
                model=self.model, max_tokens=800, temperature=0.2,
                messages=[{"role": "user", "content": prompt}]
            ).choices[0].message.content.strip()

            if "```" in raw_r:
                raw_r = raw_r.split("```")[1]
                if raw_r.startswith("json"):
                    raw_r = raw_r[4:]

            p = json.loads(raw_r[raw_r.find("{"):raw_r.rfind("}") + 1])
            return {"avg_rating": avg, "review_count": f"{len(raw):,}",
                    "reviews": p.get("reviews", []),
                    "sentiment_breakdown": p.get("sentiment_breakdown", {}),
                    "common_themes": p.get("common_themes", [])}
        except Exception as e:
            log.error(f"ReviewAnalyzer: {e}")
            return {"avg_rating": avg, "review_count": str(len(raw)),
                    "reviews": raw[:5],
                    "sentiment_breakdown": {"positive": 0, "neutral": 0, "negative": 0},
                    "common_themes": []}
