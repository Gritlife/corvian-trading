"""
Typed error contract (section 24 of the v0.1.1 spec).

Every engine-level failure is raised as an EngineError subclass carrying
a stable ErrorCode, human-readable message, an HTTP status, and optional
structured details. app.main installs an exception handler that converts
these into structured JSON and never leaks a raw Python traceback to a
TV client. Unhandled exceptions are caught by a catch-all handler and
reported as INTERNAL_ERROR without exposing internals.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from app.core.enums import ErrorCode


class EngineError(Exception):
    code: ErrorCode = ErrorCode.INTERNAL_ERROR
    http_status: int = 500

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_response(self) -> Dict[str, Any]:
        return {
            "error": {
                "code": self.code.value,
                "message": self.message,
                "details": self.details,
            }
        }


class ProviderUnavailable(EngineError):
    code = ErrorCode.PROVIDER_UNAVAILABLE
    http_status = 503


class ProviderCapabilityUnsupported(EngineError):
    code = ErrorCode.PROVIDER_CAPABILITY_UNSUPPORTED
    http_status = 501


class SymbolUnsupported(EngineError):
    code = ErrorCode.SYMBOL_UNSUPPORTED
    http_status = 404


class NoChainData(EngineError):
    code = ErrorCode.NO_CHAIN_DATA
    http_status = 502


class StaleDataRejected(EngineError):
    code = ErrorCode.STALE_DATA_REJECTED
    http_status = 409


class AnalysisFailed(EngineError):
    code = ErrorCode.ANALYSIS_FAILED
    http_status = 500


class NoValidIV(EngineError):
    code = ErrorCode.NO_VALID_IV
    http_status = 422


class InternalError(EngineError):
    code = ErrorCode.INTERNAL_ERROR
    http_status = 500
