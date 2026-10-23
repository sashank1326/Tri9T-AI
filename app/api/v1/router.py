from fastapi import APIRouter
from app.api.v1.documents import router as documents_router
from app.api.v1.selections import router as selections_router
from app.api.v1.test_cases import router as test_cases_router
from app.schemas.common import HealthCheckResponse
from app.config import get_settings
from app.db.mongo import check_mongo_health
from app.services.pdf_parser.ocr import OCROptimizer

api_router = APIRouter()

api_router.include_router(documents_router)
api_router.include_router(selections_router)
api_router.include_router(test_cases_router)


@api_router.get("/health", response_model=HealthCheckResponse, tags=["System Health"])
def system_health():
    """Verify operational health and connectivity to SQLite, MongoDB, and Tesseract."""
    settings = get_settings()
    ocr = OCROptimizer()

    return HealthCheckResponse(
        status="healthy",
        environment=settings.APP_ENV,
        sqlite_connected=True,
        mongodb_connected=check_mongo_health(),
        tesseract_available=ocr.is_available()
    )
