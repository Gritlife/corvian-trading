from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.core.config import settings
from app.core.errors import EngineError, InternalError

logger = logging.getLogger(__name__)

app = FastAPI(
    title="OCM External Gamma Engine",
    description=(
        f"{settings.architecture_designation} — {settings.purpose}. "
        "Transforms raw options-chain data into an auditable, machine-readable "
        "gamma market structure for OCM/OACM, underneath MTS. Distinguishes "
        "OBSERVED data from DERIVED mathematics from MODELED inference at every "
        "output layer."
    ),
    version=settings.engine_version,
)

app.include_router(router)


@app.exception_handler(EngineError)
async def engine_error_handler(request: Request, exc: EngineError):
    """Converts every typed engine error (section 24) into structured
    JSON. Never leaks a raw Python traceback to a TV client."""
    return JSONResponse(status_code=exc.http_status, content=exc.to_response())


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Catch-all: any exception that is not a typed EngineError is
    logged server-side and reported to the client as a generic
    INTERNAL_ERROR with no stack trace or internal detail exposed."""
    logger.exception("Unhandled exception while processing %s", request.url)
    fallback = InternalError("An internal error occurred while processing this request.")
    return JSONResponse(status_code=fallback.http_status, content=fallback.to_response())
