from __future__ import annotations

import re
from pathlib import Path

from ..config.schema import NadeConfig, RecordingConfig
from ..domain.geometry import CameraPlacement
from ..domain.grenade import Grenade
from ..domain.match import Match
from .models import CameraBeat, ClipPlayer, ClipSegment, ClipSpec, RecordingPlan

UNSAFE_NAME_PATTERN = re.compile(r"[^a-z0-9]+")
MAXIMUM_NAME_TOKEN_LENGTH = 18
ROAMING_SPECTATOR_MODE = 4
MINIMUM_FREEZE_TICKS = 1


class NadePlanBuilder:
    def __init__(self, recording: RecordingConfig, nades: NadeConfig) -> None:
        self._recording = recording
        self._nades = nades

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
        )

        rounds_by_number = {round_.number: round_ for round_ in match.rounds}
        ordered = sorted(grenades, key=lambda item: item.throw_tick)

        for index, grenade in enumerate(ordered, start=1):
            segments = self._segments(match, grenade, rounds_by_number)
            plan.clips.append(
                ClipSpec(
                    index=index,
                    name=self._clip_name(index, grenade),
                    round_number=grenade.round_number,
                    player=ClipPlayer(
                        name=grenade.thrower.name,
                        steam_id64=grenade.thrower.steam_id64,
                        account_id=grenade.thrower.account_id,
                        slot=grenade.thrower.slot,
                    ),
                    tags=(grenade.kind.label, grenade.landing_place),
                    score=0.0,
                    segments=segments,
                    action_start_tick=grenade.throw_tick,
                    action_end_tick=grenade.detonate_tick,
                    beats=self._beats(match, grenade, len(segments) > 1),
                    note=(
                        f"{grenade.kind.label} into {grenade.landing_place} | "
                        f"{grenade.setpos_command}; {grenade.setang_command}"
                    ),
                )
            )

        return plan

    def _segments(
        self, match: Match, grenade: Grenade, rounds_by_number
    ) -> tuple[ClipSegment, ...]:
        start = grenade.throw_tick - match.seconds_to_ticks(self._nades.lead_in_seconds)
        round_ = rounds_by_number.get(grenade.round_number)
        if round_ is not None:
            start = max(start, round_.freeze_end_tick)
        start = max(0, start)

        end = grenade.detonate_tick + match.seconds_to_ticks(
            self._nades.landing_hold_seconds
        )
        landing_start = grenade.detonate_tick - match.seconds_to_ticks(
            self._nades.landing_lead_seconds
        )
        throw_end = grenade.throw_tick + match.seconds_to_ticks(
            self._nades.landing_cut_seconds
        )

        if not self._worth_skipping(throw_end, landing_start):
            return (
                self._segment(match, 1, start, max(end, start + match.tick_rate), grenade),
            )

        return (
            self._segment(match, 1, start, throw_end, grenade),
            self._segment(
                match,
                2,
                landing_start,
                max(end, landing_start + match.tick_rate),
                grenade,
                setup=self._landing_commands(grenade),
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
        grenade: Grenade,
        setup: tuple[str, ...] = (),
    ) -> ClipSegment:
        return ClipSegment(
            index=index,
            start_tick=start_tick,
            end_tick=end_tick,
            kill_ticks=(grenade.throw_tick,),
            duration_seconds=match.ticks_to_seconds(end_tick - start_tick),
            setup_commands=setup,
        )

    def _landing_commands(self, grenade: Grenade) -> tuple[str, ...]:
        camera = CameraPlacement.looking_at(
            target=grenade.landing,
            from_side=grenade.thrower_position,
            distance=self._nades.landing_distance,
            height=self._nades.landing_height,
        )
        return (
            f"spec_mode {ROAMING_SPECTATOR_MODE}",
            (
                f"spec_goto {camera.position.x:.1f} {camera.position.y:.1f} "
                f"{camera.position.z:.1f} {camera.angles.pitch:.1f} "
                f"{camera.angles.yaw:.1f}"
            ),
        )

    def _beats(
        self, match: Match, grenade: Grenade, landing_is_own_segment: bool
    ) -> tuple[CameraBeat, ...]:
        freeze_start = grenade.throw_tick - match.seconds_to_ticks(
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
                    tick=self._landing_cut_tick(match, grenade),
                    name="landing",
                    commands=self._landing_commands(grenade),
                )
            )
        return tuple(beats)

    def _landing_cut_tick(self, match: Match, grenade: Grenade) -> int:
        cut = grenade.throw_tick + match.seconds_to_ticks(self._nades.landing_cut_seconds)
        return min(cut, grenade.detonate_tick)

    def _clip_name(self, index: int, grenade: Grenade) -> str:
        parts = [
            f"{index:02d}",
            f"round{grenade.round_number:02d}",
            self._slug(grenade.thrower.name),
            self._slug(grenade.kind.label),
            self._slug(grenade.landing_place),
        ]
        return "_".join(part for part in parts if part)

    @staticmethod
    def _slug(value: str) -> str:
        cleaned = UNSAFE_NAME_PATTERN.sub("_", value.lower()).strip("_")
        return cleaned[:MAXIMUM_NAME_TOKEN_LENGTH]
