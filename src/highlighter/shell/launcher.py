from __future__ import annotations

import argparse
from typing import Sequence

from .terminal import TerminalCapabilities


class ShellLauncher:
    @staticmethod
    def wanted(argv: Sequence[str], arguments: argparse.Namespace) -> bool:
        if getattr(arguments, "no_shell", False) or arguments.api:
            return False
        if getattr(arguments, "shell", False):
            return True
        if argv:
            return False
        return TerminalCapabilities.is_interactive()
