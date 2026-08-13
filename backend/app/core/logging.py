"""Structured logging with trace_id correlation."""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar

trace_id_var: ContextVar[str | None] = ContextVar("trace_id", default=None)
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

_CONFIGURED = False


class TraceFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        trace_id = trace_id_var.get() or "-"
        request_id = request_id_var.get() or "-"
        record.trace_id = trace_id
        record.request_id = request_id
        return super().format(record)


def setup_logging(level: str = "INFO") -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        TraceFormatter(
            "%(asctime)s %(levelname)s [%(name)s] trace=%(trace_id)s req=%(request_id)s %(message)s"
        )
    )
    root = logging.getLogger()
    root.setLevel(level.upper())
    root.handlers[:] = [handler]
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(name)
