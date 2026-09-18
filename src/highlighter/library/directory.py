from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .profile import DemoProfile, PlayerCard

DASH = "-"
NOTE_NAME_LIMIT = 22
TRIM_MARK = ".."


@dataclass(frozen=True, slots=True)
class PlayerHint:
    name: str
    note: str = ""
    steam_id64: int = 0

    @property
    def bare_name(self) -> str:
        return self.name.lstrip(DASH)

    def starts_with(self, prefix: str) -> bool:
        if not prefix:
            return True
        wanted = prefix.lower()
        return self.name.lower().startswith(wanted) or self.bare_name.lower().startswith(
            wanted
        )


class PlayerDirectory:
    def __init__(self, profiles: Sequence[DemoProfile]) -> None:
        self._profiles = tuple(profiles)

    def hints(self, demo_name: str = "") -> tuple[PlayerHint, ...]:
        profile = self._named(demo_name)
        if profile is not None:
            return self._from_profile(profile)
        return self._from_everything()

    def matching(self, prefix: str, demo_name: str = "") -> tuple[PlayerHint, ...]:
        return tuple(hint for hint in self.hints(demo_name) if hint.starts_with(prefix))

    def _named(self, demo_name: str) -> DemoProfile | None:
        for profile in self._profiles:
            if profile.matches(demo_name):
                return profile
        return None

    @staticmethod
    def _from_profile(profile: DemoProfile) -> tuple[PlayerHint, ...]:
        return tuple(
            sorted(
                (
                    PlayerHint(
                        name=card.name,
                        note=_side_note(card),
                        steam_id64=card.steam_id64,
                    )
                    for card in profile.players
                ),
                key=_by_name,
            )
        )

    def _from_everything(self) -> tuple[PlayerHint, ...]:
        seen: dict[str, tuple[PlayerCard, str, int]] = {}
        for profile in self._profiles:
            for card in profile.players:
                key = card.name.lower()
                if key in seen:
                    first, demo_name, count = seen[key]
                    seen[key] = (first, demo_name, count + 1)
                    continue
                seen[key] = (card, profile.name, 1)

        return tuple(
            PlayerHint(
                name=card.name,
                note=_seen_note(demo_name, count),
                steam_id64=card.steam_id64,
            )
            for card, demo_name, count in seen.values()
        )


def _side_note(card: PlayerCard) -> str:
    if not card.side_label:
        return ""
    return f"started {card.side_label}"


def _seen_note(demo_name: str, count: int) -> str:
    shortened = _short(demo_name)
    if count > 1:
        return f"in {shortened} and {count - 1} more"
    return f"in {shortened}"


def _short(demo_name: str) -> str:
    stem = Path(demo_name).stem
    if len(stem) <= NOTE_NAME_LIMIT:
        return stem
    return stem[: NOTE_NAME_LIMIT - len(TRIM_MARK)] + TRIM_MARK


def _by_name(hint: PlayerHint) -> str:
    return hint.bare_name.lower()
