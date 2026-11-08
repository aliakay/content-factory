"""What we took from cinecode/otopilot/kurgu: caption blocks, camera inertia + speed words, windowed audio facts,
and the guard on untrusted ffmpeg sources."""
import subprocess

import pytest

from factory import camera, captions, fftools, qa
from factory.config import FFMPEG


# ---------------------------------------------------------------- captions: no blink between blocks
def test_a_short_gap_is_closed_and_a_long_one_keeps_a_hold():
    words = [("Merhaba", 1.0, 1.4), ("çağrı", 1.65, 2.0), ("için", 2.1, 2.5), ("dört", 2.55, 2.9)]
    blocks = captions.blocks(words, "9:16")
    assert blocks[0]["text"] == "Merhaba çağrı için"
    assert blocks[0]["end"] == 2.55                    # 0.05 s gap: held until the next block starts (no empty frame)
    far = captions.blocks([("a", 1.0, 1.4), ("b", 2.2, 2.6)], "9:16")
    assert far[0]["end"] == pytest.approx(1.52)        # 0.8 s gap: 0.12 s hold, not 0.8


def test_blocks_break_on_words_chars_and_punctuation():
    three = [("bir", 0.0, 0.2), ("iki", 0.2, 0.4), ("üç", 0.4, 0.6), ("dört", 0.6, 0.8)]
    assert [b["text"] for b in captions.blocks(three, "9:16")] == ["bir iki üç", "dört"]   # 3 words a line on 9:16
    assert len(captions.blocks(three, "16:9")) == 1                                        # 7 a line on 16:9
    sentence = [("geldi.", 0.0, 0.3), ("sonra", 0.31, 0.6)]
    assert [b["text"] for b in captions.blocks(sentence, "16:9")] == ["geldi.", "sonra"]


def test_a_block_never_shows_for_less_than_five_frames():
    blocks = captions.blocks([("a", 1.0, 1.05)], "9:16")
    assert blocks[0]["end"] - blocks[0]["start"] == pytest.approx(captions.MIN_S)


def test_scene_windows_pick_their_blocks():
    blocks = captions.blocks([("a", 0.0, 0.3), ("b", 1.0, 1.3), ("c", 5.0, 5.3)], "9:16")
    assert [b["text"] for b in captions.overlapping(blocks, 0.9, 2.0)] == ["b"]


# ---------------------------------------------------------------- camera: the inertia curve and speed words
def test_inertia_is_a_third_linear_and_two_thirds_smoothstep():
    assert camera.inertia(0.0) == 0.0 and camera.inertia(1.0) == 1.0
    assert camera.inertia(0.25) == pytest.approx(0.35 * 0.25 + 0.65 * (0.25 * 0.25 * (3 - 2 * 0.25)))
    assert camera.inertia(0.25) < 0.25          # slower than linear at the start, catches up at the end


def test_the_inertia_easing_is_part_of_the_vocabulary():
    cam = {"move": "push_in", "seconds": 1.2, "easing": "inertia", "target": "the number"}
    assert camera.problems([{"id": "s1", "camera": cam}]) == []
    assert camera.parse(cam)["easing"] == "inertia"
    assert camera.speed_of("Hızlı") == camera.speed_of("fast") == "fast"
    assert camera.speed_of("") is None


def test_the_scene_library_carries_the_same_curve_and_a_punch():
    js = open("motion/templates/fxlib.js", encoding="utf-8").read()
    assert "FX.INERTIA" in js and "0.35 * p + 0.65" in js
    assert "FX.punch" in js and "1.12" in js and "0.18" in js and "0.20" in js


# ---------------------------------------------------------------- audio facts at a cut point
@pytest.fixture
def tone(tmp_path):
    path = str(tmp_path / "t.wav")
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=420:duration=6", path], check=True)
    return path


def test_a_cut_point_reports_level_and_holes(tone):
    facts = qa.audio_facts(tone, 3.0, window=1.0)
    assert facts["at"] == 3.0 and facts["window"] == 1.0
    assert facts["rms_db"] is not None and facts["peak_db"] is not None
    assert facts["silent_s"] == 0 and facts["speech"] is True


def test_an_untrusted_source_is_refused_before_ffmpeg():
    assert fftools.check_source("/tmp/clip.mp4") == "/tmp/clip.mp4"
    for bad in ("https://example.com/a.m3u8", "rtsp://host/live", "/tmp/a.m3u8", "/tmp/a.ffconcat"):
        with pytest.raises(ValueError):
            fftools.check_source(bad)
