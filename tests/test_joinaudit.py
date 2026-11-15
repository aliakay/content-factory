"""The two free checks on a cut of the creator's own footage (factory/joinaudit.py) — is a join made in speech / through
a word, and how dead is the pace — plus the equal-power crossfade that makes those joins inaudible without changing the
length (factory/audiofx.concat_audio: bin/talkcut.py cuts picture and sound on the same frame grid).
"""
import os, shutil

import numpy as np
import pytest
import soundfile as sf

from factory import audiofx, joinaudit as J
from factory.config import FFMPEG

HAVE_FFMPEG = shutil.which(FFMPEG) or os.path.exists(FFMPEG)
needs_ffmpeg = pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg not installed")

SR = 16000


def _take(path, dur=5.0, tone=(1.0, 3.5), freq=300.0, amp=0.3, noise=0.004, seed=0):
    """A synthetic take: the room's noise floor plus a tone standing in for speech. Returns the signal."""
    rng = np.random.default_rng(seed)
    y = rng.normal(0, noise, int(dur * SR)).astype(np.float32)
    a, b = int(tone[0] * SR), int(tone[1] * SR)
    t = np.arange(b - a) / SR
    y[a:b] += (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    sf.write(str(path), y, SR, subtype="FLOAT")
    return y


# ---------------------------------------------------------------- the level picture

def test_levels_are_10ms_frames_and_ref_reads_the_take_itself(tmp_path):
    y = _take(tmp_path / "a.wav")
    lv = J.levels(y, SR)
    assert len(lv) == 500                      # 5 s of 10 ms frames
    floor, speech = J.ref(lv)
    assert -52 < floor < -44 and -18 < speech < -8      # noise floor ~-48 dBFS, tone ~-13.5 dBFS
    assert J.levels(np.zeros(10, np.float32), SR).size == 0


def test_edge_in_a_tone_is_speech_in_the_floor_is_silence_and_a_soft_part_is_low(tmp_path):
    path = tmp_path / "b.wav"
    y = _take(path, tone=(1.0, 3.5))
    a, b = int(4.0 * SR), int(4.2 * SR)                    # a soft stretch: neither the floor nor speech
    y[a:b] = (0.03 * np.sin(2 * np.pi * 300 * np.arange(b - a) / SR)).astype(np.float32)
    lv = J.levels(y, SR)
    floor, speech = J.ref(lv)
    assert floor + J.SILENCE_DB < -40 <= speech - J.SPEECH_DB
    assert J.edge_class(lv, 2.0, floor, speech) == "speech"
    assert J.edge_class(lv, 0.2, floor, speech) == "silence"
    assert J.edge_class(lv, 4.1, floor, speech) == "low"


# ---------------------------------------------------------------- the join audit

@needs_ffmpeg
def test_audit_a_word_cut_by_a_join_in_speech_is_a_warning(tmp_path):
    src = tmp_path / "j.wav"
    _take(src)
    ranges = [(0.2, 1.6), (1.7, 2.6)]
    words = [["kelime", 1.55, 1.65], ["son", 2.0, 2.2], ["ilk", 0.4, 0.5]]
    r = J.audit(str(src), ranges, words)
    assert r["floor"] < -40 and r["speech"] > -20
    join = next(j for j in r["joins"] if j["kind"] == "join")
    assert join["at_out"] == pytest.approx(1.4)          # output time of the join = end of the first range
    assert join["out_edge"] == "speech" and join["in_edge"] == "speech"
    assert [c["word"] for c in join["clipped"]] == ["kelime"]
    assert join["clipped"][0]["edge"] == "out"
    f = next(f for f in r["findings"] if f["code"] == "clipped_word")
    assert f["level"] == f["severity"] == "warn" and f["t"] == pytest.approx(1.4)
    assert f["detail"] and f["detail_tr"] and "kelime" in f["detail"]


@needs_ffmpeg
def test_audit_a_join_in_speech_without_a_clipped_word_is_info(tmp_path):
    src = tmp_path / "k.wav"
    _take(src)
    r = J.audit(str(src), [(0.2, 2.0), (2.1, 2.6)], [["kelime", 2.3, 2.5]])
    f = r["findings"][0]
    assert f["code"] == "cut_in_speech" and f["level"] == "info"
    assert f["t"] == pytest.approx(1.8) and not any(j["clipped"] for j in r["joins"])


@needs_ffmpeg
def test_audit_a_join_in_the_floor_reports_nothing_and_keeps_the_outer_edges(tmp_path):
    src = tmp_path / "l.wav"
    _take(src)
    r = J.audit(str(src), [(0.2, 0.4), (0.6, 0.8)], [])     # both ranges sit in the noise floor before the tone
    assert r["findings"] == []
    assert [j["kind"] for j in r["joins"]] == ["head", "join", "tail"]
    edges = [(j.get("out_edge", "silence"), j.get("in_edge", "silence")) for j in r["joins"]]
    assert all(e == ("silence", "silence") for e in edges)
    assert r["joins"][-1]["at_out"] == pytest.approx(0.4)
    # the head and the tail carry their edge even though they are not joins
    r2 = J.audit(str(src), [(0.2, 2.6)], [])
    assert r2["joins"][0]["kind"] == "head" and r2["joins"][0]["in_edge"] == "silence"
    assert r2["joins"][-1]["kind"] == "tail" and r2["joins"][-1]["out_edge"] == "speech"


# ---------------------------------------------------------------- pacing

def test_pacing_finds_a_1_2s_hole_and_bu_bu():
    words = [["bu", 0.0, 0.2], ["bu", 0.25, 0.45], ["sonra", 1.65, 1.9], ["final", 2.2, 2.4]]
    p = J.pacing(words)
    assert [g["gap"] for g in p["gaps"]] == [pytest.approx(1.2)]
    assert p["long_gaps"] == 1 and p["long_gap_times"] == [pytest.approx(0.45)]
    assert p["dead_air"] == pytest.approx(0.95)              # 1.2 s hole keeps 0.25 s as a breath
    doubled = p["doubled"]
    assert len(doubled) == 1 and doubled[0]["text"] == "bu" and doubled[0]["words"] == 1
    assert doubled[0]["level"] == "info"                     # no join known: an emphasised repeat
    assert [f["code"] for f in p["findings"]] == ["gap", "doubled"]


def test_pacing_sees_a_repeated_phrase_and_turkish_case_folding():
    phrase = [["the", 0.0, 0.1], ["big", 0.1, 0.2], ["the", 0.25, 0.35], ["big", 0.35, 0.45]]
    d = J.pacing(phrase)["doubled"]
    assert len(d) == 1 and d[0]["text"] == "the big" and d[0]["words"] == 2
    tr = J.pacing([["İyi", 0.0, 0.2], ["iyi", 0.3, 0.5]])["doubled"]
    assert len(tr) == 1 and tr[0]["gap"] == pytest.approx(0.1)


def test_pacing_marks_what_sits_across_a_join_as_warn():
    words = [["bu", 0.0, 0.2], ["bu", 0.25, 0.45], ["sonra", 1.65, 1.9]]
    p = J.pacing(words, join_times=[0.25, 1.65])      # one join on the doubled take, one at the gap's end
    gap, doubled = p["findings"]
    assert doubled["level"] == "warn" and doubled["across_join"] is True
    assert gap["level"] == "warn" and gap["across_join"] is True
    calm = J.pacing(words, join_times=[0.0])                 # a join far from both: no escalation
    assert all(f["level"] == "info" for f in calm["findings"])


# ---------------------------------------------------------------- the join itself

def _tone_take(path, sr=48000, dur=6.0):
    """Two tones with a hard frequency change: a splice between them would jump (a real click)."""
    t = np.arange(int(dur * sr)) / sr
    y = (0.6 * np.sin(2 * np.pi * 300 * t) + 0.05 * np.sin(2 * np.pi * 1300 * t)).astype(np.float32)
    y[int(3 * sr):] = (0.6 * np.sin(2 * np.pi * 700 * t[int(3 * sr):])).astype(np.float32)
    sf.write(str(path), y, sr, subtype="FLOAT")
    return str(path)


@needs_ffmpeg
def test_concat_audio_keeps_the_length_exactly_and_removes_the_dip_at_every_join(tmp_path):
    src = _tone_take(tmp_path / "s.wav")
    sr = 48000
    ranges = [(0.2, 1.0), (1.5, 2.6), (3.0, 4.4)]
    new, old = tmp_path / "xf.wav", tmp_path / "old.wav"
    audiofx.concat_audio(src, ranges, str(new))              # default xfade = 0.03 s
    audiofx.concat_audio(src, ranges, str(old), xfade=0)     # the old fade-to-zero join
    want = sum(b - a for a, b in ranges)
    got = audiofx.decode(str(new), sr)
    assert len(got) / sr == pytest.approx(want, abs=1e-3)    # A/V sync depends on this
    assert len(audiofx.decode(str(old), sr)) / sr == pytest.approx(want, abs=1e-3)
    pos = np.cumsum([b - a for a, b in ranges])[:-1]         # output times of the joins
    for t0 in pos:
        i = int(round(t0 * sr))
        jump = float(np.max(np.abs(np.diff(got[i - 240:i + 240].astype(np.float64)))))
        level = float(np.sqrt(np.mean(got[i - 480:i + 480].astype(np.float64) ** 2)))
        assert jump < 0.15, f"a click at the join at {t0:.2f} s"        # a splice would jump ~2x the peak
        assert level > 0.3, f"the join at {t0:.2f} s dips to silence"
    old_y = audiofx.decode(str(old), sr)
    i = int(round(pos[0] * sr))
    assert float(np.sqrt(np.mean(old_y[i - 48:i + 48].astype(np.float64) ** 2))) < 0.1   # the old dip


@needs_ffmpeg
def test_concat_audio_falls_back_to_the_short_fades_and_still_keeps_the_length(tmp_path):
    src = _tone_take(tmp_path / "s.wav")
    sr = 48000
    for name, ranges in (("short", [(0.2, 0.25), (1.0, 1.8)]),    # a range shorter than 3*xfade: no crossfade
                         ("touching", [(0.2, 1.0), (1.0, 1.8)])):  # no cut material between them (a punch-in)
        dst = tmp_path / f"{name}.wav"
        audiofx.concat_audio(src, ranges, str(dst))
        assert len(audiofx.decode(str(dst), sr)) / sr == pytest.approx(sum(b - a for a, b in ranges), abs=1e-3)


# ---------------------------------------------------------------- wiring into the talk line

@needs_ffmpeg
def test_talk_cut_qa_carries_the_join_and_pace_findings(tmp_path):
    from factory import talk
    src = tmp_path / "t.wav"
    _take(src, dur=5.0)
    a = {"src": str(src), "words": [["kelime", 1.55, 1.65, 0.9], ["son", 2.0, 2.2, 0.9]]}
    segs = [{"in": 0.2, "frames": 42}, {"in": 1.7, "frames": 27}]   # 30 fps: (0.2-1.6) and (1.7-2.6)
    ow = [["kelime", 0.9, 1.0, 0], ["son", 1.4, 1.6, 1]]
    q = talk.cut_qa(a, segs, ow, 30)
    assert not q.get("error")
    assert [f["code"] for f in q["findings"]] == ["clipped_word"]
    assert q["findings"][0]["level"] == "warn" and q["long_gaps"] == 0


def test_talk_cut_qa_never_raises():
    from factory import talk
    q = talk.cut_qa({"src": "/nonexistent/clip.mp4", "words": []}, [{"in": 0.0, "frames": 30}], [], 30)
    assert q.get("error") or q["findings"] == []
