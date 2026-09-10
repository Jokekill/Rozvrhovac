"""SQLAlchemy models. Importing this package registers every table."""
from app.models.activity import (
    Activity,
    ActivityLink,
    ActivityRoomPolicy,
    ActivityRoomRequirement,
    ActivityStudent,
    ActivityStudentGroup,
    ActivityTeacher,
    ActivityTimeWindow,
)
from app.models.calendar import MINUTES_PER_DAY, AvailabilityWindow, CycleConfig, Day, Period
from app.models.core import (
    Room,
    RoomFeature,
    RoomFeatureAssignment,
    Student,
    StudentGroup,
    StudentGroupMember,
    Subject,
    Teacher,
)
from app.models.schedule import Schedule, ScheduledActivity, ScheduleVersion, SolverRun
from app.models.system import AuditLog, ConstraintWeight, User

__all__ = [
    "Activity",
    "ActivityLink",
    "ActivityRoomPolicy",
    "ActivityRoomRequirement",
    "ActivityStudent",
    "ActivityStudentGroup",
    "ActivityTeacher",
    "ActivityTimeWindow",
    "AuditLog",
    "AvailabilityWindow",
    "ConstraintWeight",
    "CycleConfig",
    "Day",
    "MINUTES_PER_DAY",
    "Period",
    "Room",
    "RoomFeature",
    "RoomFeatureAssignment",
    "Schedule",
    "ScheduleVersion",
    "ScheduledActivity",
    "SolverRun",
    "Student",
    "StudentGroup",
    "StudentGroupMember",
    "Subject",
    "Teacher",
    "User",
]
