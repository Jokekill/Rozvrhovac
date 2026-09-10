"""CRUD for the base registers: students, teachers, rooms, groups, subjects,
room features, availability and the planning calendar."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, db_session, require_scheduler, require_viewer
from app.models import (
    AvailabilityWindow,
    CycleConfig,
    Day,
    Period,
    Room,
    RoomFeature,
    RoomFeatureAssignment,
    Student,
    StudentGroup,
    StudentGroupMember,
    Subject,
    Teacher,
)
from app.models.enums import OwnerType
from app.schemas.core import (
    AvailabilityIn,
    AvailabilityOut,
    AvailabilityUpdate,
    CycleConfigOut,
    CycleConfigUpdate,
    DayIn,
    DayOut,
    GroupCreate,
    GroupOut,
    GroupUpdate,
    PeriodIn,
    PeriodOut,
    RoomCreate,
    RoomFeatureIn,
    RoomFeatureOut,
    RoomOut,
    RoomUpdate,
    StudentCreate,
    StudentOut,
    StudentUpdate,
    SubjectIn,
    SubjectOut,
    SubjectUpdate,
    TeacherCreate,
    TeacherOut,
    TeacherUpdate,
)
from app.services import audit
from app.services.bootstrap import ensure_cycle
from app.services.serializers import group_out, room_out, student_out

router = APIRouter()


def _get_or_404(db: Session, model, obj_id: int):
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(404, f"{model.__name__} {obj_id} not found")
    return obj


# --------------------------------------------------------------------------
# Students
# --------------------------------------------------------------------------
@router.get("/students", response_model=list[StudentOut], tags=["students"])
def list_students(
    db: Session = Depends(db_session),
    _: CurrentUser = Depends(require_viewer),
    active: bool | None = None,
    class_group_id: int | None = None,
    search: str | None = None,
) -> list[StudentOut]:
    stmt = select(Student)
    if active is not None:
        stmt = stmt.where(Student.active == active)
    if class_group_id is not None:
        stmt = stmt.where(Student.class_group_id == class_group_id)
    rows = db.execute(stmt.order_by(Student.last_name, Student.first_name)).scalars().all()
    if search:
        needle = search.lower()
        rows = [s for s in rows if needle in s.full_name.lower()]
    return [student_out(s) for s in rows]


@router.post("/students", response_model=StudentOut, status_code=201, tags=["students"])
def create_student(
    payload: StudentCreate,
    db: Session = Depends(db_session),
    user: CurrentUser = Depends(require_scheduler),
) -> StudentOut:
    student = Student(**payload.model_dump())
    db.add(student)
    db.flush()
    audit.record(
        db, entity_type="Student", entity_id=student.id, action="CREATE",
        actor=user.actor, new_value=payload.model_dump(),
    )
    db.commit()
    return student_out(student)


@router.get("/students/{student_id}", response_model=StudentOut, tags=["students"])
def get_student(
    student_id: int,
    db: Session = Depends(db_session),
    _: CurrentUser = Depends(require_viewer),
) -> StudentOut:
    return student_out(_get_or_404(db, Student, student_id))


@router.put("/students/{student_id}", response_model=StudentOut, tags=["students"])
def update_student(
    student_id: int,
    payload: StudentUpdate,
    db: Session = Depends(db_session),
    user: CurrentUser = Depends(require_scheduler),
) -> StudentOut:
    student = _get_or_404(db, Student, student_id)
    changes = payload.model_dump(exclude_unset=True)
    old = {k: getattr(student, k) for k in changes}
    for key, value in changes.items():
        setattr(student, key, value)
    audit.record(
        db, entity_type="Student", entity_id=student.id, action="UPDATE",
        actor=user.actor, old_value=old, new_value=changes,
    )
    db.commit()
    return student_out(student)


@router.delete("/students/{student_id}", status_code=204, tags=["students"])
def delete_student(
    student_id: int,
    db: Session = Depends(db_session),
    user: CurrentUser = Depends(require_scheduler),
) -> None:
    student = _get_or_404(db, Student, student_id)
    audit.record(
        db, entity_type="Student", entity_id=student.id, action="DELETE",
        actor=user.actor, old_value={"full_name": student.full_name},
    )
    db.delete(student)
    db.commit()


# --------------------------------------------------------------------------
# Teachers
# --------------------------------------------------------------------------
@router.get("/teachers", response_model=list[TeacherOut], tags=["teachers"])
def list_teachers(
    db: Session = Depends(db_session),
    _: CurrentUser = Depends(require_viewer),
    active: bool | None = None,
) -> list[Teacher]:
    stmt = select(Teacher)
    if active is not None:
        stmt = stmt.where(Teacher.active == active)
    rows = db.execute(stmt.order_by(Teacher.last_name, Teacher.first_name)).scalars().all()
    return [
        TeacherOut.model_validate({**t.__dict__, "full_name": t.full_name}) for t in rows
    ]


@router.post("/teachers", response_model=TeacherOut, status_code=201, tags=["teachers"])
def create_teacher(
    payload: TeacherCreate,
    db: Session = Depends(db_session),
    user: CurrentUser = Depends(require_scheduler),
) -> TeacherOut:
    teacher = Teacher(**payload.model_dump())
    db.add(teacher)
    db.flush()
    audit.record(
        db, entity_type="Teacher", entity_id=teacher.id, action="CREATE",
        actor=user.actor, new_value=payload.model_dump(),
    )
    db.commit()
    return TeacherOut.model_validate({**teacher.__dict__, "full_name": teacher.full_name})


@router.get("/teachers/{teacher_id}", response_model=TeacherOut, tags=["teachers"])
def get_teacher(
    teacher_id: int,
    db: Session = Depends(db_session),
    _: CurrentUser = Depends(require_viewer),
) -> TeacherOut:
    teacher = _get_or_404(db, Teacher, teacher_id)
    return TeacherOut.model_validate({**teacher.__dict__, "full_name": teacher.full_name})


@router.put("/teachers/{teacher_id}", response_model=TeacherOut, tags=["teachers"])
def update_teacher(
    teacher_id: int,
    payload: TeacherUpdate,
    db: Session = Depends(db_session),
    user: CurrentUser = Depends(require_scheduler),
) -> TeacherOut:
    teacher = _get_or_404(db, Teacher, teacher_id)
    changes = payload.model_dump(exclude_unset=True)
    old = {k: getattr(teacher, k) for k in changes}
    for key, value in changes.items():
        setattr(teacher, key, value)
    audit.record(
        db, entity_type="Teacher", entity_id=teacher.id, action="UPDATE",
        actor=user.actor, old_value=old, new_value=changes,
    )
    db.commit()
    return TeacherOut.model_validate({**teacher.__dict__, "full_name": teacher.full_name})


@router.delete("/teachers/{teacher_id}", status_code=204, tags=["teachers"])
def delete_teacher(
    teacher_id: int,
    db: Session = Depends(db_session),
    user: CurrentUser = Depends(require_scheduler),
) -> None:
    teacher = _get_or_404(db, Teacher, teacher_id)
    audit.record(
        db, entity_type="Teacher", entity_id=teacher.id, action="DELETE", actor=user.actor
    )
    db.delete(teacher)
    db.commit()


# --------------------------------------------------------------------------
# Room features and rooms
# --------------------------------------------------------------------------
@router.get("/room-features", response_model=list[RoomFeatureOut], tags=["rooms"])
def list_room_features(
    db: Session = Depends(db_session), _: CurrentUser = Depends(require_viewer)
) -> list[RoomFeature]:
    return db.execute(select(RoomFeature).order_by(RoomFeature.name)).scalars().all()


@router.post("/room-features", response_model=RoomFeatureOut, status_code=201, tags=["rooms"])
def create_room_feature(
    payload: RoomFeatureIn,
    db: Session = Depends(db_session),
    _: CurrentUser = Depends(require_scheduler),
) -> RoomFeature:
    feature = RoomFeature(**payload.model_dump())
    db.add(feature)
    db.commit()
    return feature


@router.delete("/room-features/{feature_id}", status_code=204, tags=["rooms"])
def delete_room_feature(
    feature_id: int,
    db: Session = Depends(db_session),
    _: CurrentUser = Depends(require_scheduler),
) -> None:
    db.delete(_get_or_404(db, RoomFeature, feature_id))
    db.commit()


def _apply_room_features(db: Session, room: Room, feature_ids: list[int]) -> None:
    db.execute(delete(RoomFeatureAssignment).where(RoomFeatureAssignment.room_id == room.id))
    for feature_id in dict.fromkeys(feature_ids):
        db.add(RoomFeatureAssignment(room_id=room.id, feature_id=feature_id))
    db.flush()
    db.refresh(room)


@router.get("/rooms", response_model=list[RoomOut], tags=["rooms"])
def list_rooms(
    db: Session = Depends(db_session),
    _: CurrentUser = Depends(require_viewer),
    active: bool | None = None,
) -> list[RoomOut]:
    stmt = select(Room)
    if active is not None:
        stmt = stmt.where(Room.active == active)
    rooms = db.execute(stmt.order_by(Room.name)).scalars().all()
    return [room_out(r) for r in rooms]


@router.post("/rooms", response_model=RoomOut, status_code=201, tags=["rooms"])
def create_room(
    payload: RoomCreate,
    db: Session = Depends(db_session),
    user: CurrentUser = Depends(require_scheduler),
) -> RoomOut:
    data = payload.model_dump()
    feature_ids = data.pop("feature_ids")
    room = Room(**data)
    db.add(room)
    db.flush()
    _apply_room_features(db, room, feature_ids)
    audit.record(
        db, entity_type="Room", entity_id=room.id, action="CREATE",
        actor=user.actor, new_value=payload.model_dump(),
    )
    db.commit()
    return room_out(room)


@router.get("/rooms/{room_id}", response_model=RoomOut, tags=["rooms"])
def get_room(
    room_id: int, db: Session = Depends(db_session), _: CurrentUser = Depends(require_viewer)
) -> RoomOut:
    return room_out(_get_or_404(db, Room, room_id))


@router.put("/rooms/{room_id}", response_model=RoomOut, tags=["rooms"])
def update_room(
    room_id: int,
    payload: RoomUpdate,
    db: Session = Depends(db_session),
    user: CurrentUser = Depends(require_scheduler),
) -> RoomOut:
    room = _get_or_404(db, Room, room_id)
    changes = payload.model_dump(exclude_unset=True)
    feature_ids = changes.pop("feature_ids", None)
    old = {k: getattr(room, k) for k in changes}
    for key, value in changes.items():
        setattr(room, key, value)
    db.flush()
    if feature_ids is not None:
        _apply_room_features(db, room, feature_ids)
    audit.record(
        db, entity_type="Room", entity_id=room.id, action="UPDATE",
        actor=user.actor, old_value=old, new_value=changes,
    )
    db.commit()
    return room_out(room)


@router.delete("/rooms/{room_id}", status_code=204, tags=["rooms"])
def delete_room(
    room_id: int,
    db: Session = Depends(db_session),
    user: CurrentUser = Depends(require_scheduler),
) -> None:
    room = _get_or_404(db, Room, room_id)
    audit.record(db, entity_type="Room", entity_id=room.id, action="DELETE", actor=user.actor)
    db.delete(room)
    db.commit()


# --------------------------------------------------------------------------
# Subjects
# --------------------------------------------------------------------------
@router.get("/subjects", response_model=list[SubjectOut], tags=["subjects"])
def list_subjects(
    db: Session = Depends(db_session), _: CurrentUser = Depends(require_viewer)
) -> list[Subject]:
    return db.execute(select(Subject).order_by(Subject.name)).scalars().all()


@router.post("/subjects", response_model=SubjectOut, status_code=201, tags=["subjects"])
def create_subject(
    payload: SubjectIn,
    db: Session = Depends(db_session),
    _: CurrentUser = Depends(require_scheduler),
) -> Subject:
    subject = Subject(**payload.model_dump())
    db.add(subject)
    db.commit()
    return subject


@router.put("/subjects/{subject_id}", response_model=SubjectOut, tags=["subjects"])
def update_subject(
    subject_id: int,
    payload: SubjectUpdate,
    db: Session = Depends(db_session),
    _: CurrentUser = Depends(require_scheduler),
) -> Subject:
    subject = _get_or_404(db, Subject, subject_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(subject, key, value)
    db.commit()
    return subject


@router.delete("/subjects/{subject_id}", status_code=204, tags=["subjects"])
def delete_subject(
    subject_id: int,
    db: Session = Depends(db_session),
    _: CurrentUser = Depends(require_scheduler),
) -> None:
    db.delete(_get_or_404(db, Subject, subject_id))
    db.commit()


# --------------------------------------------------------------------------
# Student groups
# --------------------------------------------------------------------------
def _apply_group_members(db: Session, group: StudentGroup, student_ids: list[int]) -> None:
    db.execute(delete(StudentGroupMember).where(StudentGroupMember.group_id == group.id))
    for student_id in dict.fromkeys(student_ids):
        db.add(StudentGroupMember(group_id=group.id, student_id=student_id))
    db.flush()
    db.refresh(group)


@router.get("/groups", response_model=list[GroupOut], tags=["groups"])
def list_groups(
    db: Session = Depends(db_session),
    _: CurrentUser = Depends(require_viewer),
    type: str | None = None,
) -> list[GroupOut]:
    stmt = select(StudentGroup)
    if type:
        stmt = stmt.where(StudentGroup.type == type)
    return [group_out(g) for g in db.execute(stmt.order_by(StudentGroup.name)).scalars()]


@router.post("/groups", response_model=GroupOut, status_code=201, tags=["groups"])
def create_group(
    payload: GroupCreate,
    db: Session = Depends(db_session),
    user: CurrentUser = Depends(require_scheduler),
) -> GroupOut:
    data = payload.model_dump()
    student_ids = data.pop("student_ids")
    group = StudentGroup(**data)
    db.add(group)
    db.flush()
    _apply_group_members(db, group, student_ids)
    audit.record(
        db, entity_type="StudentGroup", entity_id=group.id, action="CREATE",
        actor=user.actor, new_value={"name": group.name, "members": len(student_ids)},
    )
    db.commit()
    return group_out(group)


@router.get("/groups/{group_id}", response_model=GroupOut, tags=["groups"])
def get_group(
    group_id: int, db: Session = Depends(db_session), _: CurrentUser = Depends(require_viewer)
) -> GroupOut:
    return group_out(_get_or_404(db, StudentGroup, group_id))


@router.put("/groups/{group_id}", response_model=GroupOut, tags=["groups"])
def update_group(
    group_id: int,
    payload: GroupUpdate,
    db: Session = Depends(db_session),
    user: CurrentUser = Depends(require_scheduler),
) -> GroupOut:
    group = _get_or_404(db, StudentGroup, group_id)
    changes = payload.model_dump(exclude_unset=True)
    student_ids = changes.pop("student_ids", None)
    for key, value in changes.items():
        setattr(group, key, value)
    db.flush()
    if student_ids is not None:
        _apply_group_members(db, group, student_ids)
    audit.record(
        db, entity_type="StudentGroup", entity_id=group.id, action="UPDATE",
        actor=user.actor, new_value=changes,
    )
    db.commit()
    return group_out(group)


@router.delete("/groups/{group_id}", status_code=204, tags=["groups"])
def delete_group(
    group_id: int,
    db: Session = Depends(db_session),
    user: CurrentUser = Depends(require_scheduler),
) -> None:
    group = _get_or_404(db, StudentGroup, group_id)
    audit.record(
        db, entity_type="StudentGroup", entity_id=group.id, action="DELETE", actor=user.actor
    )
    db.delete(group)
    db.commit()


# --------------------------------------------------------------------------
# Availability
# --------------------------------------------------------------------------
@router.get("/availability", response_model=list[AvailabilityOut], tags=["availability"])
def list_availability(
    db: Session = Depends(db_session),
    _: CurrentUser = Depends(require_viewer),
    owner_type: OwnerType | None = None,
    owner_id: int | None = None,
) -> list[AvailabilityWindow]:
    stmt = select(AvailabilityWindow)
    if owner_type:
        stmt = stmt.where(AvailabilityWindow.owner_type == owner_type)
    if owner_id is not None:
        stmt = stmt.where(AvailabilityWindow.owner_id == owner_id)
    return (
        db.execute(stmt.order_by(AvailabilityWindow.day_ordinal, AvailabilityWindow.start_minute))
        .scalars()
        .all()
    )


@router.post("/availability", response_model=AvailabilityOut, status_code=201, tags=["availability"])
def create_availability(
    payload: AvailabilityIn,
    db: Session = Depends(db_session),
    user: CurrentUser = Depends(require_scheduler),
) -> AvailabilityWindow:
    window = AvailabilityWindow(**payload.model_dump())
    db.add(window)
    db.flush()
    audit.record(
        db, entity_type="AvailabilityWindow", entity_id=window.id, action="CREATE",
        actor=user.actor, new_value=payload.model_dump(mode="json"),
    )
    db.commit()
    return window


@router.put("/availability/{window_id}", response_model=AvailabilityOut, tags=["availability"])
def update_availability(
    window_id: int,
    payload: AvailabilityUpdate,
    db: Session = Depends(db_session),
    user: CurrentUser = Depends(require_scheduler),
) -> AvailabilityWindow:
    window = _get_or_404(db, AvailabilityWindow, window_id)
    changes = payload.model_dump(exclude_unset=True, mode="json")
    old = {k: getattr(window, k) for k in changes}
    for key, value in changes.items():
        setattr(window, key, value)
    audit.record(
        db, entity_type="AvailabilityWindow", entity_id=window.id, action="UPDATE",
        actor=user.actor, old_value=old, new_value=changes,
    )
    db.commit()
    return window


@router.delete("/availability/{window_id}", status_code=204, tags=["availability"])
def delete_availability(
    window_id: int,
    db: Session = Depends(db_session),
    user: CurrentUser = Depends(require_scheduler),
) -> None:
    window = _get_or_404(db, AvailabilityWindow, window_id)
    audit.record(
        db, entity_type="AvailabilityWindow", entity_id=window.id, action="DELETE",
        actor=user.actor,
        old_value={"owner_type": window.owner_type, "owner_id": window.owner_id},
    )
    db.delete(window)
    db.commit()


# --------------------------------------------------------------------------
# Calendar
# --------------------------------------------------------------------------
@router.get("/cycle", response_model=CycleConfigOut, tags=["cycle"])
def get_cycle(
    db: Session = Depends(db_session), _: CurrentUser = Depends(require_viewer)
) -> CycleConfig:
    config = db.get(CycleConfig, 1)
    if config is None:
        config = ensure_cycle(db)
        db.commit()
    return config


@router.put("/cycle", response_model=CycleConfigOut, tags=["cycle"])
def update_cycle(
    payload: CycleConfigUpdate,
    db: Session = Depends(db_session),
    _: CurrentUser = Depends(require_scheduler),
) -> CycleConfig:
    config = db.get(CycleConfig, 1) or ensure_cycle(db)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(config, key, value)
    db.commit()
    return config


@router.get("/cycle/days", response_model=list[DayOut], tags=["cycle"])
def list_days(
    db: Session = Depends(db_session), _: CurrentUser = Depends(require_viewer)
) -> list[Day]:
    return db.execute(select(Day).order_by(Day.ordinal)).scalars().all()


@router.put("/cycle/days", response_model=list[DayOut], tags=["cycle"])
def replace_days(
    payload: list[DayIn],
    db: Session = Depends(db_session),
    _: CurrentUser = Depends(require_scheduler),
) -> list[Day]:
    db.execute(delete(Day))
    for day in payload:
        db.add(Day(**day.model_dump()))
    db.commit()
    return db.execute(select(Day).order_by(Day.ordinal)).scalars().all()


@router.get("/cycle/periods", response_model=list[PeriodOut], tags=["cycle"])
def list_periods(
    db: Session = Depends(db_session), _: CurrentUser = Depends(require_viewer)
) -> list[Period]:
    return db.execute(select(Period).order_by(Period.index)).scalars().all()


@router.put("/cycle/periods", response_model=list[PeriodOut], tags=["cycle"])
def replace_periods(
    payload: list[PeriodIn],
    db: Session = Depends(db_session),
    _: CurrentUser = Depends(require_scheduler),
) -> list[Period]:
    db.execute(delete(Period))
    for period in payload:
        db.add(Period(**period.model_dump()))
    db.commit()
    return db.execute(select(Period).order_by(Period.index)).scalars().all()
