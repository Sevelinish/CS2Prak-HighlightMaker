from __future__ import annotations

import struct
from pathlib import Path

from conftest import make_player, make_round, make_roster

from highlighter.config.schema import RecordingConfig
from highlighter.domain.team import TeamSide
from highlighter.plan.models import ClipPlayer, ClipSegment, ClipSpec
from highlighter.recording.true_view import POV_CAPTURE_MODE, TrueViewProfile
from highlighter.voice.audience import AudiencePicker, VoiceAudience
from highlighter.voice.cues import VoiceCue, VoiceTrack, VoiceTrackBuilder
from highlighter.voice.mixer import VoiceMixer
from highlighter.voice.ogg import OggChecksum, OggOpusWriter
from highlighter.voice.overlay import VoiceOverlay
from highlighter.voice.packets import VoicePacket, VoiceReader
from highlighter.voice.utterance import Utterance, UtteranceGrouper

TICK_RATE = 64
FRAME = bytes([0x70, 0x0B, 0xE6, 0x59])


def packets(steam_id: int, ticks: list[int]) -> list[VoicePacket]:
    return [VoicePacket(tick=tick, steam_id64=steam_id, payload=FRAME) for tick in ticks]


def clip_of(player: ClipPlayer, segments: tuple[ClipSegment, ...], round_number: int = 1):
    return ClipSpec(
        index=1,
        name="01_round01",
        round_number=round_number,
        player=player,
        tags=(),
        score=1.0,
        segments=segments,
        action_start_tick=segments[0].start_tick,
        action_end_tick=segments[-1].end_tick,
    )


def segment_of(start: int, end: int, player: ClipPlayer | None = None) -> ClipSegment:
    return ClipSegment(
        index=1,
        start_tick=start,
        end_tick=end,
        kill_ticks=(start,),
        duration_seconds=(end - start) / TICK_RATE,
        player=player,
    )


def as_clip_player(player) -> ClipPlayer:
    return ClipPlayer(
        name=player.name, steam_id64=player.steam_id64, account_id=player.account_id
    )


class Recorder:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def run(self, arguments: list[str], label: str) -> None:
        self.calls.append(list(arguments))


class StubReader:
    def __init__(self, rows) -> None:
        self._rows = rows
        self.asked = 0

    def read(self, demo_path: Path):
        self.asked += 1
        return tuple(self._rows)


def test_a_packet_needs_a_payload():
    assert VoicePacket.from_mapping({"tick": 1, "steamid": 2, "bytes": b""}) is None


def test_a_packet_is_read_from_the_parser_row():
    packet = VoicePacket.from_mapping({"tick": 7, "steamid": 99, "bytes": b"ab"})

    assert (packet.tick, packet.steam_id64, packet.payload) == (7, 99, b"ab")


def test_a_row_with_nonsense_is_dropped():
    assert VoicePacket.from_mapping({"tick": "x", "steamid": 1, "bytes": b"a"}) is None


def test_a_demo_that_cannot_be_read_gives_no_voice(tmp_path: Path):
    assert VoiceReader().read(tmp_path / "missing.dem") == ()


def test_neighbouring_packets_become_one_utterance():
    grouped = UtteranceGrouper(TICK_RATE).group(packets(1, [100, 101, 102, 103]))

    assert len(grouped) == 1
    assert grouped[0].start_tick == 100
    assert len(grouped[0].payloads) == 4


def test_a_silence_splits_two_utterances():
    grouped = UtteranceGrouper(TICK_RATE, gap_seconds=0.25).group(
        packets(1, [100, 101, 500, 501])
    )

    assert [item.start_tick for item in grouped] == [100, 500]


def test_two_speakers_are_kept_apart():
    grouped = UtteranceGrouper(TICK_RATE).group(packets(1, [100, 101]) + packets(2, [100]))

    assert {item.steam_id64 for item in grouped} == {1, 2}


def test_an_utterance_lasts_ten_milliseconds_per_packet():
    utterance = Utterance(1, 0, (FRAME,) * 320)

    assert round(utterance.seconds, 2) == 3.2


def test_an_utterance_knows_when_it_overlaps_a_window():
    utterance = Utterance(1, 6400, (FRAME,) * 100)

    assert utterance.overlaps(TICK_RATE, 99.0, 101.0) is True
    assert utterance.overlaps(TICK_RATE, 0.0, 50.0) is False


def test_the_ogg_stream_starts_with_a_page():
    stream = OggOpusWriter().render([FRAME] * 3)

    assert stream[:4] == b"OggS"
    assert b"OpusHead" in stream[:64]
    assert b"OpusTags" in stream


def test_every_ogg_page_carries_a_good_checksum():
    stream = OggOpusWriter().render([FRAME] * 45)

    pages = stream.split(b"OggS")[1:]
    assert len(pages) >= 4
    for body in pages:
        page = b"OggS" + body
        stored = struct.unpack("<I", page[22:26])[0]
        blank = page[:22] + bytes(4) + page[26:]
        assert OggChecksum.of(blank) == stored


def test_the_granule_grows_with_every_frame():
    stream = OggOpusWriter(packets_per_page=2).render([FRAME] * 4)
    pages = [b"OggS" + body for body in stream.split(b"OggS")[1:]]

    granules = [struct.unpack("<q", page[6:14])[0] for page in pages]

    assert granules[-1] == 480 * 4


def test_only_the_team_of_the_point_of_view_is_heard(match, terrorists, counter_terrorists):
    match.rounds.append(make_round(roster=make_roster(terrorists, counter_terrorists)))
    picker = AudiencePicker(match)

    heard = picker.listeners(VoiceAudience.TEAM, terrorists[0].steam_id64, 1)

    assert heard == frozenset(player.steam_id64 for player in terrorists)


def test_the_enemy_point_of_view_hears_its_own_team(match, terrorists, counter_terrorists):
    match.rounds.append(make_round(roster=make_roster(terrorists, counter_terrorists)))

    heard = AudiencePicker(match).listeners(
        VoiceAudience.TEAM, counter_terrorists[0].steam_id64, 1
    )

    assert heard == frozenset(player.steam_id64 for player in counter_terrorists)


def test_everyone_means_every_player(match, terrorists, counter_terrorists):
    for player in (*terrorists, *counter_terrorists):
        match.players[player.steam_id64] = player

    heard = AudiencePicker(match).listeners(VoiceAudience.EVERYONE, 0, 1)

    assert len(heard) == 10


def test_voice_switched_off_hears_nobody(match):
    assert AudiencePicker(match).listeners(VoiceAudience.OFF, 1, 1) == frozenset()


def test_an_unknown_audience_reads_as_off():
    assert VoiceAudience.parse("nonsense") is VoiceAudience.OFF
    assert VoiceAudience.parse(None) is VoiceAudience.OFF


def test_a_cue_is_written_and_placed(tmp_path: Path):
    utterance = Utterance(7, 128, (FRAME,) * 100)
    builder = VoiceTrackBuilder(TICK_RATE, [utterance], tmp_path)

    track = builder.build(start_tick=64, end_tick=640, listeners=frozenset({7}))

    assert len(track.cues) == 1
    assert track.cues[0].source.is_file()
    assert round(track.cues[0].offset_seconds, 3) == 1.0
    assert track.cues[0].skip_seconds == 0.0


def test_a_cue_that_started_earlier_is_trimmed(tmp_path: Path):
    utterance = Utterance(7, 0, (FRAME,) * 200)
    builder = VoiceTrackBuilder(TICK_RATE, [utterance], tmp_path)

    track = builder.build(start_tick=64, end_tick=640, listeners=frozenset({7}))

    assert track.cues[0].offset_seconds == 0.0
    assert round(track.cues[0].skip_seconds, 3) == 1.0


def test_a_speaker_nobody_listens_to_is_skipped(tmp_path: Path):
    builder = VoiceTrackBuilder(TICK_RATE, [Utterance(7, 128, (FRAME,) * 10)], tmp_path)

    assert builder.build(64, 640, frozenset({8})).is_empty


def test_an_utterance_outside_the_window_is_skipped(tmp_path: Path):
    builder = VoiceTrackBuilder(TICK_RATE, [Utterance(7, 64000, (FRAME,) * 10)], tmp_path)

    assert builder.build(64, 640, frozenset({7})).is_empty


def test_the_same_utterance_is_only_written_once(tmp_path: Path):
    builder = VoiceTrackBuilder(TICK_RATE, [Utterance(7, 128, (FRAME,) * 10)], tmp_path)
    builder.build(64, 640, frozenset({7}))
    builder.build(64, 640, frozenset({7}))

    assert len(list(tmp_path.glob("*.ogg"))) == 1


def test_nothing_is_run_for_an_empty_track(tmp_path: Path):
    recorder = Recorder()
    mixer = VoiceMixer(tmp_path / "ffmpeg.exe", muxer=recorder)

    result = mixer.mix(tmp_path / "game.wav", VoiceTrack(), tmp_path / "out.wav")

    assert result == tmp_path / "game.wav"
    assert recorder.calls == []


def test_the_mix_keeps_the_length_of_the_game_audio(tmp_path: Path):
    recorder = Recorder()
    mixer = VoiceMixer(tmp_path / "ffmpeg.exe", volume=2.0, muxer=recorder)
    track = VoiceTrack(cues=(VoiceCue(source=tmp_path / "a.ogg", offset_seconds=1.5),))

    mixer.mix(tmp_path / "game.wav", track, tmp_path / "out.wav")

    graph = recorder.calls[0][recorder.calls[0].index("-filter_complex") + 1]
    assert "adelay=1500:all=1" in graph
    assert "volume=2" in graph
    assert "amix=inputs=2:duration=first:normalize=0" in graph


def test_a_cue_that_starts_late_is_seeked(tmp_path: Path):
    recorder = Recorder()
    mixer = VoiceMixer(tmp_path / "ffmpeg.exe", muxer=recorder)
    track = VoiceTrack(cues=(VoiceCue(source=tmp_path / "a.ogg", skip_seconds=0.75),))

    mixer.mix(tmp_path / "game.wav", track, tmp_path / "out.wav")

    arguments = recorder.calls[0]
    assert "-ss" in arguments
    assert arguments[arguments.index("-ss") + 1] == "0.750"


def test_a_silent_mixer_leaves_the_audio_alone(tmp_path: Path):
    recorder = Recorder()
    mixer = VoiceMixer(tmp_path / "ffmpeg.exe", volume=0.0, muxer=recorder)
    track = VoiceTrack(cues=(VoiceCue(source=tmp_path / "a.ogg"),))

    assert mixer.mix(tmp_path / "g.wav", track, tmp_path / "o.wav") == tmp_path / "g.wav"


def test_true_view_switches_the_capture_and_turns_voice_on():
    recording = RecordingConfig(true_view=True)

    TrueViewProfile.apply(recording)

    assert recording.capture_mode == POV_CAPTURE_MODE
    assert recording.spectator_mode == "first_person"
    assert recording.voice_chat == "team"


def test_true_view_keeps_a_voice_choice_that_was_made():
    recording = RecordingConfig(true_view=True, voice_chat="everyone")

    TrueViewProfile.apply(recording)

    assert recording.voice_chat == "everyone"


def test_without_true_view_nothing_is_touched():
    recording = RecordingConfig(capture_mode="clean")

    TrueViewProfile.apply(recording)

    assert recording.capture_mode == "clean"
    assert recording.voice_chat == "off"


def test_the_overlay_stays_out_of_the_way_when_voice_is_off(match, tmp_path: Path):
    overlay = VoiceOverlay(
        match=match,
        audience=VoiceAudience.OFF,
        work_directory=tmp_path,
        mixer=VoiceMixer(tmp_path / "ffmpeg.exe", muxer=Recorder()),
        reader=StubReader([]),
    )
    audio = tmp_path / "game.wav"

    player = ClipPlayer(name="a", steam_id64=1, account_id=1)
    result = overlay.apply(clip_of(player, (segment_of(0, 64),)), segment_of(0, 64), audio)

    assert overlay.is_enabled is False
    assert result == audio


def test_the_overlay_mixes_the_team_of_the_victim(
    match, terrorists, counter_terrorists, tmp_path: Path
):
    match.rounds.append(make_round(roster=make_roster(terrorists, counter_terrorists)))
    for player in (*terrorists, *counter_terrorists):
        match.players[player.steam_id64] = player

    talker = counter_terrorists[1]
    rows = packets(talker.steam_id64, [128, 129, 130])
    recorder = Recorder()
    overlay = VoiceOverlay(
        match=match,
        audience=VoiceAudience.TEAM,
        work_directory=tmp_path,
        mixer=VoiceMixer(tmp_path / "ffmpeg.exe", muxer=recorder),
        reader=StubReader(rows),
    )

    victim = as_clip_player(counter_terrorists[0])
    attacker = as_clip_player(terrorists[0])
    segment = segment_of(64, 640, player=victim)
    clip = clip_of(attacker, (segment,))

    overlay.apply(clip, segment, tmp_path / "game.wav")

    assert overlay.speaker_count == 1
    assert len(recorder.calls) == 1


def test_the_overlay_ignores_a_speaker_from_the_other_team(
    match, terrorists, counter_terrorists, tmp_path: Path
):
    match.rounds.append(make_round(roster=make_roster(terrorists, counter_terrorists)))
    rows = packets(terrorists[2].steam_id64, [128, 129])
    recorder = Recorder()
    overlay = VoiceOverlay(
        match=match,
        audience=VoiceAudience.TEAM,
        work_directory=tmp_path,
        mixer=VoiceMixer(tmp_path / "ffmpeg.exe", muxer=recorder),
        reader=StubReader(rows),
    )

    victim = as_clip_player(counter_terrorists[0])
    segment = segment_of(64, 640, player=victim)
    clip = clip_of(as_clip_player(terrorists[0]), (segment,))

    overlay.apply(clip, segment, tmp_path / "game.wav")

    assert recorder.calls == []


def test_the_demo_is_only_read_once(match, tmp_path: Path):
    reader = StubReader([])
    overlay = VoiceOverlay(
        match=match,
        audience=VoiceAudience.EVERYONE,
        work_directory=tmp_path,
        mixer=VoiceMixer(tmp_path / "ffmpeg.exe", muxer=Recorder()),
        reader=reader,
    )

    overlay.prepare()
    overlay.prepare()

    assert reader.asked == 1
