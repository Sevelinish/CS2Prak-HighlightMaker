from __future__ import annotations

import argparse

PROGRAM_NAME = "HighlighterCS2"
DESCRIPTION = "Find highlight rounds in a CS2 demo and record them through HLAE."
EPILOG = """examples:
  HighlighterCS2                          pick a demo, every player
  HighlighterCS2 match.dem                that demo, every player
  HighlighterCS2 match.dem -p s1mple      only that player
  HighlighterCS2 match.dem -p -n1clxe     names starting with a dash are fine
  HighlighterCS2 match.dem -p 76561198000000000
  HighlighterCS2 match.dem -one-file      join the picked moments into one video

The demo can be a full path or just a file name; plain names are looked up in
the demo folder and in the CS2 demo folders.
"""

PLAYER_FLAGS = ("-p", "--player", "--player-name")
CANONICAL_PLAYER_FLAG = "--player"
ONE_FILE_FLAGS = ("-one-file", "--one-file")
KNOWN_FLAGS = frozenset(
    {"-h", "--help", "-v", "--verbose", *PLAYER_FLAGS, *ONE_FILE_FLAGS}
)


class CommandLine:
    @classmethod
    def parse(cls, argv: list[str]) -> argparse.Namespace:
        return cls.build_parser().parse_args(cls.normalize(argv))

    @staticmethod
    def normalize(argv: list[str]) -> list[str]:
        normalized: list[str] = []
        index = 0
        while index < len(argv):
            token = argv[index]
            following = argv[index + 1] if index + 1 < len(argv) else None
            if (
                token in PLAYER_FLAGS
                and following is not None
                and following.startswith("-")
                and following not in KNOWN_FLAGS
            ):
                normalized.append(f"{CANONICAL_PLAYER_FLAG}={following}")
                index += 2
                continue
            normalized.append(token)
            index += 1
        return normalized

    @staticmethod
    def build_parser() -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            prog=PROGRAM_NAME,
            description=DESCRIPTION,
            epilog=EPILOG,
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        parser.add_argument(
            "demo",
            nargs="?",
            default=None,
            help="demo file name or path (omit to pick from the demo folders)",
        )
        parser.add_argument(
            *PLAYER_FLAGS,
            dest="player",
            default=None,
            metavar="NAME",
            help="only this player's highlights (name, partial name or SteamID64)",
        )
        parser.add_argument(
            *ONE_FILE_FLAGS,
            dest="one_file",
            action="store_true",
            help="join every selected moment into a single video file",
        )
        parser.add_argument(
            "-v",
            "--verbose",
            action="store_true",
            help="print debug output to the console",
        )
        return parser
