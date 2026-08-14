"""Add stable local accounts and level-one tenants."""

from collections.abc import Sequence

from alembic import op
from sqlmodel import SQLModel

import app.core.models  # noqa: F401

revision: str = "c21a8f309e6d"
down_revision: str | None = "f48c2d91a6b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    SQLModel.metadata.create_all(op.get_bind())


def downgrade() -> None:
    # Account removal is intentionally manual so a downgrade cannot orphan tenant data.
    pass
