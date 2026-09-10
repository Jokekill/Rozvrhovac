"""ORM -> API schema conversion helpers."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Activity, Room, ScheduledActivity, Student, StudentGroup
from app.models.enums import RoomPolicyKind
from app.schemas.activity import ActivityOut, ActivityTimeWindowOut
from app.schemas.core import GroupOut, RoomOut, StudentOut
from app.schemas.schedule import ScheduledActivityOut


def student_out(student: Student) -> StudentOut:
    return StudentOut(
        id=student.id,
        first_name=student.first_name,
        last_name=student.last_name,
        external_id=student.external_id,
        active=student.active,
        class_group_id=student.class_group_id,
        notes=student.notes,
        full_name=student.full_name,
        class_group_name=student.class_group.name if student.class_group else None,
    )


def room_out(room: Room) -> RoomOut:
    return RoomOut(
        id=room.id,
        name=room.name,
        code=room.code,
        building=room.building,
        floor=room.floor,
        capacity=room.capacity,
        active=room.active,
        feature_ids=sorted(fa.feature_id for fa in room.feature_assignments),
        feature_names=sorted(fa.feature.name for fa in room.feature_assignments),
    )


def group_out(group: StudentGroup) -> GroupOut:
    ids = sorted(m.student_id for m in group.members)
    return GroupOut(
        id=group.id,
        name=group.name,
        code=group.code,
        type=group.type,
        student_ids=ids,
        member_count=len(ids),
    )


def _rooms_by_kind(activity: Activity, kind: RoomPolicyKind) -> list[int]:
    return sorted(p.room_id for p in activity.room_policies if p.kind == kind)


def activity_out(activity: Activity) -> ActivityOut:
    students = {link.student_id for link in activity.students}
    for link in activity.groups:
        students |= {m.student_id for m in link.group.members}
    return ActivityOut(
        id=activity.id,
        name=activity.name,
        subject_id=activity.subject_id,
        kind=activity.kind,
        duration_minutes=activity.duration_minutes,
        occurrences_per_cycle=activity.occurrences_per_cycle,
        priority=activity.priority,
        active=activity.active,
        notes=activity.notes,
        fixed_start_minute=activity.fixed_start_minute,
        fixed_room_id=activity.fixed_room_id,
        align_to_periods=activity.align_to_periods,
        start_step_minutes=activity.start_step_minutes,
        min_capacity=activity.min_capacity,
        teacher_ids=sorted(t.teacher_id for t in activity.teachers),
        student_ids=sorted(s.student_id for s in activity.students),
        group_ids=sorted(g.group_id for g in activity.groups),
        required_feature_ids=sorted(r.feature_id for r in activity.room_requirements),
        allowed_room_ids=_rooms_by_kind(activity, RoomPolicyKind.ALLOWED),
        preferred_room_ids=_rooms_by_kind(activity, RoomPolicyKind.PREFERRED),
        forbidden_room_ids=_rooms_by_kind(activity, RoomPolicyKind.FORBIDDEN),
        time_windows=[ActivityTimeWindowOut.model_validate(w) for w in activity.time_windows],
        subject_name=activity.subject.name if activity.subject else None,
        teacher_names=[t.teacher.full_name for t in activity.teachers],
        participant_count=len(students),
    )


def scheduled_activity_out(item: ScheduledActivity) -> ScheduledActivityOut:
    activity = item.activity
    students = {link.student_id for link in activity.students}
    for link in activity.groups:
        students |= {m.student_id for m in link.group.members}
    return ScheduledActivityOut(
        id=item.id,
        version_id=item.version_id,
        activity_id=item.activity_id,
        occurrence_index=item.occurrence_index,
        start_minute=item.start_minute,
        duration_minutes=item.duration_minutes,
        day_ordinal=item.day_ordinal,
        room_id=item.room_id,
        lock_time=item.lock_time,
        lock_room=item.lock_room,
        activity_name=activity.name,
        subject_name=activity.subject.name if activity.subject else None,
        subject_color=activity.subject.color if activity.subject else None,
        room_name=item.room.name if item.room else None,
        building=item.room.building if item.room else None,
        teacher_ids=sorted(t.teacher_id for t in activity.teachers),
        teacher_names=[t.teacher.full_name for t in activity.teachers],
        student_ids=sorted(students),
        group_ids=sorted(g.group_id for g in activity.groups),
        group_names=[g.group.name for g in activity.groups],
        student_count=len(students),
        kind=activity.kind,
    )


def load_schedule_items(db: Session, version_id: int) -> list[ScheduledActivityOut]:
    from sqlalchemy import select
    from sqlalchemy.orm import joinedload

    stmt = (
        select(ScheduledActivity)
        .where(ScheduledActivity.version_id == version_id)
        .options(
            joinedload(ScheduledActivity.room),
            joinedload(ScheduledActivity.activity).joinedload(Activity.subject),
            joinedload(ScheduledActivity.activity).joinedload(Activity.teachers),
            joinedload(ScheduledActivity.activity).joinedload(Activity.students),
            joinedload(ScheduledActivity.activity).joinedload(Activity.groups),
        )
        .order_by(ScheduledActivity.start_minute)
    )
    items = db.execute(stmt).unique().scalars().all()
    return [scheduled_activity_out(i) for i in items]
