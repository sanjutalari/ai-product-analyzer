import json, logging, os
from datetime import datetime
from sqlalchemy import Column, DateTime, Float, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

log = logging.getLogger(__name__)
DB_URL = os.getenv("DATABASE_URL", "sqlite:///./product_analyzer.db")
engine = create_engine(DB_URL, connect_args={"check_same_thread": False})
Session = sessionmaker(bind=engine)

class Base(DeclarativeBase): pass

class ProductAnalysis(Base):
    __tablename__ = "product_analyses"
    id           = Column(Integer, primary_key=True)
    url          = Column(String(2048), unique=True, index=True)
    product_name = Column(String(512))
    score        = Column(Integer)
    data_json    = Column(Text)
    created_at   = Column(DateTime, default=datetime.utcnow)
    updated_at   = Column(DateTime, default=datetime.utcnow)

class PriceRecord(Base):
    __tablename__ = "price_records"
    id          = Column(Integer, primary_key=True)
    url         = Column(String(2048), index=True)
    price       = Column(Float)
    recorded_at = Column(DateTime, default=datetime.utcnow)

def init_db():
    Base.metadata.create_all(bind=engine)

def save_product_analysis(url, data):
    db = Session()
    try:
        ex = db.query(ProductAnalysis).filter_by(url=url).first()
        if ex:
            ex.data_json = json.dumps(data)
            ex.score = data.get("score", 0)
            ex.product_name = data.get("productName", "")
            ex.updated_at = datetime.utcnow()
        else:
            db.add(ProductAnalysis(
                url=url,
                product_name=data.get("productName", ""),
                score=data.get("score", 0),
                data_json=json.dumps(data)
            ))
        db.commit()
    except Exception as e:
        log.error(e); db.rollback()
    finally:
        db.close()

def get_product_analysis(url):
    db = Session()
    try:
        r = db.query(ProductAnalysis).filter_by(url=url).first()
        return json.loads(r.data_json) if r and r.data_json else None
    except:
        return None
    finally:
        db.close()

def get_recent_analyses(limit=10):
    db = Session()
    try:
        rows = db.query(ProductAnalysis).order_by(
            ProductAnalysis.updated_at.desc()
        ).limit(limit).all()
        return [{"url": r.url, "productName": r.product_name, "score": r.score} for r in rows]
    except:
        return []
    finally:
        db.close()
