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
                       char_count: int = 0):
    with Session(_engine_mod.engine) as session:
        doc = KnowledgeDoc(
            id=doc_id,
            filename=filename,
            file_path=file_path,
            content_type=content_type,
            chunk_count=chunk_count,
            char_count=char_count,
            status="ready"
        )
        session.merge(doc)
        session.commit()


def get_knowledge_docs() -> list[dict]:
    with Session(_engine_mod.engine) as session:
        statement = select(KnowledgeDoc).order_by(
            KnowledgeDoc.created_at.desc()
        )
        results = session.exec(statement).all()
        return [row.model_dump() for row in results]


@db_write_transaction
def delete_knowledge_doc(doc_id: str):
    with Session(_engine_mod.engine) as session:
        doc = session.get(KnowledgeDoc, doc_id)
        if doc:
            session.delete(doc)
            session.commit()
