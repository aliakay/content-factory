"""Planner: catalogue-bound plans, fallback, edits and start -> the right jobs."""
import json, sqlite3

import pytest

from factory import channels, llm, planner, productions as P, series
from factory.store import SCHEMA


@pytest.fixture
def con(tmp_path, monkeypatch):
    monkeypatch.setattr(channels, "DIR", str(tmp_path / "ch"))
    c = sqlite3.connect(tmp_path / "t.db")
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    P.ensure(c)
    c.execute("INSERT INTO places (place_id, name, day) VALUES (7, 'Eibsee', '2026-10-01')")
    c.execute("INSERT INTO clips (clip_id, path, kind, place_id, usable) VALUES ('A.MOV', '/x', 'video', 7, 1)")
    c.commit()
    return c


def test_model_plan_is_kept_inside_the_catalogue(con, monkeypatch):
    monkeypatch.setattr(llm, "ask", lambda *a, **k: ({"understood_tr": "Eibsee'den sakin video", "kind": "footage",
                                                      "channel": "nope", "format": "explainer_short", "look": "weird",
                                                      "n": 9, "places": [7, 99], "refs": ["x"], "brief": "calm lake",
                                                      "steps_tr": ["a"]}, {"cost_usd": 0.02}))
    pid = planner.create(con, "Eibsee çekimlerimden sakin bir video", {"places": [7]})
    p = planner.think(con, pid)
    assert p["kind"] == "footage" and p["channel"] == "seyahat" and p["format"] == "cinematic_calm"
    assert p["n"] == 5 and p["places"] == [7] and p["refs"] == [] and p["kind_tr"] == "Çekimli video"
    jobs = []
    out = planner.start(con, pid, lambda k, a: jobs.append((k, json.loads(a))) or len(jobs))
    assert out["status"] == "started" and jobs[0][0] == "p_ideas" and jobs[0][1]["channel"] == "seyahat"
    with pytest.raises(ValueError):
        planner.start(con, pid, lambda k, a: 0)          # a started plan can't start twice


def test_fallback_guess_and_series_start(con, monkeypatch):
    def boom(*a, **k):
        raise llm.LLMError("offline")
    monkeypatch.setattr(llm, "ask", boom)
    pid = planner.create(con, "Bir robot ve martı hakkında çizgi film serisi yapalım", {})
    p = planner.think(con, pid)
    assert p["kind"] == "series_new" and p["fallback"] and p["look"] == "illustrated" and p["series"]["lang"] == "tr"
    planner.update(con, pid, {"series": {"episodes": 4, "style": "anime"}, "aspect": "16:9"})
    jobs = []
    out = planner.start(con, pid, lambda k, a: jobs.append((k, json.loads(a))) or 1)
    sid = out["plan"]["series"]["id"]
    s = series.get(con, sid)
    assert jobs[0] == ("series_bible", {"id": sid}) and s["data"]["n_episodes"] == 4 and s["data"]["style"] == "anime"
    assert s["data"]["aspect"] == "16:9"


def test_topic_costs_include_illustrations(con, monkeypatch):
    monkeypatch.setattr(llm, "ask", lambda *a, **k: ({"kind": "topic", "format": "explainer_short", "look": "illustrated"}, {}))
    p = planner.think(con, planner.create(con, "Hava durumu uygulamaları neden yanılıyor gibi görünür?", {}))
    labels = [x["label"] for x in p["costs"]["lines"]]
    assert p["channel"] == "bilgi" and any("Çizimler" in x for x in labels) and p["costs"]["total"] > 0
