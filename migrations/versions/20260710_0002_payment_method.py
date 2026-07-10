"""add payment method to walk requests

Revision ID: 20260710_0002
Revises: 20260709_0001
Create Date: 2026-07-10
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision = "20260710_0002"
down_revision = "20260709_0001"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    return {col["name"] for col in inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if "payment_method" not in _columns("walk_requests"):
        op.add_column("walk_requests", sa.Column("payment_method", sa.String(30), server_default="PIX"))
    op.execute(text("UPDATE walk_requests SET payment_method='PIX' WHERE payment_method IS NULL OR payment_method=''"))


def downgrade() -> None:
    if "payment_method" in _columns("walk_requests"):
        op.drop_column("walk_requests", "payment_method")
