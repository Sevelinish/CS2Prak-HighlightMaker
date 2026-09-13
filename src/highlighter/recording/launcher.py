from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Callable

from ..config.schema import GameConfig, RecordingConfig
from ..game.installation import Cs2Installation
from ..infrastructure.errors import RecordingError
from ..infrastructure.logging import get_logger
from ..provisioning.hlae_installation import HlaeInstallation
from .game_process import GameProcessWatcher

SECONDS_PER_MINUTE = 60
STEAM_PATH_VARIABLE = "SteamPath"
WINDOWED_FLAG = "-sw"
FULLSCREEN_FLAG = "-full"
LOADER_TIMEOUT_SECONDS = 120


class HlaeLauncher:
    def __init__(
        self,
        hlae: HlaeInstallation,
        installation: Cs2Installation,
        recording: RecordingConfig,
        game: GameConfig,
        steam_root: Path | None,
        watcher: GameProcessWatcher | None = None,
    ) -> None:
        self._hlae = hlae
        self._installation = installation
        self._recording = recording
        self._game = game
        self._steam_root = steam_root
        self._watcher = watcher or GameProcessWatcher(installation.executable.name)
        self._logger = get_logger("recording.launcher")

    def run(
        self,
        entry_script: str,
        demo_path: Path,
        on_launched: Callable[[], None] | None = None,
        on_progress: Callable[[float], None] | None = None,
    ) -> None:
        self._hlae.verify_path_is_ascii()
        self._guard_against_running_game()

        self._inject(entry_script, demo_path)
        self._await_game_start()
        if on_launched is not None:
            on_launched()
        self._await_game_exit(on_progress)

    def build_arguments(self, entry_script: str, demo_path: Path) -> list[str]:
        placeholders = {
            "game_executable": str(self._installation.executable),
            "game_arguments": self._game_arguments(entry_script, demo_path),
            "hook_dll": str(self._hlae.hook_dll),
            "width": str(self._recording.width),
            "height": str(self._recording.height),
            "fullscreen": "true" if self._recording.fullscreen else "false",
        }

        arguments = [str(self._hlae.executable)]
        arguments.extend(
            token.format(**placeholders) for token in self._game.hlae_argument_template
        )
        return arguments

    def build_environment(self) -> dict[str, str]:
        environment = dict(os.environ)
        environment.update(self._steam_variables())
        return environment

    def _guard_against_running_game(self) -> None:
        if self._watcher.is_running():
            raise RecordingError(
                f"{self._watcher.executable_name} is already running. "
                f"Close Counter-Strike 2 and start the recording again."
            )

    def _inject(self, entry_script: str, demo_path: Path) -> None:
        arguments = self.build_arguments(entry_script, demo_path)
        self._logger.debug("Launching HLAE: %s", subprocess.list2cmdline(arguments))
        self._logger.debug("Steam environment: %s", self._steam_variables())

        try:
            completed = subprocess.run(
                arguments,
                cwd=str(self._hlae.root),
                env=self.build_environment(),
                timeout=LOADER_TIMEOUT_SECONDS,
            )
        except OSError as error:
            raise RecordingError(f"Could not start HLAE: {error}") from error
        except subprocess.TimeoutExpired as error:
            raise RecordingError("HLAE did not finish injecting in time") from error

        if completed.returncode != 0:
            raise RecordingError(
                f"HLAE loader failed with exit code {completed.returncode}. "
                f"See logs/highlighter.log for the exact command line."
            )
        self._logger.debug("HLAE loader finished, game process handed over")

    def _await_game_start(self) -> None:
        timeout = self._game.game_startup_timeout_seconds
        if not self._watcher.wait_until_started(timeout):
            raise RecordingError(
                f"Counter-Strike 2 did not start within {timeout} seconds. "
                f"Make sure Steam is running and you are signed in."
            )
        self._logger.debug("Game process detected, recording in progress")

    def _await_game_exit(self, on_progress: Callable[[float], None] | None) -> None:
        timeout = self._game.recording_timeout_minutes * SECONDS_PER_MINUTE
        if self._watcher.wait_until_stopped(timeout, on_progress):
            self._logger.debug("Game closed on its own, recording finished")
            return

        self._watcher.terminate()
        raise RecordingError(
            f"Recording exceeded {self._game.recording_timeout_minutes} minutes and was stopped"
        )

    def _steam_variables(self) -> dict[str, str]:
        variables = dict(self._game.steam_environment)
        if self._steam_root is not None:
            variables[STEAM_PATH_VARIABLE] = str(self._steam_root)
        return variables

    def _game_arguments(self, entry_script: str, demo_path: Path) -> str:
        tokens = list(self._game.launch_arguments)
        tokens.append(FULLSCREEN_FLAG if self._recording.fullscreen else WINDOWED_FLAG)
        tokens.extend(["-w", str(self._recording.width)])
        tokens.extend(["-h", str(self._recording.height)])
        tokens.extend(["+exec", entry_script])
        tokens.extend(["+playdemo", str(demo_path)])
        return subprocess.list2cmdline(tokens)
