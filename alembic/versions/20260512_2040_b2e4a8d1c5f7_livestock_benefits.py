"""add livestock_benefits to CoverCategory

Revision ID: b2e4a8d1c5f7
Revises: a7d1f3b9c2e4
Create Date: 2026-05-12 20:40:00.000000+00:00
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2e4a8d1c5f7'
down_revision: Union[str, None] = 'a7d1f3b9c2e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_OLD_VALUES = ('me', 'me_and_family', 'parents_and_inlaws', 'extended_family')
_NEW_VALUES = _OLD_VALUES + ('livestock_benefits',)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        # Postgres has a real ENUM type; expand it in place. `IF NOT EXISTS`
        # makes the migration idempotent if it's re-run.
        op.execute(
            "ALTER TYPE covercategory ADD VALUE IF NOT EXISTS 'livestock_benefits'"
        )
    else:
        # SQLite stores Enum as TEXT with a CHECK constraint. `batch_alter_table`
        # rebuilds the table so the check accepts the new value.
        new_enum = sa.Enum(*_NEW_VALUES, name='covercategory')
        with op.batch_alter_table('cover_plans', schema=None) as batch_op:
            batch_op.alter_column(
                'category',
                existing_type=sa.Enum(*_OLD_VALUES, name='covercategory'),
                type_=new_enum,
                existing_nullable=False,
            )


def downgrade() -> None:
    # NOTE: Postgres cannot drop a value from an enum once committed. The
    # only safe-and-portable downgrade is "no-op" - existing rows that
    # use the new value would otherwise become orphans. SQLite *can*
    # rebuild the check, but the asymmetry is too fragile to ship.
    pass
