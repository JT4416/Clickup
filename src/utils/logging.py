"""Logging setup using loguru with per-agent log isolation."""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

# Remove default handler
logger.remove()

# Console handler with rich formatting
logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | <cyan>{extra[agent_id]}</cyan> | {message}",
    level="INFO",
    filter=lambda record: "agent_id" in record["extra"],
)

# Fallback for non-agent logs
logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}",
    level="INFO",
    filter=lambda record: "agent_id" not in record["extra"],
)

# File handler - rotates daily
logger.add(
    LOG_DIR / "gladiator_{time:YYYY-MM-DD}.log",
    rotation="1 day",
    retention="30 days",
    level="DEBUG",
)


def get_agent_logger(agent_id: str):
    """Return a logger bound to a specific agent ID."""
    return logger.bind(agent_id=agent_id)
