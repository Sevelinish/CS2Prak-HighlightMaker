from __future__ import annotations

from enum import Enum
from typing import Any, Mapping

from ..demo.locator import DemoLocator
from ..detection.player_filter import PlayerNotFoundError
from ..infrastructure.errors import (
    ConfigurationError,
    DemoNotFoundError,
    DemoParsingError,
    DownloadError,
    EncodingError,
    GameNotFoundError,
    HighlighterError,
    RecordingError,
    SelectionAbortedError,
    ToolchainError,
)
from ..modes import UnknownModeError


class ErrorCode(str, Enum):
    BAD_REQUEST = "bad_request"
    UNKNOWN_COMMAND = "unknown_command"
    UNSUPPORTED_PROTOCOL = "unsupported_protocol"
    UNAUTHORIZED = "unauthorized"
    DEMO_NOT_FOUND = "demo_not_found"
    DEMO_UNREADABLE = "demo_unreadable"
    PLAYER_NOT_FOUND = "player_not_found"
    UNKNOWN_MODE = "unknown_mode"
    EMPTY_SELECTION = "empty_selection"
    CONFIG_INVALID = "config_invalid"
    GAME_NOT_FOUND = "game_not_found"
    TOOLCHAIN_UNAVAILABLE = "toolchain_unavailable"
    DOWNLOAD_FAILED = "download_failed"
    RECORDING_FAILED = "recording_failed"
    ENCODING_FAILED = "encoding_failed"
    JOB_NOT_FOUND = "job_not_found"
    JOB_CONFLICT = "job_conflict"
    CANCELLED = "cancelled"
    INTERNAL = "internal"


class ApiError(Exception):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details or {})

    def to_mapping(self) -> dict[str, Any]:
        return {
            "code": self.code.value,
            "message": self.message,
            "details": self.details,
        }


class BadRequestError(ApiError):
    def __init__(self, message: str, details: Mapping[str, Any] | None = None) -> None:
        super().__init__(ErrorCode.BAD_REQUEST, message, details)


class NotFoundError(ApiError):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(code, message, details)


_DOMAIN_CODES: tuple[tuple[type[HighlighterError], ErrorCode], ...] = (
    (PlayerNotFoundError, ErrorCode.PLAYER_NOT_FOUND),
    (UnknownModeError, ErrorCode.UNKNOWN_MODE),
    (DemoNotFoundError, ErrorCode.DEMO_NOT_FOUND),
    (DemoParsingError, ErrorCode.DEMO_UNREADABLE),
    (ConfigurationError, ErrorCode.CONFIG_INVALID),
    (GameNotFoundError, ErrorCode.GAME_NOT_FOUND),
    (DownloadError, ErrorCode.DOWNLOAD_FAILED),
    (ToolchainError, ErrorCode.TOOLCHAIN_UNAVAILABLE),
    (RecordingError, ErrorCode.RECORDING_FAILED),
    (EncodingError, ErrorCode.ENCODING_FAILED),
    (SelectionAbortedError, ErrorCode.CANCELLED),
)


class ErrorTranslator:
    @classmethod
    def translate(cls, error: BaseException) -> ApiError:
        if isinstance(error, ApiError):
            return error
        if isinstance(error, HighlighterError):
            return ApiError(cls._code_for(error), str(error))
        if isinstance(error, (ValueError, TypeError, KeyError)):
            return ApiError(ErrorCode.BAD_REQUEST, str(error))
        return ApiError(
            ErrorCode.INTERNAL,
            f"{type(error).__name__}: {error}",
        )

    @staticmethod
    def _code_for(error: HighlighterError) -> ErrorCode:
        for candidate, code in _DOMAIN_CODES:
            if isinstance(error, candidate):
                return code
        return ErrorCode.INTERNAL


class DemoNotFoundApiError(NotFoundError):
    def __init__(self, given: str, locator: DemoLocator) -> None:
        super().__init__(
            ErrorCode.DEMO_NOT_FOUND,
            f"No demo called '{given}' was found",
            {
                "requested": given,
                "searchDirectories": [
                    str(directory) for directory in locator.search_directories
                ],
            },
        )
