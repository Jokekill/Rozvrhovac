"""Generating test datasets straight into the database.

The CLI (``manage.py seed-demo`` / ``seed-school``) stays the canonical entry
point; this exposes the same generators to the GUI so that a new installation
can be filled with a working school in one click.

Generation is destructive by design, so it needs the ADMIN role, an explicit
``reset`` flag, and it can be switched off entirely with
``ALLOW_DATASET_GENERATION=false`` on a production deployment.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, db_session, require_admin
from app.config import get_settings
from app.models import SolverRun, Student
from app.models.enums import SolverStatus
from app.seed import seed_demo
from app.seed_school import GYMNASIUM_CLASSES, LYCEUM_CLASSES, SchoolSpec, seed_school
from app.services import audit
from app.services.reset import reset_all_data
from app.solver.runner import enqueue_run

router = APIRouter()


class DatasetRequest(BaseModel):
    """Global school settings for the generated dataset."""

    preset: Literal["demo", "school"] = "school"
    reset: bool = False
    seed: int = 7

    gymnasium_classes: int = Field(8, ge=0, le=len(GYMNASIUM_CLASSES))
    lyceum_classes: int = Field(4, ge=0, le=len(LYCEUM_CLASSES))
    gymnasium_class_min: int = Field(25, ge=1, le=40)
    gymnasium_class_max: int = Field(30, ge=1, le=40)
    lyceum_class_size: int = Field(25, ge=1, le=40)
    solo_share: float = Field(0.27, ge=0.0, le=1.0)
    rooms_ordinary: int = Field(10, ge=1, le=40)

    solve: bool = False
    time_limit_seconds: int = Field(60, ge=1, le=3600)

    @model_validator(mode="after")
    def _check(self) -> "DatasetRequest":
        if self.gymnasium_class_max < self.gymnasium_class_min:
            raise ValueError("gymnasium_class_max musí být >= gymnasium_class_min")
        if self.preset == "school" and self.gymnasium_classes + self.lyceum_classes == 0:
            raise ValueError("Škola musí mít alespoň jednu třídu")
        return self


class DatasetResult(BaseModel):
    preset: str
    reset: bool
    stats: dict[str, int]
    removed: dict[str, int] = Field(default_factory=dict)
    solver_run_id: int | None = None
    message: str


class DatasetInfo(BaseModel):
    enabled: bool
    database_empty: bool
    students: int
    max_gymnasium_classes: int
    max_lyceum_classes: int
    gymnasium_class_names: list[str]
    lyceum_class_names: list[str]


@router.get("/datasets", response_model=DatasetInfo, tags=["datasets"])
def dataset_info(
    db: Session = Depends(db_session), _: CurrentUser = Depends(require_admin)
) -> DatasetInfo:
    students = db.execute(select(func.count(Student.id))).scalar_one()
    return DatasetInfo(
        enabled=get_settings().allow_dataset_generation,
        database_empty=students == 0,
        students=students,
        max_gymnasium_classes=len(GYMNASIUM_CLASSES),
        max_lyceum_classes=len(LYCEUM_CLASSES),
        gymnasium_class_names=list(GYMNASIUM_CLASSES),
        lyceum_class_names=list(LYCEUM_CLASSES),
    )


@router.post("/datasets/generate", response_model=DatasetResult, tags=["datasets"])
def generate_dataset(
    payload: DatasetRequest,
    db: Session = Depends(db_session),
    user: CurrentUser = Depends(require_admin),
) -> DatasetResult:
    settings = get_settings()
    if not settings.allow_dataset_generation:
        raise HTTPException(
            403,
            "Generování testovacích dat je na tomto prostředí vypnuté "
            "(ALLOW_DATASET_GENERATION=false).",
        )

    students = db.execute(select(func.count(Student.id))).scalar_one()
    if students and not payload.reset:
        raise HTTPException(
            409,
            f"Databáze už obsahuje {students} studentů. Generování by data "
            "míchalo dohromady, zvolte smazání současných dat.",
        )

    removed: dict[str, int] = {}
    if payload.reset:
        removed = reset_all_data(db)

    if payload.preset == "demo":
        stats = seed_demo(db, seed=payload.seed)
    else:
        spec = SchoolSpec(
            seed=payload.seed,
            gymnasium_classes=tuple(GYMNASIUM_CLASSES[: payload.gymnasium_classes]),
            lyceum_classes=tuple(LYCEUM_CLASSES[: payload.lyceum_classes]),
            gymnasium_class_sizes=(payload.gymnasium_class_min, payload.gymnasium_class_max),
            lyceum_class_size=payload.lyceum_class_size,
            solo_share=payload.solo_share,
            rooms_ordinary=payload.rooms_ordinary,
        )
        stats = seed_school(db, spec)

    if stats.get("skipped"):
        raise HTTPException(409, "Databáze není prázdná, generování přeskočeno.")

    audit.record(
        db,
        entity_type="Dataset",
        action="GENERATE",
        actor=user.actor,
        old_value={"removed_rows": sum(removed.values())} if removed else None,
        new_value={"preset": payload.preset, **stats},
    )
    db.commit()

    run_id: int | None = None
    if payload.solve:
        run = SolverRun(
            status=SolverStatus.QUEUED,
            time_limit_seconds=payload.time_limit_seconds,
            params={"reoptimize": False, "version_name": "Draft 1"},
        )
        db.add(run)
        db.commit()
        run_id = run.id
        enqueue_run(run_id)

    counts = ", ".join(f"{key} {value}" for key, value in stats.items())
    return DatasetResult(
        preset=payload.preset,
        reset=payload.reset,
        stats=stats,
        removed=removed,
        solver_run_id=run_id,
        message=f"Vygenerováno: {counts}."
        + (" Solver byl spuštěn." if run_id else ""),
    )
