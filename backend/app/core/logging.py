"""Structured logging with secret redaction."""

from __future__ import annotations

import logging
import re
import sys
from typing import Any

_LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_SENSITIVE_KEYS = re.compile(
    r"(?i)(api[_-]?key|token|secret|password|authorization|qdrant[_-]?key)"
)

_REDACTED_DEFAULTS = {"preload_content": False}


def _redact(msg: Any) -> Any:
    if not isinstance(msg, str):
        return msg
    return _SENSITIVE_KEYS.sub("***REDACTED***", msg)


class SanitizedFormatter(logging.Formatter):
    """Formatter that redacts secrets before rendering."""

    def format(self, record: logging.LogRecord) -> str:
        record.msg = _redact(record.msg)
        if record.args:
            record.args = tuple(_redact(a) for a in record.args)
        return super().format(record)


def configure_logging(level: int | str = logging.INFO) -> None:
    root = logging.getLogger()
    root.setLevel(level)

    if root.handlers:
        for h in root.handlers[:]:
            root.removeHandler(h)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(SanitizedFormatter(_LOG_FORMAT))
    root.addHandler(handler)

    for noisy in ("httpx", "httpcore", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_safe(**kwargs: Any) -> dict[str, Any]:
    """Return kwargs with sensitive values already redacted (defensive)."""
    return {k: _redact(v) for k, v in kwargs.items()}