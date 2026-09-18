from __future__ import annotations

import logging
from pathlib import Path

from rich.logging import RichHandler

LOGGER_NAME = "highlighter"
QUIET_CONSOLE_LEVEL = logging.WARNING
THIRD_PARTY_LOGGERS = ("demoparser2", "polars", "pyarrow", "numexpr", "matplotlib", "PIL")


class LoggingConfigurator:
    def __init__(
        self, log_directory: Path, verbose: bool = False, console: bool = True
    ) -> None:
        self._log_directory = log_directory
        self._verbose = verbose
        self._console = console

    def configure(self) -> logging.Logger:
        self._log_directory.mkdir(parents=True, exist_ok=True)

        logger = logging.getLogger(LOGGER_NAME)
        logger.setLevel(logging.DEBUG)
        self._release(logger)
        logger.propagate = False

        file_handler = logging.FileHandler(
            self._log_directory / "highlighter.log", encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )

        logger.addHandler(file_handler)
        if self._console:
            logger.addHandler(self._console_handler())
        self._quiet_third_parties()
        return logger

    @staticmethod
    def _release(logger: logging.Logger) -> None:
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            try:
                handler.close()
            except (OSError, ValueError):
                continue

    def _console_handler(self) -> logging.Handler:
        handler = RichHandler(
            rich_tracebacks=True,
            show_path=False,
            show_time=False,
            markup=True,
        )
        handler.setLevel(logging.DEBUG if self._verbose else QUIET_CONSOLE_LEVEL)
        handler.setFormatter(logging.Formatter("%(message)s"))
        return handler

    def _quiet_third_parties(self) -> None:
        root = logging.getLogger()
        root.setLevel(logging.DEBUG if self._verbose else QUIET_CONSOLE_LEVEL)
        for name in THIRD_PARTY_LOGGERS:
            logging.getLogger(name).setLevel(
                logging.DEBUG if self._verbose else QUIET_CONSOLE_LEVEL
            )


def get_logger(suffix: str | None = None) -> logging.Logger:
    if suffix is None:
        return logging.getLogger(LOGGER_NAME)
    return logging.getLogger(f"{LOGGER_NAME}.{suffix}")
