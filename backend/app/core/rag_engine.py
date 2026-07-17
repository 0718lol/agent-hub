"""
RAG Engine — 简易知识库检索增强生成引擎

使用 chromadb 作为嵌入式向量数据库，支持：
  - 文档分块 (固定长度 + 重叠滑窗)
  - Embedding (通过 LLM 提供商的 embedding API 或 chromadb 内置模型)
  - 语义检索 (Top-K 相似度查询)
  - 上下文注入 (将检索结果拼接到 Agent prompt)
"""

import hashlib
import logging
import os

logger = logging.getLogger("rag_engine")

# chromadb 数据持久化目录
CHROMA_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'chroma_db')
os.makedirs(CHROMA_DIR, exist_ok=True)

# 分块参数
CHUNK_SIZE = 500       # 每块最大字符数
CHUNK_OVERLAP = 80     # 相邻块重叠字符数
TOP_K = 5              # 检索返回的最相似块数


def tenant_collection_name(user_id: str, knowledge_base_id: str) -> str:
    """Return a Chroma-safe collection name that cannot collide across tenants."""
    tenant = hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:24]
    resource = "default" if knowledge_base_id == "__default__" else knowledge_base_id
    return f"tenant_{tenant}_{resource}"


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
    语义感知型递归文本分块策略：按段落、行、中英文标点、词句边界逐级递归切分，
    保证每个分块的内容最大程度保留语义连贯性，并且其大小不超过 chunk_size 字符。
    """
    if not text or not text.strip():
        return []

    # 递归分割符列表，从最高优先级（段落）到最低优先级（字符）
    separators = ["\n\n", "\n", "。", "！", "？", ".", "!", "?", "；", ";", "，", ",", " ", ""]

    def _recursive_split(content: str, seps: list[str]) -> list[str]:
        if len(content) <= chunk_size:
            return [content]
        if not seps:
            # 已经没有分割符可用，强行硬截断
            chunks = []
            start = 0
            while start < len(content):
                end = min(start + chunk_size, len(content))
                chunks.append(content[start:end])
                start += chunk_size - overlap
                if start >= len(content) or chunk_size <= overlap:
                    break
            return chunks

        sep = seps[0]
        # 使用当前分割符将文本拆分成片段
        if sep == "":
            splits = list(content)
        else:
            splits = content.split(sep)

        # 重组片段，使其尽量接近 chunk_size，同时保证相邻块有 overlap
        chunks = []
        current_part = ""

        for part in splits:
            if not part:
                continue

            # 如果加上这个片段和分隔符仍然不超过 chunk_size，则累加
            potential = current_part + (sep if current_part else "") + part
            if len(potential) <= chunk_size:
                current_part = potential
            else:
                # 先把当前已有的累加块存入结果
                if current_part:
                    chunks.append(current_part.strip())

                # 如果这个新片段本身就超过 chunk_size，递归下级分割符进行子分块
                if len(part) > chunk_size:
                    sub_chunks = _recursive_split(part, seps[1:])
                    # 子分块重组
                    for sc in sub_chunks:
                        chunks.append(sc.strip())
                    current_part = ""
                else:
                    # 用重叠部分开始新块
                    if overlap > 0 and current_part:
                        overlap_prefix = current_part[-overlap:]
                        current_part = overlap_prefix + (sep if overlap_prefix else "") + part
                    else:
                        current_part = part

        if current_part.strip():
            chunks.append(current_part.strip())

        return [c for c in chunks if c]

    return _recursive_split(text, separators)


class RAGEngine:
    """知识库 RAG 引擎单例"""

    def __init__(self):
        self._enabled = True

    def add_document(self, doc_id: str, text: str, metadata: dict | None = None) -> int:
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

    def query(
        self,
        query_text: str,
        top_k: int = TOP_K,
        collection_name: str = "knowledge_base",
    ) -> list[dict]:
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
            collection = _get_or_create_collection(collection_name)
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

                for doc, dist, meta in zip(docs, distances, metadatas, strict=False):
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

    def build_tenant_context_prompt(
        self,
        user_id: str,
        query_text: str,
        top_k: int = TOP_K,
    ) -> str:
        """Search every knowledge base owned by one tenant and format the best hits."""
        if not user_id or not query_text.strip():
            return ""
        try:
            from sqlmodel import Session, select

            from app.core._engine import engine
            from app.core.models import KnowledgeBase

            with Session(engine) as session:
                base_ids = ["__default__"] + list(session.exec(
                    select(KnowledgeBase.id).where(KnowledgeBase.user_id == user_id)
                ).all())
            hits = []
            for knowledge_base_id in base_ids:
                hits.extend(self.query(
                    query_text,
                    top_k,
                    tenant_collection_name(user_id, knowledge_base_id),
                ))
            hits.sort(key=lambda hit: hit.get("score", 0), reverse=True)
            hits = hits[:top_k]
        except Exception as exc:
            logger.debug("Tenant RAG lookup skipped: %s", exc)
            return ""
        if not hits:
            return ""
        context_parts = []
        for index, hit in enumerate(hits, 1):
            source = hit.get("metadata", {}).get("filename", "未知来源")
            context_parts.append(
                f"[参考文档 {index} | 来源: {source} | 相关度: {hit.get('score', 0)}]\n{hit.get('text', '')}"
            )
        return (
            "以下是当前用户知识库中检索到的参考资料，请结合相关内容回答：\n\n"
            + "\n\n---\n\n".join(context_parts)
            + "\n\n---\n如果资料与问题无关，可以忽略。"
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
