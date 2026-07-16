"""Tests for Agent export/import API."""
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.agents import router


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return TestClient(app)


class TestExportAgent:
    def test_export_existing_agent(self, client):
        with patch('app.routers.agents.async_get_custom_agents', new_callable=AsyncMock) as mock:
            mock.return_value = [{
                "agent_id": "agent_custom_123",
                "name": "Test Agent",
                "avatar": "🤖",
                "role": "tester",
                "style": "friendly",
                "system_prompt": "You are a test agent",
                "tools": ["tool1"],
                "api_key": "secret123",
            }]
            resp = client.get("/api/agents/custom/agent_custom_123/export")
            assert resp.status_code == 200
            data = resp.json()
            assert data["version"] == "1.0"
            assert data["agent"]["name"] == "Test Agent"
            assert "api_key" not in data["agent"]

    def test_export_nonexistent_agent(self, client):
        with patch('app.routers.agents.async_get_custom_agents', new_callable=AsyncMock) as mock:
            mock.return_value = []
            resp = client.get("/api/agents/custom/nonexistent/export")
            assert resp.status_code == 404


class TestImportAgent:
    def test_import_valid_agent(self, client):
        with patch('app.routers.agents.async_get_custom_agents', new_callable=AsyncMock) as mock_list, \
             patch('app.routers.agents.agent_registry') as mock_registry:
            mock_list.return_value = []
            mock_registry.register_custom_agent = AsyncMock()
            resp = client.post("/api/agents/import", json={
                "version": "1.0",
                "agent": {
                    "name": "Imported Agent",
                    "avatar": "🤖",
                    "role": "tester",
                    "system_prompt": "You are a test agent",
                    "tools": [],
                }
            })
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "imported"
            assert data["agent"]["name"] == "Imported Agent"

    def test_import_duplicate_name(self, client):
        with patch('app.routers.agents.async_get_custom_agents', new_callable=AsyncMock) as mock_list, \
             patch('app.routers.agents.agent_registry') as mock_registry:
            mock_list.return_value = [{"name": "Test Agent", "agent_id": "existing"}]
            mock_registry.register_custom_agent = AsyncMock()
            resp = client.post("/api/agents/import", json={
                "version": "1.0",
                "agent": {
                    "name": "Test Agent",
                    "system_prompt": "You are a test agent",
                }
            })
            assert resp.status_code == 200
            data = resp.json()
            assert data["duplicate_renamed"] is True
            assert "imported" in data["agent"]["name"]

    def test_import_missing_name(self, client):
        resp = client.post("/api/agents/import", json={
            "version": "1.0",
            "agent": {"system_prompt": "test"}
        })
        assert resp.status_code == 400
        assert "name" in resp.json()["detail"].lower()

    def test_import_missing_system_prompt(self, client):
        resp = client.post("/api/agents/import", json={
            "version": "1.0",
            "agent": {"name": "test"}
        })
        assert resp.status_code == 400
        assert "system_prompt" in resp.json()["detail"].lower()
