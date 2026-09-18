from __future__ import annotations

import json
import time
from pathlib import Path

from conftest import make_player, make_round, make_roster

from highlighter.domain.team import TeamSide
from highlighter.library.directory import PlayerDirectory, PlayerHint
from highlighter.library.index import DemoIndex
from highlighter.library.inspector import DemoProfiler
from highlighter.library.librarian import DemoLibrarian
from highlighter.library.library import DemoLibrary
from highlighter.library.profile import DemoProfile, PlayerCard

MIRAGE = "de_mirage"
INDEXED_AT = 200.0


def make_demo(root: Path, name: str, size: int = 32) -> Path:
    path = root / name
    path.write_bytes(b"P" * size)
    return path


def make_profile(
    name: str = "mirage17.dem",
    map_name: str = MIRAGE,
    players: tuple[PlayerCard, ...] = (),
    size_bytes: int = 32,
    modified_at: float = 100.0,
) -> DemoProfile:
    return DemoProfile(
        name=name,
        path=f"D:/demos/{name}",
        size_bytes=size_bytes,
        modified_at=modified_at,
        map_name=map_name,
        players=players,
        indexed_at=INDEXED_AT,
    )


def cards(*names: str) -> tuple[PlayerCard, ...]:
    return tuple(
        PlayerCard(name=name, steam_id64=76561197960265728 + index, side=TeamSide.TERRORIST)
        for index, name in enumerate(names, start=1)
    )


class CountingProfiler:
    def __init__(self, players: int = 2, pause: float = 0.0) -> None:
        self.seen: list[str] = []
        self._players = players
        self._pause = pause

    def profile(self, demo: Path) -> DemoProfile:
        self.seen.append(demo.name)
        if self._pause:
            time.sleep(self._pause)
        return DemoProfile(
            name=demo.name,
            path=str(demo),
            size_bytes=demo.stat().st_size,
            modified_at=demo.stat().st_mtime,
            map_name=MIRAGE,
            players=cards(*[f"player{index}" for index in range(self._players)]),
            indexed_at=time.time(),
        )


def test_a_profile_is_keyed_by_name_and_size():
    assert make_profile(size_bytes=512).key == "mirage17.dem:512"


def test_the_key_of_a_file_on_disk_matches_its_profile(tmp_path: Path):
    demo = make_demo(tmp_path, "mirage17.dem", size=512)

    assert DemoProfile.key_for(demo) == make_profile(size_bytes=512).key


def test_a_missing_file_has_no_key(tmp_path: Path):
    assert DemoProfile.key_for(tmp_path / "gone.dem") == ""


def test_a_profile_survives_the_round_trip():
    profile = make_profile(players=cards("s1mple", "-n1clxe"))

    restored = DemoProfile.from_mapping(profile.to_mapping())

    assert restored == profile


def test_a_player_keeps_its_side_through_the_round_trip():
    card = PlayerCard(name="s1mple", steam_id64=76561198000000000, side=TeamSide.COUNTER_TERRORIST)

    assert PlayerCard.from_mapping(card.to_mapping()) == card


def test_a_nameless_player_is_dropped():
    assert PlayerCard.from_mapping({"name": "  "}) is None


def test_a_profile_is_found_by_file_name_or_by_stem():
    profile = make_profile()

    assert profile.matches("mirage17.dem") is True
    assert profile.matches("MIRAGE17") is True
    assert profile.matches("") is False


def test_the_index_hands_back_what_it_was_given(tmp_path: Path):
    index = DemoIndex(tmp_path)
    index.remember(make_profile(players=cards("s1mple")))

    assert index.count == 1
    assert index.named("mirage17").map_name == MIRAGE


def test_the_index_is_read_back_from_disk(tmp_path: Path):
    DemoIndex(tmp_path).remember(make_profile(players=cards("s1mple", "b1t")))

    reopened = DemoIndex(tmp_path)

    assert reopened.count == 1
    assert reopened.profiles()[0].player_names == ("s1mple", "b1t")


def test_an_index_from_another_version_is_ignored(tmp_path: Path):
    (tmp_path / "demo_index.json").write_text(
        json.dumps({"version": 99, "demos": [make_profile().to_mapping()]}), encoding="utf-8"
    )

    assert DemoIndex(tmp_path).count == 0


def test_a_broken_index_starts_over(tmp_path: Path):
    (tmp_path / "demo_index.json").write_text("{not json", encoding="utf-8")

    assert DemoIndex(tmp_path).count == 0


def test_the_index_knows_a_demo_by_its_file(tmp_path: Path):
    demo = make_demo(tmp_path, "mirage17.dem", size=32)
    index = DemoIndex(tmp_path)
    index.remember(make_profile(size_bytes=32))

    assert index.knows(demo) is True
    assert index.profile_for(demo).map_name == MIRAGE


def test_a_demo_that_changed_size_counts_as_new(tmp_path: Path):
    demo = make_demo(tmp_path, "mirage17.dem", size=64)
    index = DemoIndex(tmp_path)
    index.remember(make_profile(size_bytes=32))

    assert index.knows(demo) is False


def test_demos_that_vanished_are_dropped(tmp_path: Path):
    demo = make_demo(tmp_path, "mirage17.dem", size=32)
    index = DemoIndex(tmp_path)
    index.remember(make_profile(size_bytes=32))
    index.remember(make_profile(name="nuke04.dem", size_bytes=32))

    dropped = index.keep_only([demo])

    assert dropped == 1
    assert index.count == 1


def test_an_empty_folder_never_empties_the_book(tmp_path: Path):
    index = DemoIndex(tmp_path)
    index.remember(make_profile())

    assert index.keep_only([]) == 0
    assert index.count == 1


def test_profiles_come_back_newest_first(tmp_path: Path):
    index = DemoIndex(tmp_path)
    index.remember(make_profile(name="old.dem", modified_at=10.0))
    index.remember(make_profile(name="new.dem", modified_at=90.0))

    assert [profile.name for profile in index.profiles()] == ["new.dem", "old.dem"]


def test_only_unknown_demos_are_read(tmp_path: Path):
    known = make_demo(tmp_path, "known.dem", size=32)
    fresh = make_demo(tmp_path, "fresh.dem", size=32)
    index = DemoIndex(tmp_path)
    index.remember(make_profile(name="known.dem", size_bytes=32))
    profiler = CountingProfiler()

    report = DemoLibrarian(index, profiler).catch_up([known, fresh])

    assert profiler.seen == ["fresh.dem"]
    assert (report.read, report.left) == (1, 0)


def test_a_second_pass_has_nothing_to_do(tmp_path: Path):
    demo = make_demo(tmp_path, "mirage17.dem")
    index = DemoIndex(tmp_path)
    librarian = DemoLibrarian(index, CountingProfiler())
    librarian.catch_up([demo])

    assert librarian.catch_up([demo]).did_work is False


def test_the_budget_stops_a_long_catch_up(tmp_path: Path):
    demos = [make_demo(tmp_path, f"demo{index}.dem") for index in range(4)]
    profiler = CountingProfiler(pause=0.02)

    report = DemoLibrarian(DemoIndex(tmp_path), profiler).catch_up(demos, budget_seconds=0.01)

    assert report.read == 1
    assert report.left == 3
    assert report.ran_out_of_time is True


def test_the_first_demo_is_always_read(tmp_path: Path):
    demo = make_demo(tmp_path, "mirage17.dem")

    report = DemoLibrarian(DemoIndex(tmp_path), CountingProfiler(pause=0.02)).catch_up(
        [demo], budget_seconds=0.001
    )

    assert report.read == 1


def test_the_report_counts_the_nicknames(tmp_path: Path):
    demos = [make_demo(tmp_path, f"demo{index}.dem") for index in range(2)]

    report = DemoLibrarian(DemoIndex(tmp_path), CountingProfiler(players=5)).catch_up(demos)

    assert report.players == 10


def test_players_of_one_demo_are_sorted_ignoring_the_dash():
    profile = make_profile(players=cards("zeus", "-alpha", "Mid"))

    names = [hint.name for hint in PlayerDirectory([profile]).hints("mirage17.dem")]

    assert names == ["-alpha", "Mid", "zeus"]


def test_a_player_of_one_demo_is_noted_by_side():
    profile = make_profile(players=cards("s1mple"))

    assert PlayerDirectory([profile]).hints("mirage17.dem")[0].note == "started T"


def test_players_of_every_demo_are_listed_once():
    first = make_profile(name="mirage17.dem", players=cards("s1mple", "b1t"))
    second = make_profile(name="nuke04.dem", players=cards("s1mple", "electronic"))

    hints = PlayerDirectory([first, second]).hints()

    assert sorted(hint.name for hint in hints) == ["b1t", "electronic", "s1mple"]


def test_a_player_seen_twice_says_so():
    first = make_profile(name="mirage17.dem", players=cards("s1mple"))
    second = make_profile(name="nuke04.dem", players=cards("s1mple"))

    hint = next(item for item in PlayerDirectory([first, second]).hints() if item.name == "s1mple")

    assert hint.note == "in mirage17 and 1 more"


def test_a_long_demo_name_is_shortened_in_the_note():
    profile = make_profile(name="1-16fe85f3-da86-4bde-a29c-4dda86a2773c-1-1.dem", players=cards("s1mple"))

    assert PlayerDirectory([profile]).hints()[0].note == "in 1-16fe85f3-da86-4bde.."


def test_a_nickname_is_found_with_or_without_its_dash():
    hint = PlayerHint(name="-n1clxe")

    assert hint.starts_with("-n1") is True
    assert hint.starts_with("n1c") is True
    assert hint.starts_with("clx") is False


def test_a_prefix_search_narrows_the_roster():
    profile = make_profile(players=cards("s1mple", "-n1clxe", "b1t"))

    found = PlayerDirectory([profile]).matching("n1", "mirage17.dem")

    assert [hint.name for hint in found] == ["-n1clxe"]


def test_a_parsed_match_becomes_a_profile(tmp_path: Path, match, terrorists, counter_terrorists):
    match.demo_path = make_demo(tmp_path, "mirage17.dem")
    match.players = {player.steam_id64: player for player in terrorists}
    match.rounds.append(
        make_round(roster=make_roster(terrorists, counter_terrorists))
    )

    profile = DemoProfiler().from_match(match)

    assert profile.name == "mirage17.dem"
    assert profile.map_name == match.map_name
    assert len(profile.players) == len(terrorists)
    assert profile.players[0].side is TeamSide.TERRORIST


def test_a_match_without_rounds_still_profiles(tmp_path: Path, match):
    match.demo_path = make_demo(tmp_path, "mirage17.dem")
    match.players = {76561197960265729: make_player(1)}

    profile = DemoProfiler().from_match(match)

    assert profile.players[0].side is None


def test_the_library_ties_it_together(tmp_path: Path):
    work = tmp_path / "work"
    demo = make_demo(tmp_path, "mirage17.dem")
    library = DemoLibrary(work, profiler=CountingProfiler(players=3))

    report = library.catch_up([demo])

    assert report.read == 1
    assert library.known_count == 1
    assert library.player_count() == 3
    assert library.named("mirage17").map_name == MIRAGE
    assert (work / "demo_index.json").is_file()
