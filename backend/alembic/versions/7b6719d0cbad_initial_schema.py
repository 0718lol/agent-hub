"""Create the AgentHub schema.

Revision ID: 7b6719d0cbad
Revises:
"""

from collections.abc import Sequence

from alembic import op
from sqlmodel import SQLModel

# Importing models registers every table on SQLModel.metadata.
import app.core.models  # noqa: F401

revision: str = "7b6719d0cbad"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    SQLModel.metadata.create_all(op.get_bind())


def downgrade() -> None:
    SQLModel.metadata.drop_all(op.get_bind())
