"""Series + illustrated look with the model and ElevenLabs stubbed: bible -> sheets -> episode -> plates -> voices."""
import json, os, sqlite3, subprocess

import pytest

from factory import channels, eleven, illustrate, llm, productions as P, series
from factory.config import FFMPEG
from factory.store import SCHEMA

BIBLE = {"title": "Pip & the Lighthouse", "logline": "A robot keeps a lighthouse.", "tone": "warm", "world": "A rocky isle.",
         "art_style": "storybook gouache", "narrator": {"voice_hint": "warm"},
         "characters": [{"id": "Pip", "name": "Pip", "role": "robot", "look": "small round teal robot, red scarf"},
                        {"id": "gull", "name": "Gull", "role": "friend", "look": "grey gull, yellow beak"}],
         "chapters": [{"n": 1, "title": "Storm", "summary": "A storm comes.", "text": "Night falls. " * 30},
                      {"n": 2, "title": "Ship", "summary": "A ship is lost.", "text": "Waves rise. " * 30}],
         "episodes": [{"n": 1, "title": "The Storm", "chapters": [1], "logline": "x", "cliffhanger": "a light!"},
                      {"n": 2, "title": "The Ship", "chapters": [2], "logline": "y"}]}
EPISODE = {"ideas": [{"title": "The Storm", "hook": "Night fell.", "header": "PIP · EP 1", "art_style": "storybook gouache",
                      "voice": {"lines": ["Night fell on the isle.", "Pip, the storm is here!", "I will keep the light on."],
                                "speakers": ["narrator", "gull", "pip"]},
                      "scenes": [{"id": "s1", "lines": [0, 0], "elements": [{"type": "label", "text": "PIP · EP 1", "at": 0.2}],
                                  "plate": {"prompt": "lighthouse at night", "cast": ["pip"], "camera": "push_in"}},
                                 {"id": "s2", "lines": [1, 2], "elements": [],
                                  "plate": {"prompt": "gull lands near Pip inside the lamp room", "cast": ["pip", "gull"],
                                            "same_place_as": "s1", "camera": "zoom_to", "focus": [0.6, 0.3],
                                            "annotations": [{"type": "pin", "text": "PIP", "at": "Pip", "where": [0.5, 0.5, 0.1, 0.1]},
                                                            {"type": "bogus"}]}}]}]}


@pytest.fixture
def con(tmp_path, monkeypatch):
    monkeypatch.setattr(channels, "DIR", str(tmp_path / "ch"))
    c = sqlite3.connect(tmp_path / "t.db")
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    P.ensure(c)
    return c


def fake_image(calls):
    def img(con, prompt, approved, account=None, aspect="9:16", flow_id=None, refs=(), idea_id=None, model=None):
        calls.append({"prompt": prompt, "refs": list(refs), "flow": flow_id, "approved": approved})
        return f"/tmp/img{len(calls)}.png", 210.0, flow_id or "flow1", f"node{len(calls)}"
    return img


def test_series_bible_sheets_episode_and_plates(con, monkeypatch):
    replies = [(BIBLE, {"cost_usd": 1.0}), (EPISODE, {"cost_usd": 0.5})]
    monkeypatch.setattr(llm, "ask", lambda *a, **k: replies.pop(0))
    calls = []
    monkeypatch.setattr(eleven, "image", fake_image(calls))
    sid = series.create(con, "a robot who keeps a lighthouse", "bilgi", "storybook", 2)
    s = series.write_bible(con, sid)
    assert s["status"] == "bible" and [c["id"] for c in s["data"]["characters"]] == ["pip", "gull"]
    with pytest.raises(ValueError):
        series.write_episode(con, sid, 1)                     # not approved / no sheets yet
    assert series.approve_bible(con, sid)["status"] == "casting"
    series.make_sheets(con, sid, 500, "ali")
    s = series.get(con, sid)
    assert s["status"] == "ready" and s["data"]["flow_id"] == "flow1" and len(calls) == 2
    assert "Character reference sheet" in calls[0]["prompt"] and calls[1]["flow"] == "flow1"
    series.set_voice(con, sid, "narrator", "V_NARR")
    series.set_voice(con, sid, "gull", "V_GULL")
    series.set_voice(con, sid, "pip", "V_PIP")
    pid = series.write_episode(con, sid, 1)
    p = P.get(con, pid)
    d = p["data"]
    assert p["format"] == "series_episode" and p["channel_id"] == "bilgi" and d["series"]["episode"] == 1
    assert d["voice"]["speakers"] == ["narrator", "gull", "pip"] and d["cast_voices"]["gull"] == "V_GULL"
    assert P.multi_voice(d) and illustrate.needs_plates(d) and illustrate.missing(d) == ["s1", "s2"]
    assert d["scenes"][1]["plate"]["same_place_as"] == "s1" and len(d["scenes"][1]["plate"]["annotations"]) == 1
    assert series.get(con, sid)["data"]["episodes"][0]["prod_id"] == pid
    chars, flow = series.cast_for(con, p)
    monkeypatch.setattr(illustrate.os.path, "exists", lambda f: True)
    illustrate.make_plates(con, p, 420, chars, flow)
    assert calls[2]["refs"] == ["node1"]                          # s1 made from Pip's sheet
    assert calls[3]["refs"][0] == "node3" and "node2" in calls[3]["refs"]   # s2 from s1's plate + both sheets
    assert "small round teal robot" in calls[3]["prompt"] and "No text" in calls[3]["prompt"]
    assert set(d["plates"]) == {"s1", "s2"} and d["art_flow"] == "flow1"
    with pytest.raises(ValueError):
        P.preview(con, P.create(con, "series_episode", dict(d, plates={})))   # no plates yet: no preview


def test_cast_voice_joins_takes(con, monkeypatch, tmp_path):
    def tts(con, text, vid, model, approved=None, account=None):
        f = tmp_path / f"{vid}_{abs(hash(text)) % 999}.mp3"
        subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "sine=f=440:d=0.4", str(f)], check=True)
        return str(f), 10.0
    monkeypatch.setattr(eleven, "tts", tts)
    monkeypatch.setattr(P, "ROOT", str(tmp_path))
    os.makedirs(tmp_path / "assets" / "eleven")
    d = {"voice": {"lines": ["a b", "c d", "e f"], "speakers": ["narrator", "narrator", "gull"]},
         "cast_voices": {"narrator": "N", "gull": "G"}}
    path, cost = P.cast_voice(con, d, 30)
    assert os.path.exists(path) and cost == 20.0                   # two runs: narrator x2 lines, gull
    assert not P.multi_voice({"voice": {"lines": ["a"], "speakers": ["narrator"]}, "cast_voices": {"narrator": "N"}})
