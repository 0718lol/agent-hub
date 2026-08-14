"""Restore model tables missing from an already-versioned database."""

from collections.abc import Sequence

from alembic import op
from sqlmodel import SQLModel

import app.core.models  # noqa: F401

revision: str = "d184a60a53f2"
down_revision: str | None = "a92f5c11d744"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    SQLModel.metadata.create_all(op.get_bind())


def downgrade() -> None:
    pass
