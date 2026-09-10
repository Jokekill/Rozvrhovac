"""Timetable views (§19).

The same stored data, filtered for one student, class, group, teacher, room or
the whole school. A student's view is their *real* personal timetable: class
lessons, the cross-class drama group and the individual piano lesson together.
"""
from __future__ import annotations

from enum import StrEnum

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, db_session, require_viewer
from app.models import Room, ScheduleVersion, Student, StudentGroup, Teacher
from app.schemas.schedule import ScheduledActivityOut
from app.services.serializers import load_schedule_items

router = APIRouter()


class ViewScope(StrEnum):
    SCHOOL = "school"
    STUDENT = "student"
    CLASS = "class"
    GROUP = "group"
    TEACHER = "teacher"
    ROOM = "room"


class TimetableView(BaseModel):
    version_id: int
    scope: ViewScope
    subject_id: int | None = None
    title: str
    items: list[ScheduledActivityOut]


def filter_items(
    items: list[ScheduledActivityOut], scope: ViewScope, entity_id: int | None
) -> list[ScheduledActivityOut]:
    if scope == ViewScope.SCHOOL or entity_id is None:
        return items
    if scope == ViewScope.STUDENT:
        return [i for i in items if entity_id in i.student_ids]
    if scope in (ViewScope.CLASS, ViewScope.GROUP):
        return [i for i in items if entity_id in i.group_ids]
    if scope == ViewScope.TEACHER:
        return [i for i in items if entity_id in i.teacher_ids]
    if scope == ViewScope.ROOM:
        return [i for i in items if i.room_id == entity_id]
    return items


@router.get("/versions/{version_id}/view", response_model=TimetableView, tags=["views"])
def timetable_view(
    version_id: int,
    scope: ViewScope = ViewScope.SCHOOL,
    entity_id: int | None = Query(None, description="Student / class / teacher / room id"),
    db: Session = Depends(db_session),
    _: CurrentUser = Depends(require_viewer),
) -> TimetableView:
    version = db.get(ScheduleVersion, version_id)
    if version is None:
        raise HTTPException(404, "Schedule version not found")
    items = load_schedule_items(db, version_id)

    title = "Celá škola"
    if scope != ViewScope.SCHOOL and entity_id is not None:
        if scope == ViewScope.STUDENT:
            person = db.get(Student, entity_id)
            title = person.full_name if person else f"Student {entity_id}"
            # A class view by group id misses lessons attached student by
            # student, so a student view always filters on the student itself.
            items = [i for i in items if entity_id in i.student_ids]
            return TimetableView(
                version_id=version_id, scope=scope, subject_id=entity_id,
                title=title, items=items,
            )
        if scope in (ViewScope.CLASS, ViewScope.GROUP):
            group = db.get(StudentGroup, entity_id)
            title = group.name if group else f"Skupina {entity_id}"
        elif scope == ViewScope.TEACHER:
            teacher = db.get(Teacher, entity_id)
            title = teacher.full_name if teacher else f"Učitel {entity_id}"
        elif scope == ViewScope.ROOM:
            room = db.get(Room, entity_id)
            title = room.name if room else f"Učebna {entity_id}"

    return TimetableView(
        version_id=version_id,
        scope=scope,
        subject_id=entity_id,
        title=title,
        items=filter_items(items, scope, entity_id),
    )
