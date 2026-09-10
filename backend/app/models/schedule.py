"""Schedules, versions, scheduled occurrences and solver runs."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db import Base
from app.models.activity import Activity
from app.models.core import Room
from app.models.enums import SolverStatus, VersionStatus


class Schedule(Base):
    __tablename__ = "schedule"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    versions: Mapped[list["ScheduleVersion"]] = relationship(
        back_populates="schedule", cascade="all, delete-orphan", order_by="ScheduleVersion.id"
    )


class ScheduleVersion(Base):
    """Immutable-by-convention snapshot. Never overwrite destructively."""

    __tablename__ = "schedule_version"

    id: Mapped[int] = mapped_column(primary_key=True)
    schedule_id: Mapped[int] = mapped_column(
        ForeignKey("schedule.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(150))
    status: Mapped[str] = mapped_column(String(16), default=VersionStatus.DRAFT)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    parent_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("schedule_version.id", ondelete="SET NULL")
    )
    solver_run_id: Mapped[int | None] = mapped_column(Integer)
    total_penalty: Mapped[int | None] = mapped_column(Integer)
    penalties: Mapped[dict | None] = mapped_column(JSON)
    note: Mapped[str | None] = mapped_column(Text)

    schedule: Mapped[Schedule] = relationship(back_populates="versions")
    items: Mapped[list["ScheduledActivity"]] = relationship(
        back_populates="version", cascade="all, delete-orphan"
    )


class ScheduledActivity(Base):
    """One occurrence of an activity placed in time and space."""

    __tablename__ = "scheduled_activity"

    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(
        ForeignKey("schedule_version.id", ondelete="CASCADE"), index=True
    )
    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activity.id", ondelete="CASCADE"), index=True
    )
    occurrence_index: Mapped[int] = mapped_column(Integer, default=0)
    start_minute: Mapped[int] = mapped_column(Integer, index=True)  # absolute cycle minute
    duration_minutes: Mapped[int] = mapped_column(Integer)
    day_ordinal: Mapped[int] = mapped_column(Integer, index=True)
    room_id: Mapped[int | None] = mapped_column(ForeignKey("room.id", ondelete="SET NULL"))
    lock_time: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    lock_room: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")

    version: Mapped[ScheduleVersion] = relationship(back_populates="items")
    activity: Mapped[Activity] = relationship()
    room: Mapped[Room | None] = relationship()

    @property
    def end_minute(self) -> int:
        return self.start_minute + self.duration_minutes


class SolverRun(Base):
    __tablename__ = "solver_run"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(16), default=SolverStatus.QUEUED, index=True)
    time_limit_seconds: Mapped[int] = mapped_column(Integer, default=60)
    best_score: Mapped[int | None] = mapped_column(Integer)
    schedule_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("schedule_version.id", ondelete="SET NULL")
    )
    schedule_id: Mapped[int | None] = mapped_column(
        ForeignKey("schedule.id", ondelete="SET NULL")
    )
    base_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("schedule_version.id", ondelete="SET NULL")
    )
    params: Mapped[dict | None] = mapped_column(JSON)
    penalties: Mapped[dict | None] = mapped_column(JSON)
    diagnostics: Mapped[list | None] = mapped_column(JSON)
    log: Mapped[str | None] = mapped_column(Text)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
