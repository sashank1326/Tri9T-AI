import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.db.models  # Ensure models are registered on Base
from app.main import create_app
from app.db.sqlite import Base, get_db
from app.db.mongo import set_mock_mongo
from tests.fixtures.pdf_generator import create_synthetic_pdf_v1, create_synthetic_pdf_v2

# Configure test in-memory SQLite database with StaticPool so all connections share the same memory DB
TEST_SQLITE_URL = "sqlite:///:memory:"


@pytest.fixture(scope="session", autouse=True)
def setup_test_mongo():
    """Use in-memory mongomock for test isolation across the test suite."""
    set_mock_mongo(True)
    yield
    set_mock_mongo(False)


@pytest.fixture
def db_session():
    """Create fresh isolated in-memory SQLite database session for each test."""
    test_engine = create_engine(
        TEST_SQLITE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def client(db_session):
    """FastAPI TestClient with overridden get_db dependency."""
    app = create_app()

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def pdf_v1_bytes():
    return create_synthetic_pdf_v1()


@pytest.fixture
def pdf_v2_bytes():
    return create_synthetic_pdf_v2()
