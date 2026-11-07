import os
from pathlib import Path
import psycopg
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.config import settings
from app.db import Base, get_db
from app.main import app
from app.models.users import User, UserRole
from app.security import create_session_token

TEST_DB_URL = "postgresql+psycopg://provenance:provenance@localhost:5432/provenance_test"
ADMIN_DB_URL = "postgresql://provenance:provenance@localhost:5432/postgres"

# Configure test environment
settings.ENV = "test"
settings.GITHUB_CLIENT_ID = "test_client_id_12345"
settings.GITHUB_CLIENT_SECRET = "test_client_secret_67890"
settings.SESSION_SECRET = "test-secret-key-that-is-at-least-32-characters-long"
settings.FRONTEND_URL = "http://localhost:3000"
settings.DATABASE_URL = TEST_DB_URL
settings.REPO_STORAGE_PATH = "./data/test_repos"


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """
    Ensures the separate provenance_test database exists and has migrations applied.
    Never modifies the development database.
    """
    try:
        conn = psycopg.connect(ADMIN_DB_URL, autocommit=True)
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", ("provenance_test",))
            if not cur.fetchone():
                cur.execute("CREATE DATABASE provenance_test")
        conn.close()
    except Exception as e:
        pytest.skip(f"Postgres not reachable for tests: {e}")

    # Run alembic migrations on test db
    from alembic import command
    from alembic.config import Config

    alembic_ini_path = Path(__file__).resolve().parent.parent / "alembic.ini"
    alembic_cfg = Config(str(alembic_ini_path))
    alembic_cfg.set_main_option("sqlalchemy.url", TEST_DB_URL)
    command.upgrade(alembic_cfg, "head")


test_engine = create_engine(TEST_DB_URL, echo=False)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture
def db_session():
    """
    Provides an isolated database session for each test,
    cleaning up modified tables afterwards.
    """
    connection = test_engine.connect()
    transaction = connection.begin()
    session = TestSessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def test_user(db_session):
    user = User(
        github_id=1001,
        username="teststudent",
        display_name="Test Student",
        email="student@example.com",
        role=UserRole.student,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def other_user(db_session):
    user = User(
        github_id=1002,
        username="otheruser",
        display_name="Other User",
        email="other@example.com",
        role=UserRole.student,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def admin_user(db_session):
    user = User(
        github_id=1003,
        username="adminuser",
        display_name="Admin User",
        email="admin@example.com",
        role=UserRole.admin,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def authenticated_client(test_user, db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app)
    token = create_session_token(test_user.id)
    test_client.cookies.set("provenance_session", token)
    yield test_client
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def other_client(other_user, db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app)
    token = create_session_token(other_user.id)
    test_client.cookies.set("provenance_session", token)
    yield test_client
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def admin_client(admin_user, db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app)
    token = create_session_token(admin_user.id)
    test_client.cookies.set("provenance_session", token)
    yield test_client
    app.dependency_overrides.pop(get_db, None)
