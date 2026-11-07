import pytest
from fastapi.testclient import TestClient
from app.config import settings
from app.main import app

# Set test environment settings
settings.ENV = "test"
settings.GITHUB_CLIENT_ID = "test_client_id_12345"
settings.GITHUB_CLIENT_SECRET = "test_client_secret_67890"
settings.SESSION_SECRET = "test-secret-key-that-is-at-least-32-characters-long"
settings.FRONTEND_URL = "http://localhost:3000"


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client
