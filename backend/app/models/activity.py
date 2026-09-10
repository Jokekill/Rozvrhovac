"""Activity – the single central scheduling entity.

A regular lesson, a split group, a choir rehearsal and a one-to-one piano
lesson are all the same entity; only the values differ.
"""
from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.core import Room, RoomFeature, Student, StudentGroup, Subject, Teacher
from app.models.enums import ActivityKind, LinkKind, RoomPolicyKind, TimeWindowKind


class Activity(Base):
    __tablename__ = "activity"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    subject_id: Mapped[int | None] = mapped_column(
        ForeignKey("subject.id", ondelete="SET NULL"), index=True
    )
    kind: Mapped[str] = mapped_column(String(32), default=ActivityKind.STANDARD)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=45)
    occurrences_per_cycle: Mapped[int] = mapped_column(Integer, default=1)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    notes: Mapped[str | None] = mapped_column(Text)

    # HC09 – fixed lesson. Applies to occurrence 0. Either or both may be set.
    fixed_start_minute: Mapped[int | None] = mapped_column(Integer)
    fixed_room_id: Mapped[int | None] = mapped_column(
        ForeignKey("room.id", ondelete="SET NULL")
    )

    # Start granularity: aligned to the classic period grid, or free steps.
    align_to_periods: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    start_step_minutes: Mapped[int | None] = mapped_column(Integer)
    min_capacity: Mapped[int | None] = mapped_column(Integer)

    subject: Mapped[Subject | None] = relationship()
    fixed_room: Mapped[Room | None] = relationship(foreign_keys=[fixed_room_id])
    teachers: Mapped[list["ActivityTeacher"]] = relationship(
        back_populates="activity", cascade="all, delete-orphan"
    )
    students: Mapped[list["ActivityStudent"]] = relationship(
        back_populates="activity", cascade="all, delete-orphan"
    )
    groups: Mapped[list["ActivityStudentGroup"]] = relationship(
        back_populates="activity", cascade="all, delete-orphan"
    )
    room_requirements: Mapped[list["ActivityRoomRequirement"]] = relationship(
        back_populates="activity", cascade="all, delete-orphan"
    )
    room_policies: Mapped[list["ActivityRoomPolicy"]] = relationship(
        back_populates="activity", cascade="all, delete-orphan"
    )
    time_windows: Mapped[list["ActivityTimeWindow"]] = relationship(
        back_populates="activity", cascade="all, delete-orphan"
    )


class ActivityTeacher(Base):
    __tablename__ = "activity_teacher"
    __table_args__ = (UniqueConstraint("activity_id", "teacher_id", name="uq_activity_teacher"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activity.id", ondelete="CASCADE"), index=True
    )
    teacher_id: Mapped[int] = mapped_column(
        ForeignKey("teacher.id", ondelete="CASCADE"), index=True
    )

    activity: Mapped[Activity] = relationship(back_populates="teachers")
    teacher: Mapped[Teacher] = relationship()


class ActivityStudent(Base):
    """Participant attached directly, without going through a group."""

    __tablename__ = "activity_student"
    __table_args__ = (UniqueConstraint("activity_id", "student_id", name="uq_activity_student"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activity.id", ondelete="CASCADE"), index=True
    )
    student_id: Mapped[int] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), index=True
    )

    activity: Mapped[Activity] = relationship(back_populates="students")
    student: Mapped[Student] = relationship()


class ActivityStudentGroup(Base):
    """Participants attached through a group; expanded before solving."""

    __tablename__ = "activity_student_group"
    __table_args__ = (UniqueConstraint("activity_id", "group_id", name="uq_activity_group"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activity.id", ondelete="CASCADE"), index=True
    )
    group_id: Mapped[int] = mapped_column(
        ForeignKey("student_group.id", ondelete="CASCADE"), index=True
    )

    activity: Mapped[Activity] = relationship(back_populates="groups")
    group: Mapped[StudentGroup] = relationship()


class ActivityRoomRequirement(Base):
    """Mandatory room feature (HC08)."""

    __tablename__ = "activity_room_requirement"
    __table_args__ = (
        UniqueConstraint("activity_id", "feature_id", name="uq_activity_requirement"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activity.id", ondelete="CASCADE"), index=True
    )
    feature_id: Mapped[int] = mapped_column(
        ForeignKey("room_feature.id", ondelete="CASCADE"), index=True
    )

    activity: Mapped[Activity] = relationship(back_populates="room_requirements")
    feature: Mapped[RoomFeature] = relationship()


class ActivityRoomPolicy(Base):
    """allowed_rooms / preferred_rooms / forbidden_rooms in one table."""

    __tablename__ = "activity_room_policy"
    __table_args__ = (
        UniqueConstraint("activity_id", "room_id", "kind", name="uq_activity_room_policy"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activity.id", ondelete="CASCADE"), index=True
    )
    room_id: Mapped[int] = mapped_column(ForeignKey("room.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16), default=RoomPolicyKind.ALLOWED)

    activity: Mapped[Activity] = relationship(back_populates="room_policies")
    room: Mapped[Room] = relationship()


class ActivityTimeWindow(Base):
    """Per-activity time restriction, e.g. "only Mon/Tue afternoons".

    ``day_ordinal = NULL`` means the window repeats on every day.
    """

    __tablename__ = "activity_time_window"

    id: Mapped[int] = mapped_column(primary_key=True)
    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activity.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(16), default=TimeWindowKind.ALLOWED)
    day_ordinal: Mapped[int | None] = mapped_column(Integer)
    start_minute: Mapped[int | None] = mapped_column(Integer)
    end_minute: Mapped[int | None] = mapped_column(Integer)

    activity: Mapped[Activity] = relationship(back_populates="time_windows")


class ActivityLink(Base):
    """HC12/HC13/HC14 – relation between two activities."""

    __tablename__ = "activity_link"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(24), default=LinkKind.SAME_START)
    activity_a_id: Mapped[int] = mapped_column(
        ForeignKey("activity.id", ondelete="CASCADE"), index=True
    )
    activity_b_id: Mapped[int] = mapped_column(
        ForeignKey("activity.id", ondelete="CASCADE"), index=True
    )
    note: Mapped[str | None] = mapped_column(Text)

    activity_a: Mapped[Activity] = relationship(foreign_keys=[activity_a_id])
    activity_b: Mapped[Activity] = relationship(foreign_keys=[activity_b_id])
