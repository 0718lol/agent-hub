"""Cross-tenant isolation tests for user-owned resources."""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.core.models import KnowledgeBase, KnowledgeDoc
from app.routers import knowledge


@pytest.fixture
def knowledge_app(monkeypatch):
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(test_engine)
    import app.core._engine as engine_module
    monkeypatch.setattr(engine_module, "engine", test_engine)
    monkeypatch.setattr(knowledge, "engine", test_engine)
    monkeypatch.setattr(
        knowledge,
        "request_user_id",
        lambda request: request.headers.get("x-test-user", "anonymous"),
    )
    with Session(test_engine) as session:
        session.add(KnowledgeBase(id="kb_a", user_id="user-A", name="A"))
        session.add(KnowledgeBase(id="kb_b", user_id="user-B", name="B"))
        session.add(KnowledgeDoc(
            id="doc_a", user_id="user-A", filename="a.txt", knowledge_base_id="kb_a"
        ))
        session.add(KnowledgeDoc(
            id="doc_b", user_id="user-B", filename="b.txt", knowledge_base_id="kb_b"
        ))
        session.commit()

    app = FastAPI()
    app.include_router(knowledge.router, prefix="/api")
    return app, test_engine


@pytest.mark.asyncio
async def test_knowledge_list_and_stats_are_tenant_scoped(knowledge_app):
    app, _engine = knowledge_app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        listing = await client.get("/api/knowledge", headers={"x-test-user": "user-A"})
        stats = await client.get("/api/knowledge/stats", headers={"x-test-user": "user-A"})

    assert listing.status_code == 200
    assert [base["id"] for base in listing.json()["bases"]] == ["kb_a"]
    assert stats.json() == {"total_bases": 1, "total_docs": 1, "total_chunks": 0}


@pytest.mark.asyncio
async def test_knowledge_resources_cannot_be_read_or_deleted_cross_tenant(knowledge_app):
    app, test_engine = knowledge_app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        read = await client.get("/api/knowledge/kb_b", headers={"x-test-user": "user-A"})
        delete = await client.delete(
            "/api/knowledge/kb_a/files/doc_b", headers={"x-test-user": "user-A"}
        )

    assert read.status_code == 404
    assert delete.status_code == 404
    with Session(test_engine) as session:
        assert session.get(KnowledgeDoc, "doc_b") is not None


def test_rag_queries_only_current_tenant_collections(knowledge_app, monkeypatch):
    from app.core import rag_engine as rag_module

    queried = []

    class Collection:
        def __init__(self, name):
            self.name = name

        def count(self):
            return 1

        def query(self, **_kwargs):
            queried.append(self.name)
            return {
                "documents": [[f"content from {self.name}"]],
                "distances": [[0.1]],
                "metadatas": [[{"filename": "owned.txt"}]],
            }

    monkeypatch.setattr(
        rag_module,
        "_get_or_create_collection",
        lambda name="knowledge_base": Collection(name),
    )

    context = rag_module.RAGEngine().build_tenant_context_prompt("user-A", "query")

    assert context
    assert set(queried) == {
        rag_module.tenant_collection_name("user-A", "__default__"),
        rag_module.tenant_collection_name("user-A", "kb_a"),
    }
    assert rag_module.tenant_collection_name("user-B", "kb_b") not in queried
