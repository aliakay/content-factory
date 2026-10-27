"""Studio pieces that must not regress: credit guard, link detection, timeline compiler."""
import json, sqlite3

import pytest

from factory import credits, productions as P, tracking
from factory.store import SCHEMA


@pytest.fixture
def con(tmp_path):
    c = sqlite3.connect(tmp_path / "t.db")
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    P.ensure(c)
    credits.ensure(c)
    c.execute("INSERT INTO clips (clip_id, path, kind, duration, fps, usable) VALUES "
              "('A.MOV', '/x/raw/A.MOV', 'video', 10.0, 60, 1), ('B.JPG', '/x/raw/B.JPG', 'photo', NULL, NULL, 1), "
              "('C.MOV', '/x/raw/C.MOV', 'video', 2.0, 30, 1)")
    c.commit()
    return c


def test_guard_needs_approval(con):
    with pytest.raises(credits.BudgetError):
        credits.guard(con, "tts", "eleven_v4", 100, None)
    assert credits.guard(con, "tts", "eleven_v4", 100, 200) <= 200
    with pytest.raises(credits.BudgetError):  # estimate far above what was approved
        credits.guard(con, "tts", "eleven_v4", 1000, 100)


def test_guard_unknown_model_capped_by_approval(con):
    assert credits.guard(con, "video", "some-new-model", 5, 3000) == 3000
    with pytest.raises(credits.BudgetError):
        credits.guard(con, "video", "some-new-model", 5, credits.MONTHLY_CAP + 1)


def test_detect_links():
    assert tracking.detect("https://youtube.com/shorts/abcdefghijk?si=x") == ("youtube", "abcdefghijk")
    assert tracking.detect("https://www.tiktok.com/@ali/video/7412345678901234567")[0] == "tiktok"
    assert tracking.detect("https://www.instagram.com/reel/C9xYz12AbC/")[0] == "instagram"
    with pytest.raises(ValueError):
        tracking.detect("https://example.com/v/1")


def prod(con, fmt, data):
    pid = P.create(con, fmt, data)
    return P.get(con, pid)


def test_calm_timeline(con):
    p = prod(con, "cinematic_calm", {"title": "t", "hook": "Hook here", "shots": [
        {"clip_id": "A.MOV", "in": 1.0, "out": 4.0, "speed": 1.0, "text": ""},
        {"clip_id": "B.JPG", "dur": 3.0, "drift": 0.02, "focus": [0.5, 0.5], "text": "Second"}],
        "end_card": "", "post": {}})
    spec, total, starts, warn = P.timeline(con, p)
    assert total == 6.0 and starts == [0, 3.0]
    assert [t["text"] for t in spec["text"]] == ["Hook here", "Second"]
    assert spec["text"][0]["start"] == 0.0  # hook is on screen at frame 0 (the cover)
    assert any("sessiz" in w for w in warn)  # photo without an ambience bed


def test_story_draft_cuts_on_lines_and_fits_short_clip(con):
    p = prod(con, "story_vo", {"title": "s", "voice": {"lines": ["one two three four", "five six seven eight",
                                                                   "nine ten eleven twelve"]},
                                "shots": [{"clip_id": "A.MOV", "in": 0, "out": 3, "speed": 1.0},
                                          {"clip_id": "C.MOV", "in": 0, "out": 2, "speed": 1.0, "at_line": 1},
                                          {"clip_id": "B.JPG", "dur": 2, "drift": 0.02, "focus": [0.5, 0.5],
                                           "at_line": 2}],
                                "end_card": "Place · Region", "tail_s": 3.0, "post": {}})
    spec, total, starts, warn = P.timeline(con, p)
    lt, _, real = P.line_times(p["data"])
    assert not real and abs(starts[1] - (lt[1]["start"] - 0.1)) < 0.01
    durs = [(s["out"] - s["in"]) / s["speed"] if "video" in s else s["dur"] for s in spec["shots"]]
    assert abs(sum(durs) - total) < 0.01  # a 2 s / 30 fps clip can't fill its slot: the time moves on
    assert spec["shots"][1]["out"] <= 2.0
    assert spec["text"][-1]["text"] == "Place · Region"


def test_aspect_reaches_the_spec_and_wraps_wider(con):
    p = prod(con, "cinematic_calm", {"title": "t", "hook": "A fairly long hook line that would wrap on a phone",
                                     "aspect": "16:9", "shots": [
        {"clip_id": "A.MOV", "in": 1.0, "out": 4.0, "speed": 1.0, "text": ""}], "post": {}})
    spec, *_ = P.timeline(con, p)
    assert spec["aspect"] == "16:9"
    assert "\\N" not in spec["text"][0]["text"]  # 51 chars fit one horizontal line


def test_renderer_geometry():
    import importlib.util, os
    path = os.path.join(os.path.dirname(__file__), "..", "bin", "stylecut.py")
    spec = importlib.util.spec_from_file_location("stylecut_t", path)
    sc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sc)
    assert sc.geometry("letterbox", 1080, 1920) == (1080, 608, 656)   # 16:9 band on a phone frame
    assert sc.geometry("letterbox", 1920, 1080)[1] == 804             # becomes the 2.39:1 band on 16:9
    assert sc.geometry("full", 1920, 1080) == (1920, 1080, 0)
