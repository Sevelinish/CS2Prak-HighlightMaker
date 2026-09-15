from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from ..config.schema import RecordingConfig
from ..infrastructure.logging import get_logger
from ..plan.models import RecordingPlan
from .game_process import GameProcessWatcher
from .netcon import NetconEndpoint

WARM_SESSION_VERSION = 2
DEMO_CHANNEL = "demo"
NETCON_CHANNEL = "netcon"
MARKER_FILE_NAME = "warm_session.json"
EXPIRY_MARGIN_SECONDS = 30.0
MINIMUM_WINDOW_SECONDS = 60.0


@dataclass(frozen=True, slots=True)
class WarmSession:
    pid: int
    executable: str
    demo_path: str
    demo_name: str
    config_directory: str
    handover_script: str
    width: int
    height: int
    fullscreen: bool
    started_at: float
    expires_at: float
    graphics_restore_pending: bool = True
    channel: str = DEMO_CHANNEL
    netcon_port: int = 0
    netcon_password: str = ""

    @property
    def uses_netcon(self) -> bool:
        return self.channel == NETCON_CHANNEL and self.netcon_port > 0

    @property
    def endpoint(self) -> NetconEndpoint:
        return NetconEndpoint(port=self.netcon_port, password=self.netcon_password)

    @property
    def seconds_left(self) -> float:
        return max(0.0, self.expires_at - time.time())

    @property
    def is_expired(self) -> bool:
        return self.seconds_left <= 0.0

    def is_running(self) -> bool:
        return self.pid in GameProcessWatcher(self.executable).running_process_ids()

    def fits(self, plan: RecordingPlan, recording: RecordingConfig) -> bool:
        if not self._window_matches(recording):
            return False
        if self.uses_netcon:
            return True
        return self.demo_path == str(plan.demo_path)

    def _window_matches(self, recording: RecordingConfig) -> bool:
        return (
            self.width == recording.width
            and self.height == recording.height
            and self.fullscreen == recording.fullscreen
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "version": WARM_SESSION_VERSION,
            "pid": self.pid,
            "executable": self.executable,
            "demoPath": self.demo_path,
            "demoName": self.demo_name,
            "configDirectory": self.config_directory,
            "handoverScript": self.handover_script,
            "width": self.width,
            "height": self.height,
            "fullscreen": self.fullscreen,
            "startedAt": round(self.started_at, 3),
            "expiresAt": round(self.expires_at, 3),
            "secondsLeft": round(self.seconds_left, 1),
            "graphicsRestorePending": self.graphics_restore_pending,
            "channel": self.channel,
            "netconPort": self.netcon_port,
            "demoClosed": self.uses_netcon,
        }

    def to_marker(self) -> dict[str, Any]:
        return {**self.to_mapping(), "netconPassword": self.netcon_password}

    @classmethod
    def from_mapping(cls, source: Mapping[str, Any]) -> "WarmSession | None":
        if int(source.get("version") or 0) != WARM_SESSION_VERSION:
            return None
        try:
            return cls(
                pid=int(source["pid"]),
                executable=str(source["executable"]),
                demo_path=str(source["demoPath"]),
                demo_name=str(source["demoName"]),
                config_directory=str(source["configDirectory"]),
                handover_script=str(source["handoverScript"]),
                width=int(source["width"]),
                height=int(source["height"]),
                fullscreen=bool(source["fullscreen"]),
                started_at=float(source["startedAt"]),
                expires_at=float(source["expiresAt"]),
                graphics_restore_pending=bool(source.get("graphicsRestorePending", True)),
                channel=str(source.get("channel") or DEMO_CHANNEL),
                netcon_port=int(source.get("netconPort") or 0),
                netcon_password=str(source.get("netconPassword") or ""),
            )
        except (KeyError, TypeError, ValueError):
            return None


class WarmSessionStore:
    def __init__(self, work_directory: Path) -> None:
        self._marker = work_directory / MARKER_FILE_NAME
        self._logger = get_logger("recording.warm")

    @property
    def marker_file(self) -> Path:
        return self._marker

    def load(self) -> WarmSession | None:
        if not self._marker.is_file():
            return None
        try:
            raw = json.loads(self._marker.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(raw, dict):
            return None
        return WarmSession.from_mapping(raw)

    def live(self) -> WarmSession | None:
        session = self.load()
        if session is None:
            if self._marker.is_file():
                self._logger.debug("Dropping a marker this build cannot read")
                self.clear()
            return None
        if not session.is_running():
            self._logger.debug("Warm session pid %d is gone", session.pid)
            self.clear()
            return None
        return session

    def usable_for(
        self, plan: RecordingPlan, recording: RecordingConfig
    ) -> WarmSession | None:
        session = self.live()
        if session is None:
            return None
        if session.is_expired:
            self._logger.debug("Warm session expired %.0fs ago", -session.seconds_left)
            return None
        if not session.fits(plan, recording):
            self._logger.debug("Warm session does not fit this plan")
            return None
        return session

    def remember(
        self,
        plan: RecordingPlan,
        recording: RecordingConfig,
        executable: str,
        config_directory: Path,
        handover_script: str,
        graphics_restore_pending: bool,
        channel: str = DEMO_CHANNEL,
        netcon: NetconEndpoint | None = None,
    ) -> WarmSession | None:
        pids = GameProcessWatcher(executable).running_process_ids()
        if len(pids) != 1:
            self._logger.debug("Expected one %s, found %d", executable, len(pids))
            self.clear()
            return None

        now = time.time()
        session = WarmSession(
            pid=pids[0],
            executable=executable,
            demo_path=str(plan.demo_path),
            demo_name=plan.demo_name,
            config_directory=str(config_directory),
            handover_script=handover_script,
            width=recording.width,
            height=recording.height,
            fullscreen=recording.fullscreen,
            started_at=now,
            expires_at=now + self._window_seconds(plan),
            graphics_restore_pending=graphics_restore_pending,
            channel=channel,
            netcon_port=netcon.port if netcon is not None else 0,
            netcon_password=netcon.password if netcon is not None else "",
        )
        self._write(session)
        return session

    def _write(self, session: WarmSession) -> None:
        self._marker.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(session.to_marker(), ensure_ascii=False, indent=2)
        self._marker.write_text(payload + "\n", encoding="utf-8")
        self._logger.debug("Warm session saved to %s", self._marker)

    def clear(self) -> None:
        self._marker.unlink(missing_ok=True)

    @staticmethod
    def _window_seconds(plan: RecordingPlan) -> float:
        if plan.tick_rate <= 0 or plan.demo_end_tick <= 0:
            return MINIMUM_WINDOW_SECONDS
        playable = plan.demo_end_tick / plan.tick_rate
        return max(MINIMUM_WINDOW_SECONDS, playable - EXPIRY_MARGIN_SECONDS)
