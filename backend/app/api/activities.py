"""Activities, activity links and the individual-tuition bulk editor."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import CurrentUser, db_session, require_scheduler, require_viewer
from app.models import (
    Activity,
    ActivityLink,
    ActivityRoomPolicy,
    ActivityRoomRequirement,
    ActivityStudent,
    ActivityStudentGroup,
    ActivityTeacher,
    ActivityTimeWindow,
    Day,
    RoomFeature,
    Student,
    Subject,
    Teacher,
)
from app.models.enums import ActivityKind, RoomPolicyKind, TimeWindowKind
from app.schemas.activity import (
    ActivityCreate,
    ActivityLinkIn,
    ActivityLinkOut,
    ActivityOut,
    ActivityUpdate,
    IndividualLessonBulk,
    IndividualLessonOut,
)
from app.services import audit
from app.services.serializers import activity_out

router = APIRouter()

RELATION_KEYS = {
    "teacher_ids",
    "student_ids",
    "group_ids",
    "required_feature_ids",
    "allowed_room_ids",
    "preferred_room_ids",
    "forbidden_room_ids",
    "time_windows",
}


def _load(db: Session, activity_id: int) -> Activity:
    activity = db.get(Activity, activity_id)
    if activity is None:
        raise HTTPException(404, f"Activity {activity_id} not found")
    return activity


def _apply_relations(db: Session, activity: Activity, data: dict) -> None:
    if "teacher_ids" in data and data["teacher_ids"] is not None:
        db.execute(delete(ActivityTeacher).where(ActivityTeacher.activity_id == activity.id))
        for teacher_id in dict.fromkeys(data["teacher_ids"]):
            db.add(ActivityTeacher(activity_id=activity.id, teacher_id=teacher_id))
    if "student_ids" in data and data["student_ids"] is not None:
        db.execute(delete(ActivityStudent).where(ActivityStudent.activity_id == activity.id))
        for student_id in dict.fromkeys(data["student_ids"]):
            db.add(ActivityStudent(activity_id=activity.id, student_id=student_id))
    if "group_ids" in data and data["group_ids"] is not None:
        db.execute(
            delete(ActivityStudentGroup).where(ActivityStudentGroup.activity_id == activity.id)
        )
        for group_id in dict.fromkeys(data["group_ids"]):
            db.add(ActivityStudentGroup(activity_id=activity.id, group_id=group_id))
    if "required_feature_ids" in data and data["required_feature_ids"] is not None:
        db.execute(
            delete(ActivityRoomRequirement).where(
                ActivityRoomRequirement.activity_id == activity.id
            )
        )
        for feature_id in dict.fromkeys(data["required_feature_ids"]):
            db.add(ActivityRoomRequirement(activity_id=activity.id, feature_id=feature_id))

    policy_map = {
        "allowed_room_ids": RoomPolicyKind.ALLOWED,
        "preferred_room_ids": RoomPolicyKind.PREFERRED,
        "forbidden_room_ids": RoomPolicyKind.FORBIDDEN,
    }
    for key, kind in policy_map.items():
        if key in data and data[key] is not None:
            db.execute(
                delete(ActivityRoomPolicy).where(
                    ActivityRoomPolicy.activity_id == activity.id,
                    ActivityRoomPolicy.kind == kind,
                )
            )
            for room_id in dict.fromkeys(data[key]):
                db.add(
                    ActivityRoomPolicy(activity_id=activity.id, room_id=room_id, kind=kind)
                )
    if "time_windows" in data and data["time_windows"] is not None:
        db.execute(
            delete(ActivityTimeWindow).where(ActivityTimeWindow.activity_id == activity.id)
        )
        for window in data["time_windows"]:
            db.add(ActivityTimeWindow(activity_id=activity.id, **window))
    db.flush()
    db.refresh(activity)


@router.get("/activities", response_model=list[ActivityOut], tags=["activities"])
def list_activities(
    db: Session = Depends(db_session),
    _: CurrentUser = Depends(require_viewer),
    active: bool | None = None,
    kind: ActivityKind | None = None,
    teacher_id: int | None = None,
    subject_id: int | None = None,
) -> list[ActivityOut]:
    stmt = select(Activity).options(
        joinedload(Activity.teachers).joinedload(ActivityTeacher.teacher),
        joinedload(Activity.students),
        joinedload(Activity.groups).joinedload(ActivityStudentGroup.group),
        joinedload(Activity.room_requirements),
        joinedload(Activity.room_policies),
        joinedload(Activity.time_windows),
        joinedload(Activity.subject),
    )
    if active is not None:
        stmt = stmt.where(Activity.active == active)
    if kind is not None:
        stmt = stmt.where(Activity.kind == kind)
    if subject_id is not None:
        stmt = stmt.where(Activity.subject_id == subject_id)
    rows = db.execute(stmt.order_by(Activity.name)).unique().scalars().all()
    if teacher_id is not None:
        rows = [a for a in rows if any(t.teacher_id == teacher_id for t in a.teachers)]
    return [activity_out(a) for a in rows]


@router.post("/activities", response_model=ActivityOut, status_code=201, tags=["activities"])
def create_activity(
    payload: ActivityCreate,
    db: Session = Depends(db_session),
    user: CurrentUser = Depends(require_scheduler),
) -> ActivityOut:
    data = payload.model_dump(mode="python")
    relations = {k: data.pop(k) for k in list(data) if k in RELATION_KEYS}
    relations["time_windows"] = [
        w if isinstance(w, dict) else w.model_dump() for w in relations.get("time_windows") or []
    ]
    activity = Activity(**data)
    db.add(activity)
    db.flush()
    _apply_relations(db, activity, relations)
    audit.record(
        db, entity_type="Activity", entity_id=activity.id, action="CREATE",
        actor=user.actor, new_value={"name": activity.name},
    )
    db.commit()
    return activity_out(activity)


@router.get("/activities/{activity_id}", response_model=ActivityOut, tags=["activities"])
def get_activity(
    activity_id: int,
    db: Session = Depends(db_session),
    _: CurrentUser = Depends(require_viewer),
) -> ActivityOut:
    return activity_out(_load(db, activity_id))


@router.put("/activities/{activity_id}", response_model=ActivityOut, tags=["activities"])
def update_activity(
    activity_id: int,
    payload: ActivityUpdate,
    db: Session = Depends(db_session),
    user: CurrentUser = Depends(require_scheduler),
) -> ActivityOut:
    activity = _load(db, activity_id)
    data = payload.model_dump(exclude_unset=True, mode="python")
    relations = {k: data.pop(k) for k in list(data) if k in RELATION_KEYS}
    if relations.get("time_windows") is not None:
        relations["time_windows"] = [
            w if isinstance(w, dict) else w.model_dump() for w in relations["time_windows"]
        ]
    old = {k: getattr(activity, k) for k in data}
    for key, value in data.items():
        setattr(activity, key, value)
    db.flush()
    _apply_relations(db, activity, relations)
    audit.record(
        db, entity_type="Activity", entity_id=activity.id, action="UPDATE",
        actor=user.actor, old_value=old, new_value=data,
    )
    db.commit()
    return activity_out(activity)


@router.delete("/activities/{activity_id}", status_code=204, tags=["activities"])
def delete_activity(
    activity_id: int,
    db: Session = Depends(db_session),
    user: CurrentUser = Depends(require_scheduler),
) -> None:
    activity = _load(db, activity_id)
    audit.record(
        db, entity_type="Activity", entity_id=activity.id, action="DELETE",
        actor=user.actor, old_value={"name": activity.name},
    )
    db.delete(activity)
    db.commit()


# --------------------------------------------------------------------------
# Links (HC12 / HC13 / HC14)
# --------------------------------------------------------------------------
@router.get("/activity-links", response_model=list[ActivityLinkOut], tags=["activities"])
def list_links(
    db: Session = Depends(db_session), _: CurrentUser = Depends(require_viewer)
) -> list[ActivityLink]:
    return db.execute(select(ActivityLink).order_by(ActivityLink.id)).scalars().all()


@router.post("/activity-links", response_model=ActivityLinkOut, status_code=201, tags=["activities"])
def create_link(
    payload: ActivityLinkIn,
    db: Session = Depends(db_session),
    _: CurrentUser = Depends(require_scheduler),
) -> ActivityLink:
    if payload.activity_a_id == payload.activity_b_id:
        raise HTTPException(400, "An activity cannot be linked to itself")
    link = ActivityLink(**payload.model_dump())
    db.add(link)
    db.commit()
    return link


@router.delete("/activity-links/{link_id}", status_code=204, tags=["activities"])
def delete_link(
    link_id: int,
    db: Session = Depends(db_session),
    _: CurrentUser = Depends(require_scheduler),
) -> None:
    link = db.get(ActivityLink, link_id)
    if link is None:
        raise HTTPException(404, "Link not found")
    db.delete(link)
    db.commit()


# --------------------------------------------------------------------------
# Individual tuition bulk editor (§8)
# --------------------------------------------------------------------------
def _individual_row(db: Session, activity: Activity) -> IndividualLessonOut:
    student_link = activity.students[0] if activity.students else None
    student = db.get(Student, student_link.student_id) if student_link else None
    teacher_link = activity.teachers[0] if activity.teachers else None
    teacher = db.get(Teacher, teacher_link.teacher_id) if teacher_link else None
    allowed_days = sorted(
        {
            w.day_ordinal
            for w in activity.time_windows
            if w.kind == TimeWindowKind.ALLOWED and w.day_ordinal is not None
        }
    )
    return IndividualLessonOut(
        id=activity.id,
        student_id=student.id if student else 0,
        student_name=student.full_name if student else "?",
        class_name=student.class_group.name if student and student.class_group else None,
        subject_id=activity.subject_id,
        subject_name=activity.subject.name if activity.subject else None,
        teacher_id=teacher.id if teacher else None,
        teacher_name=teacher.full_name if teacher else None,
        duration_minutes=activity.duration_minutes,
        occurrences_per_cycle=activity.occurrences_per_cycle,
        allowed_day_ordinals=allowed_days,
        required_feature_ids=sorted(r.feature_id for r in activity.room_requirements),
        name=activity.name,
        active=activity.active,
    )


@router.get(
    "/individual-lessons", response_model=list[IndividualLessonOut], tags=["individual-lessons"]
)
def list_individual_lessons(
    db: Session = Depends(db_session), _: CurrentUser = Depends(require_viewer)
) -> list[IndividualLessonOut]:
    rows = (
        db.execute(
            select(Activity)
            .where(Activity.kind == ActivityKind.INDIVIDUAL)
            .order_by(Activity.name)
        )
        .unique()
        .scalars()
        .all()
    )
    return [_individual_row(db, a) for a in rows]


@router.post(
    "/individual-lessons/bulk",
    response_model=list[IndividualLessonOut],
    tags=["individual-lessons"],
)
def bulk_individual_lessons(
    payload: IndividualLessonBulk,
    db: Session = Depends(db_session),
    user: CurrentUser = Depends(require_scheduler),
) -> list[IndividualLessonOut]:
    """Create/update/delete many one-to-one lessons in a single call.

    An individual lesson is an ordinary :class:`Activity`; this endpoint only
    saves the scheduler from filling the generic form hundreds of times.
    """
    day_ordinals = {d.ordinal: d for d in db.execute(select(Day)).scalars()}
    saved: list[Activity] = []
    for row in payload.rows:
        student = db.get(Student, row.student_id)
        if student is None:
            raise HTTPException(400, f"Student {row.student_id} not found")
        subject = db.get(Subject, row.subject_id) if row.subject_id else None
        activity = db.get(Activity, row.id) if row.id else None
        if activity is None:
            activity = Activity(kind=ActivityKind.INDIVIDUAL, align_to_periods=False)
            db.add(activity)
        activity.kind = ActivityKind.INDIVIDUAL
        activity.name = row.name or (
            f"{subject.name if subject else 'Individuální výuka'} – {student.full_name}"
        )
        activity.subject_id = row.subject_id
        activity.duration_minutes = row.duration_minutes
        activity.occurrences_per_cycle = row.occurrences_per_cycle
        activity.active = row.active
        db.flush()
        windows = [
            {
                "kind": TimeWindowKind.ALLOWED,
                "day_ordinal": ordinal,
                "start_minute": day_ordinals[ordinal].start_minute if ordinal in day_ordinals else None,
                "end_minute": day_ordinals[ordinal].end_minute if ordinal in day_ordinals else None,
            }
            for ordinal in row.allowed_day_ordinals
        ]
        _apply_relations(
            db,
            activity,
            {
                "student_ids": [row.student_id],
                "group_ids": [],
                "teacher_ids": [row.teacher_id] if row.teacher_id else [],
                "required_feature_ids": row.required_feature_ids,
                "time_windows": windows,
            },
        )
        saved.append(activity)

    for activity_id in payload.delete_ids:
        activity = db.get(Activity, activity_id)
        if activity is not None:
            db.delete(activity)

    audit.record(
        db, entity_type="Activity", action="BULK_INDIVIDUAL", actor=user.actor,
        new_value={"saved": len(saved), "deleted": len(payload.delete_ids)},
    )
    db.commit()
    return [_individual_row(db, a) for a in saved]
