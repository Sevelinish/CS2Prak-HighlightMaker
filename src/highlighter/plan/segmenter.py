from __future__ import annotations

from dataclasses import dataclass, field

from ..config.schema import RecordingConfig
from ..domain.kill import Kill
from ..domain.match import Match
from ..domain.round import Round
from .models import ClipSegment


@dataclass(slots=True)
class SegmentDraft:
    start_tick: int
    kill_ticks: list[int] = field(default_factory=list)

    @property
    def last_kill_tick(self) -> int:
        return self.kill_ticks[-1]


class ClipSegmenter:
    def __init__(self, settings: RecordingConfig, match: Match) -> None:
        self._settings = settings
        self._match = match

    def segment(self, kills: tuple[Kill, ...], round_: Round | None) -> tuple[ClipSegment, ...]:
        kill_ticks = sorted(kill.tick for kill in kills)
        if not kill_ticks:
            return ()

        drafts = self._split(kill_ticks)
        return tuple(
            self._materialise(index, draft, round_, is_final=draft is drafts[-1])
            for index, draft in enumerate(drafts, start=1)
        )

    def _split(self, kill_ticks: list[int]) -> list[SegmentDraft]:
        lead_in = self._ticks(self._settings.lead_in_seconds)
        resume_lead = self._ticks(self._settings.resume_lead_seconds)
        cut_threshold = (
            self._ticks(self._settings.gap_hold_seconds + self._settings.resume_lead_seconds)
            + self._settings.seek_lead_ticks
        )

        drafts = [SegmentDraft(kill_ticks[0] - lead_in, [kill_ticks[0]])]
        for tick in kill_ticks[1:]:
            if tick - drafts[-1].last_kill_tick <= cut_threshold:
                drafts[-1].kill_ticks.append(tick)
            else:
                drafts.append(SegmentDraft(tick - resume_lead, [tick]))
        return drafts

    def _materialise(
        self,
        index: int,
        draft: SegmentDraft,
        round_: Round | None,
        is_final: bool,
    ) -> ClipSegment:
        tail_seconds = (
            self._settings.post_roll_seconds if is_final else self._settings.gap_hold_seconds
        )

        start_tick = max(0, draft.start_tick)
        end_tick = draft.last_kill_tick + self._ticks(tail_seconds)
        if round_ is not None:
            if draft.kill_ticks[0] >= round_.freeze_end_tick:
                start_tick = max(start_tick, round_.freeze_end_tick)
            if draft.last_kill_tick <= round_.end_tick:
                end_tick = min(end_tick, round_.end_tick)

        end_tick = max(end_tick, start_tick + self._match.tick_rate)
        maximum_span = self._ticks(self._settings.max_clip_seconds)
        if end_tick - start_tick > maximum_span:
            end_tick = start_tick + maximum_span

        return ClipSegment(
            index=index,
            start_tick=start_tick,
            end_tick=end_tick,
            kill_ticks=tuple(draft.kill_ticks),
            duration_seconds=self._match.ticks_to_seconds(end_tick - start_tick),
        )

    def _ticks(self, seconds: float) -> int:
        return self._match.seconds_to_ticks(seconds)
