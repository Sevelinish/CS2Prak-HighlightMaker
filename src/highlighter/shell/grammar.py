from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence

from ..modes import RunMode


class ValueKind(Enum):
    NONE = "none"
    PLAYER = "player"
    MODE = "mode"
    TRANSPORT = "transport"
    HOST = "host"
    PORT = "port"
    TOKEN = "token"
    PATH = "path"


class CandidateKind(Enum):
    COMMAND = "command"
    FLAG = "flag"
    VALUE = "value"
    DEMO = "demo"
    PLAYER = "player"


@dataclass(frozen=True, slots=True)
class Candidate:
    text: str
    summary: str = ""
    kind: CandidateKind = CandidateKind.VALUE


@dataclass(frozen=True, slots=True)
class Option:
    flags: tuple[str, ...]
    summary: str
    value: ValueKind = ValueKind.NONE
    placeholder: str = ""
    choices: tuple[str, ...] = ()

    @property
    def primary(self) -> str:
        return self.flags[0]

    @property
    def takes_value(self) -> bool:
        return self.value is not ValueKind.NONE

    def matches(self, prefix: str) -> tuple[str, ...]:
        return tuple(flag for flag in self.flags if flag.startswith(prefix))

    def best_match(self, prefix: str) -> str:
        matches = self.matches(prefix)
        if not matches:
            return ""
        return min(matches, key=lambda flag: (len(flag), flag))


@dataclass(frozen=True, slots=True)
class ShellCommand:
    names: tuple[str, ...]
    summary: str

    @property
    def primary(self) -> str:
        return self.names[0]


OPTIONS: tuple[Option, ...] = (
    Option(
        flags=("-p", "--player", "--player-name"),
        summary="only this player, by name, partial name or SteamID64",
        value=ValueKind.PLAYER,
        placeholder="<nickname>",
    ),
    Option(
        flags=("-m", "--mode"),
        summary="what to look for in the demo",
        value=ValueKind.MODE,
        placeholder="<mode>",
        choices=RunMode.tokens(),
    ),
    Option(
        flags=("-enemy", "--enemy"),
        summary="replay each kill from the victim's own eyes",
    ),
    Option(
        flags=("-fly", "--fly"),
        summary="follow the grenade from the throw to the detonation",
    ),
    Option(
        flags=("-one-file", "--one-file"),
        summary="join every selected moment into a single video",
    ),
    Option(
        flags=("-exit0", "--exit0", "--keep-game-open"),
        summary="leave CS2 running so the next run skips the startup",
    ),
    Option(
        flags=("-demoget", "--demoget"),
        summary="import new demos from Downloads and the game folders",
    ),
    Option(
        flags=("-update", "--update"),
        summary="install the newest release, keeping clips and config",
    ),
    Option(
        flags=("-v", "--verbose"),
        summary="print debug output to the console",
    ),
    Option(
        flags=("--api",),
        summary="serve the plugin API instead of recording",
        value=ValueKind.TRANSPORT,
        placeholder="<transport>",
        choices=("http", "stdio"),
    ),
    Option(
        flags=("--api-host",),
        summary="address the HTTP API binds to",
        value=ValueKind.HOST,
        placeholder="<host>",
    ),
    Option(
        flags=("--api-port",),
        summary="port the HTTP API binds to, 0 picks a free one",
        value=ValueKind.PORT,
        placeholder="<port>",
    ),
    Option(
        flags=("--api-token",),
        summary="bearer token clients must send",
        value=ValueKind.TOKEN,
        placeholder="<token>",
    ),
    Option(
        flags=("--api-endpoint-file",),
        summary="write the base URL and token to this JSON file",
        value=ValueKind.PATH,
        placeholder="<path>",
    ),
    Option(
        flags=("--api-no-events",),
        summary="stop the stdio transport from pushing job events",
    ),
    Option(
        flags=("-h", "--help"),
        summary="print the full argument reference",
    ),
)

COMMANDS: tuple[ShellCommand, ...] = (
    ShellCommand(("run",), "record with the arguments that follow, or with none at all"),
    ShellCommand(("help", "?"), "show what can be typed here"),
    ShellCommand(("demos",), "list the demos found, with map and player count"),
    ShellCommand(("players",), "list the nicknames read out of a demo"),
    ShellCommand(("clear", "cls"), "wipe the screen"),
    ShellCommand(("version",), "print the installed version"),
    ShellCommand(("exit", "quit"), "leave the shell"),
)

DEMO_PLACEHOLDER = "<demo>"
FLAG_PLACEHOLDER = "<flag>"


class Grammar:
    def __init__(
        self,
        options: Sequence[Option] = OPTIONS,
        commands: Sequence[ShellCommand] = COMMANDS,
    ) -> None:
        self._options = tuple(options)
        self._commands = tuple(commands)
        self._by_flag = {flag: option for option in self._options for flag in option.flags}
        self._by_name = {name: command for command in self._commands for name in command.names}

    @property
    def options(self) -> tuple[Option, ...]:
        return self._options

    @property
    def commands(self) -> tuple[ShellCommand, ...]:
        return self._commands

    def option_for(self, flag: str) -> Option | None:
        return self._by_flag.get(flag)

    def command_for(self, name: str) -> ShellCommand | None:
        return self._by_name.get(name.lower())

    def flag_candidates(self, prefix: str, taken: Sequence[str] = ()) -> tuple[Candidate, ...]:
        excluded = {self._by_flag[flag].primary for flag in taken if flag in self._by_flag}
        found: list[Candidate] = []
        for option in self._options:
            if option.primary in excluded:
                continue
            flag = option.best_match(prefix)
            if flag:
                found.append(
                    Candidate(text=flag, summary=option.summary, kind=CandidateKind.FLAG)
                )
        return tuple(found)

    def command_candidates(self, prefix: str) -> tuple[Candidate, ...]:
        lowered = prefix.lower()
        return tuple(
            Candidate(
                text=command.primary, summary=command.summary, kind=CandidateKind.COMMAND
            )
            for command in self._commands
            if command.primary.startswith(lowered)
        )

    @staticmethod
    def value_candidates(option: Option, prefix: str) -> tuple[Candidate, ...]:
        return tuple(
            Candidate(text=choice, summary=option.summary, kind=CandidateKind.VALUE)
            for choice in option.choices
            if choice.startswith(prefix.lower())
        )
