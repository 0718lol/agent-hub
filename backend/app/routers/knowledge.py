"""Knowledge Base Router — 知识库 CRUD + 文件管理 + 检索。

支持多知识库，每个知识库对应一个 chromadb collection。
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlmodel import col, select

from app.core.database import (
    KnowledgeDoc,
    Session,
    delete_knowledge_doc,
    engine,
    save_knowledge_doc,
)

logger = logging.getLogger("knowledge_router")
router = APIRouter(tags=["knowledge"])

# 知识库元数据存储（简易方案：JSON 文件）
KB_META_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'knowledge_bases.json')


def _load_kb_meta() -> dict:
    try:
        if os.path.exists(KB_META_PATH):
            with open(KB_META_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_kb_meta(data: dict):
    os.makedirs(os.path.dirname(KB_META_PATH), exist_ok=True)
    with open(KB_META_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---- Request Models ----

class KnowledgeBaseCreate(BaseModel):
    name: str
    description: str = ""

class KnowledgeBaseUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class KnowledgeQuery(BaseModel):
    query: str
    top_k: int = 5


# ---- Knowledge Base CRUD ----

@router.get("/knowledge")
async def list_knowledge_bases():
    """列出所有知识库及其统计信息。"""
    meta = _load_kb_meta()
    bases = []
    for kb_id, info in meta.items():
        # 统计该知识库下的文档
        with Session(engine) as session:
            docs = session.exec(
                select(KnowledgeDoc).where(KnowledgeDoc.knowledge_base_id == kb_id)
            ).all()
            total_chunks = sum(d.chunk_count for d in docs)
            total_chars = sum(d.char_count for d in docs)
            bases.append({
                "id": kb_id,
                "name": info.get("name", kb_id),
                "description": info.get("description", ""),
                "created_at": info.get("created_at", ""),
                "doc_count": len(docs),
                "total_chunks": total_chunks,
                "total_chars": total_chars,
            })
    # 也统计没有 knowledge_base_id 的旧文档（归入"默认知识库"）
    with Session(engine) as session:
        orphan_docs = session.exec(
            select(KnowledgeDoc).where(KnowledgeDoc.knowledge_base_id.is_(None))
        ).all()
    if orphan_docs:
        bases.append({
            "id": "__default__",
            "name": "默认知识库",
            "description": "系统自动创建，包含早期上传的文档",
            "created_at": "",
            "doc_count": len(orphan_docs),
            "total_chunks": sum(d.chunk_count for d in orphan_docs),
            "total_chars": sum(d.char_count for d in orphan_docs),
        })
    return {"bases": bases}


@router.post("/knowledge")
async def create_knowledge_base(req: KnowledgeBaseCreate):
    """创建新知识库。"""
    kb_id = f"kb_{uuid.uuid4().hex[:8]}"
    meta = _load_kb_meta()
    meta[kb_id] = {
        "name": req.name,
        "description": req.description,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _save_kb_meta(meta)
    # 在 chromadb 中创建对应的 collection
    try:
        from app.core.rag_engine import _get_or_create_collection
        _get_or_create_collection(kb_id)
    except Exception as e:
        logger.warning(f"Failed to create chromadb collection for {kb_id}: {e}")
    return {"status": "created", "id": kb_id, "name": req.name}


@router.get("/knowledge/{kb_id}")
async def get_knowledge_base(kb_id: str):
    """获取知识库详情（含文档列表）。"""
    if kb_id == "__default__":
        # 默认知识库：返回没有 knowledge_base_id 的文档
        with Session(engine) as session:
            docs = session.exec(
                select(KnowledgeDoc).where(KnowledgeDoc.knowledge_base_id.is_(None))
            ).all()
        return {
            "id": "__default__",
            "name": "默认知识库",
            "description": "系统自动创建",
            "docs": [d.model_dump() for d in docs],
        }

    meta = _load_kb_meta()
    info = meta.get(kb_id)
    if not info:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    with Session(engine) as session:
        docs = session.exec(
            select(KnowledgeDoc).where(KnowledgeDoc.knowledge_base_id == kb_id)
        ).all()

    return {
        "id": kb_id,
        "name": info.get("name", kb_id),
        "description": info.get("description", ""),
        "created_at": info.get("created_at", ""),
        "docs": [d.model_dump() for d in docs],
    }


@router.put("/knowledge/{kb_id}")
async def update_knowledge_base(kb_id: str, req: KnowledgeBaseUpdate):
    """更新知识库名称或描述。"""
    if kb_id == "__default__":
        raise HTTPException(status_code=400, detail="Cannot rename default knowledge base")

    meta = _load_kb_meta()
    if kb_id not in meta:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    if req.name is not None:
        meta[kb_id]["name"] = req.name
    if req.description is not None:
        meta[kb_id]["description"] = req.description

    _save_kb_meta(meta)
    return {"status": "updated", "id": kb_id, "name": meta[kb_id]["name"]}


@router.delete("/knowledge/{kb_id}")
async def delete_knowledge_base(kb_id: str):
    """删除知识库及其所有文档。"""
    if kb_id == "__default__":
        raise HTTPException(status_code=400, detail="Cannot delete default knowledge base")

    meta = _load_kb_meta()
    if kb_id not in meta:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    # 删除该知识库下的所有文档
    with Session(engine) as session:
        docs = session.exec(
            select(KnowledgeDoc).where(KnowledgeDoc.knowledge_base_id == kb_id)
        ).all()
        for doc in docs:
            # 删除 chromadb 中的数据
            try:
                _delete_from_chroma(kb_id, doc.id)
            except Exception:
                pass
            # 删除文件
            if doc.file_path and os.path.exists(doc.file_path):
                try:
                    os.remove(doc.file_path)
                except Exception:
                    pass
            session.delete(doc)
        session.commit()

    # 删除 chromadb collection
    try:
        import chromadb
        client = chromadb.PersistentClient(path=os.path.join(
            os.path.dirname(__file__), '..', '..', 'data', 'chroma_db'
        ))
        client.delete_collection(kb_id)
    except Exception:
        pass

    del meta[kb_id]
    _save_kb_meta(meta)
    return {"status": "deleted", "id": kb_id}


# ---- File Management ----

def _delete_from_chroma(kb_id: str, doc_id: str):
    """从 chromadb 中删除指定文档的所有 chunk。"""
    from app.core.rag_engine import _get_or_create_collection
    collection = _get_or_create_collection(kb_id)
    # 删除该文档的所有 chunk
    try:
        results = collection.get(where={"doc_id": doc_id})
        if results and results['ids']:
            collection.delete(ids=results['ids'])
    except Exception:
        pass


@router.post("/knowledge/{kb_id}/files")
async def upload_file_to_kb(kb_id: str, file: UploadFile = File(...)):
    """上传文件到指定知识库。"""
    if kb_id == "__default__":
        # 默认知识库不需要创建
        pass
    else:
        meta = _load_kb_meta()
        if kb_id not in meta:
            raise HTTPException(status_code=404, detail="Knowledge base not found")

    # 读取文件内容
    content = await file.read()
    filename = file.filename or "unnamed.txt"

    # 检查文件类型
    from app.core.document_parser import DocumentParser
    if not DocumentParser.is_supported(filename):
        raise HTTPException(status_code=400, detail=f"不支持的文件类型，支持: {', '.join(DocumentParser.SUPPORTED_EXTENSIONS)}")

    # 保存文件到磁盘
    from app.core.file_storage import FileStorageManager
    stored_name = FileStorageManager.generate_stored_name(filename)
    file_path = FileStorageManager.save(content, stored_name)

    # 解析文档
    text = DocumentParser.extract_text(file_path)
    if not text:
        # 清理已保存的文件
        FileStorageManager.delete(stored_name)
        raise HTTPException(status_code=400, detail="无法解析文件内容")

    # 分块
    from app.core.rag_engine import _get_or_create_collection, split_text
    chunks = split_text(text)
    if not chunks:
        FileStorageManager.delete(stored_name)
        raise HTTPException(status_code=400, detail="文件内容为空或无法分块")

    # 保存文档记录到数据库
    doc_id = f"doc_{uuid.uuid4().hex[:8]}"
    save_knowledge_doc(
        doc_id=doc_id,
        filename=filename,
        file_path=file_path,
        content_type=file.content_type or '',
        chunk_count=len(chunks),
        char_count=len(text),
    )
    # 更新 knowledge_base_id
    if kb_id != "__default__":
        with Session(engine) as session:
            doc = session.get(KnowledgeDoc, doc_id)
            if doc:
                doc.knowledge_base_id = kb_id
                session.add(doc)
                session.commit()

    # 写入 chromadb
    collection_name = kb_id if kb_id != "__default__" else "knowledge_base"
    collection = _get_or_create_collection(collection_name)
    for i, chunk in enumerate(chunks):
        collection.add(
            ids=[f"{doc_id}_chunk_{i}"],
            documents=[chunk],
            metadatas=[{"doc_id": doc_id, "filename": filename, "chunk_index": i}],
        )

    return {
        "status": "uploaded",
        "doc_id": doc_id,
        "filename": filename,
        "chunk_count": len(chunks),
        "char_count": len(text),
    }


@router.delete("/knowledge/{kb_id}/files/{doc_id}")
async def delete_file_from_kb(kb_id: str, doc_id: str):
    """从知识库中删除指定文档。"""
    # 从 chromadb 删除
    collection_name = kb_id if kb_id != "__default__" else "knowledge_base"
    try:
        _delete_from_chroma(collection_name, doc_id)
    except Exception:
        pass

    # 从数据库删除
    with Session(engine) as session:
        doc = session.get(KnowledgeDoc, doc_id)
        if doc:
            # 删除文件
            if doc.file_path and os.path.exists(doc.file_path):
                try:
                    os.remove(doc.file_path)
                except Exception:
                    pass
            session.delete(doc)
            session.commit()

    return {"status": "deleted", "doc_id": doc_id}


# ---- Search ----

@router.post("/knowledge/{kb_id}/search")
async def search_knowledge_base(kb_id: str, req: KnowledgeQuery):
    """在指定知识库中检索。"""
    collection_name = kb_id if kb_id != "__default__" else "knowledge_base"
    try:
        from app.core.rag_engine import _get_or_create_collection
        collection = _get_or_create_collection(collection_name)
        results = collection.query(
            query_texts=[req.query],
            n_results=req.top_k,
        )
        hits = []
        if results and results['documents'] and results['documents'][0]:
            for i, doc in enumerate(results['documents'][0]):
                hits.append({
                    "text": doc,
                    "score": round(1 - (results['distances'][0][i] if results['distances'] else 0), 3),
                    "metadata": results['metadatas'][0][i] if results['metadatas'] else {},
                })
        return {"results": hits}
    except Exception as e:
        logger.warning(f"Knowledge search failed for {kb_id}: {e}")
        return {"results": [], "error": str(e)}


# ---- Stats ----

@router.get("/knowledge/stats")
async def knowledge_stats():
    """获取所有知识库的总统计。"""
    meta = _load_kb_meta()
    total_chunks = 0
    total_docs = 0
    with Session(engine) as session:
        all_docs = session.exec(select(KnowledgeDoc)).all()
        total_docs = len(all_docs)
        total_chunks = sum(d.chunk_count for d in all_docs)
    return {
        "total_bases": len(meta),
        "total_docs": total_docs,
        "total_chunks": total_chunks,
    }
