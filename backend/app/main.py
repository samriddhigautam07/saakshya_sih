"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings, get_settings
from app.database import create_database_engine, create_session_factory, initialize_database
from app.file_storage import resolve_private_storage_root
from app.routes.auth import router as auth_router
from app.routes.applications import router as applications_router
from app.routes.documents import router as documents_router
from app.routes.regulatory import router as regulatory_router
from app.routes.validation import router as validation_router
from app.routes.reports import router as reports_router
from app.security import validate_auth_settings
from app.structured_extraction import configured_provider

logger = logging.getLogger("verifywise")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the API app and initialize its configured database on startup."""
    app_settings = settings or get_settings()
    engine = create_database_engine(app_settings.database_url)
    session_factory = create_session_factory(engine)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        validate_auth_settings(app_settings)
        initialize_database(engine)
        _app.state.engine = engine
        _app.state.session_factory = session_factory
        _app.state.settings = app_settings
        _app.state.storage_root = resolve_private_storage_root(app_settings.document_storage_dir)
        provider = configured_provider(app_settings)
        _app.state.llm_provider = provider
        api_key_present = bool(
            app_settings.llm_api_key
            and app_settings.llm_api_key.get_secret_value().strip()
        )
        model_present = bool(app_settings.llm_model and app_settings.llm_model.strip())
        logger.info(
            "Structured extraction configuration: LLM_API_KEY_present=%s LLM_MODEL_present=%s provider_ready=%s",
            api_key_present,
            model_present,
            provider is not None,
        )
        yield
        engine.dispose()

    application = FastAPI(
        title="VerifyWise AI Backend",
        description="Authenticated application and document API for the VerifyWise AI prototype.",
        version="0.4.0",
        lifespan=lifespan,
    )
    origins = [origin.strip() for origin in app_settings.cors_origins.split(",") if origin.strip()]
    application.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @application.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    application.include_router(auth_router)
    application.include_router(applications_router)
    application.include_router(documents_router)
    application.include_router(regulatory_router)
    application.include_router(validation_router)
    application.include_router(reports_router)
    return application


app = create_app()
