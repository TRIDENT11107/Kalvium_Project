import enum
from datetime import datetime, timezone
from sqlalchemy import String, Text, DateTime, ForeignKey, Integer, Float, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON
from app.database import Base

def now(): return datetime.now(timezone.utc)
class User(Base):
    __tablename__="users"
    id: Mapped[int]=mapped_column(primary_key=True)
    email: Mapped[str]=mapped_column(String(320),unique=True,index=True)
    password_hash: Mapped[str]=mapped_column(String(255))
    password_reset_jti: Mapped[str|None]=mapped_column(String(36),nullable=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    lessons: Mapped[list["Lesson"]]=relationship(back_populates="owner",cascade="all, delete-orphan")
class Lesson(Base):
    __tablename__="lessons"
    __table_args__=(Index("ix_lessons_owner_updated","owner_id","updated_at"),)
    id: Mapped[int]=mapped_column(primary_key=True)
    owner_id: Mapped[int]=mapped_column(ForeignKey("users.id",ondelete="CASCADE"),index=True)
    title: Mapped[str]=mapped_column(String(180))
    objective: Mapped[str]=mapped_column(Text)
    audience: Mapped[str]=mapped_column(String(200),default="")
    difficulty: Mapped[str]=mapped_column(String(40),default="Beginner")
    status: Mapped[str]=mapped_column(String(30),default="draft")
    research_status: Mapped[str]=mapped_column(String(24),default="not_started")
    generation_status: Mapped[str]=mapped_column(String(24),default="not_started")
    factual_qc_status: Mapped[str]=mapped_column(String(24),default="not_started")
    instructional_qc_status: Mapped[str]=mapped_column(String(24),default="not_started")
    lesson: Mapped[dict]=mapped_column(JSON,default=dict)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now,onupdate=now)
    owner: Mapped[User]=relationship(back_populates="lessons")
    sources: Mapped[list["ResearchSource"]]=relationship(cascade="all, delete-orphan")
    reports: Mapped[list["QCReport"]]=relationship(cascade="all, delete-orphan")
    sections: Mapped[list["LessonSection"]]=relationship(cascade="all, delete-orphan")
    revisions: Mapped[list["LessonRevision"]]=relationship(cascade="all, delete-orphan")
class ResearchSource(Base):
    __tablename__="research_sources"
    id: Mapped[int]=mapped_column(primary_key=True)
    lesson_id: Mapped[int]=mapped_column(ForeignKey("lessons.id",ondelete="CASCADE"),index=True)
    kind: Mapped[str]=mapped_column(String(30))
    title: Mapped[str]=mapped_column(Text)
    url: Mapped[str]=mapped_column(Text)
    description: Mapped[str]=mapped_column(Text,default="")
    metadata_json: Mapped[dict]=mapped_column(JSON,default=dict)
class QCReport(Base):
    __tablename__="qc_reports"
    __table_args__=(UniqueConstraint("lesson_id","kind","execution_id",name="uq_qc_report_execution"),)
    id: Mapped[int]=mapped_column(primary_key=True)
    lesson_id: Mapped[int]=mapped_column(ForeignKey("lessons.id",ondelete="CASCADE"),index=True)
    kind: Mapped[str]=mapped_column(String(30),index=True)
    execution_id: Mapped[str|None]=mapped_column(String(36),nullable=True,index=True)
    score: Mapped[float]=mapped_column(Float,default=0)
    report: Mapped[dict]=mapped_column(JSON,default=dict)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
class LessonRevision(Base):
    __tablename__="lesson_revisions"
    id: Mapped[int]=mapped_column(primary_key=True)
    lesson_id: Mapped[int]=mapped_column(ForeignKey("lessons.id",ondelete="CASCADE"),index=True)
    lesson: Mapped[dict]=mapped_column(JSON)
    title: Mapped[str]=mapped_column(String(180),default="")
    objective: Mapped[str]=mapped_column(Text,default="")
    audience: Mapped[str]=mapped_column(String(200),default="")
    difficulty: Mapped[str]=mapped_column(String(40),default="Beginner")
    status: Mapped[str]=mapped_column(String(30),default="draft")
    note: Mapped[str]=mapped_column(String(300),default="Instructor edit")
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
class BackgroundTask(Base):
    __tablename__="background_tasks"
    id: Mapped[str]=mapped_column(String(36),primary_key=True)
    owner_id: Mapped[int]=mapped_column(ForeignKey("users.id",ondelete="CASCADE"),index=True)
    lesson_id: Mapped[int]=mapped_column(ForeignKey("lessons.id",ondelete="CASCADE"),index=True)
    kind: Mapped[str]=mapped_column(String(40))
    status: Mapped[str]=mapped_column(String(24),default="queued")
    progress: Mapped[int]=mapped_column(Integer,default=0)
    message: Mapped[str]=mapped_column(Text,default="Queued")
    error: Mapped[str|None]=mapped_column(Text,nullable=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)

class Recommendation(Base):
    __tablename__="recommendations"
    id: Mapped[int]=mapped_column(primary_key=True)
    lesson_id: Mapped[int]=mapped_column(ForeignKey("lessons.id",ondelete="CASCADE"),index=True)
    issue_key: Mapped[str]=mapped_column(String(180),index=True)
    status: Mapped[str]=mapped_column(String(20),default="open")
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)

class LessonSection(Base):
    __tablename__="lesson_sections"
    __table_args__=(UniqueConstraint("lesson_id","section_key",name="uq_lesson_section_key"),)
    id: Mapped[int]=mapped_column(primary_key=True)
    lesson_id: Mapped[int]=mapped_column(ForeignKey("lessons.id",ondelete="CASCADE"),index=True)
    section_key: Mapped[str]=mapped_column(String(100))
    title: Mapped[str]=mapped_column(String(160))
    content: Mapped[object]=mapped_column(JSON)
    order_index: Mapped[int]=mapped_column(Integer,default=0)

class QCIssue(Base):
    __tablename__="qc_issues"
    id: Mapped[int]=mapped_column(primary_key=True)
    report_id: Mapped[int]=mapped_column(ForeignKey("qc_reports.id",ondelete="CASCADE"),index=True)
    issue_key: Mapped[str]=mapped_column(String(180),index=True)
    section: Mapped[str]=mapped_column(String(160),default="")
    severity: Mapped[str]=mapped_column(String(20),default="Medium")
    issue_data: Mapped[dict]=mapped_column(JSON,default=dict)
    status: Mapped[str]=mapped_column(String(20),default="open")
