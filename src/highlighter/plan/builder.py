from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path
from typing import Sequence

from ..config.schema import RecordingConfig
from ..domain.highlight import Highlight
from ..domain.kill import Kill
from ..domain.match import Match
from ..domain.round import Round
from ..domain.player import Player
from .grouping import OverlapGrouper, Window
from .models import ClipPlayer, ClipSegment, ClipSpec, RecordingPlan
from .passes import PassPlanner, PassSlot
from .segmenter import ClipSegmenter

UNSAFE_NAME_PATTERN = re.compile(r"[^a-z0-9]+")
MAXIMUM_NAME_TOKEN_LENGTH = 18
PRIMARY_TAG_COUNT = 2
ENEMY_LABEL = "enemy"


class RecordingPlanBuilder:
    def __init__(self, settings: RecordingConfig) -> None:
        self._settings = settings
        self._merged = 0

    @property
    def merged_count(self) -> int:
        return self._merged

    def build(
        self, match: Match, highlights: list[Highlight], output_directory: Path
    ) -> RecordingPlan:
        plan = RecordingPlan(
            demo_path=match.demo_path,
            demo_name=match.demo_name,
            map_name=match.map_name,
            tick_rate=match.tick_rate,
            fps=self._settings.fps,
            width=self._settings.width,
            height=self._settings.height,
            output_directory=output_directory,
            demo_end_tick=_demo_end_tick(match),
        )

        segmenter = ClipSegmenter(self._settings, match)
        rounds_by_number = {round_.number: round_ for round_ in match.rounds}
        groups = OverlapGrouper.group(
            highlights, lambda item: self._window(match, item, rounds_by_number)
        )
        self._merged = OverlapGrouper.merged_count(groups)

        index = 0
        for group in groups:
            ordered = sorted(group, key=lambda item: item.first_tick)
            lead = self._leading(ordered)
            kills = self._kills(ordered)
            segments = segmenter.segment(
                kills, self._round_for(ordered, rounds_by_number)
            )
            if not segments:
                continue
            segments = (*segments, *self._enemy_segments(match, kills, len(segments)))

            index += 1
            plan.clips.append(
                ClipSpec(
                    index=index,
                    name=self._clip_name(index, lead, len(ordered)),
                    round_number=lead.round_number,
                    player=ClipPlayer(
                        name=lead.player.name,
                        steam_id64=lead.player.steam_id64,
                        account_id=lead.player.account_id,
                        slot=lead.player.slot,
                    ),
                    tags=self._tags(ordered),
                    score=max(item.score for item in ordered),
                    segments=segments,
                    action_start_tick=min(item.first_tick for item in ordered),
                    action_end_tick=max(item.last_tick for item in ordered),
                    note=self._note(ordered, lead),
                )
            )

        plan.merged_sources = self._merged
        self._assign_passes(plan)
        return plan

    def _enemy_segments(
        self, match: Match, kills: Sequence[Kill], offset: int
    ) -> tuple[ClipSegment, ...]:
        if not self._settings.record_enemy_view:
            return ()

        lead = match.seconds_to_ticks(self._settings.enemy_lead_seconds)
        hold = match.seconds_to_ticks(self._settings.enemy_hold_seconds)
        collected: list[ClipSegment] = []

        for position, kill in enumerate(kills, start=1):
            victim = match.players.get(kill.victim.steam_id64, kill.victim)
            start = max(0, kill.tick - lead)
            end = max(kill.tick + hold, start + match.tick_rate)
            collected.append(
                ClipSegment(
                    index=offset + position,
                    start_tick=start,
                    end_tick=end,
                    kill_ticks=(kill.tick,),
                    duration_seconds=match.ticks_to_seconds(end - start),
                    player=self._as_clip_player(victim),
                    label=ENEMY_LABEL,
                )
            )
        return tuple(collected)

    def _assign_passes(self, plan: RecordingPlan) -> None:
        pairs = [
            (clip_index, segment_index, segment)
            for clip_index, clip in enumerate(plan.clips)
            for segment_index, segment in enumerate(clip.segments)
        ]
        ordered = [item for item in pairs if item[2].label != ENEMY_LABEL]
        enemies = [item for item in pairs if item[2].label == ENEMY_LABEL]
        if not enemies:
            return
        ordered += enemies

        slots = [PassSlot(item[2].start_tick, item[2].end_tick) for item in ordered]
        reserved = sum(1 for item in ordered if item[2].label != ENEMY_LABEL)
        numbers = PassPlanner(self._settings.seek_lead_ticks).assign(slots, reserved)

        rebuilt = [list(clip.segments) for clip in plan.clips]
        for (clip_index, segment_index, segment), number in zip(ordered, numbers):
            rebuilt[clip_index][segment_index] = replace(segment, pass_index=number)

        plan.clips[:] = [
            replace(clip, segments=tuple(rebuilt[index]))
            for index, clip in enumerate(plan.clips)
        ]

    @staticmethod
    def _as_clip_player(player: Player) -> ClipPlayer:
        return ClipPlayer(
            name=player.name,
            steam_id64=player.steam_id64,
            account_id=player.account_id,
            slot=player.slot,
        )

    def _window(self, match: Match, highlight: Highlight, rounds_by_number) -> Window:
        start = highlight.first_tick - match.seconds_to_ticks(
            self._settings.lead_in_seconds
        )
        round_ = rounds_by_number.get(highlight.round_number)
        if round_ is not None and highlight.first_tick >= round_.freeze_end_tick:
            start = max(start, round_.freeze_end_tick)
        end = highlight.last_tick + match.seconds_to_ticks(
            self._settings.post_roll_seconds
        )
        return Window(start=max(0, start), end=end)

    @staticmethod
    def _leading(group: Sequence[Highlight]) -> Highlight:
        return max(group, key=lambda item: (item.score, item.kill_count))

    @staticmethod
    def _kills(group: Sequence[Highlight]) -> tuple[Kill, ...]:
        collected = [kill for highlight in group for kill in highlight.kills]
        return tuple(sorted(collected, key=lambda kill: kill.tick))

    @staticmethod
    def _round_for(group: Sequence[Highlight], rounds_by_number) -> Round | None:
        numbers = {item.round_number for item in group}
        if len(numbers) != 1:
            return None
        return rounds_by_number.get(next(iter(numbers)))

    @staticmethod
    def _tags(group: Sequence[Highlight]) -> tuple[str, ...]:
        collected: list[str] = []
        for highlight in group:
            for code in highlight.tag_codes:
                if code not in collected:
                    collected.append(code)
        return tuple(collected)

    @staticmethod
    def _note(group: Sequence[Highlight], lead: Highlight) -> str:
        if len(group) == 1:
            return ""
        others = ", ".join(
            item.player.name for item in group if item.player.steam_id64 != lead.player.steam_id64
        )
        return (
            f"{len(group)} moments share this stretch of the demo, "
            f"filmed once following {lead.player.name}"
            + (f" while {others} were also in it" if others else "")
        )

    def _clip_name(self, index: int, highlight: Highlight, count: int) -> str:
        parts = [
            f"{index:02d}",
            f"round{highlight.round_number:02d}",
            self._slug(highlight.player.name),
        ]
        parts.extend(self._slug(tag) for tag in highlight.tag_codes[:PRIMARY_TAG_COUNT])
        if count > 1:
            parts.append(f"plus{count - 1}")
        return "_".join(part for part in parts if part)

    @staticmethod
    def _slug(value: str) -> str:
        cleaned = UNSAFE_NAME_PATTERN.sub("_", value.lower()).strip("_")
        return cleaned[:MAXIMUM_NAME_TOKEN_LENGTH]


def _demo_end_tick(match: Match) -> int:
    return max((round_.end_tick for round_ in match.rounds), default=0)
