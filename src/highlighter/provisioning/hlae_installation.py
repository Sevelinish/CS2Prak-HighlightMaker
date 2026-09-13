from __future__ import annotations

from pathlib import Path

from ..infrastructure.errors import ToolchainError
from ..infrastructure.logging import get_logger

FFMPEG_FOLDER = "ffmpeg"
FFMPEG_CONFIG_FILE = "ffmpeg.ini"
FFMPEG_CONFIG_TEMPLATE = "[Ffmpeg]\nPath={path}\n"
INJECTOR_COMPANIONS = ("AfxHook.dat", "injector.exe")


class HlaeInstallation:
    def __init__(self, executable: Path, hook_dll_relative_path: str) -> None:
        self._executable = executable
        self._hook_dll_relative_path = hook_dll_relative_path
        self._logger = get_logger("toolchain.hlae")

    @property
    def executable(self) -> Path:
        return self._executable

    @property
    def root(self) -> Path:
        return self._executable.parent

    @property
    def hook_dll(self) -> Path:
        candidate = self.root / self._hook_dll_relative_path
        if not candidate.is_file():
            raise ToolchainError(self._repair_hint([candidate]))
        return candidate

    def required_files(self) -> list[Path]:
        hook_dll = self.root / self._hook_dll_relative_path
        injector_directory = hook_dll.parent
        return [
            self._executable,
            hook_dll,
            *(injector_directory / name for name in INJECTOR_COMPANIONS),
        ]

    def missing_files(self) -> list[Path]:
        return [candidate for candidate in self.required_files() if not candidate.is_file()]

    def is_complete(self) -> bool:
        return not self.missing_files()

    def verify(self) -> None:
        missing = self.missing_files()
        if missing:
            raise ToolchainError(self._repair_hint(missing))

    def register_ffmpeg(self, ffmpeg_executable: Path) -> Path:
        ffmpeg_directory = self.root / FFMPEG_FOLDER
        ffmpeg_directory.mkdir(parents=True, exist_ok=True)

        config_file = ffmpeg_directory / FFMPEG_CONFIG_FILE
        config_file.write_text(
            FFMPEG_CONFIG_TEMPLATE.format(path=ffmpeg_executable), encoding="utf-8"
        )
        self._logger.debug("Pointed HLAE at ffmpeg via %s", config_file)
        return config_file

    def verify_path_is_ascii(self) -> None:
        if not str(self.root).isascii():
            raise ToolchainError(
                f"HLAE cannot run from a path with non-ASCII characters: {self.root}. "
                f"Move the application to a folder with a latin-only path."
            )

    def _repair_hint(self, missing: list[Path]) -> str:
        names = ", ".join(str(path.relative_to(self.root)) for path in missing)
        return (
            f"HLAE install at {self.root} is incomplete (missing: {names}). "
            f"Delete the tools folder and run again to reinstall it."
        )
