"""Entry point for the Code Review Agent."""

import logging
import sys

import uvicorn

from code_review_agent.config import get_config


def setup_logging(config):
    level = config.get("logging", "level", default="INFO")
    fmt = config.get("logging", "format", default="json")

    if fmt == "json":
        logging.basicConfig(
            level=getattr(logging, level.upper(), logging.INFO),
            format='{"time": "%(asctime)s", "level": "%(levelname)s", "name": "%(name)s", "message": "%(message)s"}',
            stream=sys.stdout,
        )
    else:
        logging.basicConfig(
            level=getattr(logging, level.upper(), logging.INFO),
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            stream=sys.stdout,
        )


def main():
    config = get_config()
    setup_logging(config)
    logger = logging.getLogger(__name__)

    host = config.get("server", "host", default="0.0.0.0")
    port = config.get("server", "port", default=8000)
    workers = config.get("server", "workers", default=4)

    logger.info("Starting Code Review Agent on %s:%d", host, port)

    uvicorn.run(
        "code_review_agent.api.app:app",
        host=host,
        port=port,
        workers=workers,
        log_level="info",
    )


if __name__ == "__main__":
    main()
