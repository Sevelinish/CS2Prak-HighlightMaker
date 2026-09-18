from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..domain.chase import ChasePath

PLAN_VERSION = 5


@dataclass(frozen=True, slots=True)
class ClipPlayer:
    name: str
    steam_id64: int
    account_id: int
    slot: int = 0

    def to_mapping(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "steamId64": str(self.steam_id64),
            "accountId": self.account_id,
            "slot": self.slot,
        }


@dataclass(frozen=True, slots=True)
class CameraBeat:
    tick: int
    name: str
    commands: tuple[str, ...]

    def to_mapping(self) -> dict[str, Any]:
        return {"tick": self.tick, "name": self.name, "commands": list(self.commands)}


@dataclass(frozen=True, slots=True)
class ClipSegment:
    index: int
    start_tick: int
    end_tick: int
    kill_ticks: tuple[int, ...]
    duration_seconds: float
    setup_commands: tuple[str, ...] = ()
    pass_index: int = 1
    player: "ClipPlayer | None" = None
    label: str = ""

    @property
    def name(self) -> str:
        return f"s{self.index:02d}"

    def to_mapping(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "startTick": self.start_tick,
            "endTick": self.end_tick,
            "killTicks": list(self.kill_ticks),
            "durationSeconds": round(self.duration_seconds, 2),
            "setupCommands": list(self.setup_commands),
            "pass": self.pass_index,
            "player": self.player.to_mapping() if self.player else None,
            "label": self.label,
        }


@dataclass(frozen=True, slots=True)
class ClipSpec:
    index: int
    name: str
    round_number: int
    player: ClipPlayer
    tags: tuple[str, ...]
    score: float
    segments: tuple[ClipSegment, ...]
    action_start_tick: int
    action_end_tick: int
    beats: tuple[CameraBeat, ...] = ()
    camera_path: ChasePath = ChasePath()
    note: str = ""

    @property
    def start_tick(self) -> int:
        return self.segments[0].start_tick

    @property
    def end_tick(self) -> int:
        return self.segments[-1].end_tick

    @property
    def duration_seconds(self) -> float:
        return sum(segment.duration_seconds for segment in self.segments)

    @property
    def skipped_seconds(self) -> float:
        covered = self.end_tick - self.start_tick
        recorded = sum(segment.end_tick - segment.start_tick for segment in self.segments)
        span = self.duration_seconds
        return span * (covered - recorded) / recorded if recorded else 0.0

    def to_mapping(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "name": self.name,
            "roundNumber": self.round_number,
            "player": self.player.to_mapping(),
            "tags": list(self.tags),
            "score": self.score,
            "startTick": self.start_tick,
            "endTick": self.end_tick,
            "actionStartTick": self.action_start_tick,
            "actionEndTick": self.action_end_tick,
            "durationSeconds": round(self.duration_seconds, 2),
            "segments": [segment.to_mapping() for segment in self.segments],
            "beats": [beat.to_mapping() for beat in self.beats],
            "cameraPath": {
                "startTick": self.camera_path.start_tick,
                "keyframes": self.camera_path.to_mapping(),
            },
            "note": self.note,
        }


@dataclass(slots=True)
class RecordingPlan:
    demo_path: Path
    demo_name: str
    map_name: str
    tick_rate: int
    fps: int
    width: int
    height: int
    output_directory: Path
    demo_end_tick: int = 0
    merged_sources: int = 0
    clips: list[ClipSpec] = field(default_factory=list)

    @property
    def clip_count(self) -> int:
        return len(self.clips)

    @property
    def total_seconds(self) -> float:
        return sum(clip.duration_seconds for clip in self.clips)

    def to_mapping(self) -> dict[str, Any]:
        return {
            "version": PLAN_VERSION,
            "demo": {
                "path": str(self.demo_path),
                "name": self.demo_name,
                "map": self.map_name,
                "tickRate": self.tick_rate,
                "endTick": self.demo_end_tick,
            },
            "recording": {
                "fps": self.fps,
                "width": self.width,
                "height": self.height,
            },
            "output": {
                "directory": str(self.output_directory),
            },
            "mergedSources": self.merged_sources,
            "clips": [clip.to_mapping() for clip in self.clips],
        }
