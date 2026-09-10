"""Enumerations shared by the domain model.

They are stored as plain strings so that adding a value never requires a
database type migration.
"""
from __future__ import annotations

from enum import StrEnum


class GroupType(StrEnum):
    CLASS = "CLASS"
    SUBGROUP = "SUBGROUP"
    CROSS_CLASS = "CROSS_CLASS"
    ENSEMBLE = "ENSEMBLE"
    OTHER = "OTHER"


class ActivityKind(StrEnum):
    """Purely descriptive: the solver treats every kind identically."""

    STANDARD = "STANDARD"
    SPLIT = "SPLIT"
    CROSS_CLASS = "CROSS_CLASS"
    ENSEMBLE = "ENSEMBLE"
    INDIVIDUAL = "INDIVIDUAL"
    OTHER = "OTHER"


class OwnerType(StrEnum):
    TEACHER = "TEACHER"
    STUDENT = "STUDENT"
    ROOM = "ROOM"


class AvailabilityKind(StrEnum):
    UNAVAILABLE = "UNAVAILABLE"
    PREFERRED = "PREFERRED"


class RoomPolicyKind(StrEnum):
    ALLOWED = "ALLOWED"
    PREFERRED = "PREFERRED"
    FORBIDDEN = "FORBIDDEN"


class TimeWindowKind(StrEnum):
    ALLOWED = "ALLOWED"
    FORBIDDEN = "FORBIDDEN"
    PREFERRED = "PREFERRED"


class LinkKind(StrEnum):
    SAME_START = "SAME_START"
    NOT_SIMULTANEOUS = "NOT_SIMULTANEOUS"
    BEFORE = "BEFORE"


class SolverStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    FEASIBLE = "FEASIBLE"
    OPTIMAL = "OPTIMAL"
    INFEASIBLE = "INFEASIBLE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class VersionStatus(StrEnum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


class Role(StrEnum):
    ADMIN = "ADMIN"
    SCHEDULER = "SCHEDULER"
    TEACHER = "TEACHER"
    VIEWER = "VIEWER"


class Severity(StrEnum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


# Soft constraint weight scale from the specification.
WEIGHT_VERY_LOW = 1
WEIGHT_LOW = 10
WEIGHT_MEDIUM = 100
WEIGHT_HIGH = 1000
