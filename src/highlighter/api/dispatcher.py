from __future__ import annotations

import time
from typing import Any, Callable, Mapping

from ..infrastructure.logging import get_logger
from .envelope import ApiRequest, ApiResponse
from .errors import ApiError, ErrorCode, ErrorTranslator
from .service import PluginService

Handler = Callable[[Mapping[str, Any]], dict[str, Any]]
MILLISECONDS = 1000


class CommandDispatcher:
    def __init__(self, service: PluginService) -> None:
        self._service = service
        self._handlers = self._build(service)
        self._logger = get_logger("api")

    @property
    def command_names(self) -> tuple[str, ...]:
        return tuple(self._handlers)

    def handle(self, request: ApiRequest) -> ApiResponse:
        started_at = time.monotonic()
        handler = self._handlers.get(request.command)
        if handler is None:
            return ApiResponse.failed(
                request,
                ApiError(
                    ErrorCode.UNKNOWN_COMMAND,
                    f"Unknown command {request.command}",
                    {"available": list(self._handlers)},
                ),
                self._elapsed(started_at),
            )

        try:
            data = handler(request.payload)
        except BaseException as error:
            if isinstance(error, (KeyboardInterrupt, SystemExit)):
                raise
            translated = ErrorTranslator.translate(error)
            self._logger.debug(
                "Command %s failed: %s", request.command, translated.message, exc_info=True
            )
            return ApiResponse.failed(request, translated, self._elapsed(started_at))

        return ApiResponse.succeeded(request, data, self._elapsed(started_at))

    @staticmethod
    def _build(service: PluginService) -> dict[str, Handler]:
        return {
            "handshake": service.handshake,
            "system.probe": service.probe,
            "config.get": service.config_get,
            "config.describe": service.config_describe,
            "config.patch": service.config_patch,
            "demos.list": service.demos_list,
            "demos.inspect": service.demos_inspect,
            "match.rounds": service.match_rounds,
            "match.players": service.match_players,
            "highlights.find": service.highlights_find,
            "grenades.find": service.grenades_find,
            "plan.preview": service.plan_preview,
            "jobs.submit": service.jobs_submit,
            "jobs.get": service.jobs_get,
            "jobs.list": service.jobs_list,
            "jobs.events": service.jobs_events,
            "jobs.cancel": service.jobs_cancel,
            "jobs.result": service.jobs_result,
            "session.get": service.session_get,
            "session.release": service.session_release,
            "update.check": service.update_check,
            "update.install": service.update_install,
            "output.list": service.output_list,
            "output.reveal": service.output_reveal,
            "shutdown": service.shutdown,
        }

    @staticmethod
    def _elapsed(started_at: float) -> int:
        return int((time.monotonic() - started_at) * MILLISECONDS)
