"""
Knowledge Base Document CRUD operations.

Handles saving, listing, and deleting knowledge base documents used for
retrieval-augmented generation.
"""
from sqlmodel import Session, select

import app.core._engine as _engine_mod
from app.core.crud.utils import db_write_transaction
from app.core.models import KnowledgeDoc


@db_write_transaction
def save_knowledge_doc(doc_id: str, filename: str, file_path: str = "",
                       content_type: str = "", chunk_count: int = 0,
                       char_count: int = 0, user_id: str = "legacy",
                       knowledge_base_id: str | None = None):
    with Session(_engine_mod.engine) as session:
        doc = KnowledgeDoc(
            id=doc_id,
            user_id=user_id,
            filename=filename,
            file_path=file_path,
            content_type=content_type,
            chunk_count=chunk_count,
            char_count=char_count,
            status="ready",
            knowledge_base_id=knowledge_base_id,
        )
        session.merge(doc)
        session.commit()


def get_knowledge_docs(user_id: str | None = None) -> list[dict]:
    with Session(_engine_mod.engine) as session:
        statement = select(KnowledgeDoc).order_by(
            KnowledgeDoc.created_at.desc()
        )
        if user_id is not None:
            statement = statement.where(KnowledgeDoc.user_id == user_id)
        results = session.exec(statement).all()
        return [row.model_dump() for row in results]


@db_write_transaction
def delete_knowledge_doc(doc_id: str, user_id: str | None = None) -> bool:
    with Session(_engine_mod.engine) as session:
        statement = select(KnowledgeDoc).where(KnowledgeDoc.id == doc_id)
        if user_id is not None:
            statement = statement.where(KnowledgeDoc.user_id == user_id)
        doc = session.exec(statement).first()
        if doc:
            session.delete(doc)
            session.commit()
            return True
        return False
