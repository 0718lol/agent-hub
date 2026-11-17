"""
Uploaded File CRUD operations.

Handles saving, retrieving, and listing files uploaded by users.
"""
from sqlmodel import Session, select

import app.core._engine as _engine_mod
from app.core.crud.utils import db_write_transaction
from app.core.models import UploadedFile
from app.core.tenancy import infer_tenant_id


def _infer_upload_tenant(stored_name: str, tenant_id: str | None) -> str:
    if tenant_id and tenant_id.strip():
        return tenant_id.strip()
    if stored_name.startswith("tenantfile__") and "__" in stored_name[len("tenantfile__"):]:
        extracted = stored_name[len("tenantfile__"):].split("__", 1)[0]
        if extracted:
            return extracted
    return infer_tenant_id(None, None)


@db_write_transaction
def save_uploaded_file(file_id: str, original_name: str, stored_name: str,
                       file_path: str, content_type: str = "", size: int = 0,
                       extracted_text: str = "", tenant_id: str | None = None):
    resolved_tenant = _infer_upload_tenant(stored_name or file_id, tenant_id)
    with Session(_engine_mod.engine) as session:
        file = UploadedFile(
            id=file_id,
            tenant_id=resolved_tenant,
            original_name=original_name,
            stored_name=stored_name,
            file_path=file_path,
            content_type=content_type,
            size=size,
            extracted_text=extracted_text,
        )
        session.merge(file)
        session.commit()


def get_uploaded_file(file_id: str, tenant_id: str | None = None) -> dict | None:
    with Session(_engine_mod.engine) as session:
        file = session.get(UploadedFile, file_id)
        if file is None:
            return None
        if tenant_id is not None and file.tenant_id != tenant_id:
            return None
        return file.model_dump()


def get_all_uploaded_files(tenant_id: str | None = None) -> list[dict]:
    with Session(_engine_mod.engine) as session:
        statement = select(UploadedFile)
        if tenant_id is not None:
            statement = statement.where(UploadedFile.tenant_id == tenant_id)
        statement = statement.order_by(UploadedFile.uploaded_at.desc())
        results = session.exec(statement).all()
        return [row.model_dump() for row in results]
