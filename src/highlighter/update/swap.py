from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

SCRIPT_NAME = "apply_update.cmd"
MARKER_NAME = "applied.txt"
LOG_NAME = "update.log"
MAXIMUM_WAIT_TICKS = 180
ROBOCOPY_FAILURE_LEVEL = 8
SYSTEM_DIRECTORY = r"%SystemRoot%\System32"
TASKLIST = r'"%SYSTEM%\tasklist.exe"'
FIND = r'"%SYSTEM%\find.exe"'
PING = r'"%SYSTEM%\ping.exe"'
ROBOCOPY = r'"%SYSTEM%\robocopy.exe"'
BUNDLE = r'"%TARGET%\_internal"'
RELEASE_EXECUTABLE = "HighlighterCS2.exe"


@dataclass(frozen=True, slots=True)
class SwapPlan:
    script: Path
    marker: Path
    log: Path


class SwapScriptWriter:
    def __init__(self, staging_directory: Path, log_directory: Path) -> None:
        self._staging = staging_directory
        self._log_directory = log_directory

    def plan(self) -> SwapPlan:
        return SwapPlan(
            script=self._staging / SCRIPT_NAME,
            marker=self._staging / MARKER_NAME,
            log=self._log_directory / LOG_NAME,
        )

    def write(
        self,
        target: Path,
        payload_root: Path,
        archive: Path,
        process_id: int,
        version: str,
        protected_files: Sequence[str],
        protected_directories: Sequence[str],
        relaunch: bool,
    ) -> SwapPlan:
        plan = self.plan()
        self._staging.mkdir(parents=True, exist_ok=True)
        self._log_directory.mkdir(parents=True, exist_ok=True)
        plan.marker.unlink(missing_ok=True)
        plan.script.write_text(
            self._render(
                target=target,
                payload_root=payload_root,
                archive=archive,
                process_id=process_id,
                version=version,
                plan=plan,
                protected_files=protected_files,
                protected_directories=protected_directories,
                relaunch=relaunch,
            ),
            encoding="utf-8",
        )
        return plan

    def _render(
        self,
        target: Path,
        payload_root: Path,
        archive: Path,
        process_id: int,
        version: str,
        plan: SwapPlan,
        protected_files: Sequence[str],
        protected_directories: Sequence[str],
        relaunch: bool,
    ) -> str:
        staged_root = (
            payload_root.parent if payload_root.parent != self._staging else payload_root
        )
        relaunch_line = (
            f'start "" "{target / RELEASE_EXECUTABLE}"' if relaunch else ""
        )

        return "\n".join(
            [
                "@echo off",
                "setlocal",
                f'set "SYSTEM={SYSTEM_DIRECTORY}"',
                f'set "TARGET={target}"',
                f'set "PAYLOAD={payload_root}"',
                f'set "LOGFILE={plan.log}"',
                f'set "MARKER={plan.marker}"',
                'set "WAITED=0"',
                "",
                f'>>"%LOGFILE%" echo [%date% %time%] waiting for pid {process_id}',
                ":wait",
                f'{TASKLIST} /FI "PID eq {process_id}" /NH 2>nul'
                f' | {FIND} "{process_id}" >nul',
                "if errorlevel 1 goto ready",
                "set /a WAITED+=1",
                f"if %WAITED% GEQ {MAXIMUM_WAIT_TICKS} goto giveup",
                f"{PING} -n 2 127.0.0.1 >nul",
                "goto wait",
                "",
                ":giveup",
                '>>"%LOGFILE%" echo [%date% %time%] the old version is still running,'
                " nothing changed",
                "exit /b 1",
                "",
                ":ready",
                '>>"%LOGFILE%" echo [%date% %time%] replacing the program files',
                f"if exist {BUNDLE} rmdir /s /q {BUNDLE}",
                f'{ROBOCOPY} "%PAYLOAD%" "%TARGET%" /E /NFL /NDL /NJH /NJS /NP /R:3 /W:2'
                f' {self._exclusions(protected_files, protected_directories)}'
                f' >>"%LOGFILE%"',
                f"if errorlevel {ROBOCOPY_FAILURE_LEVEL} goto failed",
                "",
                f'>"%MARKER%" echo {version}',
                f'>>"%LOGFILE%" echo [%date% %time%] installed {version}',
                f'rmdir /s /q "{staged_root}"',
                f'del /q "{archive}" 2>nul',
                relaunch_line,
                "endlocal",
                "exit /b 0",
                "",
                ":failed",
                '>>"%LOGFILE%" echo [%date% %time%] robocopy could not replace the files',
                "endlocal",
                "exit /b 1",
                "",
            ]
        )

    @staticmethod
    def _exclusions(
        protected_files: Sequence[str], protected_directories: Sequence[str]
    ) -> str:
        files = " ".join(f'"{name}"' for name in protected_files)
        directories = " ".join(f'"{name}"' for name in protected_directories)
        parts = (
            f"/XF {files}" if files else "",
            f"/XD {directories}" if directories else "",
        )
        return " ".join(part for part in parts if part)
