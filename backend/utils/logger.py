"""
Structured JSON logging for the SEO Audit platform.

Every log record is emitted as a single JSON line with:
  - timestamp (ISO-8601)
  - level
  - logger name
  - message
  - Optional context fields injected via LogContext or extra= kwarg
"""

import json
import logging
import sys
import time
from contextvars import ContextVar
from typing import Any

# Per-request / per-task context injected at the log call-site via LogContext
_ctx_audit_id:   ContextVar[str] = ContextVar("audit_id",   default="")
_ctx_agent_name: ContextVar[str] = ContextVar("agent_name", default="")
_ctx_request_id: ContextVar[str] = ContextVar("request_id", default="")


class LogContext:
    """Context manager that injects structured fields into all log records
    emitted within the ``with`` block."""

    def __init__(self, audit_id: str = "", agent_name: str = "", request_id: str = "") -> None:
        self._tokens: list = []
        self._audit_id   = audit_id
        self._agent_name = agent_name
        self._request_id = request_id

    def __enter__(self):
        self._tokens = [
            _ctx_audit_id.set(self._audit_id),
            _ctx_agent_name.set(self._agent_name),
            _ctx_request_id.set(self._request_id),
        ]
        return self

    def __exit__(self, *_):
        for tok in self._tokens:
            tok.var.reset(tok)


class JSONFormatter(logging.Formatter):
    """Emit one JSON object per log record on a single line."""

    RESERVED = {"name", "msg", "args", "levelname", "levelno", "pathname",
                 "filename", "module", "exc_info", "exc_text", "stack_info",
                 "lineno", "funcName", "created", "msecs", "relativeCreated",
                 "thread", "threadName", "processName", "process", "message",
                 "taskName"}

    def format(self, record: logging.LogRecord) -> str:
        record.message = record.getMessage()
        if record.exc_info:
            record.exc_text = self.formatException(record.exc_info)

        payload: dict[str, Any] = {
            "timestamp":  self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level":      record.levelname,
            "logger":     record.name,
            "message":    record.message,
        }

        # Inject contextvars if set
        if (v := _ctx_audit_id.get()):
            payload["audit_id"] = v
        if (v := _ctx_agent_name.get()):
            payload["agent_name"] = v
        if (v := _ctx_request_id.get()):
            payload["request_id"] = v

        # Caller location (only for WARNING+)
        if record.levelno >= logging.WARNING:
            payload["location"] = f"{record.filename}:{record.lineno}"

        # Any extra= fields passed by the caller
        for k, v in record.__dict__.items():
            if k not in self.RESERVED and not k.startswith("_"):
                payload[k] = v

        if record.exc_text:
            payload["exception"] = record.exc_text

        return json.dumps(payload, default=str)


def setup_logging(level: int = logging.INFO) -> None:
    """Call once at application startup to configure the root logger."""
    root = logging.getLogger()
    # Remove any handlers added by libraries before our setup
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root.addHandler(handler)
    root.setLevel(level)
    # Silence noisy third-party loggers
    for noisy in ("httpx", "httpcore", "chromadb", "urllib3", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger.  setup_logging() must be called at startup."""
    return logging.getLogger(name)
