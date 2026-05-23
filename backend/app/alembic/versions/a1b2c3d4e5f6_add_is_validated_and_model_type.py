"""add is_validated and model_type columns

Revision ID: a1b2c3d4e5f6
Revises: d313d1bb189d
Create Date: 2026-05-23 10:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "d313d1bb189d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("vital", sa.Column("is_validated", sa.Boolean(), nullable=False, server_default="true"))
    op.add_column("model_version", sa.Column("model_type", sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column("model_version", "model_type")
    op.drop_column("vital", "is_validated")
