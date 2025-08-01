from sqlalchemy import Column, Integer, String, ForeignKey, Enum, Table
from sqlalchemy.orm import relationship
from checklist.db.base import Base 

user_department_access = Table(
    "user_department_access", Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("department_id", Integer, ForeignKey("departments.id", ondelete="CASCADE"), primary_key=True)
)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    telegram_id = Column(Integer, unique=True, nullable=True)
    phone = Column(String, nullable=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    position_id = Column(Integer, ForeignKey("positions.id"), nullable=True)
    login = Column(String, unique=True, nullable=True)
    hashed_password = Column(String, nullable=True)
    position = relationship("Position", backref="users")
    departments = relationship("Department", secondary=user_department_access, back_populates="users")
