"""
Structured logging module for Scrapwisest.
Supports both human-readable format for local development and structured JSON for production.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict


class JSONFormatter(logging.Formatter):
    """
    Format log records as structured single-line JSON objects.
    Suitable for containerized deployment, Datadog, CloudWatch, and Nebius logs.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_obj: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "line": record.lineno,
        }

        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        # Include custom extra fields if provided
        standard_attrs = {
            "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
            "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
            "created", "msecs", "relativeCreated", "thread", "threadName",
            "processName", "process", "message"
        }
        extras = {k: v for k, v in record.__dict__.items() if k not in standard_attrs}
        if extras:
            log_obj["extra"] = extras

        return json.dumps(log_obj, ensure_ascii=False)


def setup_logging(json_logs: bool | None = None, level: str | None = None) -> None:
    """
    Configure root logger.
    If json_logs is True, outputs JSON. Otherwise, outputs human-readable aligned text.
    """
    if json_logs is None:
        json_logs = os.getenv("LOG_FORMAT", "").lower() == "json"
    if level is None:
        level = os.getenv("LOG_LEVEL", "INFO").upper()

    log_level = getattr(logging, level, logging.INFO)
    root = logging.getLogger()
    root.setLevel(log_level)

    # Remove existing handlers to prevent duplicate lines
    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)

    if json_logs:
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
        )

    root.addHandler(handler)

    # Silence overly verbose external loggers
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
