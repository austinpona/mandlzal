"""add user role

Revision ID: 78cb5b6ea99e
Revises: 9ffff74acfe3
Create Date: 2026-05-10 23:39:45.783826+00:00
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '78cb5b6ea99e'
down_revision: Union[str, None] = '9ffff74acfe3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


role_enum = sa.Enum('admin', 'agent', 'viewer', name='role')


def upgrade() -> None:
    bind = op.get_bind()
    # On Postgres the named ENUM type must exist before the column can use it.
    role_enum.create(bind, checkfirst=True)

    # Add the column with a temporary server_default so existing rows are populated.
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'role', role_enum,
            nullable=False, server_default='viewer',
        ))

    # Backfill: anyone who was previously is_admin=True becomes admin.
    op.execute("UPDATE users SET role = 'admin' WHERE is_admin = 1 OR is_admin = TRUE")

    # Drop the server_default - the application supplies the default going forward.
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('role', server_default=None)


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('role')
    bind = op.get_bind()
    role_enum.drop(bind, checkfirst=True)
