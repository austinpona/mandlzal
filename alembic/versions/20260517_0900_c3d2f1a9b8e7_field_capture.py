"""field capture backend schema

Revision ID: c3d2f1a9b8e7
Revises: b2e4a8d1c5f7
Create Date: 2026-05-17 09:00:00.000000+00:00
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c3d2f1a9b8e7"
down_revision: Union[str, None] = "b2e4a8d1c5f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


device_status_enum = sa.Enum("active", "revoked", name="devicestatus")
field_submission_status_enum = sa.Enum(
    "processed", "partial", "failed", name="fieldsubmissionstatus",
)


def upgrade() -> None:
    bind = op.get_bind()
    device_status_enum.create(bind, checkfirst=True)
    field_submission_status_enum.create(bind, checkfirst=True)

    op.create_table(
        "devices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("status", device_status_enum, nullable=False),
        sa.Column("enrolled_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "device_enrollment_codes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=6), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
        sa.Column("consumed_by_device_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["consumed_by_device_id"], ["devices.id"]),
    )
    op.create_index(
        "ix_device_enrollment_codes_code",
        "device_enrollment_codes",
        ["code"],
        unique=True,
    )

    op.create_table(
        "field_submissions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("device_id", sa.Integer(), nullable=False),
        sa.Column("client_uuid", sa.String(length=36), nullable=False),
        sa.Column("submitted_at", sa.DateTime(), nullable=False),
        sa.Column("signups_count", sa.Integer(), nullable=False),
        sa.Column("payments_count", sa.Integer(), nullable=False),
        sa.Column("status", field_submission_status_enum, nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "raw_payload",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"]),
        sa.UniqueConstraint("device_id", "client_uuid", name="uq_field_submission_dedupe"),
    )
    op.create_index("ix_field_submissions_device_id", "field_submissions", ["device_id"])
    op.create_index("ix_field_submissions_client_uuid", "field_submissions", ["client_uuid"])

    with op.batch_alter_table("beneficiaries", schema=None) as batch_op:
        batch_op.add_column(sa.Column("title", sa.String(length=8), nullable=True))
        batch_op.add_column(sa.Column("gender", sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column("date_of_birth", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("nationality", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("email", sa.String(length=255), nullable=True))

    with op.batch_alter_table("customers", schema=None) as batch_op:
        batch_op.add_column(sa.Column("id_photo_path", sa.String(length=255), nullable=True))

    with op.batch_alter_table("policies", schema=None) as batch_op:
        batch_op.add_column(sa.Column("field_submission_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_policies_field_submission_id",
            "field_submissions",
            ["field_submission_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_policies_field_submission_id", ["field_submission_id"])

    with op.batch_alter_table("payments", schema=None) as batch_op:
        batch_op.add_column(sa.Column("field_submission_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_payments_field_submission_id",
            "field_submissions",
            ["field_submission_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_payments_field_submission_id", ["field_submission_id"])


def downgrade() -> None:
    with op.batch_alter_table("payments", schema=None) as batch_op:
        batch_op.drop_index("ix_payments_field_submission_id")
        batch_op.drop_constraint("fk_payments_field_submission_id", type_="foreignkey")
        batch_op.drop_column("field_submission_id")

    with op.batch_alter_table("policies", schema=None) as batch_op:
        batch_op.drop_index("ix_policies_field_submission_id")
        batch_op.drop_constraint("fk_policies_field_submission_id", type_="foreignkey")
        batch_op.drop_column("field_submission_id")

    with op.batch_alter_table("customers", schema=None) as batch_op:
        batch_op.drop_column("id_photo_path")

    with op.batch_alter_table("beneficiaries", schema=None) as batch_op:
        for column in ("email", "nationality", "date_of_birth", "gender", "title"):
            batch_op.drop_column(column)

    op.drop_index("ix_field_submissions_client_uuid", table_name="field_submissions")
    op.drop_index("ix_field_submissions_device_id", table_name="field_submissions")
    op.drop_table("field_submissions")
    op.drop_index("ix_device_enrollment_codes_code", table_name="device_enrollment_codes")
    op.drop_table("device_enrollment_codes")
    op.drop_table("devices")

    bind = op.get_bind()
    field_submission_status_enum.drop(bind, checkfirst=True)
    device_status_enum.drop(bind, checkfirst=True)
