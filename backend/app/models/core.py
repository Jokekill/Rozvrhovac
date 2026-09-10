"""People, rooms and groups."""
from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import GroupType


class Student(Base):
    """A real person and the lowest level scheduling resource.

    GDPR: only what scheduling needs. No birth date, address or phone.
    """

    __tablename__ = "student"

    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    external_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    class_group_id: Mapped[int | None] = mapped_column(
        ForeignKey("student_group.id", ondelete="SET NULL"), index=True
    )
    notes: Mapped[str | None] = mapped_column(Text)

    class_group: Mapped["StudentGroup | None"] = relationship(
        foreign_keys=[class_group_id], back_populates="class_students"
    )
    memberships: Mapped[list["StudentGroupMember"]] = relationship(
        back_populates="student", cascade="all, delete-orphan"
    )

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


class Teacher(Base):
    __tablename__ = "teacher"

    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    external_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    max_minutes_per_day: Mapped[int | None] = mapped_column(Integer)
    max_consecutive_minutes: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


class StudentGroup(Base):
    """One universal entity for classes, subgroups, ensembles, seminars…

    Nothing in the solver distinguishes them; only ``type`` does, for the UI.
    """

    __tablename__ = "student_group"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    code: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    type: Mapped[str] = mapped_column(String(32), default=GroupType.OTHER)

    members: Mapped[list["StudentGroupMember"]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )
    class_students: Mapped[list[Student]] = relationship(
        foreign_keys=[Student.class_group_id], back_populates="class_group"
    )


class StudentGroupMember(Base):
    __tablename__ = "student_group_member"
    __table_args__ = (UniqueConstraint("group_id", "student_id", name="uq_group_student"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(
        ForeignKey("student_group.id", ondelete="CASCADE"), index=True
    )
    student_id: Mapped[int] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), index=True
    )

    group: Mapped[StudentGroup] = relationship(back_populates="members")
    student: Mapped[Student] = relationship(back_populates="memberships")


class RoomFeature(Base):
    __tablename__ = "room_feature"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text)


class Room(Base):
    __tablename__ = "room"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    code: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    building: Mapped[str | None] = mapped_column(String(64), index=True)
    floor: Mapped[str | None] = mapped_column(String(32))
    capacity: Mapped[int] = mapped_column(Integer, default=30)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")

    feature_assignments: Mapped[list["RoomFeatureAssignment"]] = relationship(
        back_populates="room", cascade="all, delete-orphan"
    )

    @property
    def feature_ids(self) -> set[int]:
        return {fa.feature_id for fa in self.feature_assignments}


class RoomFeatureAssignment(Base):
    __tablename__ = "room_feature_assignment"
    __table_args__ = (UniqueConstraint("room_id", "feature_id", name="uq_room_feature"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("room.id", ondelete="CASCADE"), index=True)
    feature_id: Mapped[int] = mapped_column(
        ForeignKey("room_feature.id", ondelete="CASCADE"), index=True
    )

    room: Mapped[Room] = relationship(back_populates="feature_assignments")
    feature: Mapped[RoomFeature] = relationship()


class Subject(Base):
    __tablename__ = "subject"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    code: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    color: Mapped[str | None] = mapped_column(String(16))
