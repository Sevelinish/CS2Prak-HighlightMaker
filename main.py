from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from highlighter.application import Application
from highlighter.cli import CommandLine


def main() -> int:
    arguments = CommandLine.parse(sys.argv[1:])
    return Application(
        demo_argument=arguments.demo,
        player_query=arguments.player,
        mode_token=arguments.mode,
        one_file=arguments.one_file,
        verbose=arguments.verbose,
    ).run()


if __name__ == "__main__":
    raise SystemExit(main())
