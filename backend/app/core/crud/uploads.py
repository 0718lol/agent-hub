"""
Uploaded File CRUD operations.

Handles saving, retrieving, and listing files uploaded by users.
"""
from sqlmodel import Session, select

import app.core._engine as _engine_mod
from app.core.crud.utils import db_write_transaction
from app.core.models import UploadedFile


@db_write_transaction
def save_uploaded_file(file_id: str, original_name: str, stored_name: str,
                       file_path: str, content_type: str = "", size: int = 0,
                       extracted_text: str = ""):
    with Session(_engine_mod.engine) as session:
        file = UploadedFile(
            id=file_id,
            original_name=original_name,
            stored_name=stored_name,
            file_path=file_path,
            content_type=content_type,
            size=size,
            extracted_text=extracted_text
        )
        session.merge(file)
        session.commit()


def get_uploaded_file(file_id: str) -> dict | None:
    with Session(_engine_mod.engine) as session:
        file = session.get(UploadedFile, file_id)
        return file.model_dump() if file else None


def get_all_uploaded_files() -> list[dict]:
    with Session(_engine_mod.engine) as session:
        statement = select(UploadedFile).order_by(
            UploadedFile.uploaded_at.desc()
        )
        results = session.exec(statement).all()
        return [row.model_dump() for row in results]
