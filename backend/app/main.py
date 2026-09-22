"""
FastAPI entrypoint for the Scrapwisest platform.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.endpoints import chat, health, voice
from app.api.router import api_router
from app.core.config import settings
from app.core.exceptions import AppException, app_exception_handler, unhandled_exception_handler
from app.core.logging import setup_logging
from app.db.session import init_db

# Initialize logging
setup_logging()
logger = logging.getLogger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up %s (version: %s)...", settings.PROJECT_NAME, settings.VERSION)
    try:
        await init_db()
    except Exception:
        logger.warning("Database table initialization skipped or already present.")
    yield
    logger.info("Shutting down %s...", settings.PROJECT_NAME)


app = FastAPI(
    title=settings.PROJECT_NAME,
    description=settings.PROJECT_DESCRIPTION,
    version=settings.VERSION,
    lifespan=lifespan,
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exception Handlers
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

# Mount API v1 Routes
app.include_router(api_router, prefix=settings.API_V1_STR)

# Root-level endpoints for direct frontend & test backwards-compatibility
app.include_router(chat.router)
app.include_router(health.router)
app.include_router(voice.router)

# Serve SPA static build when present
_static_candidates = (
    settings.STATIC_DIR,
    settings.FRONTEND_DIST_DIR,
)
for _static in _static_candidates:
    index = _static / "index.html"
    if index.exists():
        @app.get("/", include_in_schema=False)
        def _spa_index():
            return FileResponse(index)

        assets = _static / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")
        logger.info("Serving frontend from %s", _static)
        break
