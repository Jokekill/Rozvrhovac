"""Constraint weights and the audit trail."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, db_session, require_admin, require_viewer
from app.models import AuditLog, ConstraintWeight
from app.schemas.schedule import (
    AuditOut,
    ConstraintWeightOut,
    ConstraintWeightUpdate,
)
from app.services import audit
from app.services.bootstrap import ensure_constraint_weights

router = APIRouter()


@router.get("/constraint-weights", response_model=list[ConstraintWeightOut], tags=["settings"])
def list_weights(
    db: Session = Depends(db_session), _: CurrentUser = Depends(require_viewer)
) -> list[ConstraintWeight]:
    rows = db.execute(select(ConstraintWeight).order_by(ConstraintWeight.code)).scalars().all()
    if not rows:
        ensure_constraint_weights(db)
        db.commit()
        rows = (
            db.execute(select(ConstraintWeight).order_by(ConstraintWeight.code)).scalars().all()
        )
    return rows


@router.put(
    "/constraint-weights/{code}", response_model=ConstraintWeightOut, tags=["settings"]
)
def update_weight(
    code: str,
    payload: ConstraintWeightUpdate,
    db: Session = Depends(db_session),
    user: CurrentUser = Depends(require_admin),
) -> ConstraintWeight:
    """Weights are data, not code: an administrator tunes them at runtime."""
    row = db.execute(
        select(ConstraintWeight).where(ConstraintWeight.code == code)
    ).scalars().first()
    if row is None:
        raise HTTPException(404, f"Constraint {code} not found")
    changes = payload.model_dump(exclude_unset=True)
    old = {k: getattr(row, k) for k in changes}
    for key, value in changes.items():
        setattr(row, key, value)
    audit.record(
        db, entity_type="ConstraintWeight", entity_id=row.id, action="UPDATE",
        actor=user.actor, old_value=old, new_value=changes,
    )
    db.commit()
    return row


@router.get("/audit", response_model=list[AuditOut], tags=["settings"])
def list_audit(
    db: Session = Depends(db_session),
    _: CurrentUser = Depends(require_viewer),
    limit: int = 100,
    entity_type: str | None = None,
) -> list[AuditLog]:
    stmt = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    return db.execute(stmt).scalars().all()
