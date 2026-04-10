from __future__ import annotations

import logging
from typing import cast

import structlog


def configure_logging(log_level: str = "INFO", log_format: str = "json") -> None:
    level = getattr(logging, log_level.upper(), logging.INFO)

    shared_processors: list[structlog.typing.Processor] = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    renderer: structlog.typing.Processor
    if log_format == "console":
        renderer = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    logging.basicConfig(level=level, format="%(message)s", force=True)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[renderer],
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    for handler in root_logger.handlers:
        handler.setFormatter(formatter)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return cast("structlog.stdlib.BoundLogger", structlog.get_logger(name))
