"""zeroth hour, core block and minimum lessons per day

Adds the shape-of-the-day settings to ``cycle_config`` and retrofits the grid:
existing databases get a 07:10 zeroth period, their remaining periods are
renumbered so that ``index`` finally matches the human name, and the teaching
day is widened so the new slot is actually reachable.

Revision ID: a1c7e4b9d210
Revises: cfb43a2d33e1
Create Date: 2026-09-11 10:40:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = 'a1c7e4b9d210'
down_revision = 'cfb43a2d33e1'
branch_labels = None
depends_on = None

ZEROTH_START = 7 * 60 + 10
ZEROTH_END = 7 * 60 + 55
CORE_DAY_START = 8 * 60

NEW_WEIGHTS = [
    (
        "SC16",
        "Minimální počet hodin za den",
        10000,
        "Penalizuje každou chybějící hodinu pod min_student_lessons_per_day v den, "
        "kdy student do školy vůbec jde. Den bez výuky se nepenalizuje.",
    ),
    (
        "SC17",
        "Jádro dne – první hodiny povinně",
        10000,
        "Penalizuje každou z prvních core_block_periods hodin, ve které student nemá "
        "výuku. Platí pro každý vyučovací den a vynucuje společný dopolední blok.",
    ),
    (
        "SC18",
        "Nultá hodina jen výjimečně",
        100,
        "Penalizuje každý výskyt, který začíná před core_day_start_minute, aby se "
        "nultá hodina používala méně než zbytek mřížky.",
    ),
]


def upgrade() -> None:
    with op.batch_alter_table('cycle_config', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'core_day_start_minute',
                sa.Integer(),
                nullable=False,
                server_default=str(CORE_DAY_START),
            )
        )
        batch_op.add_column(
            sa.Column('core_block_periods', sa.Integer(), nullable=False, server_default='4')
        )
        batch_op.add_column(
            sa.Column(
                'min_student_lessons_per_day',
                sa.Integer(),
                nullable=False,
                server_default='4',
            )
        )

    connection = op.get_bind()

    # Only touch a grid that has periods but no zeroth hour yet.
    has_periods = connection.execute(sa.text("SELECT COUNT(*) FROM period")).scalar()
    already_zeroth = connection.execute(
        sa.text("SELECT COUNT(*) FROM period WHERE start_minute < :boundary"),
        {"boundary": CORE_DAY_START},
    ).scalar()
    if has_periods and not already_zeroth:
        # Renumber first so the new slot can take index 0 without a collision.
        connection.execute(sa.text("UPDATE period SET \"index\" = \"index\" + 1"))
        connection.execute(
            sa.text(
                'INSERT INTO period ("index", name, start_minute, end_minute) '
                'VALUES (0, :name, :start, :end)'
            ),
            {"name": "0. hodina", "start": ZEROTH_START, "end": ZEROTH_END},
        )
        connection.execute(
            sa.text("UPDATE day SET start_minute = :start WHERE start_minute > :start"),
            {"start": ZEROTH_START},
        )

    for code, name, weight, description in NEW_WEIGHTS:
        exists = connection.execute(
            sa.text("SELECT COUNT(*) FROM constraint_weight WHERE code = :code"),
            {"code": code},
        ).scalar()
        if exists:
            continue
        connection.execute(
            sa.text(
                "INSERT INTO constraint_weight (code, name, type, weight, enabled, description) "
                "VALUES (:code, :name, 'SOFT', :weight, true, :description)"
            ),
            {"code": code, "name": name, "weight": weight, "description": description},
        )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text("DELETE FROM constraint_weight WHERE code IN ('SC16', 'SC17', 'SC18')")
    )
    connection.execute(
        sa.text("DELETE FROM period WHERE start_minute < :boundary"),
        {"boundary": CORE_DAY_START},
    )
    connection.execute(sa.text("UPDATE period SET \"index\" = \"index\" - 1"))

    with op.batch_alter_table('cycle_config', schema=None) as batch_op:
        batch_op.drop_column('min_student_lessons_per_day')
        batch_op.drop_column('core_block_periods')
        batch_op.drop_column('core_day_start_minute')
