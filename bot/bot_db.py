from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from checklist.models import Company, Checklist, User, Base

# ✅ Строка подключения к Postgres (замени user, password и db_name по своим данным)
DATABASE_URL = "postgresql+psycopg2://postgres:postgres@localhost:5432/checklist_db"

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(bind=engine)

# ✅ Инициализация таблиц (если нужно)
def init_db():
    Base.metadata.create_all(bind=engine)
