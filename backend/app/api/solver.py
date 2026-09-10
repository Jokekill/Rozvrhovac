"""Solver runs, pre-solve validation and re-optimisation."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, db_session, require_scheduler, require_viewer
from app.models import Schedule, ScheduleVersion, SolverRun
from app.models.enums import SolverStatus
from app.schemas.schedule import DiagnosticItem, SolverRunCreate, SolverRunOut
from app.services import audit
from app.solver.diagnostics import validate_dataset
from app.solver.loader import load_solver_input
from app.solver.runner import enqueue_run

router = APIRouter()


@router.post("/solver/runs", response_model=SolverRunOut, status_code=201, tags=["solver"])
def create_run(
    payload: SolverRunCreate,
    db: Session = Depends(db_session),
    user: CurrentUser = Depends(require_scheduler),
) -> SolverRun:
    """Queue a solver run.

    ``base_version_id`` turns this into a re-optimisation: locked occurrences
    become hard constraints and, with ``reoptimize``, every change against the
    base schedule is penalised (SC15).
    """
    schedule_id = payload.schedule_id
    if payload.base_version_id is not None:
        base = db.get(ScheduleVersion, payload.base_version_id)
        if base is None:
            raise HTTPException(404, "Base schedule version not found")
        schedule_id = schedule_id or base.schedule_id
    if schedule_id is None:
        schedule = db.execute(select(Schedule).order_by(Schedule.id)).scalars().first()
        schedule_id = schedule.id if schedule else None

    run = SolverRun(
        status=SolverStatus.QUEUED,
        time_limit_seconds=max(1, payload.time_limit_seconds),
        schedule_id=schedule_id,
        base_version_id=payload.base_version_id,
        params={
            "reoptimize": payload.reoptimize,
            "version_name": payload.version_name,
            "keep_locked_only": payload.keep_locked_only,
        },
    )
    db.add(run)
    db.flush()
    audit.record(
        db, entity_type="SolverRun", entity_id=run.id, action="CREATE",
        actor=user.actor,
        new_value={
            "time_limit_seconds": run.time_limit_seconds,
            "base_version_id": run.base_version_id,
        },
    )
    db.commit()

    enqueue_run(run.id)
    db.expire_all()
    return db.get(SolverRun, run.id)


@router.get("/solver/runs", response_model=list[SolverRunOut], tags=["solver"])
def list_runs(
    db: Session = Depends(db_session),
    _: CurrentUser = Depends(require_viewer),
    limit: int = 25,
) -> list[SolverRun]:
    return (
        db.execute(select(SolverRun).order_by(SolverRun.id.desc()).limit(limit))
        .scalars()
        .all()
    )


@router.get("/solver/runs/{run_id}", response_model=SolverRunOut, tags=["solver"])
def get_run(
    run_id: int,
    db: Session = Depends(db_session),
    _: CurrentUser = Depends(require_viewer),
) -> SolverRun:
    run = db.get(SolverRun, run_id)
    if run is None:
        raise HTTPException(404, "Solver run not found")
    return run


@router.post("/solver/runs/{run_id}/cancel", response_model=SolverRunOut, tags=["solver"])
def cancel_run(
    run_id: int,
    db: Session = Depends(db_session),
    user: CurrentUser = Depends(require_scheduler),
) -> SolverRun:
    run = db.get(SolverRun, run_id)
    if run is None:
        raise HTTPException(404, "Solver run not found")
    if run.status in (SolverStatus.QUEUED,):
        run.status = SolverStatus.CANCELLED
    run.cancel_requested = True
    audit.record(
        db, entity_type="SolverRun", entity_id=run.id, action="CANCEL", actor=user.actor
    )
    db.commit()
    return run


@router.post("/solver/validate", response_model=list[DiagnosticItem], tags=["solver"])
def validate(
    db: Session = Depends(db_session), _: CurrentUser = Depends(require_viewer)
) -> list[DiagnosticItem]:
    """Run the dataset checks without solving (§15)."""
    data = load_solver_input(db)
    return [DiagnosticItem(**issue) for issue in validate_dataset(data)]
