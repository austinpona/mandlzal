"""funeral cover signup: plans, beneficiaries, demographic fields

Revision ID: a7d1f3b9c2e4
Revises: 78cb5b6ea99e
Create Date: 2026-05-12 14:30:00.000000+00:00
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7d1f3b9c2e4'
down_revision: Union[str, None] = '78cb5b6ea99e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


cover_category_enum = sa.Enum(
    'me', 'me_and_family', 'parents_and_inlaws', 'extended_family',
    name='covercategory',
)


def upgrade() -> None:
    bind = op.get_bind()
    cover_category_enum.create(bind, checkfirst=True)

    # 1. Cover plan catalog.
    op.create_table(
        'cover_plans',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('category', cover_category_enum, nullable=False, index=True),
        sa.Column('cover_type', sa.String(length=80), nullable=False),
        sa.Column('monthly_premium', sa.Numeric(12, 2), nullable=False),
        sa.Column('max_dependents', sa.Integer(), nullable=False),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    # The Column above already declares `index=True` which creates
    # `ix_cover_plans_category`; no second `create_index` call needed.

    # 2. Beneficiaries.
    op.create_table(
        'beneficiaries',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('policy_id', sa.Integer(), sa.ForeignKey('policies.id', ondelete='CASCADE'),
                  nullable=False, index=True),
        sa.Column('relationship_to_holder', sa.String(length=64), nullable=False),
        sa.Column('first_name', sa.String(length=120), nullable=False),
        sa.Column('surname', sa.String(length=120), nullable=False),
        sa.Column('cellphone', sa.String(length=32), nullable=True),
        sa.Column('country_of_birth', sa.String(length=80), nullable=True),
        sa.Column('share_pct', sa.Numeric(5, 2), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )

    # 3. Demographic columns on customers + members. All nullable so the
    # migration is non-destructive for existing rows.
    with op.batch_alter_table('customers', schema=None) as batch_op:
        batch_op.add_column(sa.Column('title', sa.String(length=8), nullable=True))
        batch_op.add_column(sa.Column('first_names', sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column('surname', sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column('gender', sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column('date_of_birth', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('nationality', sa.String(length=80), nullable=True))

    with op.batch_alter_table('members', schema=None) as batch_op:
        batch_op.add_column(sa.Column('title', sa.String(length=8), nullable=True))
        batch_op.add_column(sa.Column('first_names', sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column('surname', sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column('gender', sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column('date_of_birth', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('nationality', sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column('email', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('cellphone', sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column('country_of_birth', sa.String(length=80), nullable=True))

    # 4. Link policies -> cover_plans (nullable; legacy policies have no plan).
    with op.batch_alter_table('policies', schema=None) as batch_op:
        batch_op.add_column(sa.Column('cover_plan_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_policies_cover_plan_id',
            'cover_plans', ['cover_plan_id'], ['id'],
            ondelete='SET NULL',
        )
    op.create_index('ix_policies_cover_plan_id', 'policies', ['cover_plan_id'])


def downgrade() -> None:
    with op.batch_alter_table('policies', schema=None) as batch_op:
        batch_op.drop_index('ix_policies_cover_plan_id')
        batch_op.drop_constraint('fk_policies_cover_plan_id', type_='foreignkey')
        batch_op.drop_column('cover_plan_id')

    with op.batch_alter_table('members', schema=None) as batch_op:
        for col in (
            'country_of_birth', 'cellphone', 'email', 'nationality',
            'date_of_birth', 'gender', 'surname', 'first_names', 'title',
        ):
            batch_op.drop_column(col)

    with op.batch_alter_table('customers', schema=None) as batch_op:
        for col in (
            'nationality', 'date_of_birth', 'gender',
            'surname', 'first_names', 'title',
        ):
            batch_op.drop_column(col)

    op.drop_table('beneficiaries')
    op.drop_table('cover_plans')

    bind = op.get_bind()
    cover_category_enum.drop(bind, checkfirst=True)
