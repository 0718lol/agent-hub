"""Add lightweight goal snapshots to conversations.

Revision ID: b6f3920ad4e1
Revises: e8c92d07b1fa
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b6f3920ad4e1"
down_revision: str | None = "e8c92d07b1fa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _columns() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if "conversations" not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns("conversations")}


def upgrade() -> None:
    columns = _columns()
    additions = (
        ("goal_objective", sa.String(), True, None),
        ("goal_stage", sa.String(), False, "not_started"),
        ("goal_latest_deliverable", sa.String(), True, None),
        ("goal_latest_artifact_id", sa.Integer(), True, None),
        ("goal_pending_decision", sa.String(), True, None),
        ("goal_next_action", sa.String(), True, None),
    )
    for name, column_type, nullable, default in additions:
        if name in columns:
            continue
        kwargs = {"nullable": nullable}
        if default is not None:
            kwargs["server_default"] = default
        op.add_column("conversations", sa.Column(name, column_type, **kwargs))


def downgrade() -> None:
    columns = _columns()
    with op.batch_alter_table("conversations") as batch_op:
        for name in (
            "goal_next_action",
            "goal_pending_decision",
            "goal_latest_artifact_id",
            "goal_latest_deliverable",
            "goal_stage",
            "goal_objective",
        ):
            if name in columns:
                batch_op.drop_column(name)
