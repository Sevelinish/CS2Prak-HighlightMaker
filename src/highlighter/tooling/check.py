from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from ..config.schema import PathsConfig, ToolchainConfig
from ..infrastructure.paths import ApplicationPaths
from .inventory import ToolInventory, ToolStatus
from .latest import LatestVersion, LatestVersionResolver


class ToolState(Enum):
    MISSING = "not installed"
    DAMAGED = "files are missing"
    CURRENT = "up to date"
    OUTDATED = "a newer one is out"
    NEWER = "newer than the source"
    UNKNOWN = "cannot tell"


@dataclass(frozen=True, slots=True)
class ToolCheck:
    status: ToolStatus
    latest: LatestVersion = LatestVersion()

    @property
    def state(self) -> ToolState:
        if not self.status.is_installed:
            return ToolState.MISSING
        if not self.status.is_complete:
            return ToolState.DAMAGED
        return self._compared()

    @property
    def needs_attention(self) -> bool:
        return self.state in (ToolState.MISSING, ToolState.DAMAGED, ToolState.OUTDATED)

    def _compared(self) -> ToolState:
        installed = self.status.version
        newest = self.latest.version
        if installed is None or newest is None:
            return ToolState.UNKNOWN
        if newest > installed:
            return ToolState.OUTDATED
        if installed > newest:
            return ToolState.NEWER
        return ToolState.CURRENT


class ToolchainInspector:
    def __init__(
        self,
        paths: PathsConfig,
        settings: ToolchainConfig,
        tools_directory: Path,
        hook_dll_relative_path: str = "",
        application_paths: ApplicationPaths | None = None,
    ) -> None:
        self._inventory = ToolInventory(
            paths, tools_directory, hook_dll_relative_path, application_paths
        )
        self._resolver = LatestVersionResolver(settings)

    def installed(self) -> tuple[ToolStatus, ...]:
        return self._inventory.take()

    def inspect(self, ask_online: bool = True) -> tuple[ToolCheck, ...]:
        return tuple(
            ToolCheck(
                status=status,
                latest=self._resolver.for_tool(status.key) if ask_online else LatestVersion(),
            )
            for status in self.installed()
        )
