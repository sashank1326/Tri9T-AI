import logging
from typing import Optional
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from app.config import get_settings
from app.core.exceptions import DatabaseConnectionError

logger = logging.getLogger(__name__)

_mongo_client: Optional[MongoClient] = None
_use_mock_mongo: bool = False


def set_mock_mongo(enabled: bool = True):
    """Enable or disable mongomock for test isolation."""
    global _use_mock_mongo, _mongo_client
    _use_mock_mongo = enabled
    _mongo_client = None


def get_mongo_client() -> MongoClient:
    """Retrieve or initialize the MongoDB client instance."""
    global _mongo_client
    if _mongo_client is not None:
        return _mongo_client

    if _use_mock_mongo:
        import mongomock
        logger.info("Initializing in-memory mongomock client for testing.")
        _mongo_client = mongomock.MongoClient()
        return _mongo_client

    settings = get_settings()
    try:
        _mongo_client = MongoClient(
            settings.MONGODB_URI,
            serverSelectionTimeoutMS=3000,
            connectTimeoutMS=3000
        )
        # Verify connection immediately
        _mongo_client.admin.command('ping')
        logger.info("Successfully connected to MongoDB at %s", settings.MONGODB_URI)
        return _mongo_client
    except (ConnectionFailure, ServerSelectionTimeoutError, Exception) as exc:
        _mongo_client = None
        raise DatabaseConnectionError(
            f"Could not connect to MongoDB at {settings.MONGODB_URI}: {str(exc)}. "
            f"Please ensure MongoDB daemon is running."
        ) from exc


def get_mongo_db() -> Database:
    """Retrieve the application's MongoDB database."""
    settings = get_settings()
    client = get_mongo_client()
    return client[settings.MONGODB_DB_NAME]


def get_test_cases_collection() -> Collection:
    """Collection storing generated AI QA test cases."""
    return get_mongo_db()["test_cases"]


def get_generations_collection() -> Collection:
    """Collection storing AI generation batches and original source snapshots."""
    return get_mongo_db()["generations"]


def get_staleness_audits_collection() -> Collection:
    """Collection storing staleness audit records and diff reports."""
    return get_mongo_db()["staleness_audits"]


def check_mongo_health() -> bool:
    """Check whether MongoDB is currently reachable."""
    try:
        get_mongo_client().admin.command('ping')
        return True
    except Exception:
        return False
