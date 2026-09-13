from __future__ import annotations

import logging
from pathlib import Path

from rich.logging import RichHandler

LOGGER_NAME = "highlighter"
QUIET_CONSOLE_LEVEL = logging.WARNING


class LoggingConfigurator:
    def __init__(self, log_directory: Path, verbose: bool = False) -> None:
        self._log_directory = log_directory
        self._verbose = verbose

    def configure(self) -> logging.Logger:
        self._log_directory.mkdir(parents=True, exist_ok=True)

        logger = logging.getLogger(LOGGER_NAME)
        logger.setLevel(logging.DEBUG)
        logger.handlers.clear()
        logger.propagate = False

        console_handler = RichHandler(
            rich_tracebacks=True,
            show_path=False,
            show_time=False,
            markup=True,
        )
        console_handler.setLevel(
            logging.DEBUG if self._verbose else QUIET_CONSOLE_LEVEL
        )
        console_handler.setFormatter(logging.Formatter("%(message)s"))

        file_handler = logging.FileHandler(
            self._log_directory / "highlighter.log", encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )

        logger.addHandler(console_handler)
        logger.addHandler(file_handler)
        return logger


def get_logger(suffix: str | None = None) -> logging.Logger:
    if suffix is None:
        return logging.getLogger(LOGGER_NAME)
    return logging.getLogger(f"{LOGGER_NAME}.{suffix}")
