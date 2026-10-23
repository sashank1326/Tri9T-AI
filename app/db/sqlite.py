import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from app.config import get_settings

settings = get_settings()

# Ensure directory for sqlite db exists
if settings.SQLITE_DB_URL.startswith("sqlite:///"):
    db_path = settings.SQLITE_DB_URL.replace("sqlite:///", "")
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

engine = create_engine(
    settings.SQLITE_DB_URL,
    connect_args={"check_same_thread": False} if settings.SQLITE_DB_URL.startswith("sqlite") else {},
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI dependency for SQLite database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all SQLite database tables."""
    import app.db.models  # Ensure models are imported before creating tables
    Base.metadata.create_all(bind=engine)
