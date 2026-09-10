"""Conflict checking for manual edits (§16 and §35).

The scheduler must be told *why* a move is impossible, naming the student, the
teacher and the room, and which rooms would work instead.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import (
    Activity,
    AvailabilityWindow,
    Day,
    Room,
    ScheduledActivity,
)
from app.models.calendar import MINUTES_PER_DAY
from app.models.enums import AvailabilityKind, OwnerType, RoomPolicyKind, Severity
from app.schemas.schedule import Conflict, MoveCheckOut, RoomSuggestion
from app.services.participants import students_of


def _minutes_to_hhmm(minute: int) -> str:
    minute_of_day = minute % MINUTES_PER_DAY
    return f"{minute_of_day // 60:02d}:{minute_of_day % 60:02d}"


def _blocked(
    db: Session,
    owner_type: OwnerType,
    owner_ids: set[int],
    start: int,
    end: int,
) -> dict[int, AvailabilityWindow]:
    """Owners whose UNAVAILABLE window overlaps [start, end)."""
    if not owner_ids:
        return {}
    day_ordinal = start // MINUTES_PER_DAY
    offset = day_ordinal * MINUTES_PER_DAY
    rows = db.execute(
        select(AvailabilityWindow).where(
            AvailabilityWindow.owner_type == owner_type,
            AvailabilityWindow.owner_id.in_(owner_ids),
            AvailabilityWindow.kind == AvailabilityKind.UNAVAILABLE,
        )
    ).scalars()
    hits: dict[int, AvailabilityWindow] = {}
    for window in rows:
        if window.day_ordinal is not None and window.day_ordinal != day_ordinal:
            continue
        window_start = offset + window.start_minute
        window_end = offset + window.end_minute
        if start < window_end and end > window_start:
            hits.setdefault(window.owner_id, window)
    return hits


def room_is_compatible(activity: Activity, room: Room, student_count: int) -> str | None:
    """None when the room fits, otherwise a human readable reason."""
    if not room.active:
        return "učebna je neaktivní"
    forbidden = {
        p.room_id for p in activity.room_policies if p.kind == RoomPolicyKind.FORBIDDEN
    }
    allowed = {p.room_id for p in activity.room_policies if p.kind == RoomPolicyKind.ALLOWED}
    if room.id in forbidden:
        return "učebna je na seznamu zakázaných"
    if allowed and room.id not in allowed:
        return "učebna není na seznamu povolených"
    required = {r.feature_id for r in activity.room_requirements}
    missing = required - room.feature_ids
    if missing:
        return "učebna nemá požadované vlastnosti"
    needed = max(student_count, activity.min_capacity or 0)
    if room.capacity < needed:
        return f"kapacita {room.capacity} < {needed}"
    return None


def check_move(
    db: Session,
    item: ScheduledActivity,
    start_minute: int,
    room_id: int | None,
) -> MoveCheckOut:
    activity = item.activity
    duration = item.duration_minutes
    end_minute = start_minute + duration
    conflicts: list[Conflict] = []

    day_ordinal = start_minute // MINUTES_PER_DAY
    day = db.execute(select(Day).where(Day.ordinal == day_ordinal)).scalars().first()
    if day is None or not day.active:
        conflicts.append(
            Conflict(
                code="HC10_NO_SUCH_DAY",
                message=f"Den {day_ordinal} není součástí plánovacího cyklu.",
            )
        )
    elif start_minute < day.abs_start or end_minute > day.abs_end:
        conflicts.append(
            Conflict(
                code="HC10_OUTSIDE_SCHOOL_DAY",
                message=(
                    f"Aktivita by přesáhla vyučovací den "
                    f"({_minutes_to_hhmm(day.abs_start)}–{_minutes_to_hhmm(day.abs_end)})."
                ),
            )
        )

    student_ids = students_of(db, activity)
    teacher_ids = {t.teacher_id for t in activity.teachers}

    # HC01 / HC02 / HC03 against the rest of this version.
    others = (
        db.execute(
            select(ScheduledActivity)
            .where(
                ScheduledActivity.version_id == item.version_id,
                ScheduledActivity.id != item.id,
            )
            .options(
                joinedload(ScheduledActivity.activity).joinedload(Activity.teachers),
                joinedload(ScheduledActivity.activity).joinedload(Activity.students),
                joinedload(ScheduledActivity.activity).joinedload(Activity.groups),
                joinedload(ScheduledActivity.room),
            )
        )
        .unique()
        .scalars()
        .all()
    )
    for other in others:
        if not (start_minute < other.end_minute and end_minute > other.start_minute):
            continue
        other_students = students_of(db, other.activity)
        shared_students = student_ids & other_students
        if shared_students:
            from app.models import Student

            sample = db.execute(
                select(Student).where(Student.id.in_(sorted(shared_students)[:3]))
            ).scalars().all()
            listed = ", ".join(s.full_name for s in sample)
            more = len(shared_students) - len(sample)
            conflicts.append(
                Conflict(
                    code="HC01_STUDENT_CONFLICT",
                    message=(
                        f"Student{'i' if len(shared_students) > 1 else ''} {listed}"
                        + (f" a další {more}" if more > 0 else "")
                        + f" má v tuto dobu '{other.activity.name}'."
                    ),
                    entity_type="Student",
                    entity_id=sorted(shared_students)[0],
                    conflicting_item_id=other.id,
                )
            )
        shared_teachers = teacher_ids & {t.teacher_id for t in other.activity.teachers}
        if shared_teachers:
            names = ", ".join(
                t.teacher.full_name
                for t in other.activity.teachers
                if t.teacher_id in shared_teachers
            )
            conflicts.append(
                Conflict(
                    code="HC02_TEACHER_CONFLICT",
                    message=f"Učitel {names} v tuto dobu učí '{other.activity.name}'.",
                    entity_type="Teacher",
                    entity_id=sorted(shared_teachers)[0],
                    conflicting_item_id=other.id,
                )
            )
        if room_id is not None and other.room_id == room_id:
            conflicts.append(
                Conflict(
                    code="HC03_ROOM_CONFLICT",
                    message=(
                        f"Učebna {other.room.name if other.room else room_id} je obsazená "
                        f"aktivitou '{other.activity.name}'."
                    ),
                    entity_type="Room",
                    entity_id=room_id,
                    conflicting_item_id=other.id,
                )
            )

    # HC04 / HC05 / HC06 availability.
    for owner_type, owner_ids, code, label in (
        (OwnerType.TEACHER, teacher_ids, "HC04_TEACHER_AVAILABILITY", "Učitel"),
        (OwnerType.STUDENT, student_ids, "HC05_STUDENT_AVAILABILITY", "Student"),
    ):
        for owner_id, window in _blocked(
            db, owner_type, owner_ids, start_minute, end_minute
        ).items():
            from app.models import Student, Teacher

            person = db.get(Teacher if owner_type == OwnerType.TEACHER else Student, owner_id)
            conflicts.append(
                Conflict(
                    code=code,
                    message=(
                        f"{label} {person.full_name if person else owner_id} není v tuto dobu "
                        f"dostupný ({_minutes_to_hhmm(window.start_minute)}"
                        f"–{_minutes_to_hhmm(window.end_minute)})."
                    ),
                    entity_type=label,
                    entity_id=owner_id,
                )
            )
    if room_id is not None:
        for _, window in _blocked(
            db, OwnerType.ROOM, {room_id}, start_minute, end_minute
        ).items():
            room = db.get(Room, room_id)
            conflicts.append(
                Conflict(
                    code="HC06_ROOM_AVAILABILITY",
                    message=(
                        f"Učebna {room.name if room else room_id} je v tuto dobu nedostupná "
                        f"({window.note or 'blokace'})."
                    ),
                    entity_type="Room",
                    entity_id=room_id,
                )
            )

    # HC07 / HC08 room suitability.
    if room_id is not None:
        room = db.get(Room, room_id)
        if room is None:
            conflicts.append(
                Conflict(code="ROOM_NOT_FOUND", message=f"Učebna {room_id} neexistuje.")
            )
        else:
            reason = room_is_compatible(activity, room, len(student_ids))
            if reason:
                conflicts.append(
                    Conflict(
                        code="HC07_HC08_ROOM_UNSUITABLE",
                        message=f"Učebna {room.name} nevyhovuje: {reason}.",
                        entity_type="Room",
                        entity_id=room.id,
                    )
                )

    if item.lock_time and start_minute != item.start_minute:
        conflicts.append(
            Conflict(
                code="LOCKED_TIME",
                severity=Severity.WARNING,
                message="Hodina má uzamčený čas; přesunem zámek porušíte.",
            )
        )
    if item.lock_room and room_id != item.room_id:
        conflicts.append(
            Conflict(
                code="LOCKED_ROOM",
                severity=Severity.WARNING,
                message="Hodina má uzamčenou učebnu.",
            )
        )

    suggestions = suggest_rooms(db, item, start_minute, others)
    return MoveCheckOut(
        ok=not any(c.severity == Severity.ERROR for c in conflicts),
        conflicts=conflicts,
        room_suggestions=suggestions,
    )


def suggest_rooms(
    db: Session,
    item: ScheduledActivity,
    start_minute: int,
    others: list[ScheduledActivity] | None = None,
) -> list[RoomSuggestion]:
    """Which rooms would host this occurrence at ``start_minute``."""
    activity = item.activity
    student_count = len(students_of(db, activity))
    end_minute = start_minute + item.duration_minutes
    if others is None:
        others = (
            db.execute(
                select(ScheduledActivity).where(
                    ScheduledActivity.version_id == item.version_id,
                    ScheduledActivity.id != item.id,
                )
            )
            .scalars()
            .all()
        )
    occupied = {
        other.room_id
        for other in others
        if other.room_id is not None
        and start_minute < other.end_minute
        and end_minute > other.start_minute
    }
    blocked_rooms = set(
        _blocked(
            db,
            OwnerType.ROOM,
            {r.id for r in db.execute(select(Room)).scalars()},
            start_minute,
            end_minute,
        )
    )
    suggestions: list[RoomSuggestion] = []
    for room in db.execute(
        select(Room).where(Room.active.is_(True)).options(joinedload(Room.feature_assignments))
    ).unique().scalars():
        reason = room_is_compatible(activity, room, student_count)
        if reason:
            continue
        if room.id in blocked_rooms:
            suggestions.append(
                RoomSuggestion(
                    room_id=room.id, room_name=room.name, free=False, reason="nedostupná"
                )
            )
            continue
        free = room.id not in occupied
        suggestions.append(
            RoomSuggestion(
                room_id=room.id,
                room_name=room.name,
                free=free,
                reason=None if free else "obsazená",
            )
        )
    suggestions.sort(key=lambda s: (not s.free, s.room_name))
    return suggestions
