from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from checklist.models import Base
import os
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)


def init_db():
    Base.metadata.create_all(bind=engine)
SessionLocal = Session  # для обратной совместимости
