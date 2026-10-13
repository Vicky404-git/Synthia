"""Synthia FastAPI application entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import __version__
from .config import get_settings
from .errors import (
    SynthiaError,
    synthia_error_handler,
    unhandled_error_handler,
)
from .routers import chat, providers, system, tools, transcriptions

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("synthia")


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    logger.info(
        "Synthia starting (env=%s, demo_mode=%s, llm=%s, auth=%s)",
        settings.app_env,
        settings.demo_mode,
        settings.llm_provider,
        bool(settings.api_auth_token),
    )
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Synthia",
        description="Speak to your infrastructure. A cloud voice operations assistant.",
        version=__version__,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    app.add_exception_handler(SynthiaError, synthia_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(_: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Request validation failed.",
                    "details": {"errors": jsonable_encoder(exc.errors())},
                }
            },
        )

    app.include_router(system.router)
    app.include_router(providers.router)
    app.include_router(tools.router)
    app.include_router(chat.router)
    app.include_router(transcriptions.router)

    @app.get("/", tags=["system"])
    async def root() -> dict:
        return {
            "service": settings.app_name,
            "version": __version__,
            "tagline": "Speak to your infrastructure.",
            "docs": "/docs",
            "demo_mode": settings.demo_mode,
        }

    return app


app = create_app()
