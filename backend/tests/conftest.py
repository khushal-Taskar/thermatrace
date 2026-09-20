import os
import tempfile
from pathlib import Path
import pytest

TEST_ROOT=Path(tempfile.mkdtemp(prefix="thermatrace-test-"))
os.environ["DATABASE_URL"]="sqlite:///"+(TEST_ROOT/"test.db").as_posix()

from fastapi.testclient import TestClient
from app.main import app
from app.api.routes import attempts


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as client:
        yield client


@pytest.fixture(autouse=True)
def clean_client_auth(client):
    client.cookies.clear()
    attempts.clear()
    yield
    client.cookies.clear()


@pytest.fixture
def authenticated(client):
    result=client.post("/api/auth/login",json={"email":"admin@thermatrace.local","password":"PharmaDemo!2026"})
    assert result.status_code==200
    return client
