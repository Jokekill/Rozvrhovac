"""Import and export endpoints."""
from __future__ import annotations

import re
import unicodedata

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, db_session, require_scheduler, require_viewer
from app.api.views import ViewScope, filter_items
from app.models import Day, Room, ScheduleVersion, Student, StudentGroup, Teacher
from app.services import audit
from app.services.exporters import MEDIA_TYPES, to_csv, to_ics, to_pdf, to_xlsx
from app.services.importers import IMPORTERS, run_import
from app.services.serializers import load_schedule_items

router = APIRouter()


class ImportErrorOut(BaseModel):
    row: int
    message: str
    data: dict = {}


class ImportResultOut(BaseModel):
    entity: str
    rows_detected: int
    new: int
    updated: int
    unchanged: int
    committed: bool
    errors: list[ImportErrorOut]
    preview: list[dict]


@router.get("/imports", response_model=list[str], tags=["imports"])
def list_importers(_: CurrentUser = Depends(require_viewer)) -> list[str]:
    return sorted(IMPORTERS)


def _import(db: Session, entity: str, upload: UploadFile, commit: bool) -> ImportResultOut:
    if entity not in IMPORTERS:
        raise HTTPException(404, f"Unknown import '{entity}'")
    content = upload.file.read()
    try:
        result = run_import(db, entity, content, upload.filename or "", commit=commit)
    except UnicodeDecodeError as exc:
        raise HTTPException(400, "Soubor není v kódování UTF-8.") from exc
    return ImportResultOut(
        entity=result.entity,
        rows_detected=result.rows_detected,
        new=result.new,
        updated=result.updated,
        unchanged=result.unchanged,
        committed=result.committed,
        errors=[ImportErrorOut(row=e.row, message=e.message, data=e.data) for e in result.errors],
        preview=result.preview,
    )


@router.post("/imports/{entity}/preview", response_model=ImportResultOut, tags=["imports"])
def preview_import(
    entity: str,
    file: UploadFile = File(...),
    db: Session = Depends(db_session),
    _: CurrentUser = Depends(require_scheduler),
) -> ImportResultOut:
    """Parse the file and report what would happen, without changing anything."""
    return _import(db, entity, file, commit=False)


@router.post("/imports/{entity}", response_model=ImportResultOut, tags=["imports"])
def import_entity(
    entity: str,
    file: UploadFile = File(...),
    db: Session = Depends(db_session),
    user: CurrentUser = Depends(require_scheduler),
) -> ImportResultOut:
    """Shorthand for ``/imports/{entity}/commit`` (see §24 of the specification)."""
    return commit_import(entity, file, db, user)


@router.post("/imports/{entity}/commit", response_model=ImportResultOut, tags=["imports"])
def commit_import(
    entity: str,
    file: UploadFile = File(...),
    db: Session = Depends(db_session),
    user: CurrentUser = Depends(require_scheduler),
) -> ImportResultOut:
    """Apply the import. Any row error aborts the whole file."""
    result = _import(db, entity, file, commit=True)
    if result.committed:
        audit.record(
            db, entity_type="Import", action=entity.upper(), actor=user.actor,
            new_value={"new": result.new, "updated": result.updated},
        )
        db.commit()
    return result


# --------------------------------------------------------------------------
# Export
# --------------------------------------------------------------------------
def _slug(value: str) -> str:
    normalised = unicodedata.normalize("NFKD", value)
    ascii_only = normalised.encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "-", ascii_only).strip("-").lower() or "rozvrh"


@router.get("/exports/schedule/{version_id}", tags=["exports"])
def export_schedule(
    version_id: int,
    format: str = Query("csv", pattern="^(csv|xlsx|pdf|ics)$"),
    scope: ViewScope = ViewScope.SCHOOL,
    entity_id: int | None = None,
    db: Session = Depends(db_session),
    _: CurrentUser = Depends(require_viewer),
) -> Response:
    """Export one student, class, teacher, room or the whole school."""
    version = db.get(ScheduleVersion, version_id)
    if version is None:
        raise HTTPException(404, "Schedule version not found")
    items = load_schedule_items(db, version_id)
    items = filter_items(items, scope, entity_id)

    title = "Celá škola"
    if entity_id is not None:
        if scope == ViewScope.STUDENT:
            person = db.get(Student, entity_id)
            title = person.full_name if person else title
        elif scope in (ViewScope.CLASS, ViewScope.GROUP):
            group = db.get(StudentGroup, entity_id)
            title = group.name if group else title
        elif scope == ViewScope.TEACHER:
            teacher = db.get(Teacher, entity_id)
            title = teacher.full_name if teacher else title
        elif scope == ViewScope.ROOM:
            room = db.get(Room, entity_id)
            title = room.name if room else title

    day_names = {d.ordinal: d.name for d in db.execute(select(Day)).scalars()}
    heading = f"{version.name} – {title}"

    if format == "csv":
        payload = to_csv(items, day_names)
    elif format == "xlsx":
        payload = to_xlsx(items, day_names, title)
    elif format == "pdf":
        payload = to_pdf(items, day_names, heading)
    else:
        payload = to_ics(items, day_names, heading)

    filename = f"{_slug(heading)}.{format}"
    return Response(
        content=payload,
        media_type=MEDIA_TYPES[format],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
