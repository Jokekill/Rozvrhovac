"""Schemas for activities and their relations."""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.enums import ActivityKind, LinkKind, TimeWindowKind
from app.schemas.core import ORMModel


class ActivityTimeWindowIn(BaseModel):
    kind: TimeWindowKind = TimeWindowKind.ALLOWED
    day_ordinal: int | None = None
    start_minute: int | None = None
    end_minute: int | None = None


class ActivityTimeWindowOut(ORMModel, ActivityTimeWindowIn):
    id: int


class ActivityBase(BaseModel):
    name: str
    subject_id: int | None = None
    kind: ActivityKind = ActivityKind.STANDARD
    duration_minutes: int = 45
    occurrences_per_cycle: int = 1
    priority: int = 0
    active: bool = True
    notes: str | None = None
    fixed_start_minute: int | None = None
    fixed_room_id: int | None = None
    align_to_periods: bool = True
    start_step_minutes: int | None = None
    min_capacity: int | None = None


class ActivityCreate(ActivityBase):
    teacher_ids: list[int] = Field(default_factory=list)
    student_ids: list[int] = Field(default_factory=list)
    group_ids: list[int] = Field(default_factory=list)
    required_feature_ids: list[int] = Field(default_factory=list)
    allowed_room_ids: list[int] = Field(default_factory=list)
    preferred_room_ids: list[int] = Field(default_factory=list)
    forbidden_room_ids: list[int] = Field(default_factory=list)
    time_windows: list[ActivityTimeWindowIn] = Field(default_factory=list)


class ActivityUpdate(BaseModel):
    name: str | None = None
    subject_id: int | None = None
    kind: ActivityKind | None = None
    duration_minutes: int | None = None
    occurrences_per_cycle: int | None = None
    priority: int | None = None
    active: bool | None = None
    notes: str | None = None
    fixed_start_minute: int | None = None
    fixed_room_id: int | None = None
    align_to_periods: bool | None = None
    start_step_minutes: int | None = None
    min_capacity: int | None = None
    teacher_ids: list[int] | None = None
    student_ids: list[int] | None = None
    group_ids: list[int] | None = None
    required_feature_ids: list[int] | None = None
    allowed_room_ids: list[int] | None = None
    preferred_room_ids: list[int] | None = None
    forbidden_room_ids: list[int] | None = None
    time_windows: list[ActivityTimeWindowIn] | None = None


class ActivityOut(ORMModel, ActivityBase):
    id: int
    teacher_ids: list[int] = Field(default_factory=list)
    student_ids: list[int] = Field(default_factory=list)
    group_ids: list[int] = Field(default_factory=list)
    required_feature_ids: list[int] = Field(default_factory=list)
    allowed_room_ids: list[int] = Field(default_factory=list)
    preferred_room_ids: list[int] = Field(default_factory=list)
    forbidden_room_ids: list[int] = Field(default_factory=list)
    time_windows: list[ActivityTimeWindowOut] = Field(default_factory=list)
    subject_name: str | None = None
    teacher_names: list[str] = Field(default_factory=list)
    participant_count: int = 0


class ActivityLinkIn(BaseModel):
    kind: LinkKind
    activity_a_id: int
    activity_b_id: int
    note: str | None = None


class ActivityLinkOut(ORMModel, ActivityLinkIn):
    id: int


class IndividualLessonRow(BaseModel):
    """One row of the bulk editor for one-to-one tuition."""

    id: int | None = None
    student_id: int
    subject_id: int | None = None
    teacher_id: int | None = None
    duration_minutes: int = 45
    occurrences_per_cycle: int = 1
    allowed_day_ordinals: list[int] = Field(default_factory=list)
    required_feature_ids: list[int] = Field(default_factory=list)
    name: str | None = None
    active: bool = True


class IndividualLessonOut(IndividualLessonRow):
    id: int
    student_name: str
    class_name: str | None = None
    subject_name: str | None = None
    teacher_name: str | None = None


class IndividualLessonBulk(BaseModel):
    rows: list[IndividualLessonRow]
    delete_ids: list[int] = Field(default_factory=list)
