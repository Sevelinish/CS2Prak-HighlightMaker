from __future__ import annotations

import os
import subprocess
from pathlib import Path

from ..infrastructure.logging import get_logger

EXPLORER = "explorer"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class FolderOpener:
    def __init__(self, enabled: bool = True) -> None:
        self._enabled = enabled
        self._logger = get_logger("media.folder")

    def open(self, folder: Path) -> bool:
        if not self._enabled or not folder.is_dir():
            return False

        try:
            os.startfile(str(folder))
        except (OSError, AttributeError):
            return self._open_with_explorer(folder)
        return True

    def _open_with_explorer(self, folder: Path) -> bool:
        try:
            subprocess.Popen([EXPLORER, str(folder)], creationflags=NO_WINDOW)
        except OSError as error:
            self._logger.warning("Could not open %s: %s", folder, error)
            return False
        return True
