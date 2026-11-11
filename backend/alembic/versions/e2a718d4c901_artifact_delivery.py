"""Persist artifact lineage and deployment input snapshots."""
import hashlib

from alembic import op
import sqlalchemy as sa
from sqlmodel import SQLModel

import app.core.models  # noqa: F401

revision = 'e2a718d4c901'
down_revision = 'b6f3920ad4e1'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    columns = {c['name'] for c in sa.inspect(bind).get_columns('artifacts')}
    for name, kind, default, nullable in (
        ('version', sa.Integer(), '1', False),
        ('parent_id', sa.Integer(), None, True),
        ('content_hash', sa.String(), '', False),
    ):
        if name not in columns:
            op.add_column('artifacts', sa.Column(name, kind, server_default=default, nullable=nullable))
    previous = {}
    for row in bind.execute(sa.text('SELECT id,conversation_id,name,code FROM artifacts ORDER BY created_at,id')).mappings().all():
        key = (row['conversation_id'], row['name'])
        parent, version = previous.get(key, (None, 0))
        bind.execute(sa.text('UPDATE artifacts SET version=:version,parent_id=:parent,content_hash=:hash WHERE id=:id'),
            {'id':row['id'],'version':version+1,'parent':parent,'hash':hashlib.sha256(row['code'].encode()).hexdigest()})
        previous[key] = (row['id'], version+1)
    SQLModel.metadata.create_all(bind)


def downgrade():
    op.drop_table('delivery_records')
    op.drop_table('delivery_snapshots')
    with op.batch_alter_table('artifacts') as batch:
        batch.drop_column('content_hash')
        batch.drop_column('parent_id')
        batch.drop_column('version')
