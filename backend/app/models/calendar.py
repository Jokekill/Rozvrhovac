"""Time model: cycle configuration, days, periods, availability windows.

Absolute time is expressed in *cycle minutes*::

    cycle_minute = day.ordinal * MINUTES_PER_DAY + minutes_from_midnight

Offsetting each day by a full day makes it impossible for an interval to
silently spill over into the next day, so day boundaries (HC10) reduce to a
domain restriction on ``start``.
"""
from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import AvailabilityKind, OwnerType

MINUTES_PER_DAY = 1440


class CycleConfig(Base):
    """Singleton (id == 1) describing the planning cycle."""

    __tablename__ = "cycle_config"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    name: Mapped[str] = mapped_column(String(100), default="Default cycle")
    weeks_in_cycle: Mapped[int] = mapped_column(Integer, default=1)
    granularity_minutes: Mapped[int] = mapped_column(Integer, default=5)

    # Soft-constraint tuning that is not per-entity.
    lunch_start_minute: Mapped[int] = mapped_column(Integer, default=11 * 60 + 30)
    lunch_end_minute: Mapped[int] = mapped_column(Integer, default=13 * 60 + 30)
    lunch_break_minutes: Mapped[int] = mapped_column(Integer, default=30)
    early_threshold_minute: Mapped[int] = mapped_column(Integer, default=8 * 60)
    late_threshold_minute: Mapped[int] = mapped_column(Integer, default=16 * 60)
    max_student_minutes_per_day: Mapped[int] = mapped_column(Integer, default=8 * 45)
    individual_preferred_start: Mapped[int] = mapped_column(Integer, default=13 * 60)
    individual_preferred_end: Mapped[int] = mapped_column(Integer, default=19 * 60)


class Day(Base):
    """One day of the planning cycle.

    ``ordinal`` is the position in the cycle (0..n-1) and drives absolute time.
    ``week_index`` allows a two week cycle (Week A = 0, Week B = 1).
    """

    __tablename__ = "day"
    __table_args__ = (UniqueConstraint("ordinal", name="uq_day_ordinal"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    ordinal: Mapped[int] = mapped_column(Integer, index=True)
    week_index: Mapped[int] = mapped_column(Integer, default=0)
    weekday: Mapped[int] = mapped_column(Integer)  # 0 = Monday
    name: Mapped[str] = mapped_column(String(64))
    start_minute: Mapped[int] = mapped_column(Integer, default=8 * 60)
    end_minute: Mapped[int] = mapped_column(Integer, default=17 * 60)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")

    @property
    def offset(self) -> int:
        return self.ordinal * MINUTES_PER_DAY

    @property
    def abs_start(self) -> int:
        return self.offset + self.start_minute

    @property
    def abs_end(self) -> int:
        return self.offset + self.end_minute


class Period(Base):
    """Optional classic lesson grid (08:00-08:45, ...).

    Activities with ``align_to_periods`` may only start at a period start.
    """

    __tablename__ = "period"

    id: Mapped[int] = mapped_column(primary_key=True)
    index: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(64))
    start_minute: Mapped[int] = mapped_column(Integer)
    end_minute: Mapped[int] = mapped_column(Integer)


class AvailabilityWindow(Base):
    """Availability / preference of a teacher, student or room.

    Default state is *available*; a restriction is entered as an
    ``UNAVAILABLE`` window. ``PREFERRED`` windows feed SC03/SC04.
    A window with ``day_ordinal = NULL`` applies to every day of the cycle.
    """

    __tablename__ = "availability_window"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_type: Mapped[str] = mapped_column(String(16), index=True)
    owner_id: Mapped[int] = mapped_column(Integer, index=True)
    kind: Mapped[str] = mapped_column(String(16), default=AvailabilityKind.UNAVAILABLE)
    day_ordinal: Mapped[int | None] = mapped_column(Integer, index=True)
    start_minute: Mapped[int] = mapped_column(Integer)  # minutes from midnight
    end_minute: Mapped[int] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(Text)

    def matches(self, owner_type: OwnerType, owner_id: int) -> bool:
        return self.owner_type == owner_type and self.owner_id == owner_id
