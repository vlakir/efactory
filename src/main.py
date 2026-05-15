"""Application entry point."""

from __future__ import annotations

import logging
import sys

logger = logging.getLogger(__name__)


def _stdout_filter(record: logging.LogRecord) -> bool:
    """Pass only records below WARNING level (DEBUG/INFO) to stdout."""
    return record.levelno < logging.WARNING


def _configure_logging() -> None:
    """Send DEBUG/INFO to stdout, WARNING and above to stderr."""
    fmt = logging.Formatter('%(levelname)s:%(name)s:%(message)s')

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(logging.DEBUG)
    stdout_handler.addFilter(_stdout_filter)
    stdout_handler.setFormatter(fmt)

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.WARNING)
    stderr_handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(stdout_handler)
    root.addHandler(stderr_handler)


def main() -> None:
    """Run the application."""
    _configure_logging()
    logger.info('Hello from efactory!')
    logger.warning('Sample warning — goes to stderr')


if __name__ == '__main__':
    main()
