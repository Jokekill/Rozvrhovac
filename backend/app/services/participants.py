"""Expansion of activity participants into concrete student ids.

Rule from the specification: whatever the UI used (a class, a cross-class
ensemble or a single student), the solver always receives a flat set of
``student_id``.
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Activity,
    ActivityStudent,
    ActivityStudentGroup,
    ActivityTeacher,
    StudentGroupMember,
)


def group_members_map(db: Session) -> dict[int, set[int]]:
    """group_id -> set(student_id) for every group in one query."""
    result: dict[int, set[int]] = defaultdict(set)
    for group_id, student_id in db.execute(
        select(StudentGroupMember.group_id, StudentGroupMember.student_id)
    ):
        result[group_id].add(student_id)
    return result


def activity_students_map(
    db: Session, members: dict[int, set[int]] | None = None
) -> dict[int, set[int]]:
    """activity_id -> flat set of student ids (direct members + groups)."""
    members = members if members is not None else group_members_map(db)
    result: dict[int, set[int]] = defaultdict(set)
    for activity_id, student_id in db.execute(
        select(ActivityStudent.activity_id, ActivityStudent.student_id)
    ):
        result[activity_id].add(student_id)
    for activity_id, group_id in db.execute(
        select(ActivityStudentGroup.activity_id, ActivityStudentGroup.group_id)
    ):
        result[activity_id] |= members.get(group_id, set())
    return result


def activity_teachers_map(db: Session) -> dict[int, set[int]]:
    result: dict[int, set[int]] = defaultdict(set)
    for activity_id, teacher_id in db.execute(
        select(ActivityTeacher.activity_id, ActivityTeacher.teacher_id)
    ):
        result[activity_id].add(teacher_id)
    return result


def students_of(db: Session, activity: Activity) -> set[int]:
    """Flat participant set of a single activity."""
    students = {link.student_id for link in activity.students}
    for link in activity.groups:
        students |= {m.student_id for m in link.group.members}
    return students
