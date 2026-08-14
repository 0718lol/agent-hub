"""Persist conversation and message UI metadata.

Revision ID: e8c92d07b1fa
Revises: c21a8f309e6d
"""

from alembic import op
import sqlalchemy as sa

revision: str = "e8c92d07b1fa"
down_revision: str | None = "c21a8f309e6d"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    conversation_columns = _columns("conversations")
    if "pinned" not in conversation_columns:
        op.add_column("conversations", sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.false()))
    if "archived" not in conversation_columns:
        op.add_column("conversations", sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()))
    if "sort_order" not in conversation_columns:
        op.add_column("conversations", sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"))
    if "updated_at" not in conversation_columns:
        op.add_column("conversations", sa.Column("updated_at", sa.String(), nullable=True))
        op.execute("UPDATE conversations SET updated_at = created_at WHERE updated_at IS NULL")
    if "pinned" not in _columns("messages"):
        op.add_column("messages", sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("messages", "pinned")
    op.drop_column("conversations", "updated_at")
    op.drop_column("conversations", "sort_order")
    op.drop_column("conversations", "archived")
    op.drop_column("conversations", "pinned")
