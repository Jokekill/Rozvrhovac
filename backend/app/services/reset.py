"""Wiping the database before a test dataset is generated.

Both generators refuse to run on a non-empty database, which is the right
default. Regenerating test data therefore needs an explicit, deliberate reset,
and this is the only place in the codebase that deletes everything.
"""
from __future__ import annotations

from sqlalchemy import delete
from sqlalchemy.orm import Session

import app.models  # noqa: F401  (registers every table on the metadata)
from app.db import Base


def reset_all_data(db: Session) -> dict[str, int]:
    """Delete every domain row. Returns the row count removed per table.

    Tables are emptied in reverse dependency order so that foreign keys stay
    satisfied on databases that check them (PostgreSQL always, SQLite when
    enforcement is on).
    """
    removed: dict[str, int] = {}
    for table in reversed(Base.metadata.sorted_tables):
        result = db.execute(delete(table))
        if result.rowcount:
            removed[table.name] = result.rowcount
    db.commit()
    return removed
