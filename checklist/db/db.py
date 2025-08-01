from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from checklist.db.base import Base  # <--- изменено!
import os
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Session = SessionLocal

def init_db():
    Base.metadata.create_all(bind=engine)
