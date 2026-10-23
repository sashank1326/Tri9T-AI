from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    APP_ENV: str = "development"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000

    SQLITE_DB_URL: str = "sqlite:///./data/medical_qa.db"
    MONGODB_URI: str = "mongodb://localhost:27017"
    MONGODB_DB_NAME: str = "medical_qa_system"

    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-3.8-flash"

    OCR_ENABLED: bool = True
    TESSERACT_CMD: str = "tesseract"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
