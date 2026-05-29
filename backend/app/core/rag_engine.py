"""
RAG Engine — 简易知识库检索增强生成引擎

使用 chromadb 作为嵌入式向量数据库，支持：
  - 文档分块 (固定长度 + 重叠滑窗)
  - Embedding (通过 LLM 提供商的 embedding API 或 chromadb 内置模型)
  - 语义检索 (Top-K 相似度查询)
  - 上下文注入 (将检索结果拼接到 Agent prompt)
"""

import os
import uuid
import logging
from typing import Optional

logger = logging.getLogger("rag_engine")

# chromadb 数据持久化目录
CHROMA_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'chroma_db')
os.makedirs(CHROMA_DIR, exist_ok=True)

# 分块参数
CHUNK_SIZE = 500       # 每块最大字符数
CHUNK_OVERLAP = 80     # 相邻块重叠字符数
TOP_K = 5              # 检索返回的最相似块数


def _get_chroma_client():
    """延迟加载 chromadb 客户端（避免启动时未安装报错）"""
    import chromadb
    return chromadb.PersistentClient(path=CHROMA_DIR)


def _get_or_create_collection(collection_name: str = "knowledge_base"):
    """获取或创建向量集合"""
    client = _get_chroma_client()
    return client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )


def split_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """
    将长文本切分为固定大小的块，相邻块有重叠。
    按段落边界优先切分，段落内按句号/换行切分。
    """
    if not text or not text.strip():
        return []

    # 先按段落分割
    paragraphs = [p.strip() for p in text.split('\n') if p.strip()]

    chunks = []
    current_chunk = ""

    for para in paragraphs:
        # 如果当前段落本身就超过 chunk_size，需要进一步切分
        if len(para) > chunk_size:
            # 先把已积累的 chunk 保存
            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = ""
            # 对长段落做滑窗切分
            start = 0
            while start < len(para):
                end = min(start + chunk_size, len(para))
                chunks.append(para[start:end].strip())
                start += chunk_size - overlap
        elif len(current_chunk) + len(para) + 1 > chunk_size:
            # 当前积累的内容加上新段落会超出限制，先保存
            if current_chunk:
                chunks.append(current_chunk.strip())
            # 用重叠部分开始新块
            if overlap > 0 and current_chunk:
                current_chunk = current_chunk[-overlap:] + "\n" + para
            else:
                current_chunk = para
        else:
            current_chunk = (current_chunk + "\n" + para) if current_chunk else para

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return [c for c in chunks if c]


class RAGEngine:
    """知识库 RAG 引擎单例"""

    def __init__(self):
        self._enabled = True

    def add_document(self, doc_id: str, text: str, metadata: dict = None) -> int:
        """
        将文档分块并写入向量库。
        返回写入的块数。
        """
        chunks = split_text(text)
        if not chunks:
            return 0

        collection = _get_or_create_collection()

        ids = [f"{doc_id}_chunk_{i}" for i in range(len(chunks))]
        metadatas = [
            {
                "doc_id": doc_id,
                "chunk_index": i,
                "source": (metadata or {}).get("source", "unknown"),
                "filename": (metadata or {}).get("filename", ""),
            }
            for i in range(len(chunks))
        ]

        # chromadb 内置 embedding (all-MiniLM-L6-v2) 自动处理
        collection.add(
            ids=ids,
            documents=chunks,
            metadatas=metadatas,
        )

        logger.info(f"RAG: Added document '{doc_id}' with {len(chunks)} chunks")
        return len(chunks)

    def remove_document(self, doc_id: str):
        """删除某个文档的所有分块"""
        try:
            collection = _get_or_create_collection()
            # 查询属于该文档的所有块
            results = collection.get(
                where={"doc_id": doc_id},
            )
            if results and results["ids"]:
                collection.delete(ids=results["ids"])
                logger.info(f"RAG: Removed {len(results['ids'])} chunks for doc '{doc_id}'")
        except Exception as e:
            logger.error(f"RAG: Failed to remove document '{doc_id}': {e}")

    def query(self, query_text: str, top_k: int = TOP_K) -> list[dict]:
        """
        语义检索：返回最相关的 top_k 个文档块。
        每个结果包含 text, score, metadata。
        """
        if not query_text.strip():
            return []

        from app.core.metrics import active_step_var
        step = active_step_var.get()
        span = None
        if step:
            span = step.start_span(
                name="rag_semantic_search",
                span_type="rag",
                input_data={"query_text": query_text, "top_k": top_k}
            )

        try:
            collection = _get_or_create_collection()
            # 检查集合是否有数据
            if collection.count() == 0:
                if span:
                    span.finish(output_data=[], status="success", metadata={"hits_count": 0})
                return []

            results = collection.query(
                query_texts=[query_text],
                n_results=min(top_k, collection.count()),
            )

            hits = []
            if results and results["documents"] and results["documents"][0]:
                docs = results["documents"][0]
                distances = results["distances"][0] if results.get("distances") else [0] * len(docs)
                metadatas = results["metadatas"][0] if results.get("metadatas") else [{}] * len(docs)

                for doc, dist, meta in zip(docs, distances, metadatas):
                    hits.append({
                        "text": doc,
                        "score": round(1 - dist, 4),  # cosine distance -> similarity
                        "metadata": meta,
                    })

            if span:
                scores = [h["score"] for h in hits]
                span.finish(
                    output_data=[{"score": h["score"], "metadata": h["metadata"]} for h in hits],
                    status="success",
                    metadata={"hits_count": len(hits), "scores": scores}
                )
            return hits

        except Exception as e:
            logger.error(f"RAG query error: {e}")
            if span:
                span.finish(
                    output_data={"error": str(e)},
                    status="error"
                )
            return []

    def build_context_prompt(self, query_text: str, top_k: int = TOP_K) -> str:
        """
        检索并构建注入到 Agent prompt 的上下文文本。
        如果没有检索到任何内容，返回空字符串。
        """
        hits = self.query(query_text, top_k)
        if not hits:
            return ""

        context_parts = []
        for i, hit in enumerate(hits, 1):
            source = hit["metadata"].get("filename", "未知来源")
            context_parts.append(
                f"[参考文档 {i} | 来源: {source} | 相关度: {hit['score']}]\n{hit['text']}"
            )

        return (
            "以下是从知识库中检索到的相关参考资料，请结合这些信息回答用户问题：\n\n"
            + "\n\n---\n\n".join(context_parts)
            + "\n\n---\n请基于以上参考资料和你的专业知识来回答。如果参考资料不相关，可以忽略。"
        )

    def get_stats(self) -> dict:
        """获取知识库统计信息"""
        try:
            collection = _get_or_create_collection()
            count = collection.count()
            return {"total_chunks": count, "enabled": self._enabled}
        except Exception:
            return {"total_chunks": 0, "enabled": self._enabled}


# 模块级单例
rag_engine = RAGEngine()
