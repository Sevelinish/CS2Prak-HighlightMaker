from __future__ import annotations

import math

import pytest

from highlighter.domain.camera import (
    FLIGHT_MODE,
    THROWER_MODE,
    LandingCameraDirector,
)
from highlighter.domain.flight import FlightPoint, GrenadeFlight
from highlighter.domain.geometry import Vector3, ViewAngles
from highlighter.domain.grenade import Grenade, GrenadeKind
from highlighter.domain.player import Player

DISTANCE = 220.0
HEIGHT = 90.0
MINIMUM_APPROACH = 60.0


def flight(*positions: tuple[float, float, float]) -> GrenadeFlight:
    return GrenadeFlight.of(
        [FlightPoint(index, Vector3(*point)) for index, point in enumerate(positions)]
    )


def make_grenade(
    path: GrenadeFlight | None = None,
    landing: tuple[float, float, float] = (500.0, 0.0, 0.0),
    thrower: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> Grenade:
    return Grenade(
        kind=GrenadeKind.SMOKE,
        round_number=1,
        thrower=Player(76561197960265729, "kul"),
        side=None,
        throw_tick=0,
        detonate_tick=100,
        thrower_position=Vector3(*thrower),
        thrower_angles=ViewAngles(0.0, 0.0),
        landing=Vector3(*landing),
        flight=path or GrenadeFlight(),
    )


def direct(grenade: Grenade, mode: str = FLIGHT_MODE):
    return LandingCameraDirector(DISTANCE, HEIGHT, MINIMUM_APPROACH, mode).direct(grenade)


def descending_arc() -> GrenadeFlight:
    return flight(
        (0.0, 0.0, 0.0),
        (150.0, 0.0, 160.0),
        (300.0, 0.0, 200.0),
        (400.0, 0.0, 140.0),
        (470.0, 0.0, 50.0),
        (500.0, 0.0, 0.0),
        (500.0, 0.0, 0.0),
    )


def test_a_grenade_without_a_flight_uses_the_thrower_line():
    shot = direct(make_grenade())

    assert shot.mode is THROWER_MODE or shot.mode == THROWER_MODE
    assert shot.follows_the_flight is False


def test_a_lobbed_grenade_is_filmed_from_where_it_came_in():
    shot = direct(make_grenade(descending_arc()))

    assert shot.mode == FLIGHT_MODE
    assert shot.placement.position.x < 500.0
    assert shot.placement.position.z > 0.0


def test_the_camera_keeps_the_configured_distance():
    shot = direct(make_grenade(descending_arc()))

    assert shot.placement.position.distance_to(Vector3(500.0, 0.0, 0.0)) == pytest.approx(
        DISTANCE
    )


def test_the_camera_looks_at_the_landing():
    grenade = make_grenade(descending_arc())
    shot = direct(grenade)
    expected = shot.placement.position.angles_towards(grenade.landing)

    assert shot.placement.angles.pitch == pytest.approx(expected.pitch)
    assert shot.placement.angles.yaw == pytest.approx(expected.yaw)


def test_the_flight_camera_sits_above_the_arc_not_on_the_thrower_line():
    grenade = make_grenade(descending_arc())
    along_the_flight = direct(grenade).placement.position
    along_the_thrower_line = direct(grenade, THROWER_MODE).placement.position

    assert along_the_flight.z > along_the_thrower_line.z - HEIGHT
    assert along_the_flight.distance_to(along_the_thrower_line) > 1.0


def test_thrower_mode_is_still_available():
    shot = direct(make_grenade(descending_arc()), THROWER_MODE)

    assert shot.mode == THROWER_MODE


def test_an_unknown_mode_falls_back_to_following_the_flight():
    director = LandingCameraDirector(DISTANCE, HEIGHT, MINIMUM_APPROACH, "sideways")

    assert director.mode == FLIGHT_MODE


def test_a_grenade_that_only_settled_falls_back_to_the_thrower_line():
    barely_moved = flight((498.0, 0.0, 0.0), (499.0, 0.0, 0.0), (500.0, 0.0, 0.0))

    assert direct(make_grenade(barely_moved)).mode == THROWER_MODE


def test_a_bouncy_tail_stops_the_walk_early():
    zig_zag = flight(
        (300.0, 0.0, 0.0),
        (350.0, 80.0, 0.0),
        (400.0, 0.0, 0.0),
        (450.0, 80.0, 0.0),
        (500.0, 0.0, 0.0),
        (500.0, 0.0, 0.0),
    )
    approach = zig_zag.approach(DISTANCE)

    assert approach is not None
    assert approach.point == Vector3(450.0, 80.0, 0.0)
    assert approach.distance < DISTANCE


def test_the_camera_still_keeps_its_distance_after_a_short_approach():
    zig_zag = flight(
        (300.0, 0.0, 0.0),
        (350.0, 80.0, 0.0),
        (400.0, 0.0, 0.0),
        (450.0, 80.0, 0.0),
        (500.0, 0.0, 0.0),
        (500.0, 0.0, 0.0),
    )
    shot = direct(make_grenade(zig_zag))

    assert shot.mode == FLIGHT_MODE
    assert shot.placement.position.distance_to(Vector3(500.0, 0.0, 0.0)) == pytest.approx(
        DISTANCE
    )


def test_a_rolling_grenade_is_filmed_from_where_it_rolled_in():
    rolled = flight(
        (200.0, 0.0, 0.0),
        (300.0, 0.0, 0.0),
        (400.0, 0.0, 0.0),
        (500.0, 0.0, 0.0),
        (500.0, 0.0, 0.0),
    )
    shot = direct(make_grenade(rolled))

    assert shot.mode == FLIGHT_MODE
    assert shot.placement.position.x == pytest.approx(280.0)
    assert shot.placement.position.z == pytest.approx(0.0)


def test_a_grenade_dropped_straight_down_is_not_filmed_from_overhead():
    dropped = flight(
        (500.0, 0.0, 400.0),
        (500.0, 0.0, 260.0),
        (500.0, 0.0, 120.0),
        (500.0, 0.0, 0.0),
        (500.0, 0.0, 0.0),
    )
    shot = direct(make_grenade(dropped, thrower=(200.0, 0.0, 0.0)))
    offset = shot.placement.position - Vector3(500.0, 0.0, 0.0)
    elevation = math.degrees(math.atan2(offset.z, math.hypot(offset.x, offset.y) or 1e-9))

    assert shot.mode == THROWER_MODE
    assert elevation <= 56.0


def test_a_steep_but_not_vertical_approach_is_levelled_off():
    steep = flight(
        (520.0, 0.0, 400.0),
        (510.0, 0.0, 200.0),
        (505.0, 0.0, 60.0),
        (500.0, 0.0, 0.0),
        (500.0, 0.0, 0.0),
    )
    shot = direct(make_grenade(steep))
    offset = shot.placement.position - Vector3(500.0, 0.0, 0.0)
    elevation = math.degrees(math.atan2(offset.z, math.hypot(offset.x, offset.y) or 1e-9))

    assert shot.mode == FLIGHT_MODE
    assert elevation == pytest.approx(55.0, abs=0.5)


def test_the_resting_tail_is_not_mistaken_for_the_flight():
    settled = flight(
        (200.0, 0.0, 0.0),
        (350.0, 0.0, 0.0),
        (500.0, 0.0, 0.0),
        (500.0, 0.0, 0.0),
        (500.0, 0.0, 0.0),
        (500.0, 0.0, 0.0),
    )

    assert len(settled.moving()) == 3


def test_a_flight_keeps_only_the_last_samples():
    long_path = flight(*[(float(index), 0.0, 0.0) for index in range(900)])

    assert len(long_path.points) == 320


def test_the_approach_is_capped_at_the_asked_for_distance():
    approach = descending_arc().approach(120.0)

    assert approach is not None
    assert approach.distance >= 120.0
    assert approach.direction.length == pytest.approx(1.0)
