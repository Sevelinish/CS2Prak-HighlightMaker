from __future__ import annotations

import re
from dataclasses import dataclass

__version__ = "1.2.0"

VERSION_PATTERN = re.compile(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?")
TAG_PREFIXES = ("v", "V", "release-", "highlightercs2-")


@dataclass(frozen=True, order=True, slots=True)
class Version:
    major: int = 0
    minor: int = 0
    patch: int = 0

    @classmethod
    def parse(cls, text: str) -> "Version | None":
        cleaned = (text or "").strip()
        for prefix in TAG_PREFIXES:
            if cleaned.lower().startswith(prefix.lower()):
                cleaned = cleaned[len(prefix) :]
                break

        match = VERSION_PATTERN.match(cleaned.strip())
        if match is None:
            return None
        return cls(
            major=int(match.group(1)),
            minor=int(match.group(2) or 0),
            patch=int(match.group(3) or 0),
        )

    @classmethod
    def current(cls) -> "Version":
        return cls.parse(__version__) or cls()

    def is_newer_than(self, other: "Version") -> bool:
        return self > other

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"
