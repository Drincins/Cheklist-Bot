from sqlalchemy import Column, Integer, String, ForeignKey, Table, text
from sqlalchemy.orm import relationship
from checklist.db.base import Base 

position_checklist_access = Table(
    "position_checklist_access", Base.metadata,
    Column("position_id", Integer, ForeignKey("positions.id", ondelete="CASCADE"), primary_key=True),
    Column("checklist_id", Integer, ForeignKey("checklists.id", ondelete="CASCADE"), primary_key=True)
)

class Role(Base):
    __tablename__ = "roles"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    description = Column(String, nullable=True)
    level = Column(Integer, nullable=False, server_default=text("1"))  
    # связь с должностями
    positions = relationship("Position", back_populates="role")

class Position(Base):
    __tablename__ = "positions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False)
    # связь с ролью
    role = relationship("Role", back_populates="positions")
    # связь с чек-листами
    checklists = relationship(
        "Checklist",
        secondary=position_checklist_access,
        back_populates="positions"
    )
    # users — связь в user.py через back_populates
