from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping, Sequence

from ..domain.grenade import Grenade, GrenadeKind
from ..domain.highlight import Highlight
from .errors import BadRequestError
from .serialization import Identity

ORDER_SCORE_DESC = "score_desc"
ORDER_ROUND_ASC = "round_asc"
ORDER_TIME_ASC = "time_asc"
ORDERS = (ORDER_SCORE_DESC, ORDER_ROUND_ASC, ORDER_TIME_ASC)
NO_LIMIT = 0


@dataclass(frozen=True, slots=True)
class RoundRange:
    first: int
    last: int

    def contains(self, number: int) -> bool:
        return self.first <= number <= self.last

    @classmethod
    def from_mapping(cls, source: Any) -> "RoundRange | None":
        if source is None:
            return None
        if not isinstance(source, Mapping):
            raise BadRequestError("'roundRange' must be an object with 'from' and 'to'")
        first = _integer(source.get("from"), "roundRange.from")
        last = _integer(source.get("to"), "roundRange.to")
        if last < first:
            raise BadRequestError("'roundRange.to' must not be smaller than 'roundRange.from'")
        return cls(first=first, last=last)

    def to_mapping(self) -> dict[str, int]:
        return {"from": self.first, "to": self.last}


@dataclass(frozen=True, slots=True)
class SelectionCriteria:
    identifiers: tuple[str, ...] = ()
    rounds: tuple[int, ...] = ()
    round_range: RoundRange | None = None
    players: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    weapons: tuple[str, ...] = ()
    grenade_kinds: tuple[GrenadeKind, ...] = ()
    landing_places: tuple[str, ...] = ()
    minimum_score: float | None = None
    minimum_kills: int | None = None
    order: str = ORDER_ROUND_ASC
    limit: int = NO_LIMIT

    @classmethod
    def from_mapping(cls, source: Any) -> "SelectionCriteria":
        if source is None:
            return cls()
        if not isinstance(source, Mapping):
            raise BadRequestError("'selection' must be a JSON object")

        order = str(source.get("order") or ORDER_ROUND_ASC).strip().lower()
        if order not in ORDERS:
            raise BadRequestError(
                f"Unknown order {order}. Available: {', '.join(ORDERS)}"
            )

        return cls(
            identifiers=_strings(source.get("ids"), "ids"),
            rounds=_integers(source.get("rounds"), "rounds"),
            round_range=RoundRange.from_mapping(source.get("roundRange")),
            players=_strings(source.get("players"), "players"),
            tags=_lowered(source.get("tags"), "tags"),
            weapons=_lowered(source.get("weapons"), "weapons"),
            grenade_kinds=_kinds(source.get("grenadeKinds")),
            landing_places=_lowered(source.get("landingPlaces"), "landingPlaces"),
            minimum_score=_optional_number(source.get("minimumScore"), "minimumScore"),
            minimum_kills=_optional_integer(source.get("minimumKills"), "minimumKills"),
            order=order,
            limit=max(NO_LIMIT, _optional_integer(source.get("limit"), "limit") or NO_LIMIT),
        )

    @property
    def is_empty(self) -> bool:
        return not any(
            (
                self.identifiers,
                self.rounds,
                self.round_range,
                self.players,
                self.tags,
                self.weapons,
                self.grenade_kinds,
                self.landing_places,
                self.minimum_score is not None,
                self.minimum_kills is not None,
                self.limit,
            )
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "ids": list(self.identifiers),
            "rounds": list(self.rounds),
            "roundRange": self.round_range.to_mapping() if self.round_range else None,
            "players": list(self.players),
            "tags": list(self.tags),
            "weapons": list(self.weapons),
            "grenadeKinds": [kind.value for kind in self.grenade_kinds],
            "landingPlaces": list(self.landing_places),
            "minimumScore": self.minimum_score,
            "minimumKills": self.minimum_kills,
            "order": self.order,
            "limit": self.limit,
        }


class PlayerMatcher:
    def __init__(self, queries: Sequence[str]) -> None:
        self._queries = [query.strip().lower() for query in queries if query.strip()]

    @property
    def is_open(self) -> bool:
        return not self._queries

    def matches(self, steam_id64: int, name: str) -> bool:
        if self.is_open:
            return True
        identifier = str(steam_id64)
        lowered = name.strip().lower()
        for query in self._queries:
            if query == identifier or query == lowered or query in lowered:
                return True
        return False


class HighlightSelection:
    def __init__(self, criteria: SelectionCriteria) -> None:
        self._criteria = criteria
        self._players = PlayerMatcher(criteria.players)

    def apply(self, highlights: Iterable[Highlight]) -> list[Highlight]:
        kept = [item for item in highlights if self._keeps(item)]
        ordered = _ordered(kept, self._criteria.order, self._sort_keys)
        return _limited(ordered, self._criteria.limit)

    def _keeps(self, highlight: Highlight) -> bool:
        criteria = self._criteria
        if criteria.identifiers and Identity.for_highlight(highlight) not in criteria.identifiers:
            return False
        if not _round_allowed(criteria, highlight.round_number):
            return False
        if not self._players.matches(highlight.player.steam_id64, highlight.player.name):
            return False
        if criteria.tags and not set(criteria.tags) & {
            code.lower() for code in highlight.tag_codes
        }:
            return False
        if criteria.weapons and not set(criteria.weapons) & {
            kill.weapon.display_name for kill in highlight.kills
        }:
            return False
        if criteria.minimum_score is not None and highlight.score < criteria.minimum_score:
            return False
        if criteria.minimum_kills is not None and highlight.kill_count < criteria.minimum_kills:
            return False
        return True

    @staticmethod
    def _sort_keys(order: str) -> Callable[[Highlight], Any]:
        if order == ORDER_SCORE_DESC:
            return lambda item: (-item.score, item.round_number)
        if order == ORDER_TIME_ASC:
            return lambda item: item.first_tick
        return lambda item: (item.round_number, -item.score)


class GrenadeSelection:
    def __init__(self, criteria: SelectionCriteria) -> None:
        self._criteria = criteria
        self._players = PlayerMatcher(criteria.players)

    def apply(self, grenades: Iterable[Grenade]) -> list[Grenade]:
        kept = [item for item in grenades if self._keeps(item)]
        ordered = _ordered(kept, self._criteria.order, self._sort_keys)
        return _limited(ordered, self._criteria.limit)

    def _keeps(self, grenade: Grenade) -> bool:
        criteria = self._criteria
        if criteria.identifiers and Identity.for_grenade(grenade) not in criteria.identifiers:
            return False
        if not _round_allowed(criteria, grenade.round_number):
            return False
        if not self._players.matches(grenade.thrower.steam_id64, grenade.thrower.name):
            return False
        if criteria.grenade_kinds and grenade.kind not in criteria.grenade_kinds:
            return False
        if criteria.landing_places and not _place_allowed(
            criteria.landing_places, grenade.landing_place
        ):
            return False
        return True

    @staticmethod
    def _sort_keys(order: str) -> Callable[[Grenade], Any]:
        if order == ORDER_SCORE_DESC:
            return lambda item: (item.round_number, item.throw_tick)
        return lambda item: item.throw_tick


def _place_allowed(wanted: Sequence[str], place: str) -> bool:
    lowered = place.strip().lower()
    return any(candidate in lowered or lowered in candidate for candidate in wanted)


def _round_allowed(criteria: SelectionCriteria, number: int) -> bool:
    if criteria.rounds and number not in criteria.rounds:
        return False
    if criteria.round_range is not None and not criteria.round_range.contains(number):
        return False
    return True


def _ordered(items: list, order: str, keys: Callable[[str], Callable[[Any], Any]]) -> list:
    return sorted(items, key=keys(order))


def _limited(items: list, limit: int) -> list:
    return items[:limit] if limit else items


def _strings(source: Any, field_name: str) -> tuple[str, ...]:
    if source is None:
        return ()
    if isinstance(source, str):
        return (source,)
    if not isinstance(source, Sequence):
        raise BadRequestError(f"{field_name} must be a string or an array of strings")
    return tuple(str(item) for item in source if str(item).strip())


def _lowered(source: Any, field_name: str) -> tuple[str, ...]:
    return tuple(item.strip().lower() for item in _strings(source, field_name))


def _integers(source: Any, field_name: str) -> tuple[int, ...]:
    if source is None:
        return ()
    if isinstance(source, (int, float)) and not isinstance(source, bool):
        return (int(source),)
    if not isinstance(source, Sequence) or isinstance(source, str):
        raise BadRequestError(f"{field_name} must be a number or an array of numbers")
    return tuple(_integer(item, field_name) for item in source)


def _integer(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise BadRequestError(f"{field_name} must be a whole number")
    try:
        return int(str(value).strip())
    except ValueError as error:
        raise BadRequestError(f"{field_name} must be a whole number") from error


def _optional_integer(value: Any, field_name: str) -> int | None:
    return None if value is None else _integer(value, field_name)


def _optional_number(value: Any, field_name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise BadRequestError(f"{field_name} must be a number")
    try:
        return float(str(value).strip())
    except ValueError as error:
        raise BadRequestError(f"{field_name} must be a number") from error


def _kinds(source: Any) -> tuple[GrenadeKind, ...]:
    collected: list[GrenadeKind] = []
    for token in _strings(source, "grenadeKinds"):
        kind = GrenadeKind.from_token(token)
        if kind is None:
            available = ", ".join(GrenadeKind.tokens())
            raise BadRequestError(f"Unknown grenade kind {token}. Available: {available}")
        if kind not in collected:
            collected.append(kind)
    return tuple(collected)
