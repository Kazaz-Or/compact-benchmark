"""Test fixtures."""

import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import src.database as db_module
from src.app import app
from src.database import init_db


@pytest.fixture(autouse=True)
def tmp_db(tmp_path: Path):
    """Use a temporary database for each test."""
    test_db = tmp_path / "test.db"
    db_module.DB_PATH = test_db
    init_db()
    yield test_db
    if test_db.exists():
        test_db.unlink()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def sample_project(client):
    """Create a sample project and return its data."""
    resp = client.post("/api/v1/projects", json={"name": "Test Project", "description": "A test project"})
    assert resp.status_code == 201
    return resp.json()


@pytest.fixture
def sample_task(client, sample_project):
    """Create a sample task and return its data."""
    resp = client.post(
        f"/api/v1/projects/{sample_project['id']}/tasks",
        json={"title": "Test Task", "description": "A test task", "priority": 1},
    )
    assert resp.status_code == 201
    return resp.json()
