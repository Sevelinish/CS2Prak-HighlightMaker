from __future__ import annotations

import pandas as pd
from demoparser2 import DemoParser

from ..infrastructure.logging import get_logger


class MatchStartResolver:
    PRIMARY_ANCHORS = ("begin_new_match", "round_announce_warmup")
    FALLBACK_ANCHOR = "round_announce_match_start"

    def __init__(self, parser: DemoParser) -> None:
        self._parser = parser
        self._logger = get_logger("demo.timeline")

    def resolve(self) -> int:
        for event_name in self.PRIMARY_ANCHORS:
            tick = self._last_tick(event_name)
            if tick is not None:
                self._logger.debug("Match start anchored on %s at tick %d", event_name, tick)
                return tick

        tick = self._first_tick(self.FALLBACK_ANCHOR)
        if tick is not None:
            self._logger.debug("Match start anchored on %s at tick %d", self.FALLBACK_ANCHOR, tick)
            return tick

        self._logger.debug("No match start anchor found, keeping every tick")
        return 0

    def _last_tick(self, event_name: str) -> int | None:
        ticks = self._ticks_of(event_name)
        return max(ticks) if ticks else None

    def _first_tick(self, event_name: str) -> int | None:
        ticks = self._ticks_of(event_name)
        return min(ticks) if ticks else None

    def _ticks_of(self, event_name: str) -> list[int]:
        try:
            frame = self._parser.parse_event(event_name)
        except (KeyboardInterrupt, SystemExit):
            raise
        except BaseException:
            return []
        if frame is None or frame.empty or "tick" not in frame.columns:
            return []
        return [int(tick) for tick in frame["tick"].tolist() if not pd.isna(tick)]
