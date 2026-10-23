from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class StatusResponse(BaseModel):
    status: str = "ok"
    message: str = "Operation succeeded"
    details: Optional[Dict[str, Any]] = None


class HealthCheckResponse(BaseModel):
    status: str
    environment: str
    sqlite_connected: bool
    mongodb_connected: bool
    tesseract_available: bool
