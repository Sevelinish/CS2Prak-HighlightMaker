from __future__ import annotations

import re
from pathlib import Path
from typing import Sequence

from ..config.schema import NadeConfig, RecordingConfig
from ..domain.camera import LandingCameraDirector, LandingShot
from ..domain.grenade import Grenade
from ..domain.match import Match
from .grouping import OverlapGrouper, Window
from .models import CameraBeat, ClipPlayer, ClipSegment, ClipSpec, RecordingPlan

UNSAFE_NAME_PATTERN = re.compile(r"[^a-z0-9]+")
MAXIMUM_NAME_TOKEN_LENGTH = 18
MAXIMUM_NAME_PLACES = 2
ROAMING_SPECTATOR_MODE = 4
MINIMUM_FREEZE_TICKS = 1


class NadePlanBuilder:
    def __init__(self, recording: RecordingConfig, nades: NadeConfig) -> None:
        self._recording = recording
        self._nades = nades
        self._merged = 0

    @property
    def merged_count(self) -> int:
        return self._merged

    def build(
        self, match: Match, grenades: list[Grenade], output_directory: Path
    ) -> RecordingPlan:
        plan = RecordingPlan(
            demo_path=match.demo_path,
            demo_name=match.demo_name,
            map_name=match.map_name,
            tick_rate=match.tick_rate,
            fps=self._recording.fps,
            width=self._recording.width,
            height=self._recording.height,
            output_directory=output_directory,
            demo_end_tick=_demo_end_tick(match),
        )

        rounds_by_number = {round_.number: round_ for round_ in match.rounds}
        groups = OverlapGrouper.group(
            grenades, lambda item: self._window(match, item, rounds_by_number)
        )
        self._merged = OverlapGrouper.merged_count(groups)

        for index, group in enumerate(groups, start=1):
            ordered = sorted(group, key=lambda item: item.throw_tick)
            segments = self._segments(match, ordered, rounds_by_number)
            plan.clips.append(
                ClipSpec(
                    index=index,
                    name=self._clip_name(index, ordered),
                    round_number=ordered[0].round_number,
                    player=self._player(ordered[0]),
                    tags=self._tags(ordered),
                    score=0.0,
                    segments=segments,
                    action_start_tick=ordered[0].throw_tick,
                    action_end_tick=max(item.detonate_tick for item in ordered),
                    beats=self._beats(match, ordered, len(segments) > 1),
                    note=self._note(ordered),
                )
            )

        plan.merged_sources = self._merged
        return plan

    def _window(
        self, match: Match, grenade: Grenade, rounds_by_number
    ) -> Window:
        return Window(
            start=self._clip_start(match, grenade.throw_tick, grenade, rounds_by_number),
            end=grenade.detonate_tick
            + match.seconds_to_ticks(self._nades.landing_hold_seconds),
        )

    def _clip_start(
        self, match: Match, throw_tick: int, grenade: Grenade, rounds_by_number
    ) -> int:
        start = throw_tick - match.seconds_to_ticks(self._nades.lead_in_seconds)
        round_ = rounds_by_number.get(grenade.round_number)
        if round_ is not None and throw_tick >= round_.freeze_end_tick:
            start = max(start, round_.freeze_end_tick)
        return max(0, start)

    def _segments(
        self, match: Match, group: Sequence[Grenade], rounds_by_number
    ) -> tuple[ClipSegment, ...]:
        first = group[0]
        start = self._clip_start(match, first.throw_tick, first, rounds_by_number)
        end = max(item.detonate_tick for item in group) + match.seconds_to_ticks(
            self._nades.landing_hold_seconds
        )
        landing_start = min(item.detonate_tick for item in group) - match.seconds_to_ticks(
            self._nades.landing_lead_seconds
        )
        throw_end = max(item.throw_tick for item in group) + match.seconds_to_ticks(
            self._nades.landing_cut_seconds
        )

        if not self._worth_skipping(throw_end, landing_start):
            return (
                self._segment(match, 1, start, max(end, start + match.tick_rate), group),
            )

        return (
            self._segment(match, 1, start, throw_end, group),
            self._segment(
                match,
                2,
                landing_start,
                max(end, landing_start + match.tick_rate),
                group,
                setup=self._landing_commands(group),
            ),
        )

    def _worth_skipping(self, throw_end: int, landing_start: int) -> bool:
        return landing_start - self._recording.seek_lead_ticks > throw_end

    @staticmethod
    def _segment(
        match: Match,
        index: int,
        start_tick: int,
        end_tick: int,
        group: Sequence[Grenade],
        setup: tuple[str, ...] = (),
    ) -> ClipSegment:
        return ClipSegment(
            index=index,
            start_tick=start_tick,
            end_tick=end_tick,
            kill_ticks=tuple(item.throw_tick for item in group),
            duration_seconds=match.ticks_to_seconds(end_tick - start_tick),
            setup_commands=setup,
        )

    def _director(self) -> LandingCameraDirector:
        return LandingCameraDirector(
            distance=self._nades.landing_distance,
            height=self._nades.landing_height,
            minimum_approach=self._nades.minimum_approach,
            mode=self._nades.camera_mode,
            maximum_spread=self._nades.maximum_group_spread,
        )

    def _landing_shot(self, group: Sequence[Grenade]) -> LandingShot:
        return self._director().direct_group(list(group))

    def _landing_commands(self, group: Sequence[Grenade]) -> tuple[str, ...]:
        camera = self._landing_shot(group).placement
        return (
            f"spec_mode {ROAMING_SPECTATOR_MODE}",
            (
                f"spec_goto {camera.position.x:.1f} {camera.position.y:.1f} "
                f"{camera.position.z:.1f} {camera.angles.pitch:.1f} "
                f"{camera.angles.yaw:.1f}"
            ),
        )

    def _beats(
        self,
        match: Match,
        group: Sequence[Grenade],
        landing_is_own_segment: bool,
    ) -> tuple[CameraBeat, ...]:
        freeze_start = group[0].throw_tick - match.seconds_to_ticks(
            self._nades.freeze_lead_seconds
        )
        freeze_ticks = max(
            MINIMUM_FREEZE_TICKS, match.seconds_to_ticks(self._nades.freeze_seconds)
        )
        beats = [
            CameraBeat(
                tick=freeze_start,
                name="zoom",
                commands=(f"mirv_fov {self._nades.zoom_fov:g}",),
            ),
            CameraBeat(
                tick=freeze_start + freeze_ticks,
                name="unzoom",
                commands=("mirv_fov default",),
            ),
        ]

        if not landing_is_own_segment:
            beats.append(
                CameraBeat(
                    tick=self._landing_cut_tick(match, group),
                    name="landing",
                    commands=self._landing_commands(group),
                )
            )
        return tuple(beats)

    def _landing_cut_tick(self, match: Match, group: Sequence[Grenade]) -> int:
        cut = max(item.throw_tick for item in group) + match.seconds_to_ticks(
            self._nades.landing_cut_seconds
        )
        return min(cut, min(item.detonate_tick for item in group))

    @staticmethod
    def _player(grenade: Grenade) -> ClipPlayer:
        return ClipPlayer(
            name=grenade.thrower.name,
            steam_id64=grenade.thrower.steam_id64,
            account_id=grenade.thrower.account_id,
            slot=grenade.thrower.slot,
        )

    @staticmethod
    def _tags(group: Sequence[Grenade]) -> tuple[str, ...]:
        kinds = _unique(item.kind.label for item in group)
        places = _unique(item.landing_place for item in group)
        return (*kinds, *places)

    def _note(self, group: Sequence[Grenade]) -> str:
        shot = self._landing_shot(group)
        lines = [
            f"{item.kind.label} into {item.landing_place} | "
            f"{item.setpos_command}; {item.setang_command}"
            for item in group
        ]
        if len(group) > 1:
            lines.insert(0, f"{len(group)} throws filmed as one clip")
        lines.append(f"landing camera {shot.mode}: {shot.reason}")
        return " | ".join(lines)

    def _clip_name(self, index: int, group: Sequence[Grenade]) -> str:
        kinds = _unique(item.kind.label for item in group)
        places = _unique(item.landing_place for item in group)
        count = f"{len(group)}x" if len(group) > 1 else ""
        parts = [
            f"{index:02d}",
            f"round{group[0].round_number:02d}",
            self._slug(group[0].thrower.name),
            f"{count}{self._slug('_'.join(kinds))}",
        ]
        parts.extend(self._slug(place) for place in places[:MAXIMUM_NAME_PLACES])
        return "_".join(part for part in parts if part)

    @staticmethod
    def _slug(value: str) -> str:
        cleaned = UNSAFE_NAME_PATTERN.sub("_", value.lower()).strip("_")
        return cleaned[:MAXIMUM_NAME_TOKEN_LENGTH]


def _unique(values) -> tuple[str, ...]:
    seen: list[str] = []
    for value in values:
        if value not in seen:
            seen.append(value)
    return tuple(seen)


def _demo_end_tick(match: Match) -> int:
    return max((round_.end_tick for round_ in match.rounds), default=0)
