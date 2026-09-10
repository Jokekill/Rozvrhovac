"""Tiny builders so that solver tests read like the scenario they describe."""
from __future__ import annotations

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models import (
    Activity,
    ActivityLink,
    ActivityRoomRequirement,
    ActivityStudent,
    ActivityStudentGroup,
    ActivityTeacher,
    AvailabilityWindow,
    Day,
    Period,
    Room,
    RoomFeature,
    RoomFeatureAssignment,
    SolverRun,
    Student,
    StudentGroup,
    StudentGroupMember,
    Subject,
    Teacher,
)
from app.models.calendar import MINUTES_PER_DAY
from app.models.enums import ActivityKind, AvailabilityKind, GroupType, OwnerType
from app.solver.runner import execute_run

SLOT = 45


def set_calendar(db: Session, *, days: int = 1, slots: int = 2, start: int = 8 * 60) -> None:
    """Replace the cycle with ``days`` days of exactly ``slots`` lesson slots."""
    db.execute(delete(Day))
    db.execute(delete(Period))
    for ordinal in range(days):
        db.add(
            Day(
                ordinal=ordinal,
                week_index=0,
                weekday=ordinal % 7,
                name=f"D{ordinal}",
                start_minute=start,
                end_minute=start + slots * SLOT,
            )
        )
    for index in range(slots):
        db.add(
            Period(
                index=index,
                name=f"{index + 1}.",
                start_minute=start + index * SLOT,
                end_minute=start + (index + 1) * SLOT,
            )
        )
    db.flush()


def abs_minute(day_ordinal: int, minute_of_day: int) -> int:
    return day_ordinal * MINUTES_PER_DAY + minute_of_day


def make_student(db: Session, name: str, group: StudentGroup | None = None) -> Student:
    first, _, last = name.partition(" ")
    student = Student(first_name=first, last_name=last or "X")
    if group is not None:
        student.class_group_id = group.id
    db.add(student)
    db.flush()
    if group is not None:
        db.add(StudentGroupMember(group_id=group.id, student_id=student.id))
        db.flush()
    return student


def make_group(
    db: Session, name: str, group_type: GroupType = GroupType.CLASS, students=()
) -> StudentGroup:
    group = StudentGroup(name=name, type=group_type)
    db.add(group)
    db.flush()
    for student in students:
        db.add(StudentGroupMember(group_id=group.id, student_id=student.id))
    db.flush()
    return group


def make_teacher(db: Session, name: str) -> Teacher:
    first, _, last = name.partition(" ")
    teacher = Teacher(first_name=first, last_name=last or "X")
    db.add(teacher)
    db.flush()
    return teacher


def make_room(db: Session, name: str, capacity: int = 30, features=()) -> Room:
    room = Room(name=name, code=name, capacity=capacity, building="A")
    db.add(room)
    db.flush()
    for feature_name in features:
        feature = (
            db.query(RoomFeature).filter(RoomFeature.name == feature_name).one_or_none()
        )
        if feature is None:
            feature = RoomFeature(name=feature_name)
            db.add(feature)
            db.flush()
        db.add(RoomFeatureAssignment(room_id=room.id, feature_id=feature.id))
    db.flush()
    return room


def make_subject(db: Session, name: str) -> Subject:
    subject = Subject(name=name, code=name[:6])
    db.add(subject)
    db.flush()
    return subject


def make_activity(
    db: Session,
    name: str,
    *,
    teachers=(),
    students=(),
    groups=(),
    duration: int = SLOT,
    occurrences: int = 1,
    features=(),
    kind: ActivityKind = ActivityKind.STANDARD,
    align: bool = True,
    fixed_start: int | None = None,
    fixed_room: Room | None = None,
    subject: Subject | None = None,
) -> Activity:
    activity = Activity(
        name=name,
        duration_minutes=duration,
        occurrences_per_cycle=occurrences,
        kind=kind,
        align_to_periods=align,
        fixed_start_minute=fixed_start,
        fixed_room_id=fixed_room.id if fixed_room else None,
        subject_id=subject.id if subject else None,
    )
    db.add(activity)
    db.flush()
    for teacher in teachers:
        db.add(ActivityTeacher(activity_id=activity.id, teacher_id=teacher.id))
    for student in students:
        db.add(ActivityStudent(activity_id=activity.id, student_id=student.id))
    for group in groups:
        db.add(ActivityStudentGroup(activity_id=activity.id, group_id=group.id))
    for feature_name in features:
        feature = db.query(RoomFeature).filter(RoomFeature.name == feature_name).one()
        db.add(ActivityRoomRequirement(activity_id=activity.id, feature_id=feature.id))
    db.flush()
    return activity


def make_link(db: Session, kind: str, left: Activity, right: Activity) -> ActivityLink:
    link = ActivityLink(kind=kind, activity_a_id=left.id, activity_b_id=right.id)
    db.add(link)
    db.flush()
    return link


def block(
    db: Session,
    owner_type: OwnerType,
    owner_id: int,
    day_ordinal: int | None,
    start: int,
    end: int,
) -> AvailabilityWindow:
    window = AvailabilityWindow(
        owner_type=owner_type,
        owner_id=owner_id,
        kind=AvailabilityKind.UNAVAILABLE,
        day_ordinal=day_ordinal,
        start_minute=start,
        end_minute=end,
    )
    db.add(window)
    db.flush()
    return window


def solve(db: Session, *, time_limit: int = 20, base_version_id: int | None = None,
          reoptimize: bool = False) -> SolverRun:
    """Run the solver synchronously and return the finished run."""
    db.commit()
    run = SolverRun(
        time_limit_seconds=time_limit,
        base_version_id=base_version_id,
        params={"reoptimize": reoptimize, "workers": 4},
    )
    db.add(run)
    db.commit()
    execute_run(run.id, db)
    db.refresh(run)
    return run


def items_of(db: Session, run: SolverRun):
    from app.models import ScheduledActivity

    return (
        db.query(ScheduledActivity)
        .filter(ScheduledActivity.version_id == run.schedule_version_id)
        .all()
    )


def overlaps(a, b) -> bool:
    return a.start_minute < b.end_minute and b.start_minute < a.end_minute
