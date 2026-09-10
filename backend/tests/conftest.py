"""Test fixtures. Tests run on a throwaway SQLite file database."""
from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator

import pytest

os.environ.setdefault("RUN_SOLVER_INLINE", "true")
os.environ.setdefault("AUTH_MODE", "disabled")

_TMP_DIR = tempfile.mkdtemp(prefix="timetable-tests-")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DIR}/test.db"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

import app.models  # noqa: E402,F401
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402
from app.services.bootstrap import bootstrap  # noqa: E402


@pytest.fixture()
def db() -> Iterator[Session]:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    session = SessionLocal()
    bootstrap(session)
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db: Session) -> Iterator[TestClient]:
    with TestClient(fastapi_app) as test_client:
        yield test_client
