from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from checklist.db.base import Base
import os
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = (os.getenv("DATABASE_URL") or "").strip()

# Create engine with safer defaults for managed Postgres (e.g., Railway)
if DATABASE_URL.startswith("postgresql"):
    if "sslmode=" not in DATABASE_URL:
        # Enforce SSL when not explicitly set in URL
        DATABASE_URL += ("&" if "?" in DATABASE_URL else "?") + "sslmode=require"
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,   # validate connections before use
        pool_recycle=300,     # recycle connections periodically
    )
else:
    # Fallback to local SQLite if no DATABASE_URL provided
    engine = create_engine(DATABASE_URL or "sqlite:///./app.db")

SessionLocal = sessionmaker(bind=engine)
Session = SessionLocal


def init_db():
    # Prefer Alembic for production; create_all is fine for dev / first run
    Base.metadata.create_all(bind=engine)

