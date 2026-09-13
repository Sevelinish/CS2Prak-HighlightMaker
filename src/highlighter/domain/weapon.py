from __future__ import annotations

SNIPER_RIFLES = frozenset({"awp", "ssg08", "scar20", "g3sg1"})
PISTOLS = frozenset(
    {
        "glock",
        "hkp2000",
        "usp_silencer",
        "p250",
        "fiveseven",
        "tec9",
        "cz75a",
        "deagle",
        "revolver",
        "elite",
    }
)
GRENADES = frozenset({"hegrenade", "molotov", "inferno", "incgrenade", "decoy", "flashbang"})
TASER = "taser"


class Weapon:
    def __init__(self, raw_name: str) -> None:
        self._raw = (raw_name or "").strip().lower()

    @property
    def raw(self) -> str:
        return self._raw

    @property
    def is_knife(self) -> bool:
        return "knife" in self._raw or self._raw == "bayonet"

    @property
    def is_taser(self) -> bool:
        return self._raw == TASER

    @property
    def is_grenade(self) -> bool:
        return self._raw in GRENADES

    @property
    def is_sniper(self) -> bool:
        return self._raw in SNIPER_RIFLES

    @property
    def is_awp(self) -> bool:
        return self._raw == "awp"

    @property
    def is_deagle(self) -> bool:
        return self._raw in {"deagle", "revolver"}

    @property
    def is_pistol(self) -> bool:
        return self._raw in PISTOLS

    @property
    def display_name(self) -> str:
        if self.is_knife:
            return "knife"
        return self._raw or "unknown"

    def __str__(self) -> str:
        return self.display_name

    def __repr__(self) -> str:
        return f"Weapon({self._raw!r})"
