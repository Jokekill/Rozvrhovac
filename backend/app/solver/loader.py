"""Builds the solver input from the database.

Two things happen here that the specification insists on:

* student groups are expanded into concrete ``student_id`` sets, so the solver
  never sees a class as an atomic object;
* every candidate start is precomputed in absolute cycle minutes, which turns
  day boundaries (HC10) and teacher/student availability (HC04/HC05) into a
  domain restriction instead of extra constraints.
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import (
    Activity,
    ActivityLink,
    ActivityStudentGroup,
    ActivityTeacher,
    AvailabilityWindow,
    ConstraintWeight,
    CycleConfig,
    Day,
    Period,
    Room,
    ScheduledActivity,
    Student,
    Teacher,
)
from app.models.calendar import MINUTES_PER_DAY
from app.models.enums import AvailabilityKind, OwnerType, RoomPolicyKind, TimeWindowKind
from app.solver.model import (
    ActivityData,
    Assignment,
    DayData,
    LinkData,
    PeriodData,
    PersonData,
    RoomData,
    SolverConfig,
    SolverInput,
)
from app.services.participants import activity_students_map, activity_teachers_map


def _expand_windows(
    windows: list[AvailabilityWindow], days: list[DayData]
) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """Turn per-day windows into absolute (start, end) intervals."""
    unavailable: list[tuple[int, int]] = []
    preferred: list[tuple[int, int]] = []
    for window in windows:
        targets = (
            [d for d in days if d.ordinal == window.day_ordinal]
            if window.day_ordinal is not None
            else days
        )
        for day in targets:
            interval = (day.offset + window.start_minute, day.offset + window.end_minute)
            if interval[1] <= interval[0]:
                continue
            if window.kind == AvailabilityKind.PREFERRED:
                preferred.append(interval)
            else:
                unavailable.append(interval)
    return unavailable, preferred


def _overlaps(start: int, end: int, intervals: list[tuple[int, int]]) -> bool:
    return any(start < window_end and end > window_start for window_start, window_end in intervals)


def compute_compatible_rooms(
    activity: ActivityData, rooms: dict[int, RoomData]
) -> list[int]:
    """HC07 + HC08 + allowed/forbidden policy, with a reason for each rejection."""
    needed_capacity = max(len(activity.student_ids), activity.min_capacity or 0)
    compatible: list[int] = []
    for room in rooms.values():
        if activity.fixed_room_id and room.id != activity.fixed_room_id:
            continue
        if room.id in activity.forbidden_room_ids:
            activity.room_rejections[room.id] = "forbidden"
            continue
        if activity.allowed_room_ids and room.id not in activity.allowed_room_ids:
            activity.room_rejections[room.id] = "not in allowed_rooms"
            continue
        missing = activity.required_feature_ids - room.feature_ids
        if missing:
            activity.room_rejections[room.id] = "missing features"
            continue
        if room.capacity < needed_capacity:
            activity.room_rejections[room.id] = (
                f"capacity {room.capacity} < {needed_capacity}"
            )
            continue
        compatible.append(room.id)
    return sorted(compatible)


def compute_candidate_starts(
    activity: ActivityData,
    days: list[DayData],
    period_starts: list[int],
    granularity: int,
    time_windows: list[tuple[str, int | None, int | None, int | None]],
    busy: list[tuple[int, int]],
) -> list[int]:
    """Every absolute minute at which the activity may legally start.

    ``time_windows`` are the activity's own ALLOWED/FORBIDDEN restrictions,
    ``busy`` the union of unavailability of its teachers and students.
    """
    allowed = [w for w in time_windows if w[0] == TimeWindowKind.ALLOWED]
    forbidden = [w for w in time_windows if w[0] == TimeWindowKind.FORBIDDEN]
    step = activity.start_step_minutes or granularity
    duration = activity.duration
    starts: list[int] = []

    for day in days:
        if activity.align_to_periods and period_starts:
            day_starts = [
                day.offset + p
                for p in period_starts
                if day.start_minute <= p and p + duration <= day.end_minute
            ]
        else:
            day_starts = list(
                range(day.abs_start, day.abs_end - duration + 1, step)
            )
        for start in day_starts:
            end = start + duration
            if start < day.abs_start or end > day.abs_end:
                continue  # HC10
            if allowed:
                ok = False
                for _, day_ordinal, window_start, window_end in allowed:
                    if day_ordinal is not None and day_ordinal != day.ordinal:
                        continue
                    lower = day.offset + (window_start if window_start is not None else 0)
                    upper = day.offset + (
                        window_end if window_end is not None else MINUTES_PER_DAY
                    )
                    if start >= lower and end <= upper:
                        ok = True
                        break
                if not ok:
                    continue
            blocked = False
            for _, day_ordinal, window_start, window_end in forbidden:
                if day_ordinal is not None and day_ordinal != day.ordinal:
                    continue
                lower = day.offset + (window_start if window_start is not None else 0)
                upper = day.offset + (
                    window_end if window_end is not None else MINUTES_PER_DAY
                )
                if start < upper and end > lower:
                    blocked = True
                    break
            if blocked:
                continue
            if _overlaps(start, end, busy):  # HC04 + HC05
                continue
            starts.append(start)
    return starts


def load_solver_input(
    db: Session,
    *,
    base_version_id: int | None = None,
    respect_locks: bool = True,
) -> SolverInput:
    config_row = db.get(CycleConfig, 1)
    config = SolverConfig(
        granularity_minutes=config_row.granularity_minutes if config_row else 5,
        lunch_start_minute=config_row.lunch_start_minute if config_row else 11 * 60 + 30,
        lunch_end_minute=config_row.lunch_end_minute if config_row else 13 * 60 + 30,
        lunch_break_minutes=config_row.lunch_break_minutes if config_row else 30,
        early_threshold_minute=config_row.early_threshold_minute if config_row else 8 * 60,
        late_threshold_minute=config_row.late_threshold_minute if config_row else 16 * 60,
        max_student_minutes_per_day=(
            config_row.max_student_minutes_per_day if config_row else 360
        ),
        individual_preferred_start=(
            config_row.individual_preferred_start if config_row else 13 * 60
        ),
        individual_preferred_end=config_row.individual_preferred_end if config_row else 19 * 60,
        core_day_start_minute=config_row.core_day_start_minute if config_row else 8 * 60,
        core_block_periods=config_row.core_block_periods if config_row else 4,
        min_student_lessons_per_day=(
            config_row.min_student_lessons_per_day if config_row else 4
        ),
    )

    days = [
        DayData(
            ordinal=d.ordinal,
            week_index=d.week_index,
            weekday=d.weekday,
            name=d.name,
            start_minute=d.start_minute,
            end_minute=d.end_minute,
        )
        for d in db.execute(select(Day).where(Day.active.is_(True)).order_by(Day.ordinal))
        .scalars()
        .all()
    ]
    periods = [
        PeriodData(
            index=p.index,
            name=p.name,
            start_minute=p.start_minute,
            end_minute=p.end_minute,
        )
        for p in db.execute(select(Period).order_by(Period.index)).scalars()
    ]
    period_starts = sorted(p.start_minute for p in periods)

    windows_by_owner: dict[tuple[str, int], list[AvailabilityWindow]] = defaultdict(list)
    for window in db.execute(select(AvailabilityWindow)).scalars():
        windows_by_owner[(window.owner_type, window.owner_id)].append(window)

    rooms: dict[int, RoomData] = {}
    for room in (
        db.execute(
            select(Room)
            .where(Room.active.is_(True))
            .options(joinedload(Room.feature_assignments))
        )
        .unique()
        .scalars()
    ):
        blocked, _ = _expand_windows(windows_by_owner.get((OwnerType.ROOM, room.id), []), days)
        rooms[room.id] = RoomData(
            id=room.id,
            name=room.name,
            code=room.code,
            capacity=room.capacity,
            building=room.building,
            feature_ids=room.feature_ids,
            blocked=blocked,
        )

    teachers: dict[int, PersonData] = {}
    for teacher in db.execute(select(Teacher)).scalars():
        unavailable, preferred = _expand_windows(
            windows_by_owner.get((OwnerType.TEACHER, teacher.id), []), days
        )
        teachers[teacher.id] = PersonData(
            id=teacher.id,
            name=teacher.full_name,
            unavailable=unavailable,
            preferred=preferred,
            max_minutes_per_day=teacher.max_minutes_per_day,
            max_consecutive_minutes=teacher.max_consecutive_minutes,
        )

    students: dict[int, PersonData] = {}
    for student in db.execute(select(Student)).scalars():
        unavailable, preferred = _expand_windows(
            windows_by_owner.get((OwnerType.STUDENT, student.id), []), days
        )
        students[student.id] = PersonData(
            id=student.id,
            name=student.full_name,
            unavailable=unavailable,
            preferred=preferred,
        )

    student_map = activity_students_map(db)
    teacher_map = activity_teachers_map(db)

    activity_rows = (
        db.execute(
            select(Activity)
            .where(Activity.active.is_(True))
            .options(
                joinedload(Activity.room_requirements),
                joinedload(Activity.room_policies),
                joinedload(Activity.time_windows),
            )
            .order_by(Activity.id)
        )
        .unique()
        .scalars()
        .all()
    )

    activities: list[ActivityData] = []
    for row in activity_rows:
        data = ActivityData(
            id=row.id,
            name=row.name,
            kind=row.kind,
            subject_id=row.subject_id,
            duration=row.duration_minutes,
            occurrences=max(0, row.occurrences_per_cycle),
            priority=row.priority,
            teacher_ids=sorted(teacher_map.get(row.id, set())),
            student_ids=sorted(student_map.get(row.id, set())),
            required_feature_ids={r.feature_id for r in row.room_requirements},
            allowed_room_ids={
                p.room_id for p in row.room_policies if p.kind == RoomPolicyKind.ALLOWED
            },
            preferred_room_ids={
                p.room_id for p in row.room_policies if p.kind == RoomPolicyKind.PREFERRED
            },
            forbidden_room_ids={
                p.room_id for p in row.room_policies if p.kind == RoomPolicyKind.FORBIDDEN
            },
            min_capacity=row.min_capacity,
            fixed_start_minute=row.fixed_start_minute,
            fixed_room_id=row.fixed_room_id,
            align_to_periods=row.align_to_periods,
            start_step_minutes=row.start_step_minutes,
        )
        data.compatible_room_ids = compute_compatible_rooms(data, rooms)
        busy: list[tuple[int, int]] = []
        for teacher_id in data.teacher_ids:
            person = teachers.get(teacher_id)
            if person:
                busy.extend(person.unavailable)
        for student_id in data.student_ids:
            person = students.get(student_id)
            if person:
                busy.extend(person.unavailable)
        data.candidate_starts = compute_candidate_starts(
            data,
            days,
            period_starts,
            config.granularity_minutes,
            [
                (w.kind, w.day_ordinal, w.start_minute, w.end_minute)
                for w in row.time_windows
            ],
            busy,
        )
        activities.append(data)

    links = [
        LinkData(kind=row.kind, activity_a_id=row.activity_a_id, activity_b_id=row.activity_b_id)
        for row in db.execute(select(ActivityLink)).scalars()
    ]

    weights = {
        row.code: row.effective_weight
        for row in db.execute(select(ConstraintWeight)).scalars()
    }

    base_assignments: dict[tuple[int, int], Assignment] = {}
    locked_time: set[tuple[int, int]] = set()
    locked_room: set[tuple[int, int]] = set()
    if base_version_id is not None:
        for item in db.execute(
            select(ScheduledActivity).where(ScheduledActivity.version_id == base_version_id)
        ).scalars():
            key = (item.activity_id, item.occurrence_index)
            base_assignments[key] = Assignment(
                activity_id=item.activity_id,
                occurrence_index=item.occurrence_index,
                start_minute=item.start_minute,
                room_id=item.room_id,
            )
            if respect_locks and item.lock_time:
                locked_time.add(key)
            if respect_locks and item.lock_room:
                locked_room.add(key)

    return SolverInput(
        days=days,
        period_starts=period_starts,
        periods=periods,
        activities=activities,
        rooms=rooms,
        teachers=teachers,
        students=students,
        links=links,
        config=config,
        weights=weights,
        base_assignments=base_assignments,
        locked_time=locked_time,
        locked_room=locked_room,
    )
