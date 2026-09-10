"""Pydantic schemas for the base registers."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import AvailabilityKind, GroupType, OwnerType


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Student ---------------------------------------------------------------
class StudentBase(BaseModel):
    first_name: str
    last_name: str
    external_id: str | None = None
    active: bool = True
    class_group_id: int | None = None
    notes: str | None = None


class StudentCreate(StudentBase):
    pass


class StudentUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    external_id: str | None = None
    active: bool | None = None
    class_group_id: int | None = None
    notes: str | None = None


class StudentOut(ORMModel, StudentBase):
    id: int
    full_name: str = ""
    class_group_name: str | None = None


# --- Teacher ---------------------------------------------------------------
class TeacherBase(BaseModel):
    first_name: str
    last_name: str
    external_id: str | None = None
    active: bool = True
    max_minutes_per_day: int | None = None
    max_consecutive_minutes: int | None = None
    notes: str | None = None


class TeacherCreate(TeacherBase):
    pass


class TeacherUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    external_id: str | None = None
    active: bool | None = None
    max_minutes_per_day: int | None = None
    max_consecutive_minutes: int | None = None
    notes: str | None = None


class TeacherOut(ORMModel, TeacherBase):
    id: int
    full_name: str = ""


# --- Room ------------------------------------------------------------------
class RoomBase(BaseModel):
    name: str
    code: str | None = None
    building: str | None = None
    floor: str | None = None
    capacity: int = 30
    active: bool = True


class RoomCreate(RoomBase):
    feature_ids: list[int] = Field(default_factory=list)


class RoomUpdate(BaseModel):
    name: str | None = None
    code: str | None = None
    building: str | None = None
    floor: str | None = None
    capacity: int | None = None
    active: bool | None = None
    feature_ids: list[int] | None = None


class RoomOut(ORMModel, RoomBase):
    id: int
    feature_ids: list[int] = Field(default_factory=list)
    feature_names: list[str] = Field(default_factory=list)


class RoomFeatureIn(BaseModel):
    name: str
    description: str | None = None


class RoomFeatureOut(ORMModel, RoomFeatureIn):
    id: int


# --- Subject ---------------------------------------------------------------
class SubjectIn(BaseModel):
    name: str
    code: str | None = None
    color: str | None = None


class SubjectUpdate(BaseModel):
    name: str | None = None
    code: str | None = None
    color: str | None = None


class SubjectOut(ORMModel, SubjectIn):
    id: int


# --- Student group ---------------------------------------------------------
class GroupBase(BaseModel):
    name: str
    code: str | None = None
    type: GroupType = GroupType.OTHER


class GroupCreate(GroupBase):
    student_ids: list[int] = Field(default_factory=list)


class GroupUpdate(BaseModel):
    name: str | None = None
    code: str | None = None
    type: GroupType | None = None
    student_ids: list[int] | None = None


class GroupOut(ORMModel, GroupBase):
    id: int
    student_ids: list[int] = Field(default_factory=list)
    member_count: int = 0


# --- Availability ----------------------------------------------------------
class AvailabilityIn(BaseModel):
    owner_type: OwnerType
    owner_id: int
    kind: AvailabilityKind = AvailabilityKind.UNAVAILABLE
    day_ordinal: int | None = None
    start_minute: int
    end_minute: int
    note: str | None = None


class AvailabilityUpdate(BaseModel):
    kind: AvailabilityKind | None = None
    day_ordinal: int | None = None
    start_minute: int | None = None
    end_minute: int | None = None
    note: str | None = None


class AvailabilityOut(ORMModel, AvailabilityIn):
    id: int


# --- Calendar --------------------------------------------------------------
class DayIn(BaseModel):
    ordinal: int
    week_index: int = 0
    weekday: int
    name: str
    start_minute: int = 8 * 60
    end_minute: int = 17 * 60
    active: bool = True


class DayOut(ORMModel, DayIn):
    id: int


class PeriodIn(BaseModel):
    index: int
    name: str
    start_minute: int
    end_minute: int


class PeriodOut(ORMModel, PeriodIn):
    id: int


class CycleConfigOut(ORMModel):
    id: int
    name: str
    weeks_in_cycle: int
    granularity_minutes: int
    lunch_start_minute: int
    lunch_end_minute: int
    lunch_break_minutes: int
    early_threshold_minute: int
    late_threshold_minute: int
    max_student_minutes_per_day: int
    individual_preferred_start: int
    individual_preferred_end: int


class CycleConfigUpdate(BaseModel):
    name: str | None = None
    weeks_in_cycle: int | None = None
    granularity_minutes: int | None = None
    lunch_start_minute: int | None = None
    lunch_end_minute: int | None = None
    lunch_break_minutes: int | None = None
    early_threshold_minute: int | None = None
    late_threshold_minute: int | None = None
    max_student_minutes_per_day: int | None = None
    individual_preferred_start: int | None = None
    individual_preferred_end: int | None = None
