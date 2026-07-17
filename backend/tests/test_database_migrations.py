"""Alembic migration smoke tests for fresh and legacy databases."""

from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config


def _config(database_path: Path) -> Config:
    backend_root = Path(__file__).resolve().parents[1]
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    return config


def test_fresh_database_upgrades_to_current_schema(tmp_path: Path):
    database_path = tmp_path / "fresh.db"
    command.upgrade(_config(database_path), "head")

    engine = sa.create_engine(f"sqlite:///{database_path}")
    inspector = sa.inspect(engine)
    assert "tenant_configs" in inspector.get_table_names()
    assert "knowledge_base_id" in {
        column["name"] for column in inspector.get_columns("knowledge_docs")
    }
    with engine.connect() as connection:
        revision = connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalar()
    assert revision == "d184a60a53f2"


def test_legacy_database_receives_incremental_schema(tmp_path: Path):
    database_path = tmp_path / "legacy.db"
    engine = sa.create_engine(f"sqlite:///{database_path}")
    with engine.begin() as connection:
        connection.execute(sa.text(
            "CREATE TABLE knowledge_docs ("
            "id VARCHAR PRIMARY KEY, filename VARCHAR NOT NULL, file_path VARCHAR NOT NULL, "
            "content_type VARCHAR NOT NULL, chunk_count INTEGER NOT NULL, char_count INTEGER NOT NULL, "
            "status VARCHAR NOT NULL, created_at VARCHAR NOT NULL)"
        ))
        connection.execute(sa.text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"))
        connection.execute(sa.text(
            "INSERT INTO alembic_version (version_num) VALUES ('7b6719d0cbad')"
        ))

    command.upgrade(_config(database_path), "head")

    inspector = sa.inspect(engine)
    assert "tenant_configs" in inspector.get_table_names()
    assert "knowledge_base_id" in {
        column["name"] for column in inspector.get_columns("knowledge_docs")
    }
