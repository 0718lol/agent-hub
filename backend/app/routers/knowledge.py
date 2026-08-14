"""Tenant-scoped knowledge base CRUD, ingestion, and semantic search."""

import asyncio
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.core._engine import engine
from app.core.models import KnowledgeBase, KnowledgeDoc
from app.core.tenancy import request_user_id

logger = logging.getLogger("knowledge_router")
router = APIRouter(tags=["knowledge"])


class KnowledgeBaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)


class KnowledgeBaseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)


class KnowledgeQuery(BaseModel):
    query: str = Field(min_length=1, max_length=10_000)
    top_k: int = Field(default=5, ge=1, le=20)


def _collection_name(user_id: str, kb_id: str) -> str:
    from app.core.rag_engine import tenant_collection_name
    return tenant_collection_name(user_id, kb_id)


def _base_for_user(session: Session, user_id: str, kb_id: str) -> KnowledgeBase | None:
    return session.exec(
        select(KnowledgeBase)
        .where(KnowledgeBase.id == kb_id)
        .where(KnowledgeBase.user_id == user_id)
    ).first()


def _require_base(session: Session, user_id: str, kb_id: str) -> KnowledgeBase | None:
    if kb_id == "__default__":
        return None
    knowledge_base = _base_for_user(session, user_id, kb_id)
    if knowledge_base is None:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    return knowledge_base


def _docs_for_base(session: Session, user_id: str, kb_id: str) -> list[KnowledgeDoc]:
    statement = select(KnowledgeDoc).where(KnowledgeDoc.user_id == user_id)
    if kb_id == "__default__":
        statement = statement.where(KnowledgeDoc.knowledge_base_id.is_(None))
    else:
        statement = statement.where(KnowledgeDoc.knowledge_base_id == kb_id)
    return list(session.exec(statement.order_by(KnowledgeDoc.created_at.desc())).all())


def _stats(session: Session, user_id: str) -> dict:
    bases = session.exec(
        select(KnowledgeBase).where(KnowledgeBase.user_id == user_id)
    ).all()
    docs = session.exec(
        select(KnowledgeDoc).where(KnowledgeDoc.user_id == user_id)
    ).all()
    return {
        "total_bases": len(bases),
        "total_docs": len(docs),
        "total_chunks": sum(doc.chunk_count for doc in docs),
    }


def _delete_file(doc: KnowledgeDoc) -> None:
    if not doc.file_path:
        return
    try:
        from app.core.file_storage import FileStorageManager
        FileStorageManager.delete(Path(doc.file_path).name)
    except OSError as exc:
        logger.warning("Failed to delete knowledge file %s: %s", doc.id, exc)


def _delete_from_chroma(collection_name: str, doc_id: str) -> None:
    from app.core.rag_engine import _get_or_create_collection

    collection = _get_or_create_collection(collection_name)
    results = collection.get(where={"doc_id": doc_id})
    if results and results.get("ids"):
        collection.delete(ids=results["ids"])


def _search_collection(collection_name: str, query: str, top_k: int) -> list[dict]:
    from app.core.rag_engine import _get_or_create_collection

    collection = _get_or_create_collection(collection_name)
    count = collection.count()
    if count == 0:
        return []
    results = collection.query(query_texts=[query], n_results=min(top_k, count))
    documents = results.get("documents", [[]])[0]
    distances = results.get("distances", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    return [
        {
            "text": document,
            "score": round(1 - (distances[index] if index < len(distances) else 0), 3),
            "metadata": metadatas[index] if index < len(metadatas) else {},
        }
        for index, document in enumerate(documents)
    ]


@router.get("/knowledge")
def list_knowledge_bases(request: Request):
    """List only the current tenant's bases and retain the legacy UI payload."""
    user_id = request_user_id(request)
    with Session(engine) as session:
        bases = session.exec(
            select(KnowledgeBase)
            .where(KnowledgeBase.user_id == user_id)
            .order_by(KnowledgeBase.created_at.asc())
        ).all()
        summaries = []
        for knowledge_base in bases:
            docs = _docs_for_base(session, user_id, knowledge_base.id)
            summaries.append({
                "id": knowledge_base.id,
                "name": knowledge_base.name,
                "description": knowledge_base.description,
                "created_at": knowledge_base.created_at,
                "doc_count": len(docs),
                "total_chunks": sum(doc.chunk_count for doc in docs),
                "total_chars": sum(doc.char_count for doc in docs),
            })
        default_docs = _docs_for_base(session, user_id, "__default__")
        if default_docs:
            summaries.insert(0, {
                "id": "__default__",
                "name": "默认知识库",
                "description": "未指定知识库时使用",
                "created_at": "",
                "doc_count": len(default_docs),
                "total_chunks": sum(doc.chunk_count for doc in default_docs),
                "total_chars": sum(doc.char_count for doc in default_docs),
            })
        stats = _stats(session, user_id)
        return {
            "status": "ok",
            "bases": summaries,
            "docs": [doc.model_dump(exclude={"user_id"}) for doc in default_docs],
            "stats": stats,
        }


@router.post("/knowledge")
def create_knowledge_base(body: KnowledgeBaseCreate, request: Request):
    user_id = request_user_id(request)
    knowledge_base = KnowledgeBase(
        id=f"kb_{uuid.uuid4().hex[:12]}",
        user_id=user_id,
        name=body.name.strip(),
        description=body.description.strip(),
    )
    with Session(engine) as session:
        session.add(knowledge_base)
        session.commit()
    try:
        from app.core.rag_engine import _get_or_create_collection
        _get_or_create_collection(_collection_name(user_id, knowledge_base.id))
    except Exception as exc:
        logger.warning("Failed to initialize knowledge collection: %s", exc)
    return {"status": "created", "id": knowledge_base.id, "name": knowledge_base.name}


@router.get("/knowledge/stats")
def knowledge_stats(request: Request):
    with Session(engine) as session:
        return _stats(session, request_user_id(request))


@router.post("/knowledge/upload")
async def upload_default_knowledge_file(request: Request, file: UploadFile = File(...)):
    result = await _upload_file("__default__", request_user_id(request), file)
    return {"status": "ok", **result}


@router.post("/knowledge/query")
def query_default_knowledge(body: KnowledgeQuery, request: Request):
    user_id = request_user_id(request)
    try:
        results = _search_collection(
            _collection_name(user_id, "__default__"), body.query, body.top_k
        )
    except Exception as exc:
        logger.warning("Default knowledge search failed: %s", exc)
        results = []
    return {"status": "ok", "results": results}


@router.get("/knowledge/{kb_id}")
def get_knowledge_base(kb_id: str, request: Request):
    user_id = request_user_id(request)
    with Session(engine) as session:
        knowledge_base = _require_base(session, user_id, kb_id)
        docs = _docs_for_base(session, user_id, kb_id)
        return {
            "id": kb_id,
            "name": knowledge_base.name if knowledge_base else "默认知识库",
            "description": knowledge_base.description if knowledge_base else "未指定知识库时使用",
            "created_at": knowledge_base.created_at if knowledge_base else "",
            "docs": [doc.model_dump(exclude={"user_id"}) for doc in docs],
        }


@router.put("/knowledge/{kb_id}")
def update_knowledge_base(kb_id: str, body: KnowledgeBaseUpdate, request: Request):
    if kb_id == "__default__":
        raise HTTPException(status_code=400, detail="Cannot rename default knowledge base")
    with Session(engine) as session:
        knowledge_base = _require_base(session, request_user_id(request), kb_id)
        if body.name is not None:
            knowledge_base.name = body.name.strip()
        if body.description is not None:
            knowledge_base.description = body.description.strip()
        session.add(knowledge_base)
        session.commit()
        return {"status": "updated", "id": kb_id, "name": knowledge_base.name}


@router.delete("/knowledge/{kb_id}")
def delete_knowledge_base(kb_id: str, request: Request):
    if kb_id == "__default__":
        raise HTTPException(status_code=400, detail="Cannot delete default knowledge base")
    user_id = request_user_id(request)
    collection_name = _collection_name(user_id, kb_id)
    with Session(engine) as session:
        knowledge_base = _require_base(session, user_id, kb_id)
        docs = _docs_for_base(session, user_id, kb_id)
        for doc in docs:
            _delete_file(doc)
            session.delete(doc)
        session.delete(knowledge_base)
        session.commit()
    try:
        from app.core.rag_engine import _get_chroma_client
        _get_chroma_client().delete_collection(collection_name)
    except Exception as exc:
        logger.debug("Knowledge collection cleanup skipped: %s", exc)
    return {"status": "deleted", "id": kb_id}


def _validate_knowledge_base(kb_id: str, user_id: str) -> None:
    with Session(engine) as session:
        _require_base(session, user_id, kb_id)


def _index_knowledge_file(
    kb_id: str,
    user_id: str,
    filename: str,
    content_type: str,
    content: bytes,
) -> dict:
    from app.core.document_parser import DocumentParser
    from app.core.file_storage import FileStorageManager
    from app.core.rag_engine import _get_or_create_collection, split_text

    with Session(engine) as session:
        _require_base(session, user_id, kb_id)
    if not DocumentParser.is_supported(filename):
        supported = ", ".join(DocumentParser.SUPPORTED_EXTENSIONS)
        raise HTTPException(status_code=400, detail=f"不支持的文件类型，支持: {supported}")

    suffix = Path(filename).suffix.lower()
    stored_name = f"tenantfile__{user_id}__kb_{uuid.uuid4().hex}{suffix}"
    doc = None
    collection_name = _collection_name(user_id, kb_id)
    try:
        file_path = FileStorageManager.save(content, stored_name)
        text = DocumentParser.extract_text(file_path)
        chunks = split_text(text)
        if not chunks:
            raise HTTPException(status_code=400, detail="文件内容为空或无法分块")
        doc = KnowledgeDoc(
            id=f"doc_{uuid.uuid4().hex[:12]}",
            user_id=user_id,
            filename=filename,
            file_path=file_path,
            content_type=content_type,
            chunk_count=len(chunks),
            char_count=len(text),
            knowledge_base_id=None if kb_id == "__default__" else kb_id,
        )
        collection = _get_or_create_collection(collection_name)
        collection.add(
            ids=[f"{doc.id}_chunk_{index}" for index in range(len(chunks))],
            documents=chunks,
            metadatas=[
                {"doc_id": doc.id, "filename": filename, "chunk_index": index, "user_id": user_id}
                for index in range(len(chunks))
            ],
        )
        with Session(engine) as session:
            session.add(doc)
            session.commit()
    except HTTPException:
        try:
            FileStorageManager.delete(stored_name)
        except Exception:
            pass
        raise
    except Exception as exc:
        if doc is not None:
            try:
                _delete_from_chroma(collection_name, doc.id)
            except Exception:
                pass
        try:
            FileStorageManager.delete(stored_name)
        except Exception:
            pass
        raise HTTPException(status_code=503, detail="Knowledge indexing failed") from exc
    return {
        "doc_id": doc.id,
        "filename": filename,
        "chunk_count": len(chunks),
        "char_count": len(text),
    }


async def _upload_file(kb_id: str, user_id: str, file: UploadFile) -> dict:
    from app.core.config import settings
    from app.core.upload_security import UploadLimitExceeded, read_upload_limited

    await asyncio.to_thread(_validate_knowledge_base, kb_id, user_id)
    try:
        content = await read_upload_limited(file, settings.knowledge_upload_max_bytes)
    except UploadLimitExceeded as exc:
        raise HTTPException(status_code=413, detail=f"File too large (max {exc.max_bytes} bytes)") from exc
    filename = Path(file.filename or "unnamed.txt").name
    return await asyncio.to_thread(
        _index_knowledge_file,
        kb_id,
        user_id,
        filename,
        file.content_type or "",
        content,
    )


@router.post("/knowledge/{kb_id}/files")
async def upload_file_to_kb(kb_id: str, request: Request, file: UploadFile = File(...)):
    return {"status": "uploaded", **await _upload_file(kb_id, request_user_id(request), file)}


@router.delete("/knowledge/{kb_id}/files/{doc_id}")
def delete_file_from_kb(kb_id: str, doc_id: str, request: Request):
    user_id = request_user_id(request)
    with Session(engine) as session:
        _require_base(session, user_id, kb_id)
        expected_base_id = None if kb_id == "__default__" else kb_id
        doc = session.exec(
            select(KnowledgeDoc)
            .where(KnowledgeDoc.id == doc_id)
            .where(KnowledgeDoc.user_id == user_id)
            .where(KnowledgeDoc.knowledge_base_id == expected_base_id)
        ).first()
        if doc is None:
            raise HTTPException(status_code=404, detail="Knowledge document not found")
        try:
            _delete_from_chroma(_collection_name(user_id, kb_id), doc.id)
        except Exception as exc:
            logger.warning("Knowledge vector cleanup failed for %s: %s", doc.id, exc)
        _delete_file(doc)
        session.delete(doc)
        session.commit()
    return {"status": "deleted", "doc_id": doc_id}


@router.post("/knowledge/{kb_id}/search")
def search_knowledge_base(kb_id: str, body: KnowledgeQuery, request: Request):
    user_id = request_user_id(request)
    with Session(engine) as session:
        _require_base(session, user_id, kb_id)
    try:
        hits = _search_collection(_collection_name(user_id, kb_id), body.query, body.top_k)
        return {"results": hits}
    except Exception as exc:
        logger.warning("Knowledge search failed for %s: %s", kb_id, exc)
        return {"results": [], "error": "Knowledge search is temporarily unavailable"}
