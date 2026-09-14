from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Mapping

from .contract import (
    ENVELOPE_COMMAND_KEY,
    ENVELOPE_ID_KEY,
    ENVELOPE_PAYLOAD_KEY,
    PROTOCOL_VERSION,
)
from .errors import ApiError, BadRequestError

UNKNOWN_COMMAND_LABEL = "?"


@dataclass(frozen=True, slots=True)
class ApiRequest:
    command: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    request_id: str = ""

    @classmethod
    def create(cls, command: str, payload: Mapping[str, Any] | None = None) -> "ApiRequest":
        return cls(command=command, payload=dict(payload or {}), request_id=new_identifier())

    @classmethod
    def from_mapping(cls, source: Any) -> "ApiRequest":
        if not isinstance(source, Mapping):
            raise BadRequestError("A request must be a JSON object")

        command = source.get(ENVELOPE_COMMAND_KEY)
        if not isinstance(command, str) or not command.strip():
            raise BadRequestError(f"Missing '{ENVELOPE_COMMAND_KEY}'")

        payload = source.get(ENVELOPE_PAYLOAD_KEY) or {}
        if not isinstance(payload, Mapping):
            raise BadRequestError(f"'{ENVELOPE_PAYLOAD_KEY}' must be a JSON object")

        identifier = source.get(ENVELOPE_ID_KEY)
        return cls(
            command=command.strip(),
            payload=dict(payload),
            request_id=str(identifier) if identifier else new_identifier(),
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            ENVELOPE_ID_KEY: self.request_id,
            ENVELOPE_COMMAND_KEY: self.command,
            ENVELOPE_PAYLOAD_KEY: dict(self.payload),
        }


@dataclass(frozen=True, slots=True)
class ApiResponse:
    request_id: str
    command: str
    ok: bool
    data: Mapping[str, Any] | None = None
    error: ApiError | None = None
    elapsed_ms: int = 0

    @classmethod
    def succeeded(
        cls,
        request: ApiRequest,
        data: Mapping[str, Any],
        elapsed_ms: int = 0,
    ) -> "ApiResponse":
        return cls(
            request_id=request.request_id,
            command=request.command,
            ok=True,
            data=data,
            elapsed_ms=elapsed_ms,
        )

    @classmethod
    def failed(
        cls,
        request: ApiRequest | None,
        error: ApiError,
        elapsed_ms: int = 0,
    ) -> "ApiResponse":
        return cls(
            request_id=request.request_id if request is not None else new_identifier(),
            command=request.command if request is not None else UNKNOWN_COMMAND_LABEL,
            ok=False,
            error=error,
            elapsed_ms=elapsed_ms,
        )

    def to_mapping(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "kind": "response",
            ENVELOPE_ID_KEY: self.request_id,
            ENVELOPE_COMMAND_KEY: self.command,
            "protocol": PROTOCOL_VERSION,
            "ok": self.ok,
            "elapsedMs": self.elapsed_ms,
        }
        if self.ok:
            payload["data"] = dict(self.data or {})
        else:
            payload["error"] = self.error.to_mapping() if self.error else {}
        return payload


def new_identifier() -> str:
    return uuid.uuid4().hex
