import re, logging
log = logging.getLogger(__name__)

class ScoreGenerator:
    W = {"quality": 0.30, "value": 0.25, "reviews": 0.25, "features": 0.20}

    def generate(self, pd, lr, rr, pr):
        q = self._q(pd, lr); v = self._v(pd, pr)
        r = self._r(rr);     f = self._f(pd, lr)
        s = int(q*self.W["quality"] + v*self.W["value"] +
                r*self.W["reviews"]  + f*self.W["features"])
        return {"score": max(1, min(100, s)), "value_score": v}

    def _q(self, pd, lr):
        s = (50 + min(len(lr.get("pros", "")) * 8, 30)
               - min(len(lr.get("cons", "")) * 6, 25)
               + min(len(pd.get("specifications", {})) * 2, 15))
        return max(10, min(100, s))

    def _v(self, pd, pr):
        c, b = self._p(pd.get("price", "")), self._p(pr.get("best_price", ""))
        return 55 if c <= 0 or b <= 0 else max(20, min(100, int((b / c) * 80)))

    def _r(self, rr):
        a = float(rr.get("avg_rating", 0))
        if a == 0: return 50
        sb = rr.get("sentiment_breakdown", {})
        return max(10, min(100, int((a / 5) * 100) +
                               (sb.get("positive", 50) - sb.get("negative", 10)) // 10))

    def _f(self, pd, lr):
        s = (50 + min(len(pd.get("specifications", {})) * 3, 20)
               + min(len(pd.get("tags", "")) * 2, 10))
        if pd.get("category"): s += 10
        return max(20, min(100, s))

    @staticmethod
    def _p(s):
        if not s: return 0.0
        m = re.search(r"[\d]+\.?\d*", s.replace(",", ""))
        return float(m.group()) if m else 0.0
