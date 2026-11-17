"""Add explicit indexed tenant_id columns and persistent deployment_records table.

Revision ID: 9c41e7b20a15
Revises: b6f3920ad4e1
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9c41e7b20a15"
down_revision: str | None = "b6f3920ad4e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TENANT_CONV_PREFIX = "tenant__"
_TENANT_CONV_SEP = "__conv__"
_TENANT_FILE_PREFIX = "tenantfile__"


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table: str) -> set[str]:
    if table not in _tables():
        return set()
    return {col["name"] for col in sa.inspect(op.get_bind()).get_columns(table)}


def _indexes(table: str) -> set[str]:
    if table not in _tables():
        return set()
    return {idx["name"] for idx in sa.inspect(op.get_bind()).get_indexes(table)}


def _extract_conv_tenant(conversation_id: str | None) -> str:
    if not conversation_id:
        return "local"
    if conversation_id.startswith(_TENANT_CONV_PREFIX) and _TENANT_CONV_SEP in conversation_id:
        tenant = conversation_id[len(_TENANT_CONV_PREFIX):].split(_TENANT_CONV_SEP, 1)[0]
        if tenant:
            return tenant
    return "local"


def _extract_file_tenant(stored_name: str | None) -> str:
    if not stored_name or not stored_name.startswith(_TENANT_FILE_PREFIX):
        return "local"
    rest = stored_name[len(_TENANT_FILE_PREFIX):]
    if "__" in rest:
        tenant = rest.split("__", 1)[0]
        if tenant:
            return tenant
    return "local"


def _ensure_column_and_index(table: str, column: str = "tenant_id", default: str = "local") -> None:
    if table not in _tables():
        return
    if column not in _columns(table):
        op.add_column(
            table,
            sa.Column(column, sa.String(), nullable=False, server_default=default),
        )
    idx_name = f"ix_{table}_{column}"
    if idx_name not in _indexes(table):
        op.create_index(idx_name, table, [column])


def upgrade() -> None:
    tables = _tables()

    # 1. Ensure workbench & artifact lineage columns exist before tenant backfill
    if "conversations" in tables:
        conv_cols = _columns("conversations")
        if "workspace_path" not in conv_cols:
            op.add_column("conversations", sa.Column("workspace_path", sa.String(), nullable=True))
        if "source_project_id" not in conv_cols:
            op.add_column("conversations", sa.Column("source_project_id", sa.String(), nullable=True))

    if "artifacts" in tables:
        art_cols = _columns("artifacts")
        if "version" not in art_cols:
            op.add_column("artifacts", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
        if "parent_id" not in art_cols:
            op.add_column("artifacts", sa.Column("parent_id", sa.Integer(), nullable=True))
        if "content_hash" not in art_cols:
            op.add_column("artifacts", sa.Column("content_hash", sa.String(), nullable=False, server_default=""))

    if "delivery_records" not in tables:
        op.create_table(
            "delivery_records",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("tenant_id", sa.String(), nullable=False, server_default="local"),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("conversation_id", sa.String(), nullable=False),
            sa.Column("payload", sa.String(), nullable=False),
            sa.Column("created_at", sa.String(), nullable=False),
        )
        op.create_index("ix_delivery_records_tenant_id", "delivery_records", ["tenant_id"])
        op.create_index("ix_delivery_records_user_id", "delivery_records", ["user_id"])
        op.create_index("ix_delivery_records_conversation_id", "delivery_records", ["conversation_id"])
        op.create_index("ix_delivery_records_created_at", "delivery_records", ["created_at"])

    # 2. Add explicit indexed tenant_id column across domain tables
    for tbl in (
        "conversations",
        "messages",
        "artifacts",
        "cron_tasks",
        "uploaded_files",
        "delivery_records",
    ):
        _ensure_column_and_index(tbl, "tenant_id", "local")

    # 3. Create persistent deployment_records table
    if "deployment_records" not in _tables():
        op.create_table(
            "deployment_records",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("tenant_id", sa.String(), nullable=False, server_default="local"),
            sa.Column("user_id", sa.String(), nullable=False, server_default="local"),
            sa.Column("conversation_id", sa.String(), nullable=False),
            sa.Column("target", sa.String(), nullable=False),
            sa.Column("action", sa.String(), nullable=False, server_default="deploy"),
            sa.Column("source_job_id", sa.String(), nullable=False, server_default=""),
            sa.Column("status", sa.String(), nullable=False, server_default="queued"),
            sa.Column("stage", sa.String(), nullable=False, server_default="queued"),
            sa.Column("progress", sa.Integer(), nullable=False, server_default="5"),
            sa.Column("url", sa.String(), nullable=False, server_default=""),
            sa.Column("result_type", sa.String(), nullable=False, server_default=""),
            sa.Column("provider", sa.String(), nullable=False, server_default=""),
            sa.Column("published", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("lifecycle", sa.String(), nullable=False, server_default="active"),
            sa.Column("log", sa.String(), nullable=False, server_default=""),
            sa.Column("created_at", sa.String(), nullable=False),
            sa.Column("updated_at", sa.String(), nullable=False),
        )
        op.create_index("ix_deployment_records_tenant_id", "deployment_records", ["tenant_id"])
        op.create_index("ix_deployment_records_user_id", "deployment_records", ["user_id"])
        op.create_index("ix_deployment_records_conversation_id", "deployment_records", ["conversation_id"])
        op.create_index("ix_deployment_records_status", "deployment_records", ["status"])
        op.create_index("ix_deployment_records_created_at", "deployment_records", ["created_at"])

    # 4. Backfill existing legacy prefixed rows deterministically (SQLite & PostgreSQL safe)
    bind = op.get_bind()
    current_tables = _tables()

    conv_tenant_map: dict[str, str] = {}
    if "conversations" in current_tables:
        rows = bind.execute(sa.text("SELECT id, tenant_id FROM conversations")).fetchall()
        for conv_id, existing_tid in rows:
            inferred = _extract_conv_tenant(conv_id)
            final_tid = inferred if inferred != "local" else (existing_tid or "local")
            conv_tenant_map[conv_id] = final_tid
            if final_tid != existing_tid:
                bind.execute(
                    sa.text("UPDATE conversations SET tenant_id = :tid WHERE id = :cid"),
                    {"tid": final_tid, "cid": conv_id},
                )

    for child_table in ("messages", "artifacts", "cron_tasks"):
        if child_table not in current_tables:
            continue
        rows = bind.execute(
            sa.text(f"SELECT DISTINCT conversation_id FROM {child_table} WHERE tenant_id = 'local'")  # noqa: S608
        ).fetchall()
        for (conv_id,) in rows:
            tid = conv_tenant_map.get(conv_id) or _extract_conv_tenant(conv_id)
            if tid and tid != "local":
                bind.execute(
                    sa.text(
                        f"UPDATE {child_table} SET tenant_id = :tid WHERE conversation_id = :cid"  # noqa: S608
                    ),
                    {"tid": tid, "cid": conv_id},
                )

    if "uploaded_files" in current_tables:
        rows = bind.execute(
            sa.text("SELECT id, stored_name, tenant_id FROM uploaded_files")
        ).fetchall()
        for file_id, stored_name, existing_tid in rows:
            tid = _extract_file_tenant(stored_name)
            if tid == "local":
                tid = _extract_file_tenant(file_id)
            if tid != "local" and tid != existing_tid:
                bind.execute(
                    sa.text("UPDATE uploaded_files SET tenant_id = :tid WHERE id = :fid"),
                    {"tid": tid, "fid": file_id},
                )

    if "delivery_records" in current_tables:
        bind.execute(
            sa.text(
                "UPDATE delivery_records SET tenant_id = user_id "
                "WHERE (tenant_id = 'local' OR tenant_id = '') AND user_id IS NOT NULL AND user_id != ''"
            )
        )


def downgrade() -> None:
    if "deployment_records" in _tables():
        op.drop_table("deployment_records")
