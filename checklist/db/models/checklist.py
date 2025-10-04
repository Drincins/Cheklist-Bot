from datetime import datetime

from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, DateTime, JSON, Index, UniqueConstraint
from sqlalchemy.orm import relationship

from checklist.db.base import Base
from checklist.db.models.role import position_checklist_access


class Checklist(Base):
    __tablename__ = "checklists"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    is_scored = Column(Boolean, default=False)
    created_by = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    positions = relationship(
        "Position",
        secondary=position_checklist_access,
        back_populates="checklists",
    )
    sections = relationship(
        "ChecklistSection",
        back_populates="checklist",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class ChecklistSection(Base):
    __tablename__ = "checklist_sections"

    id = Column(Integer, primary_key=True)
    checklist_id = Column(Integer, ForeignKey("checklists.id", ondelete="CASCADE"), nullable=False)
    name = Column("title", String, nullable=False)
    order = Column(Integer, nullable=True)

    checklist = relationship("Checklist", back_populates="sections")
    questions = relationship(
        "ChecklistQuestion",
        back_populates="section",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class ChecklistQuestion(Base):
    __tablename__ = "checklist_questions"

    id = Column(Integer, primary_key=True)
    checklist_id = Column(Integer, ForeignKey("checklists.id", ondelete="CASCADE"), nullable=False)
    order = Column(Integer, nullable=False)
    text = Column(String, nullable=False)
    type = Column(String, nullable=False)
    required = Column(Boolean, default=True)
    meta = Column(JSON, nullable=True)
    weight = Column(Integer, nullable=True)
    require_photo = Column(Boolean, default=False, nullable=False)
    require_comment = Column(Boolean, default=False, nullable=False)
    section_id = Column(Integer, ForeignKey("checklist_sections.id", ondelete="SET NULL"), nullable=True)

    section = relationship("ChecklistSection", back_populates="questions")


class ChecklistAnswer(Base):
    __tablename__ = "checklist_answers"

    id = Column(Integer, primary_key=True)
    checklist_id = Column(Integer, ForeignKey("checklists.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    submitted_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_ca_ck_user_date", "checklist_id", "user_id", "submitted_at"),
    )


class ChecklistQuestionAnswer(Base):
    __tablename__ = "checklist_question_answers"

    id = Column(Integer, primary_key=True)
    answer_id = Column(Integer, ForeignKey("checklist_answers.id", ondelete="CASCADE"), nullable=False)
    question_id = Column(Integer, ForeignKey("checklist_questions.id", ondelete="CASCADE"), nullable=False)
    response_value = Column(String, nullable=True)
    comment = Column(String, nullable=True)
    photo_path = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_cqa_answer_id", "answer_id"),
        Index("ix_cqa_question_id", "question_id"),
        Index("ix_cqa_answer_question", "answer_id", "question_id"),
    )


class ChecklistDraft(Base):
    __tablename__ = "checklist_drafts"

    id = Column(Integer, primary_key=True)
    checklist_id = Column(Integer, ForeignKey("checklists.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    department = Column(String, nullable=True)

    checklist = relationship("Checklist")
    answers = relationship(
        "ChecklistDraftAnswer",
        back_populates="draft",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_cd_user", "user_id"),
        UniqueConstraint("user_id", "checklist_id", name="uq_cd_user_checklist"),
    )


class ChecklistDraftAnswer(Base):
    __tablename__ = "checklist_draft_answers"

    id = Column(Integer, primary_key=True)
    draft_id = Column(Integer, ForeignKey("checklist_drafts.id", ondelete="CASCADE"), nullable=False)
    question_id = Column(Integer, ForeignKey("checklist_questions.id", ondelete="CASCADE"), nullable=False)
    response_value = Column(String, nullable=True)
    comment = Column(String, nullable=True)
    photo_path = Column(String, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    draft = relationship("ChecklistDraft", back_populates="answers")
    question = relationship("ChecklistQuestion")

    __table_args__ = (
        Index("ix_cda_draft_id", "draft_id"),
        Index("ix_cda_question_id", "question_id"),
        UniqueConstraint("draft_id", "question_id", name="uq_cda_draft_question"),
    )
