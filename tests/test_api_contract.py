from __future__ import annotations

import json

import pytest

from highlighter.api.configuration import ConfigMerger, ConfigSchema
from highlighter.api.contract import COMMAND_NAMES, COMMANDS, HOST_APPLICATION, PluginDescriptor
from highlighter.api.dispatcher import CommandDispatcher
from highlighter.api.envelope import ApiRequest, ApiResponse
from highlighter.api.errors import ApiError, BadRequestError, ErrorCode, ErrorTranslator
from highlighter.config.schema import ApplicationConfig
from highlighter.detection.player_filter import PlayerNotFoundError
from highlighter.infrastructure.errors import RecordingError
from highlighter.modes import UnknownModeError


def test_the_api_names_the_launcher_it_was_written_for():
    document = PluginDescriptor(transports=("http",)).to_mapping()

    assert document["writtenFor"]["application"] == HOST_APPLICATION
    assert "CS2Prak-Launcher" in document["writtenFor"]["statement"]
    assert document["writtenFor"]["repository"].endswith("CS2Prak-Launcher")


def test_every_advertised_command_has_a_handler():
    handlers = CommandDispatcher._build(_ServiceDouble())

    assert set(handlers) == set(COMMAND_NAMES)


def test_no_command_is_advertised_twice():
    assert len(COMMAND_NAMES) == len(set(COMMAND_NAMES))


def test_long_running_commands_are_marked():
    submit = next(command for command in COMMANDS if command.name == "jobs.submit")

    assert submit.long_running is True


def test_a_request_needs_a_command():
    with pytest.raises(BadRequestError):
        ApiRequest.from_mapping({"payload": {}})


def test_a_request_payload_must_be_an_object():
    with pytest.raises(BadRequestError):
        ApiRequest.from_mapping({"command": "handshake", "payload": [1, 2]})


def test_a_request_keeps_the_identifier_the_client_sent():
    request = ApiRequest.from_mapping({"id": "abc", "command": "handshake"})

    assert request.request_id == "abc"


def test_a_request_without_an_identifier_gets_one():
    assert ApiRequest.from_mapping({"command": "handshake"}).request_id


def test_a_successful_response_carries_the_data():
    request = ApiRequest.create("handshake")
    payload = ApiResponse.succeeded(request, {"plugin": "x"}, 12).to_mapping()

    assert payload["ok"] is True
    assert payload["kind"] == "response"
    assert payload["data"] == {"plugin": "x"}
    assert payload["elapsedMs"] == 12


def test_a_failed_response_carries_the_error_code():
    request = ApiRequest.create("demos.inspect")
    error = ApiError(ErrorCode.DEMO_NOT_FOUND, "missing", {"requested": "a.dem"})
    payload = ApiResponse.failed(request, error).to_mapping()

    assert payload["ok"] is False
    assert payload["error"]["code"] == "demo_not_found"
    assert payload["error"]["details"]["requested"] == "a.dem"


def test_responses_survive_json_serialisation():
    payload = ApiResponse.succeeded(ApiRequest.create("handshake"), {"a": 1}).to_mapping()

    assert json.loads(json.dumps(payload))["command"] == "handshake"


def test_domain_errors_become_their_own_codes():
    assert ErrorTranslator.translate(PlayerNotFoundError("x")).code is ErrorCode.PLAYER_NOT_FOUND
    assert ErrorTranslator.translate(UnknownModeError("x")).code is ErrorCode.UNKNOWN_MODE
    assert ErrorTranslator.translate(RecordingError("x")).code is ErrorCode.RECORDING_FAILED


def test_an_unexpected_error_becomes_internal():
    translated = ErrorTranslator.translate(RuntimeError("boom"))

    assert translated.code is ErrorCode.INTERNAL
    assert "boom" in translated.message


def test_an_api_error_passes_through_untouched():
    original = ApiError(ErrorCode.JOB_NOT_FOUND, "gone")

    assert ErrorTranslator.translate(original) is original


def test_a_patch_only_replaces_the_keys_it_names():
    base = ApplicationConfig()
    patched = ConfigMerger.apply(base, {"recording": {"fps": 120}})

    assert patched.recording.fps == 120
    assert patched.recording.width == base.recording.width
    assert patched.detection.minimum_score == base.detection.minimum_score


def test_a_patch_cannot_rewrite_the_config_version():
    patched = ConfigMerger.merge(ApplicationConfig().to_mapping(), {"version": 999})

    assert patched["version"] != 999


def test_a_patch_merges_nested_objects_instead_of_replacing_them():
    merged = ConfigMerger.merge(
        {"game": {"consoleVariables": {"a": "1", "b": "2"}}},
        {"game": {"consoleVariables": {"b": "3"}}},
    )

    assert merged["game"]["consoleVariables"] == {"a": "1", "b": "3"}


def test_a_patch_that_is_not_an_object_is_rejected():
    with pytest.raises(BadRequestError):
        ConfigMerger.apply(ApplicationConfig(), [1, 2, 3])


def test_every_described_field_resolves_to_a_real_default():
    described = ConfigSchema.describe()["fields"]

    assert described
    assert all(field["default"] is not None for field in described)


def test_described_fields_cover_the_settings_a_launcher_exposes():
    paths = {field["path"] for field in ConfigSchema.describe()["fields"]}

    assert {"recording.fps", "recording.width", "recording.height"} <= paths
    assert {"nades.freezeSeconds", "nades.landingLeadSeconds"} <= paths


class _ServiceDouble:
    def __getattr__(self, name):
        return lambda payload: {"called": name}
