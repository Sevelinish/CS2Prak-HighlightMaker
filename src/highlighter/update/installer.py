from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rich.console import Console

from ..config.schema import ApplicationConfig
from ..infrastructure.logging import get_logger
from ..infrastructure.paths import ApplicationPaths
from ..provisioning.release_resolver import ReleaseInfo
from ..version import Version
from .payload import PayloadStager, UpdateError, UpdatePayload
from .swap import SwapScriptWriter

UPDATE_DIRECTORY = "update"
CONFIG_FILE_NAME = "config.json"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
DETACHED = getattr(subprocess, "DETACHED_PROCESS", 0)


@dataclass(frozen=True, slots=True)
class InstallOutcome:
    version: Version
    script: Path
    log: Path
    marker: Path
    relaunch: bool

    def to_mapping(self) -> dict[str, Any]:
        return {
            "version": str(self.version),
            "script": str(self.script),
            "log": str(self.log),
            "relaunch": self.relaunch,
        }


class UpdateInstaller:
    def __init__(
        self, console: Console, paths: ApplicationPaths, config: ApplicationConfig
    ) -> None:
        self._console = console
        self._paths = paths
        self._config = config
        self._staging = (
            paths.resolve(config.paths.work_directory) / UPDATE_DIRECTORY
        )
        self._logger = get_logger("update")

    @property
    def staging_directory(self) -> Path:
        return self._staging

    def install(self, release: ReleaseInfo) -> InstallOutcome:
        self._require_frozen()
        payload = PayloadStager(self._console, self._config.update, self._staging).stage(release)
        return self._apply(payload)

    def _apply(self, payload: UpdatePayload) -> InstallOutcome:
        writer = SwapScriptWriter(self._staging, self._paths.logs)
        plan = writer.write(
            target=self._paths.root,
            payload_root=payload.root,
            archive=payload.archive,
            process_id=os.getpid(),
            version=str(payload.version),
            protected_files=self._protected_files(),
            protected_directories=self._protected_directories(),
            relaunch=self._config.update.relaunch_after_install,
        )
        self._launch(plan.script)
        return InstallOutcome(
            version=payload.version,
            script=plan.script,
            log=plan.log,
            marker=plan.marker,
            relaunch=self._config.update.relaunch_after_install,
        )

    def _launch(self, script: Path) -> None:
        try:
            subprocess.Popen(
                ["cmd.exe", "/c", str(script)],
                cwd=str(script.parent),
                creationflags=NO_WINDOW | DETACHED,
                close_fds=True,
            )
        except OSError as error:
            raise UpdateError(f"Could not start the installer: {error}") from error
        self._logger.info("Update installer started from %s", script)

    def _protected_files(self) -> list[str]:
        return [CONFIG_FILE_NAME]

    def _protected_directories(self) -> list[str]:
        paths = self._config.paths
        candidates = (
            paths.output_directory,
            paths.demo_directory,
            paths.tools_directory,
            paths.work_directory,
            "logs",
        )
        return sorted({name for name in map(self._local_name, candidates) if name})

    @staticmethod
    def _local_name(candidate: str) -> str:
        path = Path(candidate or "")
        if path.is_absolute() or len(path.parts) != 1:
            return ""
        return path.name

    def _require_frozen(self) -> None:
        import sys

        if getattr(sys, "frozen", False):
            return
        raise UpdateError(
            "Updating only works on a built release. "
            "Running from source, use git pull instead."
        )
