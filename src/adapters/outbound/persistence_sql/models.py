"""SQLAlchemy declarative models — persistence-представление сущностей."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid


class Base(DeclarativeBase):
    pass


class ProjectModel(Base):
    __tablename__ = 'projects'

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    path: Mapped[str] = mapped_column(String(1024))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    phases: Mapped[list['PhaseModel']] = relationship(
        cascade='all, delete-orphan',
        lazy='selectin',
    )


class PhaseModel(Base):
    __tablename__ = 'phases'

    project_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey('projects.id', ondelete='CASCADE'),
        primary_key=True,
    )
    name: Mapped[str] = mapped_column(String(32), primary_key=True)
    status: Mapped[str] = mapped_column(String(32))
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
