"""
Minimal engine module to break the circular dependency between database.py and crud.py.

Both database.py and crud.py import ``engine`` from here.
"""
import logging as _logging
import os

from sqlalchemy import event
from sqlmodel import create_engine

_db_logger = _logging.getLogger("database._engine")

_DEFAULT_DB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'agenthub.db')
DB_PATH = os.path.abspath(os.path.expanduser(os.environ.get('AGENTHUB_DB_PATH', _DEFAULT_DB_PATH)))

db_url = os.environ.get('DATABASE_URL')
if db_url:
    if db_url.startswith('postgres://'):
        db_url = db_url.replace('postgres://', 'postgresql://', 1)
    engine = create_engine(db_url)
else:
    engine = create_engine(
        f'sqlite:///{DB_PATH}',
        connect_args={
            'check_same_thread': False,
            'timeout': 30.0
        }
    )

    @event.listens_for(engine, 'connect')
    def set_sqlite_pragma(dbapi_connection, connection_record):
        try:
            cursor = dbapi_connection.cursor()
            cursor.execute('PRAGMA journal_mode=WAL;')
            cursor.execute('PRAGMA synchronous=NORMAL;')
            cursor.close()
        except Exception as e:
            _db_logger.warning(f"Failed to set SQLite PRAGMA (connect event): {e}")
