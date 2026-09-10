"""Schemas for schedules, versions, solver runs and manual editing."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import Severity, SolverStatus, VersionStatus
from app.schemas.core import ORMModel


class ScheduleIn(BaseModel):
    name: str
    description: str | None = None


class ScheduleOut(ORMModel, ScheduleIn):
    id: int
    created_at: datetime | None = None
    version_count: int = 0


class ScheduledActivityOut(ORMModel):
    id: int
    version_id: int
    activity_id: int
    occurrence_index: int
    start_minute: int
    duration_minutes: int
    day_ordinal: int
    room_id: int | None = None
    lock_time: bool = False
    lock_room: bool = False
    # denormalised for the grid
    activity_name: str = ""
    subject_name: str | None = None
    subject_color: str | None = None
    room_name: str | None = None
    building: str | None = None
    teacher_ids: list[int] = Field(default_factory=list)
    teacher_names: list[str] = Field(default_factory=list)
    student_ids: list[int] = Field(default_factory=list)
    group_ids: list[int] = Field(default_factory=list)
    group_names: list[str] = Field(default_factory=list)
    student_count: int = 0
    kind: str = "STANDARD"


class ScheduledActivityPatch(BaseModel):
    start_minute: int | None = None
    room_id: int | None = None
    day_ordinal: int | None = None
    lock_time: bool | None = None
    lock_room: bool | None = None


class LockIn(BaseModel):
    lock_time: bool = True
    lock_room: bool = True


class ScheduleVersionOut(ORMModel):
    id: int
    schedule_id: int
    name: str
    status: VersionStatus
    created_at: datetime | None = None
    parent_version_id: int | None = None
    solver_run_id: int | None = None
    total_penalty: int | None = None
    penalties: dict | None = None
    note: str | None = None
    item_count: int = 0


class ScheduleVersionDetail(ScheduleVersionOut):
    items: list[ScheduledActivityOut] = Field(default_factory=list)


class VersionDuplicateIn(BaseModel):
    name: str | None = None


class Conflict(BaseModel):
    code: str
    severity: Severity = Severity.ERROR
    message: str
    entity_type: str | None = None
    entity_id: int | None = None
    conflicting_item_id: int | None = None


class MoveCheckIn(BaseModel):
    start_minute: int
    room_id: int | None = None


class RoomSuggestion(BaseModel):
    room_id: int
    room_name: str
    free: bool
    reason: str | None = None


class MoveCheckOut(BaseModel):
    ok: bool
    conflicts: list[Conflict] = Field(default_factory=list)
    room_suggestions: list[RoomSuggestion] = Field(default_factory=list)


class DiagnosticItem(BaseModel):
    code: str
    severity: Severity
    message: str
    entity_type: str | None = None
    entity_id: int | None = None
    details: dict | None = None


class SolverRunCreate(BaseModel):
    schedule_id: int | None = None
    base_version_id: int | None = None
    time_limit_seconds: int = 60
    version_name: str | None = None
    reoptimize: bool = False
    keep_locked_only: bool = True


class SolverRunOut(ORMModel):
    id: int
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    status: SolverStatus
    time_limit_seconds: int
    best_score: int | None = None
    schedule_version_id: int | None = None
    schedule_id: int | None = None
    base_version_id: int | None = None
    params: dict | None = None
    penalties: dict | None = None
    diagnostics: list | None = None
    log: str | None = None


class ConstraintWeightOut(ORMModel):
    id: int
    code: str
    name: str
    type: str
    weight: int
    enabled: bool
    description: str | None = None


class ConstraintWeightUpdate(BaseModel):
    weight: int | None = None
    enabled: bool | None = None
    name: str | None = None
    description: str | None = None


class AuditOut(ORMModel):
    id: int
    at: datetime | None = None
    actor: str | None = None
    entity_type: str
    entity_id: int | None = None
    action: str
    old_value: dict | None = None
    new_value: dict | None = None


class VersionCompareItem(BaseModel):
    activity_id: int
    activity_name: str
    occurrence_index: int
    change: str  # ADDED | REMOVED | MOVED | ROOM_CHANGED | UNCHANGED
    left_start: int | None = None
    right_start: int | None = None
    left_room: str | None = None
    right_room: str | None = None


class VersionCompareOut(BaseModel):
    left_version_id: int
    right_version_id: int
    changed: int
    unchanged: int
    items: list[VersionCompareItem]
