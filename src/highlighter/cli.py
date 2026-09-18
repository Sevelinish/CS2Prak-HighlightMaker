from __future__ import annotations

import argparse
import sys

from .api.contract import DEFAULT_HTTP_HOST, DEFAULT_HTTP_PORT, HOST_APPLICATION
from .infrastructure.errors import HighlighterError

PROGRAM_NAME = "HighlighterCS2"
DESCRIPTION = "Find highlight rounds in a CS2 demo and record them through HLAE."
EPILOG = """examples:
  HighlighterCS2                          open the prompt and type the rest there
  HighlighterCS2 -no-shell                pick a demo straight away, every player
  HighlighterCS2 match.dem                that demo, every player
  HighlighterCS2 match.dem -p s1mple      only that player
  HighlighterCS2 match.dem -p -n1clxe     names starting with a dash are fine
  HighlighterCS2 match.dem -p 76561198000000000
  HighlighterCS2 match.dem -enemy         then replay every kill from the victim's eyes
  HighlighterCS2 match.dem -one-file      join the picked moments into one video
  HighlighterCS2 match.dem -exit0         leave the game running for the next batch
  HighlighterCS2 -update                  install the newest release, keeping clips and config
  HighlighterCS2 -demoget                 import new demos from Downloads and the game folders
  HighlighterCS2 match.dem -m nades_smoke every smoke that was thrown
  HighlighterCS2 match.dem -m nades       every grenade of every kind
  HighlighterCS2 match.dem -m nades_smoke -fly  fly behind each smoke until it opens

  HighlighterCS2 --api http                start the plugin API on 127.0.0.1
  HighlighterCS2 --api stdio               speak the plugin API over stdin/stdout

Started without arguments in a console, the program opens its own prompt and
takes the same arguments there, one run per line, with suggestions as you type.

The demo can be a full path or just a file name; plain names are looked up in
the demo folder and in the CS2 demo folders.

The plugin API is the integration surface built for CS2Prak-Launcher. See
docs/API.md for the command reference.
"""

PLAYER_FLAGS = ("-p", "--player", "--player-name")
CANONICAL_PLAYER_FLAG = "--player"
ONE_FILE_FLAGS = ("-one-file", "--one-file")
KEEP_GAME_FLAGS = ("-exit0", "--exit0", "--keep-game-open")
UPDATE_FLAGS = ("-update", "--update")
DEMO_GET_FLAGS = ("-demoget", "--demoget")
FLY_FLAGS = ("-fly", "--fly")
ENEMY_FLAGS = ("-enemy", "--enemy")
SHELL_FLAGS = ("-shell", "--shell")
NO_SHELL_FLAGS = ("-no-shell", "--no-shell")
MODE_FLAGS = ("-m", "--mode")
API_FLAG = "--api"
API_TRANSPORTS = ("http", "stdio")
KNOWN_FLAGS = frozenset(
    {
        "-h",
        "--help",
        "-v",
        "--verbose",
        API_FLAG,
        "--api-host",
        "--api-port",
        "--api-token",
        "--api-endpoint-file",
        "--api-no-events",
        *PLAYER_FLAGS,
        *ONE_FILE_FLAGS,
        *KEEP_GAME_FLAGS,
        *UPDATE_FLAGS,
        *DEMO_GET_FLAGS,
        *FLY_FLAGS,
        *ENEMY_FLAGS,
        *SHELL_FLAGS,
        *NO_SHELL_FLAGS,
        *MODE_FLAGS,
    }
)


class CommandLineError(HighlighterError):
    pass


class CommandLineStop(Exception):
    def __init__(self, status: int = 0) -> None:
        super().__init__(status)
        self.status = status


class QuietParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CommandLineError(message)

    def exit(self, status: int = 0, message: str | None = None) -> None:
        if message:
            self._print_message(message, sys.stderr)
        raise CommandLineStop(status)


class CommandLine:
    @classmethod
    def parse(cls, argv: list[str]) -> argparse.Namespace:
        return cls.build_parser().parse_args(cls.normalize(argv))

    @classmethod
    def parse_quietly(cls, argv: list[str]) -> argparse.Namespace:
        return cls.build_parser(quiet=True).parse_args(cls.normalize(argv))

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
    def build_parser(quiet: bool = False) -> argparse.ArgumentParser:
        factory = QuietParser if quiet else argparse.ArgumentParser
        parser = factory(
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
            *MODE_FLAGS,
            dest="mode",
            default=None,
            metavar="MODE",
            help="what to look for: highlights (default), nades, nades_smoke, nades_flash, "
            "nades_he, nades_molotov, nades_decoy",
        )
        parser.add_argument(
            *ONE_FILE_FLAGS,
            dest="one_file",
            action="store_true",
            help="join every selected moment into a single video file",
        )
        parser.add_argument(
            *KEEP_GAME_FLAGS,
            dest="keep_game_open",
            action="store_true",
            help="leave CS2 running so the next batch skips the startup",
        )
        parser.add_argument(
            *UPDATE_FLAGS,
            dest="update",
            action="store_true",
            help="check for a newer release, download it and install it",
        )
        parser.add_argument(
            *ENEMY_FLAGS,
            dest="enemy",
            action="store_true",
            help="replay each kill from the victim's own eyes after the player view",
        )
        parser.add_argument(
            *FLY_FLAGS,
            dest="fly",
            action="store_true",
            help="follow the grenade in flight, from the throw to the detonation",
        )
        parser.add_argument(
            *DEMO_GET_FLAGS,
            dest="demo_get",
            action="store_true",
            help="find new demos in Downloads and the CS2 folders and import them",
        )
        parser.add_argument(
            *SHELL_FLAGS,
            dest="shell",
            action="store_true",
            help="open the prompt instead of running straight away",
        )
        parser.add_argument(
            *NO_SHELL_FLAGS,
            dest="no_shell",
            action="store_true",
            help="never open the prompt, run straight away",
        )
        CommandLine._add_api_arguments(parser)
        parser.add_argument(
            "-v",
            "--verbose",
            action="store_true",
            help="print debug output to the console",
        )
        return parser

    @staticmethod
    def _add_api_arguments(parser: argparse.ArgumentParser) -> None:
        group = parser.add_argument_group(
            "plugin API", f"the integration surface built for {HOST_APPLICATION}"
        )
        group.add_argument(
            API_FLAG,
            dest="api",
            nargs="?",
            const=API_TRANSPORTS[0],
            default=None,
            choices=API_TRANSPORTS,
            help="serve the plugin API instead of running the interactive app",
        )
        group.add_argument(
            "--api-host",
            dest="api_host",
            default=DEFAULT_HTTP_HOST,
            metavar="HOST",
            help=f"address the HTTP API binds to (default {DEFAULT_HTTP_HOST})",
        )
        group.add_argument(
            "--api-port",
            dest="api_port",
            type=int,
            default=DEFAULT_HTTP_PORT,
            metavar="PORT",
            help=f"port the HTTP API binds to, 0 picks a free one (default {DEFAULT_HTTP_PORT})",
        )
        group.add_argument(
            "--api-token",
            dest="api_token",
            default="",
            metavar="TOKEN",
            help="bearer token clients must send, generated when omitted",
        )
        group.add_argument(
            "--api-endpoint-file",
            dest="api_endpoint_file",
            default="",
            metavar="PATH",
            help="write the base URL and token to this JSON file once the API is up",
        )
        group.add_argument(
            "--api-no-events",
            dest="api_stream_events",
            action="store_false",
            help="stop the stdio transport from pushing job events",
        )
