from __future__ import annotations

from pathlib import Path
from typing import Any

from ..domain.camera import LandingCameraDirector
from ..domain.grenade import Grenade
from ..domain.highlight import Highlight
from ..domain.kill import Kill
from ..domain.match import Match
from ..domain.player import Player
from ..domain.round import Round
from ..plan.models import RecordingPlan

HIGHLIGHT_ID_PREFIX = "h"
GRENADE_ID_PREFIX = "g"
IDENTIFIER_SEPARATOR = "-"
SPAWN_WINDOW_SECONDS = 4.0


class Identity:
    @staticmethod
    def for_highlight(highlight: Highlight) -> str:
        return IDENTIFIER_SEPARATOR.join(
            (
                HIGHLIGHT_ID_PREFIX,
                str(highlight.round_number),
                str(highlight.player.steam_id64),
            )
        )

    @staticmethod
    def for_grenade(grenade: Grenade) -> str:
        return IDENTIFIER_SEPARATOR.join(
            (
                GRENADE_ID_PREFIX,
                grenade.kind.value,
                str(grenade.throw_tick),
                str(grenade.thrower.steam_id64),
            )
        )


class PlayerView:
    @staticmethod
    def render(player: Player) -> dict[str, Any]:
        return {
            "name": player.name,
            "steamId64": str(player.steam_id64),
            "accountId": player.account_id,
            "slot": player.slot,
        }


class KillView:
    @staticmethod
    def render(match: Match, kill: Kill) -> dict[str, Any]:
        return {
            "tick": kill.tick,
            "roundNumber": kill.round_number,
            "timeSeconds": round(match.ticks_to_seconds(kill.tick), 2),
            "attacker": PlayerView.render(kill.attacker),
            "victim": PlayerView.render(kill.victim),
            "attackerSide": kill.attacker_side.label if kill.attacker_side else None,
            "victimSide": kill.victim_side.label if kill.victim_side else None,
            "weapon": kill.weapon.display_name,
            "weaponRaw": kill.weapon.raw,
            "headshot": kill.headshot,
            "wallbang": kill.wallbang,
            "noscope": kill.noscope,
            "throughSmoke": kill.through_smoke,
            "attackerBlind": kill.attacker_blind,
            "attackerAirborne": kill.attacker_airborne,
            "distance": round(kill.distance, 1),
        }


class RoundView:
    @classmethod
    def render(cls, match: Match, round_: Round, include_kills: bool) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "number": round_.number,
            "freezeEndTick": round_.freeze_end_tick,
            "endTick": round_.end_tick,
            "durationSeconds": round(
                match.ticks_to_seconds(max(0, round_.end_tick - round_.freeze_end_tick)), 2
            ),
            "winner": round_.winner.label if round_.winner else None,
            "endReason": round_.end_reason,
            "killCount": len(round_.kills),
            "roster": [
                {"steamId64": str(steam_id), "side": side.label}
                for steam_id, side in sorted(round_.roster.items())
            ],
        }
        if include_kills:
            payload["kills"] = [KillView.render(match, kill) for kill in round_.kills]
        return payload


class HighlightView:
    @staticmethod
    def render(match: Match, highlight: Highlight) -> dict[str, Any]:
        return {
            "id": Identity.for_highlight(highlight),
            "roundNumber": highlight.round_number,
            "player": PlayerView.render(highlight.player),
            "side": highlight.side.label if highlight.side else None,
            "score": highlight.score,
            "headline": highlight.headline,
            "killCount": highlight.kill_count,
            "headshotCount": highlight.headshot_count,
            "firstTick": highlight.first_tick,
            "lastTick": highlight.last_tick,
            "startSeconds": round(match.ticks_to_seconds(highlight.first_tick), 2),
            "endSeconds": round(match.ticks_to_seconds(highlight.last_tick), 2),
            "tags": [
                {"code": tag.code, "label": tag.label, "weight": tag.weight}
                for tag in highlight.tags
            ],
            "weapons": sorted({kill.weapon.display_name for kill in highlight.kills}),
            "kills": [KillView.render(match, kill) for kill in highlight.kills],
        }


class GrenadeView:
    @staticmethod
    def render(
        match: Match,
        grenade: Grenade,
        director: LandingCameraDirector | None = None,
    ) -> dict[str, Any]:
        document = {
            "id": Identity.for_grenade(grenade),
            "kind": grenade.kind.value,
            "roundNumber": grenade.round_number,
            "thrower": PlayerView.render(grenade.thrower),
            "side": grenade.side.label if grenade.side else None,
            "throwTick": grenade.throw_tick,
            "detonateTick": grenade.detonate_tick,
            "flightSeconds": round(match.ticks_to_seconds(grenade.flight_ticks), 2),
            "roundTimeSeconds": round(grenade.round_time_seconds, 2),
            "roundClock": grenade.round_clock,
            "fromSpawn": grenade.thrown_from_spawn(SPAWN_WINDOW_SECONDS),
            "landingPlace": grenade.landing_place,
            "landing": grenade.landing.to_mapping(),
            "throwerPosition": grenade.thrower_position.to_mapping(),
            "throwerAngles": grenade.thrower_angles.to_mapping(),
            "setpos": grenade.setpos_command,
            "setang": grenade.setang_command,
            "flightSamples": len(grenade.flight.points),
        }
        if director is not None:
            shot = director.direct(grenade)
            document["camera"] = {
                "mode": shot.mode,
                "reason": shot.reason,
                **shot.placement.to_mapping(),
            }
        return document


class MatchView:
    @classmethod
    def render(cls, match: Match, include_rounds: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "demo": FileView.render(match.demo_path),
            "map": match.map_name,
            "tickRate": match.tick_rate,
            "serverName": match.server_name,
            "roundCount": match.round_count,
            "durationSeconds": cls._duration(match),
            "players": [
                PlayerView.render(player)
                for player in sorted(match.players.values(), key=lambda item: item.name.lower())
            ],
        }
        if include_rounds:
            payload["rounds"] = [
                RoundView.render(match, round_, include_kills=False) for round_ in match.rounds
            ]
        return payload

    @staticmethod
    def _duration(match: Match) -> float:
        if not match.rounds:
            return 0.0
        return round(match.ticks_to_seconds(match.rounds[-1].end_tick), 2)


class FileView:
    @staticmethod
    def render(path: Path) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": path.stem,
            "fileName": path.name,
            "path": str(path),
            "sizeBytes": 0,
            "modifiedAt": 0.0,
        }
        try:
            stats = path.stat()
        except OSError:
            return payload
        payload["sizeBytes"] = stats.st_size
        payload["modifiedAt"] = round(stats.st_mtime, 3)
        return payload


class PlanView:
    @staticmethod
    def render(plan: RecordingPlan) -> dict[str, Any]:
        payload = plan.to_mapping()
        payload["summary"] = {
            "clipCount": plan.clip_count,
            "mergedSources": plan.merged_sources,
            "segmentCount": sum(len(clip.segments) for clip in plan.clips),
            "totalSeconds": round(plan.total_seconds, 2),
        }
        return payload
