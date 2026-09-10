"""CSV / XLSX import with a preview step (§22).

Every importer is stateless: the preview and the commit parse the same file,
so nothing has to be cached between the two requests. Errors are reported per
row with the row number the user sees in their spreadsheet.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Activity,
    ActivityRoomRequirement,
    ActivityStudent,
    ActivityStudentGroup,
    ActivityTeacher,
    ActivityTimeWindow,
    AvailabilityWindow,
    Day,
    Room,
    RoomFeature,
    RoomFeatureAssignment,
    Student,
    StudentGroup,
    StudentGroupMember,
    Subject,
    Teacher,
)
from app.models.enums import (
    ActivityKind,
    AvailabilityKind,
    GroupType,
    OwnerType,
    TimeWindowKind,
)

DAY_ALIASES = {
    "po": 0, "pondeli": 0, "pondělí": 0, "mon": 0, "monday": 0,
    "ut": 1, "út": 1, "utery": 1, "úterý": 1, "tue": 1, "tuesday": 1,
    "st": 2, "streda": 2, "středa": 2, "wed": 2, "wednesday": 2,
    "ct": 3, "čt": 3, "ctvrtek": 3, "čtvrtek": 3, "thu": 3, "thursday": 3,
    "pa": 4, "pá": 4, "patek": 4, "pátek": 4, "fri": 4, "friday": 4,
    "so": 5, "sa": 5, "saturday": 5,
    "ne": 6, "su": 6, "sunday": 6,
}


class RowError(ValueError):
    """A problem with one row; carries the message shown to the user."""


@dataclass
class ImportError_:
    row: int
    message: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class ImportResult:
    entity: str
    rows_detected: int = 0
    new: int = 0
    updated: int = 0
    unchanged: int = 0
    errors: list[ImportError_] = field(default_factory=list)
    preview: list[dict[str, Any]] = field(default_factory=list)
    committed: bool = False


def parse_time(value: str | None, *, default: int | None = None) -> int:
    """Accept ``8:00``, ``08:00``, ``480`` or an empty cell."""
    if value is None or str(value).strip() == "":
        if default is None:
            raise RowError("chybí čas")
        return default
    text = str(value).strip()
    if ":" in text:
        hours, _, minutes = text.partition(":")
        try:
            return int(hours) * 60 + int(minutes)
        except ValueError as exc:
            raise RowError(f"neplatný čas '{text}'") from exc
    try:
        return int(float(text))
    except ValueError as exc:
        raise RowError(f"neplatný čas '{text}'") from exc


def parse_bool(value: Any, default: bool = True) -> bool:
    if value is None or str(value).strip() == "":
        return default
    return str(value).strip().lower() in {"1", "true", "ano", "yes", "y", "x"}


def parse_int(value: Any, default: int | None = None) -> int | None:
    if value is None or str(value).strip() == "":
        return default
    try:
        return int(float(str(value).strip()))
    except ValueError as exc:
        raise RowError(f"'{value}' není číslo") from exc


def parse_list(value: Any) -> list[str]:
    if value is None or str(value).strip() == "":
        return []
    text = str(value).replace("|", ";").replace(",", ";")
    return [part.strip() for part in text.split(";") if part.strip()]


def parse_days(value: Any) -> list[int]:
    ordinals: list[int] = []
    for token in parse_list(value):
        key = token.strip().lower()
        if key.isdigit():
            ordinals.append(int(key))
        elif key in DAY_ALIASES:
            ordinals.append(DAY_ALIASES[key])
        else:
            raise RowError(f"neznámý den '{token}'")
    return ordinals


def read_rows(content: bytes, filename: str) -> list[dict[str, Any]]:
    """Read CSV or XLSX into a list of dicts with lower-cased headers."""
    if filename.lower().endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook

        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        sheet = workbook.active
        rows = sheet.iter_rows(values_only=True)
        try:
            header = [str(h or "").strip().lower() for h in next(rows)]
        except StopIteration:
            return []
        result = []
        for values in rows:
            if values is None or all(v is None or str(v).strip() == "" for v in values):
                continue
            result.append(
                {
                    header[i]: values[i] if i < len(values) else None
                    for i in range(len(header))
                }
            )
        return result

    text = content.decode("utf-8-sig")
    dialect = csv.Sniffer().sniff(text[:2048], delimiters=",;\t") if text.strip() else csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    return [
        {(k or "").strip().lower(): v for k, v in row.items()}
        for row in reader
        if any((v or "").strip() for v in row.values())
    ]


# --------------------------------------------------------------------------
# Per-entity importers
# --------------------------------------------------------------------------
def _lookup(db: Session, model, field_name: str, value: str):
    return db.execute(
        select(model).where(getattr(model, field_name) == value)
    ).scalars().first()


def _feature(db: Session, name: str) -> RoomFeature:
    feature = _lookup(db, RoomFeature, "name", name)
    if feature is None:
        feature = RoomFeature(name=name)
        db.add(feature)
        db.flush()
    return feature


def _import_students(db: Session, rows, result: ImportResult, commit: bool) -> None:
    for index, row in enumerate(rows, start=2):
        try:
            external_id = (row.get("external_id") or "").strip() or None
            first = (row.get("first_name") or "").strip()
            last = (row.get("last_name") or "").strip()
            if not first or not last:
                raise RowError("chybí first_name nebo last_name")
            existing = (
                _lookup(db, Student, "external_id", external_id) if external_id else None
            )
            class_code = (row.get("class_code") or "").strip()
            group = _lookup(db, StudentGroup, "code", class_code) if class_code else None
            if class_code and group is None:
                raise RowError(f"třída '{class_code}' neexistuje")
            payload = {
                "first_name": first,
                "last_name": last,
                "external_id": external_id,
                "active": parse_bool(row.get("active")),
                "notes": (row.get("notes") or "").strip() or None,
                "class_group_id": group.id if group else None,
            }
            result.preview.append(payload | {"_action": "UPDATE" if existing else "NEW"})
            if existing:
                result.updated += 1
                if commit:
                    for key, value in payload.items():
                        setattr(existing, key, value)
                    if group is not None:
                        _ensure_member(db, group.id, existing.id)
            else:
                result.new += 1
                if commit:
                    student = Student(**payload)
                    db.add(student)
                    db.flush()
                    if group is not None:
                        _ensure_member(db, group.id, student.id)
        except RowError as exc:
            result.errors.append(ImportError_(row=index, message=str(exc), data=dict(row)))


def _ensure_member(db: Session, group_id: int, student_id: int) -> None:
    exists = db.execute(
        select(StudentGroupMember).where(
            StudentGroupMember.group_id == group_id,
            StudentGroupMember.student_id == student_id,
        )
    ).scalars().first()
    if exists is None:
        db.add(StudentGroupMember(group_id=group_id, student_id=student_id))
        db.flush()


def _import_teachers(db: Session, rows, result: ImportResult, commit: bool) -> None:
    for index, row in enumerate(rows, start=2):
        try:
            external_id = (row.get("external_id") or "").strip() or None
            first = (row.get("first_name") or "").strip()
            last = (row.get("last_name") or "").strip()
            if not first or not last:
                raise RowError("chybí first_name nebo last_name")
            existing = (
                _lookup(db, Teacher, "external_id", external_id) if external_id else None
            )
            payload = {
                "first_name": first,
                "last_name": last,
                "external_id": external_id,
                "active": parse_bool(row.get("active")),
                "max_minutes_per_day": parse_int(row.get("max_minutes_per_day")),
                "max_consecutive_minutes": parse_int(row.get("max_consecutive_minutes")),
            }
            result.preview.append(payload | {"_action": "UPDATE" if existing else "NEW"})
            if existing:
                result.updated += 1
                if commit:
                    for key, value in payload.items():
                        setattr(existing, key, value)
            else:
                result.new += 1
                if commit:
                    db.add(Teacher(**payload))
                    db.flush()
        except RowError as exc:
            result.errors.append(ImportError_(row=index, message=str(exc), data=dict(row)))


def _import_rooms(db: Session, rows, result: ImportResult, commit: bool) -> None:
    for index, row in enumerate(rows, start=2):
        try:
            code = (row.get("code") or "").strip() or None
            name = (row.get("name") or "").strip()
            if not name:
                raise RowError("chybí name")
            existing = _lookup(db, Room, "code", code) if code else None
            payload = {
                "name": name,
                "code": code,
                "building": (row.get("building") or "").strip() or None,
                "floor": (row.get("floor") or "").strip() or None,
                "capacity": parse_int(row.get("capacity"), 30),
                "active": parse_bool(row.get("active")),
            }
            features = parse_list(row.get("features"))
            result.preview.append(
                payload | {"features": features, "_action": "UPDATE" if existing else "NEW"}
            )
            if existing:
                result.updated += 1
            else:
                result.new += 1
            if commit:
                room = existing or Room(**payload)
                if existing:
                    for key, value in payload.items():
                        setattr(room, key, value)
                else:
                    db.add(room)
                db.flush()
                if features:
                    for feature_name in features:
                        feature = _feature(db, feature_name)
                        already = db.execute(
                            select(RoomFeatureAssignment).where(
                                RoomFeatureAssignment.room_id == room.id,
                                RoomFeatureAssignment.feature_id == feature.id,
                            )
                        ).scalars().first()
                        if already is None:
                            db.add(
                                RoomFeatureAssignment(room_id=room.id, feature_id=feature.id)
                            )
                    db.flush()
        except RowError as exc:
            result.errors.append(ImportError_(row=index, message=str(exc), data=dict(row)))


def _import_groups(db: Session, rows, result: ImportResult, commit: bool) -> None:
    for index, row in enumerate(rows, start=2):
        try:
            code = (row.get("code") or "").strip() or None
            name = (row.get("name") or "").strip()
            if not name:
                raise RowError("chybí name")
            group_type = (row.get("type") or GroupType.OTHER).strip().upper()
            if group_type not in set(GroupType):
                raise RowError(f"neznámý typ skupiny '{group_type}'")
            existing = _lookup(db, StudentGroup, "code", code) if code else None
            payload = {"name": name, "code": code, "type": group_type}
            result.preview.append(payload | {"_action": "UPDATE" if existing else "NEW"})
            if existing:
                result.updated += 1
                if commit:
                    for key, value in payload.items():
                        setattr(existing, key, value)
            else:
                result.new += 1
                if commit:
                    db.add(StudentGroup(**payload))
                    db.flush()
        except RowError as exc:
            result.errors.append(ImportError_(row=index, message=str(exc), data=dict(row)))


def _import_group_members(db: Session, rows, result: ImportResult, commit: bool) -> None:
    for index, row in enumerate(rows, start=2):
        try:
            group_code = (row.get("group_code") or "").strip()
            student_ref = (row.get("student_external_id") or "").strip()
            group = _lookup(db, StudentGroup, "code", group_code)
            if group is None:
                raise RowError(f"skupina '{group_code}' neexistuje")
            student = _lookup(db, Student, "external_id", student_ref)
            if student is None:
                raise RowError(f"student '{student_ref}' neexistuje")
            existing = db.execute(
                select(StudentGroupMember).where(
                    StudentGroupMember.group_id == group.id,
                    StudentGroupMember.student_id == student.id,
                )
            ).scalars().first()
            result.preview.append(
                {
                    "group": group.name,
                    "student": student.full_name,
                    "_action": "UNCHANGED" if existing else "NEW",
                }
            )
            if existing:
                result.unchanged += 1
            else:
                result.new += 1
                if commit:
                    _ensure_member(db, group.id, student.id)
        except RowError as exc:
            result.errors.append(ImportError_(row=index, message=str(exc), data=dict(row)))


def _resolve_activity_links(db: Session, row, activity: Activity) -> None:
    db.query(ActivityTeacher).filter(ActivityTeacher.activity_id == activity.id).delete()
    db.query(ActivityStudentGroup).filter(
        ActivityStudentGroup.activity_id == activity.id
    ).delete()
    db.query(ActivityStudent).filter(ActivityStudent.activity_id == activity.id).delete()
    db.query(ActivityRoomRequirement).filter(
        ActivityRoomRequirement.activity_id == activity.id
    ).delete()
    for ref in parse_list(row.get("teacher_external_ids")):
        teacher = _lookup(db, Teacher, "external_id", ref)
        if teacher is None:
            raise RowError(f"učitel '{ref}' neexistuje")
        db.add(ActivityTeacher(activity_id=activity.id, teacher_id=teacher.id))
    for ref in parse_list(row.get("group_codes")):
        group = _lookup(db, StudentGroup, "code", ref)
        if group is None:
            raise RowError(f"skupina '{ref}' neexistuje")
        db.add(ActivityStudentGroup(activity_id=activity.id, group_id=group.id))
    for ref in parse_list(row.get("student_external_ids")):
        student = _lookup(db, Student, "external_id", ref)
        if student is None:
            raise RowError(f"student '{ref}' neexistuje")
        db.add(ActivityStudent(activity_id=activity.id, student_id=student.id))
    for feature_name in parse_list(row.get("required_features")):
        feature = _feature(db, feature_name)
        db.add(ActivityRoomRequirement(activity_id=activity.id, feature_id=feature.id))
    db.flush()


def _import_activities(db: Session, rows, result: ImportResult, commit: bool) -> None:
    for index, row in enumerate(rows, start=2):
        try:
            name = (row.get("name") or "").strip()
            if not name:
                raise RowError("chybí name")
            subject_code = (row.get("subject_code") or "").strip()
            subject = _lookup(db, Subject, "code", subject_code) if subject_code else None
            if subject_code and subject is None:
                raise RowError(f"předmět '{subject_code}' neexistuje")
            kind = (row.get("kind") or ActivityKind.STANDARD).strip().upper()
            if kind not in set(ActivityKind):
                raise RowError(f"neznámý typ aktivity '{kind}'")
            existing = _lookup(db, Activity, "name", name)
            payload = {
                "name": name,
                "subject_id": subject.id if subject else None,
                "kind": kind,
                "duration_minutes": parse_int(row.get("duration_minutes"), 45),
                "occurrences_per_cycle": parse_int(row.get("occurrences_per_cycle"), 1),
                "align_to_periods": parse_bool(row.get("align_to_periods"), True),
                "active": parse_bool(row.get("active")),
            }
            result.preview.append(payload | {"_action": "UPDATE" if existing else "NEW"})
            if existing:
                result.updated += 1
            else:
                result.new += 1
            if commit:
                activity = existing or Activity(**payload)
                if existing:
                    for key, value in payload.items():
                        setattr(activity, key, value)
                else:
                    db.add(activity)
                db.flush()
                _resolve_activity_links(db, row, activity)
        except RowError as exc:
            result.errors.append(ImportError_(row=index, message=str(exc), data=dict(row)))


def _import_individual_lessons(db: Session, rows, result: ImportResult, commit: bool) -> None:
    days = {d.ordinal: d for d in db.execute(select(Day)).scalars()}
    for index, row in enumerate(rows, start=2):
        try:
            student_ref = (row.get("student_external_id") or "").strip()
            student = _lookup(db, Student, "external_id", student_ref)
            if student is None:
                raise RowError(f"student '{student_ref}' neexistuje")
            subject_code = (row.get("subject_code") or "").strip()
            subject = _lookup(db, Subject, "code", subject_code) if subject_code else None
            if subject_code and subject is None:
                raise RowError(f"předmět '{subject_code}' neexistuje")
            teacher_ref = (row.get("teacher_external_id") or "").strip()
            teacher = _lookup(db, Teacher, "external_id", teacher_ref) if teacher_ref else None
            if teacher_ref and teacher is None:
                raise RowError(f"učitel '{teacher_ref}' neexistuje")
            duration = parse_int(row.get("duration_minutes"), 45)
            occurrences = parse_int(row.get("occurrences_per_cycle"), 1)
            allowed_days = parse_days(row.get("allowed_days"))
            name = (row.get("name") or "").strip() or (
                f"{subject.name if subject else 'Individuální výuka'} – {student.full_name}"
            )
            existing = _lookup(db, Activity, "name", name)
            result.preview.append(
                {
                    "student": student.full_name,
                    "class": student.class_group.name if student.class_group else None,
                    "subject": subject.name if subject else None,
                    "teacher": teacher.full_name if teacher else None,
                    "duration_minutes": duration,
                    "occurrences_per_cycle": occurrences,
                    "allowed_days": allowed_days,
                    "_action": "UPDATE" if existing else "NEW",
                }
            )
            if existing:
                result.updated += 1
            else:
                result.new += 1
            if commit:
                activity = existing or Activity(name=name)
                activity.kind = ActivityKind.INDIVIDUAL
                activity.subject_id = subject.id if subject else None
                activity.duration_minutes = duration
                activity.occurrences_per_cycle = occurrences
                activity.align_to_periods = False
                activity.active = parse_bool(row.get("active"))
                if existing is None:
                    db.add(activity)
                db.flush()
                db.query(ActivityTeacher).filter(
                    ActivityTeacher.activity_id == activity.id
                ).delete()
                db.query(ActivityStudent).filter(
                    ActivityStudent.activity_id == activity.id
                ).delete()
                db.query(ActivityRoomRequirement).filter(
                    ActivityRoomRequirement.activity_id == activity.id
                ).delete()
                db.query(ActivityTimeWindow).filter(
                    ActivityTimeWindow.activity_id == activity.id
                ).delete()
                db.add(ActivityStudent(activity_id=activity.id, student_id=student.id))
                if teacher is not None:
                    db.add(ActivityTeacher(activity_id=activity.id, teacher_id=teacher.id))
                for feature_name in parse_list(row.get("required_features")):
                    feature = _feature(db, feature_name)
                    db.add(
                        ActivityRoomRequirement(
                            activity_id=activity.id, feature_id=feature.id
                        )
                    )
                for ordinal in allowed_days:
                    day = days.get(ordinal)
                    db.add(
                        ActivityTimeWindow(
                            activity_id=activity.id,
                            kind=TimeWindowKind.ALLOWED,
                            day_ordinal=ordinal,
                            start_minute=day.start_minute if day else None,
                            end_minute=day.end_minute if day else None,
                        )
                    )
                db.flush()
        except RowError as exc:
            result.errors.append(ImportError_(row=index, message=str(exc), data=dict(row)))


def _import_availability(db: Session, rows, result: ImportResult, commit: bool) -> None:
    for index, row in enumerate(rows, start=2):
        try:
            owner_type = (row.get("owner_type") or "").strip().upper()
            if owner_type not in set(OwnerType):
                raise RowError(f"neznámý owner_type '{owner_type}'")
            reference = (row.get("owner_external_id") or "").strip()
            model, field_name = {
                OwnerType.TEACHER: (Teacher, "external_id"),
                OwnerType.STUDENT: (Student, "external_id"),
                OwnerType.ROOM: (Room, "code"),
            }[OwnerType(owner_type)]
            owner = _lookup(db, model, field_name, reference)
            if owner is None:
                raise RowError(f"{owner_type.lower()} '{reference}' neexistuje")
            kind = (row.get("kind") or AvailabilityKind.UNAVAILABLE).strip().upper()
            if kind not in set(AvailabilityKind):
                raise RowError(f"neznámý kind '{kind}'")
            day_value = (row.get("day") or row.get("day_ordinal") or "").strip()
            day_ordinal = parse_days(day_value)[0] if day_value else None
            start = parse_time(row.get("start"))
            end = parse_time(row.get("end"))
            if end <= start:
                raise RowError("end musí být větší než start")
            payload = {
                "owner_type": owner_type,
                "owner_id": owner.id,
                "kind": kind,
                "day_ordinal": day_ordinal,
                "start_minute": start,
                "end_minute": end,
                "note": (row.get("note") or "").strip() or None,
            }
            result.preview.append(payload | {"_action": "NEW"})
            result.new += 1
            if commit:
                db.add(AvailabilityWindow(**payload))
                db.flush()
        except RowError as exc:
            result.errors.append(ImportError_(row=index, message=str(exc), data=dict(row)))


IMPORTERS = {
    "students": _import_students,
    "teachers": _import_teachers,
    "rooms": _import_rooms,
    "groups": _import_groups,
    "group-members": _import_group_members,
    "activities": _import_activities,
    "individual-lessons": _import_individual_lessons,
    "availability": _import_availability,
}


def run_import(
    db: Session, entity: str, content: bytes, filename: str, *, commit: bool
) -> ImportResult:
    if entity not in IMPORTERS:
        raise KeyError(entity)
    rows = read_rows(content, filename)
    result = ImportResult(entity=entity, rows_detected=len(rows))
    IMPORTERS[entity](db, rows, result, commit)
    if commit and not result.errors:
        db.commit()
        result.committed = True
    else:
        db.rollback()
    result.preview = result.preview[:50]
    return result
