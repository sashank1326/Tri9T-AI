import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.core.exceptions import MedicalQAException
from app.db.sqlite import init_db
from app.db.mongo import check_mongo_health
from app.api.v1.router import api_router

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("medical_qa_system")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    logger.info("Initializing Medical Document QA and Traceability System...")
    # Initialize SQLite tables
    init_db()
    logger.info("SQLite schema initialized successfully.")

    # Check MongoDB health
    if check_mongo_health():
        logger.info("MongoDB service is connected and healthy.")
    else:
        logger.warning(
            "MongoDB is not currently reachable. Please start mongod or test cases may fail to persist."
        )

    yield
    logger.info("Shutting down Medical QA system.")


def create_app() -> FastAPI:
    """Application factory."""
    settings = get_settings()

    app = FastAPI(
        title="AI-Powered Medical Document QA and Traceability System",
        description=(
            "Backend system for ingesting medical equipment manuals (e.g. CT-200), "
            "version diffing, version-pinned requirement selections, "
            "Gemini-powered QA test-case generation, and dynamic requirement staleness detection."
        ),
        version="1.0.0",
        lifespan=lifespan
    )

    # CORS configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Global custom exception handler
    @app.exception_handler(MedicalQAException)
    async def medical_qa_exception_handler(request: Request, exc: MedicalQAException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.message,
                "status_code": exc.status_code,
                "details": exc.details
            }
        )

    # Mount API v1 router
    app.include_router(api_router, prefix="/api/v1")

    @app.get("/", include_in_schema=False)
    async def root():
        return RedirectResponse(url="/docs")

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    settings = get_settings()
    uvicorn.run("app.main:app", host=settings.APP_HOST, port=settings.APP_PORT, reload=True)
