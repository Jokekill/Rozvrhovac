"""Plain dataclasses handed to the CP-SAT engine.

The engine never touches the ORM: everything it needs is precomputed here,
groups are already expanded into concrete ``student_id`` sets and every time
value is an absolute cycle minute.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class DayData:
    ordinal: int
    week_index: int
    weekday: int
    name: str
    start_minute: int
    end_minute: int

    @property
    def offset(self) -> int:
        return self.ordinal * 1440

    @property
    def abs_start(self) -> int:
        return self.offset + self.start_minute

    @property
    def abs_end(self) -> int:
        return self.offset + self.end_minute


@dataclass(slots=True)
class RoomData:
    id: int
    name: str
    code: str | None
    capacity: int
    building: str | None
    feature_ids: set[int] = field(default_factory=set)
    blocked: list[tuple[int, int]] = field(default_factory=list)


@dataclass(slots=True)
class PersonData:
    id: int
    name: str
    unavailable: list[tuple[int, int]] = field(default_factory=list)
    preferred: list[tuple[int, int]] = field(default_factory=list)
    max_minutes_per_day: int | None = None
    max_consecutive_minutes: int | None = None


@dataclass(slots=True)
class ActivityData:
    id: int
    name: str
    kind: str
    subject_id: int | None
    duration: int
    occurrences: int
    priority: int
    teacher_ids: list[int] = field(default_factory=list)
    student_ids: list[int] = field(default_factory=list)
    required_feature_ids: set[int] = field(default_factory=set)
    allowed_room_ids: set[int] = field(default_factory=set)
    preferred_room_ids: set[int] = field(default_factory=set)
    forbidden_room_ids: set[int] = field(default_factory=set)
    min_capacity: int | None = None
    fixed_start_minute: int | None = None
    fixed_room_id: int | None = None
    align_to_periods: bool = True
    start_step_minutes: int | None = None
    # computed
    compatible_room_ids: list[int] = field(default_factory=list)
    candidate_starts: list[int] = field(default_factory=list)
    # the reason a room was rejected, for diagnostics
    room_rejections: dict[int, str] = field(default_factory=dict)


@dataclass(slots=True)
class LinkData:
    kind: str
    activity_a_id: int
    activity_b_id: int


@dataclass(slots=True)
class Assignment:
    """One placed occurrence."""

    activity_id: int
    occurrence_index: int
    start_minute: int
    room_id: int | None

    @property
    def day_ordinal(self) -> int:
        return self.start_minute // 1440


@dataclass(slots=True)
class SolverConfig:
    granularity_minutes: int = 5
    lunch_start_minute: int = 11 * 60 + 30
    lunch_end_minute: int = 13 * 60 + 30
    lunch_break_minutes: int = 30
    early_threshold_minute: int = 8 * 60
    late_threshold_minute: int = 16 * 60
    max_student_minutes_per_day: int = 360
    individual_preferred_start: int = 13 * 60
    individual_preferred_end: int = 19 * 60
    core_day_start_minute: int = 8 * 60
    core_block_periods: int = 4
    min_student_lessons_per_day: int = 4


@dataclass(slots=True)
class PeriodData:
    """One slot of the classic lesson grid, in minutes from midnight."""

    index: int
    name: str
    start_minute: int
    end_minute: int


@dataclass(slots=True)
class SolverInput:
    days: list[DayData]
    period_starts: list[int]
    activities: list[ActivityData]
    rooms: dict[int, RoomData]
    teachers: dict[int, PersonData]
    students: dict[int, PersonData]
    periods: list[PeriodData] = field(default_factory=list)
    links: list[LinkData] = field(default_factory=list)
    config: SolverConfig = field(default_factory=SolverConfig)
    weights: dict[str, int] = field(default_factory=dict)
    # Re-optimisation input
    base_assignments: dict[tuple[int, int], Assignment] = field(default_factory=dict)
    # Warm start produced by the hard-constraints-only pass.
    hints: dict[tuple[int, int], Assignment] = field(default_factory=dict)
    locked_time: set[tuple[int, int]] = field(default_factory=set)
    locked_room: set[tuple[int, int]] = field(default_factory=set)

    def weight(self, code: str) -> int:
        return int(self.weights.get(code, 0))

    def core_periods(self) -> list[PeriodData]:
        """The first ``core_block_periods`` slots of the regular grid.

        Anything starting before ``core_day_start_minute`` is the zeroth hour
        and is deliberately *not* part of the compulsory block.
        """
        regular = sorted(
            (p for p in self.periods if p.start_minute >= self.config.core_day_start_minute),
            key=lambda p: p.start_minute,
        )
        return regular[: max(0, self.config.core_block_periods)]

    def activity_by_id(self, activity_id: int) -> ActivityData | None:
        for activity in self.activities:
            if activity.id == activity_id:
                return activity
        return None


@dataclass(slots=True)
class SolveResult:
    status: str
    assignments: list[Assignment] = field(default_factory=list)
    total_penalty: int | None = None
    penalties: dict[str, int] = field(default_factory=dict)
    log: str = ""
    diagnostics: list[dict] = field(default_factory=list)
    wall_time: float = 0.0
