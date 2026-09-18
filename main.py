from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from highlighter.cli import CommandLine
from highlighter.entrypoint import EntryPoint
from highlighter.shell import ShellLauncher, ShellSession


def main() -> int:
    argv = sys.argv[1:]
    arguments = CommandLine.parse(argv)
    if ShellLauncher.wanted(argv, arguments):
        return ShellSession().run()
    return EntryPoint.execute(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
