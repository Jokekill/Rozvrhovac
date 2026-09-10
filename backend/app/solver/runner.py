"""Orchestration of a SolverRun: load, validate, solve, persist a new version."""
from __future__ import annotations

import logging
import time
import traceback
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Schedule, ScheduledActivity, ScheduleVersion, SolverRun
from app.models.enums import SolverStatus, VersionStatus
from app.solver.diagnostics import (
    has_errors,
    staged_infeasibility_probe,
    validate_dataset,
)
from app.solver.engine import InfeasibleModelError, TimetableModel
from app.solver.loader import load_solver_input
from app.solver.model import SolveResult, SolverInput

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def prepare_input(
    db: Session, *, base_version_id: int | None, reoptimize: bool
) -> SolverInput:
    data = load_solver_input(db, base_version_id=base_version_id, respect_locks=True)
    if not reoptimize:
        # Locks still apply, but we do not pay for moving anything (SC15 off).
        data.base_assignments = {
            key: value
            for key, value in data.base_assignments.items()
            if key in data.locked_time or key in data.locked_room
        }
    return data


def persist_version(
    db: Session,
    run: SolverRun,
    result: SolveResult,
    data: SolverInput,
    *,
    version_name: str | None = None,
) -> ScheduleVersion:
    schedule_id = run.schedule_id
    if schedule_id is None:
        schedule = db.execute(select(Schedule).order_by(Schedule.id)).scalars().first()
        if schedule is None:
            schedule = Schedule(name="Hlavní rozvrh")
            db.add(schedule)
            db.flush()
        schedule_id = schedule.id

    existing = db.execute(
        select(ScheduleVersion).where(ScheduleVersion.schedule_id == schedule_id)
    ).scalars().all()
    version = ScheduleVersion(
        schedule_id=schedule_id,
        name=version_name or f"Draft {len(existing) + 1}",
        status=VersionStatus.DRAFT,
        parent_version_id=run.base_version_id,
        solver_run_id=run.id,
        total_penalty=result.total_penalty,
        penalties=result.penalties,
        note=result.log,
    )
    db.add(version)
    db.flush()

    for assignment in result.assignments:
        key = (assignment.activity_id, assignment.occurrence_index)
        activity = data.activity_by_id(assignment.activity_id)
        db.add(
            ScheduledActivity(
                version_id=version.id,
                activity_id=assignment.activity_id,
                occurrence_index=assignment.occurrence_index,
                start_minute=assignment.start_minute,
                duration_minutes=activity.duration if activity else 0,
                day_ordinal=assignment.day_ordinal,
                room_id=assignment.room_id,
                lock_time=key in data.locked_time,
                lock_room=key in data.locked_room,
            )
        )
    db.flush()
    return version


def warm_start(data: SolverInput, model: TimetableModel, *, workers: int, budget: int) -> None:
    """Find any feasible schedule first, then hand it to the full model as a hint.

    Minimising student and teacher gaps is the expensive part of the objective.
    Solving the hard constraints alone takes a fraction of a second even on a
    full school, and starting the optimisation from that point means a short
    time limit still returns a usable schedule instead of nothing.
    """
    if data.hints or data.base_assignments:
        return
    import copy

    feasibility_input = copy.deepcopy(data)
    feasibility_input.weights = {}
    probe = TimetableModel(feasibility_input)
    try:
        probe.build()
    except InfeasibleModelError:
        return
    limit = max(2, min(15, budget // 4))
    outcome = probe.solve(time_limit_seconds=limit, workers=workers)
    if outcome.status not in ("OPTIMAL", "FEASIBLE"):
        return
    data.hints = {
        (a.activity_id, a.occurrence_index): a for a in outcome.assignments
    }
    model.apply_hints(data.hints)


def score_solution(
    data: SolverInput, assignments: dict[tuple[int, int], object], *, workers: int = 4
) -> SolveResult:
    """Evaluate a known schedule against the full objective."""
    import copy

    scored = TimetableModel(copy.deepcopy(data))
    scored.build()
    scored.freeze_to(assignments)
    result = scored.solve(time_limit_seconds=20, workers=workers)
    if result.status in ("OPTIMAL", "FEASIBLE"):
        result.status = "FEASIBLE"
        result.log = "Feasible schedule from the first pass (optimisation timed out)."
    return result


def execute_run(run_id: int, session: Session | None = None) -> SolverRun:
    """Run the solver for ``run_id``. Safe to call from RQ or inline."""
    owns_session = session is None
    db = session or SessionLocal()
    try:
        run = db.get(SolverRun, run_id)
        if run is None:
            raise ValueError(f"SolverRun {run_id} not found")
        if run.status == SolverStatus.CANCELLED:
            return run

        run.status = SolverStatus.RUNNING
        run.started_at = _now()
        db.commit()

        params = run.params or {}
        try:
            data = prepare_input(
                db,
                base_version_id=run.base_version_id,
                reoptimize=bool(params.get("reoptimize")),
            )
            issues = validate_dataset(data)
            run.diagnostics = issues
            if has_errors(issues):
                run.status = SolverStatus.INFEASIBLE
                run.finished_at = _now()
                run.log = "Dataset validation failed before solving."
                db.commit()
                return run

            model = TimetableModel(data)
            try:
                model.build()
            except InfeasibleModelError as exc:
                run.status = SolverStatus.INFEASIBLE
                run.diagnostics = issues + exc.diagnostics
                run.finished_at = _now()
                run.log = str(exc)
                db.commit()
                return run

            last_check = [time.monotonic()]

            def should_stop() -> bool:
                if time.monotonic() - last_check[0] < 2.0:
                    return False
                last_check[0] = time.monotonic()
                db.expire_all()
                current = db.get(SolverRun, run_id)
                return bool(current and current.cancel_requested)

            workers = int(params.get("workers", 8))
            warm_start(data, model, workers=workers, budget=run.time_limit_seconds)

            result = model.solve(
                time_limit_seconds=run.time_limit_seconds,
                workers=workers,
                should_stop=should_stop,
            )
            if not result.assignments and data.hints:
                # The optimisation ran out of time before proving anything.
                # The feasibility pass already has a valid schedule, so score
                # that one and keep it instead of returning nothing (§14).
                result = score_solution(data, data.hints, workers=workers)

            # Read the cancellation flag before touching the run, because
            # expiring the session would drop unflushed attribute changes.
            db.expire_all()
            run = db.get(SolverRun, run_id)
            cancelled = bool(run.cancel_requested)

            run.log = result.log
            run.penalties = result.penalties
            run.best_score = result.total_penalty
            run.finished_at = _now()

            if cancelled and not result.assignments:
                run.status = SolverStatus.CANCELLED
                db.commit()
                return run
            if cancelled:
                # Stopped early on request, but a valid schedule was already
                # found, so it is kept rather than thrown away.
                run.log = f"{result.log} (zrušeno uživatelem, nejlepší řešení uloženo)"

            if result.status in ("OPTIMAL", "FEASIBLE"):
                version = persist_version(
                    db, run, result, data, version_name=params.get("version_name")
                )
                run.schedule_version_id = version.id
                run.schedule_id = version.schedule_id
                run.status = (
                    SolverStatus.OPTIMAL
                    if result.status == "OPTIMAL"
                    else SolverStatus.FEASIBLE
                )
            elif result.status == "INFEASIBLE":
                run.status = SolverStatus.INFEASIBLE
                run.diagnostics = (run.diagnostics or []) + staged_infeasibility_probe(data)
            else:
                run.status = SolverStatus.FAILED
            db.commit()
            return run
        except Exception:  # pragma: no cover - defensive
            logger.exception("Solver run %s failed", run_id)
            run.status = SolverStatus.FAILED
            run.finished_at = _now()
            run.log = traceback.format_exc(limit=8)
            db.commit()
            return run
    finally:
        if owns_session:
            db.close()


def enqueue_run(run_id: int) -> str | None:
    """Push the run onto the RQ queue, or execute it inline when configured."""
    from app.config import get_settings

    settings = get_settings()
    if settings.run_solver_inline:
        execute_run(run_id)
        return None
    from redis import Redis
    from rq import Queue

    queue = Queue("solver", connection=Redis.from_url(settings.redis_url))
    job = queue.enqueue(
        "app.solver.runner.execute_run", run_id, job_timeout=60 * 60
    )
    return job.id
