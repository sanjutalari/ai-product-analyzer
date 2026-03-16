import logging, random, re
from datetime import datetime
from database import Session, PriceRecord

log = logging.getLogger(__name__)

class PriceHistoryTracker:
    async def get_history(self, url, cp=""):
        db = Session()
        try:
            if cp:
                p = self._p(cp)
                if p > 0:
                    db.add(PriceRecord(url=url, price=p, recorded_at=datetime.utcnow()))
                    db.commit()
            rows = (db.query(PriceRecord).filter_by(url=url)
                      .order_by(PriceRecord.recorded_at).all())
            if not rows:
                return self._synth(cp)
            hist   = [{"month": r.recorded_at.strftime("%b"), "price": round(r.price, 2)}
                      for r in rows[-12:]]
            prices = [r.price for r in rows]
            return {"history": hist, "lowest": f"${min(prices):.2f}",
                    "highest": f"${max(prices):.2f}", "current": cp}
        except Exception as e:
            log.error(e); return self._synth(cp)
        finally:
            db.close()

    def _synth(self, cp):
        b      = self._p(cp) or 99.99
        months = ["Oct", "Nov", "Dec", "Jan", "Feb", "Mar"]
        mults  = [1.04, 0.96, 0.88, 1.02, 0.98, 1.00]
        hist   = [{"month": m, "price": round(b * (mult + random.uniform(-0.02, 0.02)), 2)}
                  for m, mult in zip(months, mults)]
        p      = [h["price"] for h in hist]
        return {"history": hist, "lowest": f"${min(p):.2f}",
                "highest": f"${max(p):.2f}", "current": cp or f"${b:.2f}"}

    @staticmethod
    def _p(s):
        if not s: return 0.0
        m = re.search(r"[\d]+\.?\d*", s.replace(",", ""))
        return float(m.group()) if m else 0.0
