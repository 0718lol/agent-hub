"""Add tenant settings and the knowledge-base document relation.

Revision ID: a92f5c11d744
Revises: 7b6719d0cbad
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a92f5c11d744"
down_revision: str | None = "7b6719d0cbad"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def _indexes(table: str) -> set[str]:
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table)}


def upgrade() -> None:
    tables = _tables()
    if "tenant_configs" not in tables:
        op.create_table(
            "tenant_configs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("key", sa.String(), nullable=False),
            sa.Column("value", sa.String(), nullable=False),
            sa.Column("updated_at", sa.String(), nullable=False),
            sa.UniqueConstraint("user_id", "key", name="idx_tenant_config_key"),
        )
        op.create_index("ix_tenant_configs_user_id", "tenant_configs", ["user_id"])

    if "knowledge_docs" in tables and "knowledge_base_id" not in _columns("knowledge_docs"):
        op.add_column("knowledge_docs", sa.Column("knowledge_base_id", sa.String(), nullable=True))
    if "knowledge_docs" in tables and "ix_knowledge_docs_knowledge_base_id" not in _indexes("knowledge_docs"):
        op.create_index(
            "ix_knowledge_docs_knowledge_base_id",
            "knowledge_docs",
            ["knowledge_base_id"],
        )


def downgrade() -> None:
    tables = _tables()
    if "knowledge_docs" in tables and "knowledge_base_id" in _columns("knowledge_docs"):
        if "ix_knowledge_docs_knowledge_base_id" in _indexes("knowledge_docs"):
            op.drop_index("ix_knowledge_docs_knowledge_base_id", table_name="knowledge_docs")
        with op.batch_alter_table("knowledge_docs") as batch:
            batch.drop_column("knowledge_base_id")
    if "tenant_configs" in tables:
        op.drop_table("tenant_configs")
