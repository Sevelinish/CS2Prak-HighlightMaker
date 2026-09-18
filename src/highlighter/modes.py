from __future__ import annotations

from dataclasses import dataclass

from .domain.grenade import GrenadeKind
from .infrastructure.errors import HighlighterError

HIGHLIGHTS_TOKEN = "highlights"
NADES_PREFIX = "nades"
SEPARATOR = "_"


class UnknownModeError(HighlighterError):
    pass


@dataclass(frozen=True, slots=True)
class RunMode:
    token: str
    grenade_kinds: tuple[GrenadeKind, ...] = ()

    @property
    def records_grenades(self) -> bool:
        return bool(self.grenade_kinds)

    @property
    def label(self) -> str:
        if not self.records_grenades:
            return "highlights"
        return ", ".join(kind.label for kind in self.grenade_kinds)

    @classmethod
    def highlights(cls) -> "RunMode":
        return cls(token=HIGHLIGHTS_TOKEN)

    @classmethod
    def parse(cls, token: str | None) -> "RunMode":
        if token is None:
            return cls.highlights()

        normalized = token.strip().lower()
        if not normalized or normalized == HIGHLIGHTS_TOKEN:
            return cls.highlights()

        if normalized == NADES_PREFIX:
            return cls(token=normalized, grenade_kinds=tuple(GrenadeKind))

        if normalized.startswith(f"{NADES_PREFIX}{SEPARATOR}"):
            suffix = normalized[len(NADES_PREFIX) + len(SEPARATOR) :]
            kind = GrenadeKind.from_token(suffix)
            if kind is not None:
                return cls(token=normalized, grenade_kinds=(kind,))

        raise UnknownModeError(
            f"Unknown mode '{token}'. Available: {cls.available()}"
        )

    @staticmethod
    def tokens() -> tuple[str, ...]:
        grenades = tuple(
            f"{NADES_PREFIX}{SEPARATOR}{kind}" for kind in GrenadeKind.tokens()
        )
        return (HIGHLIGHTS_TOKEN, NADES_PREFIX, *grenades)

    @classmethod
    def available(cls) -> str:
        return ", ".join(cls.tokens())
