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
from .routers import chat, lex, providers, system, tools, transcriptions

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("synthia")


class _HeaderScrubbingFilter(logging.Filter):
    _SENSITIVE = {"authorization", "x-api-key", "x-synthia-llm-api-key", "api-key", "apikey"}

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if isinstance(record.msg, str):
                msg = record.msg
                for key in self._SENSITIVE:
                    # crude but effective for header dumps
                    if key in msg.lower():
                        record.msg = self._scrub(msg)
                        break
            if record.args:
                args = list(record.args)
                for i, arg in enumerate(args):
                    if isinstance(arg, str):
                        low = arg.lower()
                        if any(k in low for k in self._SENSITIVE):
                            args[i] = self._scrub(arg)
                record.args = tuple(args)
        except Exception:
            pass
        return True

    @staticmethod
    def _scrub(text: str) -> str:
        import re

        # Authorization: Bearer ...
        text = re.sub(r"(?i)(authorization\s*:\s*bearer\s+)[^\s]+", r"\1[REDACTED]", text)
        # Generic header values
        for h in ["x-api-key", "x-synthia-llm-api-key", "api-key", "apikey"]:
            text = re.sub(rf"(?i)({re.escape(h)}\s*[:=]\s*)[^\s,&]+", r"\1[REDACTED]", text)
        return text


for _h in logging.root.handlers:
    _h.addFilter(_HeaderScrubbingFilter())
logger.addFilter(_HeaderScrubbingFilter())


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
    app.include_router(lex.router)
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
