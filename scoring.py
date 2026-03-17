"""
scoring.py — Category-aware scoring with recency weighting.
Different products need different scoring weights.
"""
import re, logging
log = logging.getLogger(__name__)

# Category-specific weights
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
    "keyboard":    {"quality":0.25,"value":0.30,"reviews":0.25,"features":0.20},
    "default":     {"quality":0.30,"value":0.25,"reviews":0.25,"features":0.20},
}

# Confidence bonus — multi-model consensus adds points
CONFIDENCE_BONUS = {
    (85, 100): 5,
    (70, 84):  3,
    (55, 69):  1,
    (0,  54):  0,
}

class ScoreGenerator:
    def generate(self, pd: dict, lr: dict, rr: dict, pr: dict) -> dict:
        category = lr.get("detected_category") or lr.get("category", "default")
        W = CATEGORY_WEIGHTS.get(category, CATEGORY_WEIGHTS["default"])

        quality  = self._quality_score(pd, lr)
        value    = self._value_score(pd, pr, lr)
        reviews  = self._review_score(rr, lr)
        features = self._feature_score(pd, lr)

        raw = (
            quality  * W["quality"]  +
            value    * W["value"]    +
            reviews  * W["reviews"]  +
            features * W["features"]
        )

        # Confidence bonus from multi-model consensus
        confidence = lr.get("consensus_confidence") or lr.get("confidence", 50)
        bonus = 0
        for (lo, hi), b in CONFIDENCE_BONUS.items():
            if lo <= confidence <= hi:
                bonus = b
                break

        # Quality indicator adjustment
        qi = lr.get("quality_indicators", {})
        qi_avg = sum(qi.values()) / len(qi) if qi else 70
        qi_adj = (qi_avg - 70) * 0.1  # ±3 points max

        score = int(raw + bonus + qi_adj)
        score = max(5, min(100, score))

        # Value score for display
        value_score = self._value_score(pd, pr, lr)

        log.info(f"Score={score} category={category} Q={quality:.0f} V={value:.0f} R={reviews:.0f} F={features:.0f} bonus={bonus} qi_adj={qi_adj:.1f}")
        return {
            "score": score,
            "value_score": int(value_score),
            "category": category,
            "breakdown": {"quality": quality, "value": value, "reviews": reviews, "features": features}
        }

    def _quality_score(self, pd: dict, lr: dict) -> float:
        """Score based on AI pros/cons ratio + quality indicators."""
        pros = len(lr.get("pros", []))
        cons = len(lr.get("cons", []))
        specs = len(pd.get("specifications", {}))

        base = 50
        base += min(pros * 7, 28)      # up to +28 for pros
        base -= min(cons * 6, 22)      # up to -22 for cons
        base += min(specs * 1.5, 12)   # up to +12 for specs count

        # Quality indicators from AI
        qi = lr.get("quality_indicators", {})
        if qi:
            qi_avg = sum(qi.values()) / len(qi)
            base = (base + qi_avg) / 2  # blend

        return max(10, min(100, base))

    def _value_score(self, pd: dict, pr: dict, lr: dict) -> float:
        """Score based on price vs best available price."""
        current = self._parse_price(pd.get("price", ""))
        best    = self._parse_price(pr.get("best_price", ""))

        if current <= 0 or best <= 0:
            # Use AI's value_for_money estimate
            qi = lr.get("quality_indicators", {})
            return float(qi.get("value_for_money", 55))

        ratio = best / current
        if ratio >= 1.0:    score = 75
        elif ratio >= 0.95: score = 65
        elif ratio >= 0.90: score = 55
        elif ratio >= 0.85: score = 45
        else:               score = 35

        # Adjust for AI value rating
        qi = lr.get("quality_indicators", {})
        ai_value = qi.get("value_for_money", 0)
        if ai_value > 0:
            score = (score * 0.6 + ai_value * 0.4)

        return max(10, min(100, score))

    def _review_score(self, rr: dict, lr: dict) -> float:
        """Score based on average rating + sentiment + review count."""
        avg_rating = float(rr.get("avg_rating", 0)) or float(lr.get("avg_rating", 0))
        if avg_rating <= 0:
            avg_rating = 3.5  # neutral default

        # Base from star rating
        base = (avg_rating / 5) * 100

        # Sentiment adjustment
        sb = rr.get("sentiment_breakdown", {})
        if sb:
            pos = sb.get("positive", 50)
            neg = sb.get("negative", 10)
            sentiment_adj = (pos - neg) * 0.15
            base += sentiment_adj

        # Review count bonus (more reviews = more confidence)
        count_str = str(rr.get("review_count", "0")).replace(",", "").replace("+", "")
        try:
            count = int(re.sub(r'[^0-9]', '', count_str) or "0")
            if count >= 10000: base += 5
            elif count >= 1000: base += 3
            elif count >= 100:  base += 1
        except:
            pass

        return max(10, min(100, base))

    def _feature_score(self, pd: dict, lr: dict) -> float:
        """Score based on feature richness + tags + AI confidence."""
        specs_count = len(pd.get("specifications", {}))
        tags_count  = len(lr.get("tags", pd.get("tags", [])))
        confidence  = lr.get("confidence", 50)

        base = 50
        base += min(specs_count * 2.5, 20)
        base += min(tags_count * 2, 10)
        base += (confidence - 50) * 0.2  # confidence adjust ±10

        return max(20, min(100, base))

    @staticmethod
    def _parse_price(s: str) -> float:
        if not s:
            return 0.0
        m = re.search(r"[\d]+\.?\d*", str(s).replace(",", ""))
        return float(m.group()) if m else 0.0
