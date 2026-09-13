from __future__ import annotations

import re
from pathlib import Path

from ..config.schema import RecordingConfig
from ..domain.highlight import Highlight
from ..domain.match import Match
from .models import ClipPlayer, ClipSpec, RecordingPlan
from .segmenter import ClipSegmenter

UNSAFE_NAME_PATTERN = re.compile(r"[^a-z0-9]+")
MAXIMUM_NAME_TOKEN_LENGTH = 18
PRIMARY_TAG_COUNT = 2


class RecordingPlanBuilder:
    def __init__(self, settings: RecordingConfig) -> None:
        self._settings = settings

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
        )

        segmenter = ClipSegmenter(self._settings, match)
        rounds_by_number = {round_.number: round_ for round_ in match.rounds}
        ordered = sorted(highlights, key=lambda item: item.first_tick)

        for index, highlight in enumerate(ordered, start=1):
            round_ = rounds_by_number.get(highlight.round_number)
            segments = segmenter.segment(highlight.kills, round_)
            if not segments:
                continue

            plan.clips.append(
                ClipSpec(
                    index=index,
                    name=self._clip_name(index, highlight),
                    round_number=highlight.round_number,
                    player=ClipPlayer(
                        name=highlight.player.name,
                        steam_id64=highlight.player.steam_id64,
                        account_id=highlight.player.account_id,
                        slot=highlight.player.slot,
                    ),
                    tags=highlight.tag_codes,
                    score=highlight.score,
                    segments=segments,
                    action_start_tick=highlight.first_tick,
                    action_end_tick=highlight.last_tick,
                )
            )

        return plan

    def _clip_name(self, index: int, highlight: Highlight) -> str:
        parts = [
            f"{index:02d}",
            f"round{highlight.round_number:02d}",
            self._slug(highlight.player.name),
        ]
        parts.extend(self._slug(tag) for tag in highlight.tag_codes[:PRIMARY_TAG_COUNT])
        return "_".join(part for part in parts if part)

    @staticmethod
    def _slug(value: str) -> str:
        cleaned = UNSAFE_NAME_PATTERN.sub("_", value.lower()).strip("_")
        return cleaned[:MAXIMUM_NAME_TOKEN_LENGTH]
