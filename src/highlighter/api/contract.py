from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..domain.grenade import GrenadeKind

PROTOCOL_VERSION = "1.0"
PLUGIN_ID = "highlightercs2"
PLUGIN_NAME = "HighlighterCS2"
PLUGIN_VERSION = "1.0.0"
PLUGIN_KIND = "demo-recorder"
HOST_APPLICATION = "CS2Prak-Launcher"
HOST_REPOSITORY = "https://github.com/Sevelinish/CS2Prak-Launcher"
WRITTEN_FOR = (
    f"This plugin API is written specifically for {HOST_APPLICATION} "
    f"({HOST_REPOSITORY}). It is the supported integration surface of "
    f"{PLUGIN_NAME} and is versioned independently of the command line."
)

ENVELOPE_ID_KEY = "id"
ENVELOPE_COMMAND_KEY = "command"
ENVELOPE_PAYLOAD_KEY = "payload"
DEFAULT_HTTP_HOST = "127.0.0.1"
DEFAULT_HTTP_PORT = 8787
AUTHORIZATION_HEADER = "Authorization"
TOKEN_SCHEME = "Bearer"


@dataclass(frozen=True, slots=True)
class CommandDescriptor:
    name: str
    summary: str
    payload: tuple[str, ...] = ()
    returns: str = ""
    long_running: bool = False

    def to_mapping(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "summary": self.summary,
            "payload": list(self.payload),
            "returns": self.returns,
            "longRunning": self.long_running,
        }


@dataclass(frozen=True, slots=True)
class CapabilityDescriptor:
    name: str
    supported: bool
    detail: str = ""

    def to_mapping(self) -> dict[str, Any]:
        return {"name": self.name, "supported": self.supported, "detail": self.detail}


COMMANDS: tuple[CommandDescriptor, ...] = (
    CommandDescriptor(
        name="handshake",
        summary="Identify the plugin and return the full command and capability catalogue",
        payload=("clientName", "clientVersion", "protocol"),
        returns="PluginDescriptor",
    ),
    CommandDescriptor(
        name="system.probe",
        summary="Report whether CS2, HLAE and ffmpeg are ready and which encoder will be used",
        returns="SystemReport",
    ),
    CommandDescriptor(
        name="config.get",
        summary="Return the effective configuration exactly as config.json stores it",
        returns="ConfigDocument",
    ),
    CommandDescriptor(
        name="config.describe",
        summary="Return field metadata for every setting so a settings screen can be generated",
        returns="ConfigSchema",
    ),
    CommandDescriptor(
        name="config.patch",
        summary="Merge a partial configuration document into config.json and persist it",
        payload=("patch", "persist"),
        returns="ConfigDocument",
    ),
    CommandDescriptor(
        name="demos.list",
        summary="List every demo found in the configured folders and the CS2 replay folders",
        payload=("search", "limit"),
        returns="DemoList",
    ),
    CommandDescriptor(
        name="demos.inspect",
        summary="Parse a demo and return map, tick rate, rounds, players and team rosters",
        payload=("demo", "refresh"),
        returns="MatchDocument",
    ),
    CommandDescriptor(
        name="match.rounds",
        summary="Return the round timeline of a demo with kills folded into each round",
        payload=("demo", "rounds", "includeKills"),
        returns="RoundList",
    ),
    CommandDescriptor(
        name="match.players",
        summary="Return the roster of a demo with per player kill counts",
        payload=("demo",),
        returns="PlayerList",
    ),
    CommandDescriptor(
        name="highlights.find",
        summary="Detect highlights and return them with stable identifiers for selection",
        payload=("demo", "selection", "detection"),
        returns="HighlightList",
    ),
    CommandDescriptor(
        name="grenades.find",
        summary="Read grenade throws and return them with landing callouts and identifiers",
        payload=("demo", "kinds", "selection"),
        returns="GrenadeList",
    ),
    CommandDescriptor(
        name="plan.preview",
        summary="Build the recording plan for a selection without launching the game",
        payload=("demo", "source", "selection", "overrides"),
        returns="PlanDocument",
    ),
    CommandDescriptor(
        name="jobs.submit",
        summary="Queue a recording job for a selection and return its identifier immediately",
        payload=("demo", "source", "selection", "overrides", "label", "validate"),
        returns="JobDocument",
        long_running=True,
    ),
    CommandDescriptor(
        name="jobs.get",
        summary="Return one job with its current stage, progress and result",
        payload=("jobId",),
        returns="JobDocument",
    ),
    CommandDescriptor(
        name="jobs.list",
        summary="Return every job the plugin knows about, newest first",
        payload=("state", "limit"),
        returns="JobList",
    ),
    CommandDescriptor(
        name="jobs.events",
        summary="Read job events from a sequence number, optionally waiting for new ones",
        payload=("jobId", "since", "waitSeconds", "limit"),
        returns="EventPage",
    ),
    CommandDescriptor(
        name="jobs.cancel",
        summary="Cancel a queued job outright or stop the game of a running job",
        payload=("jobId",),
        returns="JobDocument",
    ),
    CommandDescriptor(
        name="jobs.result",
        summary="Return the produced files of a finished job",
        payload=("jobId",),
        returns="JobResult",
    ),
    CommandDescriptor(
        name="output.list",
        summary="List videos already written for a demo",
        payload=("demo",),
        returns="OutputList",
    ),
    CommandDescriptor(
        name="output.reveal",
        summary="Open the output folder of a demo in the file manager",
        payload=("demo",),
        returns="RevealResult",
    ),
    CommandDescriptor(
        name="shutdown",
        summary="Stop the API server once the current job finishes",
        payload=("force",),
        returns="ShutdownResult",
    ),
)

COMMAND_NAMES: tuple[str, ...] = tuple(command.name for command in COMMANDS)


@dataclass(frozen=True, slots=True)
class PluginDescriptor:
    transports: tuple[str, ...]
    capabilities: tuple[CapabilityDescriptor, ...] = field(default_factory=tuple)
    root: str = ""
    config_file: str = ""
    output_directory: str = ""

    def to_mapping(self) -> dict[str, Any]:
        return {
            "plugin": {
                "id": PLUGIN_ID,
                "name": PLUGIN_NAME,
                "version": PLUGIN_VERSION,
                "kind": PLUGIN_KIND,
            },
            "protocol": PROTOCOL_VERSION,
            "writtenFor": {
                "application": HOST_APPLICATION,
                "repository": HOST_REPOSITORY,
                "statement": WRITTEN_FOR,
            },
            "transports": list(self.transports),
            "capabilities": [item.to_mapping() for item in self.capabilities],
            "commands": [command.to_mapping() for command in COMMANDS],
            "grenadeKinds": list(GrenadeKind.tokens()),
            "sources": ["highlights", "grenades"],
            "paths": {
                "root": self.root,
                "configFile": self.config_file,
                "outputDirectory": self.output_directory,
            },
        }
