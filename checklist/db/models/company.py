from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from checklist.db.base import Base 

class Company(Base):
    __tablename__ = "companies"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)

class Department(Base):
    __tablename__ = "departments"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)

    company = relationship("Company", backref="departments")
    # users — связь через user_department_access (см. user.py)
    users = relationship("User", secondary="user_department_access", back_populates="departments")
