"""Add tenant ownership to custom agents and knowledge resources.

Revision ID: f48c2d91a6b0
Revises: d184a60a53f2
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f48c2d91a6b0"
down_revision: str | None = "d184a60a53f2"
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
    for table in ("custom_agents", "knowledge_docs"):
        if table in tables and "user_id" not in _columns(table):
            op.add_column(
                table,
                sa.Column("user_id", sa.String(), nullable=False, server_default="legacy"),
            )
        index_name = f"ix_{table}_user_id"
        if table in tables and index_name not in _indexes(table):
            op.create_index(index_name, table, ["user_id"])

    if "knowledge_bases" not in tables:
        op.create_table(
            "knowledge_bases",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("description", sa.String(), nullable=False, server_default=""),
            sa.Column("created_at", sa.String(), nullable=False),
        )
        op.create_index("ix_knowledge_bases_user_id", "knowledge_bases", ["user_id"])

    # Preserve legacy document groupings even when the old JSON metadata file
    # is unavailable to the migration process.
    if "knowledge_docs" in _tables():
        bind = op.get_bind()
        rows = bind.execute(sa.text(
            "SELECT DISTINCT knowledge_base_id FROM knowledge_docs "
            "WHERE knowledge_base_id IS NOT NULL"
        )).fetchall()
        for (knowledge_base_id,) in rows:
            exists = bind.execute(
                sa.text("SELECT 1 FROM knowledge_bases WHERE id = :id"),
                {"id": knowledge_base_id},
            ).first()
            if not exists:
                bind.execute(
                    sa.text(
                        "INSERT INTO knowledge_bases "
                        "(id, user_id, name, description, created_at) "
                        "VALUES (:id, 'legacy', :name, '', '1970-01-01T00:00:00+00:00')"
                    ),
                    {"id": knowledge_base_id, "name": knowledge_base_id},
                )


def downgrade() -> None:
    tables = _tables()
    if "knowledge_bases" in tables:
        op.drop_table("knowledge_bases")
    for table in ("knowledge_docs", "custom_agents"):
        if table not in tables or "user_id" not in _columns(table):
            continue
        index_name = f"ix_{table}_user_id"
        if index_name in _indexes(table):
            op.drop_index(index_name, table_name=table)
        with op.batch_alter_table(table) as batch:
            batch.drop_column("user_id")
