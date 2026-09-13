from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from highlighter.application import Application
from highlighter.config.repository import ConfigRepository
from highlighter.config.schema import ApplicationConfig
from highlighter.infrastructure.logging import LOGGER_NAME, LoggingConfigurator


def console_level() -> int:
    logger = logging.getLogger(LOGGER_NAME)
    streams = [
        handler
        for handler in logger.handlers
        if not isinstance(handler, logging.FileHandler)
    ]
    return streams[0].level if streams else logging.NOTSET


def stub_application(verbose: bool, logs: Path) -> Application:
    application = Application.__new__(Application)
    application._verbose = verbose
    application._paths = type("Paths", (), {"logs": logs})()
    return application


def test_debug_is_off_by_default():
    assert ApplicationConfig().debug is False


def test_debug_survives_a_round_trip():
    restored = ApplicationConfig.from_mapping(ApplicationConfig(debug=True).to_mapping())

    assert restored.debug is True


def test_debug_sits_at_the_top_of_the_file():
    keys = list(ApplicationConfig().to_mapping())

    assert keys.index("debug") == 1


def test_a_config_without_the_key_defaults_to_off(tmp_path: Path):
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"recording": {"fps": 60}}), encoding="utf-8")

    assert ConfigRepository(config_file).load().debug is False


def test_the_key_is_written_into_new_config_files(tmp_path: Path):
    config_file = tmp_path / "config.json"
    ConfigRepository(config_file).load()

    assert json.loads(config_file.read_text(encoding="utf-8"))["debug"] is False


def test_a_user_set_flag_is_preserved(tmp_path: Path):
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"debug": True}), encoding="utf-8")

    ConfigRepository(config_file).load()

    assert json.loads(config_file.read_text(encoding="utf-8"))["debug"] is True


def test_config_debug_turns_console_output_verbose(tmp_path: Path):
    LoggingConfigurator(tmp_path, verbose=False).configure()
    assert console_level() == logging.INFO

    stub_application(verbose=False, logs=tmp_path)._apply_debug_setting(
        ApplicationConfig(debug=True)
    )

    assert console_level() == logging.DEBUG


def test_config_debug_off_leaves_the_console_quiet(tmp_path: Path):
    LoggingConfigurator(tmp_path, verbose=False).configure()

    stub_application(verbose=False, logs=tmp_path)._apply_debug_setting(ApplicationConfig())

    assert console_level() == logging.INFO


def test_the_verbose_flag_is_not_downgraded_by_the_config(tmp_path: Path):
    LoggingConfigurator(tmp_path, verbose=True).configure()

    stub_application(verbose=True, logs=tmp_path)._apply_debug_setting(ApplicationConfig())

    assert console_level() == logging.DEBUG


@pytest.fixture(autouse=True)
def restore_logging(tmp_path: Path):
    yield
    LoggingConfigurator(tmp_path, verbose=False).configure()
