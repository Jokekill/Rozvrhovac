"""Request dependencies: database session and (pluggable) authentication.

``AUTH_MODE=disabled`` (default) resolves every request to an implicit ADMIN so
that the solver MVP works without a login. ``AUTH_MODE=oidc`` is the extension
point for Microsoft Entra ID: validate the bearer token, map claims onto
:class:`CurrentUser`. Everything else in the API already goes through
``require_role`` and therefore needs no change.
"""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models.enums import Role

ROLE_ORDER = {Role.VIEWER: 0, Role.TEACHER: 1, Role.SCHEDULER: 2, Role.ADMIN: 3}


@dataclass
class CurrentUser:
    subject: str
    display_name: str
    role: Role

    @property
    def actor(self) -> str:
        return f"{self.display_name} <{self.subject}>"


def db_session() -> Iterator[Session]:
    yield from get_db()


def get_current_user(authorization: str | None = Header(default=None)) -> CurrentUser:
    settings = get_settings()
    if settings.auth_mode == "disabled":
        return CurrentUser(subject="local", display_name="Local admin", role=Role.ADMIN)
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    raise HTTPException(
        status.HTTP_501_NOT_IMPLEMENTED,
        "OIDC authentication is not wired up yet (phase 8).",
    )


def require_role(minimum: Role):
    """Dependency factory enforcing a minimum role."""

    def _dependency(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if ROLE_ORDER[user.role] < ROLE_ORDER[minimum]:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, f"Role {minimum} required, you have {user.role}"
            )
        return user

    return _dependency


require_viewer = require_role(Role.VIEWER)
require_scheduler = require_role(Role.SCHEDULER)
require_admin = require_role(Role.ADMIN)
