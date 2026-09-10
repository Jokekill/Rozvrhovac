"""Schedules, versions and manual editing of scheduled occurrences."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import CurrentUser, db_session, require_scheduler, require_viewer
from app.models import (
    Activity,
    Schedule,
    ScheduledActivity,
    ScheduleVersion,
)
from app.models.calendar import MINUTES_PER_DAY
from app.models.enums import Severity, VersionStatus
from app.schemas.schedule import (
    LockIn,
    MoveCheckIn,
    MoveCheckOut,
    ScheduledActivityOut,
    ScheduledActivityPatch,
    ScheduleIn,
    ScheduleOut,
    ScheduleVersionDetail,
    ScheduleVersionOut,
    VersionCompareItem,
    VersionCompareOut,
    VersionDuplicateIn,
)
from app.services import audit
from app.services.conflicts import check_move, suggest_rooms
from app.services.serializers import load_schedule_items, scheduled_activity_out

router = APIRouter()


def _version_out(db: Session, version: ScheduleVersion) -> ScheduleVersionOut:
    count = db.execute(
        select(func.count(ScheduledActivity.id)).where(
            ScheduledActivity.version_id == version.id
        )
    ).scalar_one()
    return ScheduleVersionOut(
        id=version.id,
        schedule_id=version.schedule_id,
        name=version.name,
        status=version.status,
        created_at=version.created_at,
        parent_version_id=version.parent_version_id,
        solver_run_id=version.solver_run_id,
        total_penalty=version.total_penalty,
        penalties=version.penalties,
        note=version.note,
        item_count=count,
    )


def _get_version(db: Session, version_id: int) -> ScheduleVersion:
    version = db.get(ScheduleVersion, version_id)
    if version is None:
        raise HTTPException(404, f"Schedule version {version_id} not found")
    return version


def _get_item(db: Session, item_id: int) -> ScheduledActivity:
    item = db.execute(
        select(ScheduledActivity)
        .where(ScheduledActivity.id == item_id)
        .options(
            joinedload(ScheduledActivity.activity).joinedload(Activity.teachers),
            joinedload(ScheduledActivity.activity).joinedload(Activity.students),
            joinedload(ScheduledActivity.activity).joinedload(Activity.groups),
            joinedload(ScheduledActivity.activity).joinedload(Activity.room_policies),
            joinedload(ScheduledActivity.activity).joinedload(Activity.room_requirements),
            joinedload(ScheduledActivity.room),
        )
    ).unique().scalars().first()
    if item is None:
        raise HTTPException(404, f"Scheduled activity {item_id} not found")
    return item


# --------------------------------------------------------------------------
# Schedules
# --------------------------------------------------------------------------
@router.get("/schedules", response_model=list[ScheduleOut], tags=["schedules"])
def list_schedules(
    db: Session = Depends(db_session), _: CurrentUser = Depends(require_viewer)
) -> list[ScheduleOut]:
    result = []
    for schedule in db.execute(select(Schedule).order_by(Schedule.id)).scalars():
        result.append(
            ScheduleOut(
                id=schedule.id,
                name=schedule.name,
                description=schedule.description,
                created_at=schedule.created_at,
                version_count=len(schedule.versions),
            )
        )
    return result


@router.post("/schedules", response_model=ScheduleOut, status_code=201, tags=["schedules"])
def create_schedule(
    payload: ScheduleIn,
    db: Session = Depends(db_session),
    _: CurrentUser = Depends(require_scheduler),
) -> ScheduleOut:
    schedule = Schedule(**payload.model_dump())
    db.add(schedule)
    db.commit()
    return ScheduleOut(
        id=schedule.id,
        name=schedule.name,
        description=schedule.description,
        created_at=schedule.created_at,
        version_count=0,
    )


@router.get("/schedules/{schedule_id}", response_model=ScheduleOut, tags=["schedules"])
def get_schedule(
    schedule_id: int,
    db: Session = Depends(db_session),
    _: CurrentUser = Depends(require_viewer),
) -> ScheduleOut:
    schedule = db.get(Schedule, schedule_id)
    if schedule is None:
        raise HTTPException(404, "Schedule not found")
    return ScheduleOut(
        id=schedule.id,
        name=schedule.name,
        description=schedule.description,
        created_at=schedule.created_at,
        version_count=len(schedule.versions),
    )


@router.delete("/schedules/{schedule_id}", status_code=204, tags=["schedules"])
def delete_schedule(
    schedule_id: int,
    db: Session = Depends(db_session),
    _: CurrentUser = Depends(require_scheduler),
) -> None:
    schedule = db.get(Schedule, schedule_id)
    if schedule is None:
        raise HTTPException(404, "Schedule not found")
    db.delete(schedule)
    db.commit()


@router.get(
    "/schedules/{schedule_id}/versions",
    response_model=list[ScheduleVersionOut],
    tags=["schedules"],
)
def list_versions(
    schedule_id: int,
    db: Session = Depends(db_session),
    _: CurrentUser = Depends(require_viewer),
) -> list[ScheduleVersionOut]:
    versions = db.execute(
        select(ScheduleVersion)
        .where(ScheduleVersion.schedule_id == schedule_id)
        .order_by(ScheduleVersion.id.desc())
    ).scalars()
    return [_version_out(db, v) for v in versions]


@router.post(
    "/schedules/{schedule_id}/versions",
    response_model=ScheduleVersionOut,
    status_code=201,
    tags=["schedules"],
)
def create_empty_version(
    schedule_id: int,
    payload: VersionDuplicateIn,
    db: Session = Depends(db_session),
    _: CurrentUser = Depends(require_scheduler),
) -> ScheduleVersionOut:
    if db.get(Schedule, schedule_id) is None:
        raise HTTPException(404, "Schedule not found")
    version = ScheduleVersion(
        schedule_id=schedule_id, name=payload.name or "Draft", status=VersionStatus.DRAFT
    )
    db.add(version)
    db.commit()
    return _version_out(db, version)


# --------------------------------------------------------------------------
# Versions
# --------------------------------------------------------------------------
@router.get("/versions", response_model=list[ScheduleVersionOut], tags=["versions"])
def list_all_versions(
    db: Session = Depends(db_session), _: CurrentUser = Depends(require_viewer)
) -> list[ScheduleVersionOut]:
    versions = db.execute(select(ScheduleVersion).order_by(ScheduleVersion.id.desc())).scalars()
    return [_version_out(db, v) for v in versions]


@router.get("/versions/{version_id}", response_model=ScheduleVersionDetail, tags=["versions"])
def get_version(
    version_id: int,
    db: Session = Depends(db_session),
    _: CurrentUser = Depends(require_viewer),
) -> ScheduleVersionDetail:
    version = _get_version(db, version_id)
    base = _version_out(db, version)
    return ScheduleVersionDetail(**base.model_dump(), items=load_schedule_items(db, version_id))


@router.delete("/versions/{version_id}", status_code=204, tags=["versions"])
def delete_version(
    version_id: int,
    db: Session = Depends(db_session),
    _: CurrentUser = Depends(require_scheduler),
) -> None:
    db.delete(_get_version(db, version_id))
    db.commit()


@router.post(
    "/versions/{version_id}/duplicate",
    response_model=ScheduleVersionOut,
    status_code=201,
    tags=["versions"],
)
def duplicate_version(
    version_id: int,
    payload: VersionDuplicateIn,
    db: Session = Depends(db_session),
    user: CurrentUser = Depends(require_scheduler),
) -> ScheduleVersionOut:
    source = _get_version(db, version_id)
    copy = ScheduleVersion(
        schedule_id=source.schedule_id,
        name=payload.name or f"{source.name} (kopie)",
        status=VersionStatus.DRAFT,
        parent_version_id=source.id,
        total_penalty=source.total_penalty,
        penalties=source.penalties,
        note=source.note,
    )
    db.add(copy)
    db.flush()
    for item in source.items:
        db.add(
            ScheduledActivity(
                version_id=copy.id,
                activity_id=item.activity_id,
                occurrence_index=item.occurrence_index,
                start_minute=item.start_minute,
                duration_minutes=item.duration_minutes,
                day_ordinal=item.day_ordinal,
                room_id=item.room_id,
                lock_time=item.lock_time,
                lock_room=item.lock_room,
            )
        )
    audit.record(
        db, entity_type="ScheduleVersion", entity_id=copy.id, action="DUPLICATE",
        actor=user.actor, old_value={"source_version_id": source.id},
    )
    db.commit()
    return _version_out(db, copy)


@router.post(
    "/versions/{version_id}/publish", response_model=ScheduleVersionOut, tags=["versions"]
)
def publish_version(
    version_id: int,
    db: Session = Depends(db_session),
    user: CurrentUser = Depends(require_scheduler),
) -> ScheduleVersionOut:
    version = _get_version(db, version_id)
    previously_published = db.execute(
        select(ScheduleVersion).where(
            ScheduleVersion.schedule_id == version.schedule_id,
            ScheduleVersion.status == VersionStatus.PUBLISHED,
        )
    ).scalars().all()
    for other in previously_published:
        other.status = VersionStatus.ARCHIVED
    version.status = VersionStatus.PUBLISHED
    audit.record(
        db, entity_type="ScheduleVersion", entity_id=version.id, action="PUBLISH",
        actor=user.actor, new_value={"name": version.name},
    )
    db.commit()
    return _version_out(db, version)


@router.get(
    "/versions/{version_id}/compare", response_model=VersionCompareOut, tags=["versions"]
)
def compare_versions(
    version_id: int,
    other: int = Query(..., description="Version to compare against"),
    db: Session = Depends(db_session),
    _: CurrentUser = Depends(require_viewer),
) -> VersionCompareOut:
    left = _get_version(db, version_id)
    right = _get_version(db, other)
    left_items = {(i.activity_id, i.occurrence_index): i for i in left.items}
    right_items = {(i.activity_id, i.occurrence_index): i for i in right.items}
    items: list[VersionCompareItem] = []
    changed = unchanged = 0
    for key in sorted(set(left_items) | set(right_items)):
        left_item = left_items.get(key)
        right_item = right_items.get(key)
        activity = (left_item or right_item).activity
        if left_item is None:
            change = "ADDED"
        elif right_item is None:
            change = "REMOVED"
        elif left_item.start_minute != right_item.start_minute:
            change = "MOVED"
        elif left_item.room_id != right_item.room_id:
            change = "ROOM_CHANGED"
        else:
            change = "UNCHANGED"
        if change == "UNCHANGED":
            unchanged += 1
        else:
            changed += 1
        items.append(
            VersionCompareItem(
                activity_id=key[0],
                activity_name=activity.name,
                occurrence_index=key[1],
                change=change,
                left_start=left_item.start_minute if left_item else None,
                right_start=right_item.start_minute if right_item else None,
                left_room=left_item.room.name if left_item and left_item.room else None,
                right_room=right_item.room.name if right_item and right_item.room else None,
            )
        )
    return VersionCompareOut(
        left_version_id=left.id,
        right_version_id=right.id,
        changed=changed,
        unchanged=unchanged,
        items=items,
    )


# --------------------------------------------------------------------------
# Manual editing
# --------------------------------------------------------------------------
@router.patch(
    "/scheduled-activities/{item_id}",
    response_model=ScheduledActivityOut,
    tags=["scheduled-activities"],
)
def patch_scheduled_activity(
    item_id: int,
    payload: ScheduledActivityPatch,
    force: bool = Query(False, description="Apply even when the move creates conflicts"),
    db: Session = Depends(db_session),
    user: CurrentUser = Depends(require_scheduler),
) -> ScheduledActivityOut:
    item = _get_item(db, item_id)
    data = payload.model_dump(exclude_unset=True)
    new_start = data.get("start_minute", item.start_minute)
    new_room = data.get("room_id", item.room_id)

    if "start_minute" in data or "room_id" in data:
        result = check_move(db, item, new_start, new_room)
        blocking = [c for c in result.conflicts if c.severity == Severity.ERROR]
        if blocking and not force:
            raise HTTPException(
                409,
                detail={
                    "message": "Přesun by porušil hard constraint.",
                    "conflicts": [c.model_dump(mode="json") for c in blocking],
                },
            )

    old = {
        "start_minute": item.start_minute,
        "room_id": item.room_id,
        "lock_time": item.lock_time,
        "lock_room": item.lock_room,
    }
    item.start_minute = new_start
    item.room_id = new_room
    item.day_ordinal = new_start // MINUTES_PER_DAY
    if "lock_time" in data:
        item.lock_time = data["lock_time"]
    if "lock_room" in data:
        item.lock_room = data["lock_room"]
    audit.record(
        db, entity_type="ScheduledActivity", entity_id=item.id, action="MANUAL_MOVE",
        actor=user.actor, old_value=old,
        new_value={
            "start_minute": item.start_minute,
            "room_id": item.room_id,
            "lock_time": item.lock_time,
            "lock_room": item.lock_room,
        },
    )
    db.commit()
    return scheduled_activity_out(_get_item(db, item_id))


@router.post(
    "/scheduled-activities/{item_id}/validate-move",
    response_model=MoveCheckOut,
    tags=["scheduled-activities"],
)
def validate_move(
    item_id: int,
    payload: MoveCheckIn,
    db: Session = Depends(db_session),
    _: CurrentUser = Depends(require_viewer),
) -> MoveCheckOut:
    item = _get_item(db, item_id)
    return check_move(db, item, payload.start_minute, payload.room_id)


@router.get(
    "/scheduled-activities/{item_id}/room-options",
    response_model=MoveCheckOut,
    tags=["scheduled-activities"],
)
def room_options(
    item_id: int,
    start_minute: int | None = None,
    db: Session = Depends(db_session),
    _: CurrentUser = Depends(require_viewer),
) -> MoveCheckOut:
    item = _get_item(db, item_id)
    return MoveCheckOut(
        ok=True,
        conflicts=[],
        room_suggestions=suggest_rooms(db, item, start_minute or item.start_minute),
    )


@router.post(
    "/scheduled-activities/{item_id}/lock",
    response_model=ScheduledActivityOut,
    tags=["scheduled-activities"],
)
def lock_item(
    item_id: int,
    payload: LockIn,
    db: Session = Depends(db_session),
    user: CurrentUser = Depends(require_scheduler),
) -> ScheduledActivityOut:
    item = _get_item(db, item_id)
    item.lock_time = payload.lock_time
    item.lock_room = payload.lock_room
    audit.record(
        db, entity_type="ScheduledActivity", entity_id=item.id, action="LOCK",
        actor=user.actor,
        new_value={"lock_time": item.lock_time, "lock_room": item.lock_room},
    )
    db.commit()
    return scheduled_activity_out(_get_item(db, item_id))


@router.post(
    "/scheduled-activities/{item_id}/unlock",
    response_model=ScheduledActivityOut,
    tags=["scheduled-activities"],
)
def unlock_item(
    item_id: int,
    db: Session = Depends(db_session),
    user: CurrentUser = Depends(require_scheduler),
) -> ScheduledActivityOut:
    item = _get_item(db, item_id)
    item.lock_time = False
    item.lock_room = False
    audit.record(
        db, entity_type="ScheduledActivity", entity_id=item.id, action="UNLOCK",
        actor=user.actor,
    )
    db.commit()
    return scheduled_activity_out(_get_item(db, item_id))
