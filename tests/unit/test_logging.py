from __future__ import annotations

import json

from agent_review.observability.logging import configure_logging, get_logger


def test_configure_logging_json(capsys) -> None:
    configure_logging(log_level="INFO", log_format="json")
    logger = get_logger("test-json")
    logger.info("json_event", value=123)

    captured = capsys.readouterr()
    line = captured.err.strip().splitlines()[-1]
    payload = json.loads(line)
    assert payload["event"] == "json_event"
    assert payload["value"] == 123
    assert payload["logger"] == "test-json"
    assert payload["level"] == "info"


def test_configure_logging_console(capsys) -> None:
    configure_logging(log_level="DEBUG", log_format="console")
    logger = get_logger("test-console")
    logger.debug("console_event", key="v")

    captured = capsys.readouterr()
    line = captured.err.strip().splitlines()[-1]
    assert "console_event" in line
    assert "test-console" in line
