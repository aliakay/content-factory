"""Craft checks distilled from cinecode (factory/craftcheck.py) and their wiring."""
import numpy as np
import pytest

from factory import craftcheck as C, soundqa
from factory.hat import manifest, tools as T


def test_words_check_flags_dashes_phrases_and_greeting():
    f = C.words_check(["Hey everyone, welcome back", "Gas prices — again — rose", "It is a game changer."], "en")
    assert {x["kind"] for x in f} == {"greeting", "dash", "stock_phrase"}
    assert C.words_check(["Gas costs 100 euros per megawatt hour."], "en") == []
    tr = C.words_check(["Merhaba arkadaşlar, bu videoda gaz fiyatlarına bakıyoruz."], "tr")
    assert {x["kind"] for x in tr} == {"greeting", "stock_phrase"}


def test_rhythm_even_and_runs():
    assert {x["kind"] for x in C.rhythm([4, 4, 4, 4, 4, 4])} == {"even_rhythm", "flat_run"}
    assert C.rhythm([2, 6, 3, 9, 4, 2.5, 7]) == []
    assert C.rhythm([3, 5]) == []                       # too few scenes to judge


def test_sound_budget():
    whoosh = [{"t": t, "kind": "whoosh"} for t in (2, 8, 14, 20)]
    kinds = {x["kind"] for x in C.sound_budget(whoosh, 30)}
    assert "too_many_whooshes" in kinds
    ok = C.sound_budget([{"t": 5, "kind": "whoosh"}, {"t": 18, "kind": "riser"}], 30)
    assert ok == []
    cuts = [3, 6, 9, 12, 15]
    every = [{"t": t, "kind": "pop"} for t in cuts]
    assert "sound_on_every_cut" in {x["kind"] for x in C.sound_budget(every, 20, cuts)}


def test_frame_bpms():
    t = {x["bpm"]: x["frames_per_beat"] for x in C.frame_bpms(30)}
    assert t[90] == 20 and t[120] == 15 and 100 in t and 93 not in t
    assert {x["bpm"] for x in C.frame_bpms(24)} >= {80, 90, 96, 120, 144}


def test_scene_loudness_flags_the_loud_scene(tmp_path, monkeypatch):
    sr = soundqa.SR
    t = np.arange(sr) / sr
    quiet, loud = 0.05 * np.sin(2 * np.pi * 220 * t), 0.5 * np.sin(2 * np.pi * 220 * t)
    y = np.concatenate([quiet, quiet, loud, quiet]).astype(np.float32)
    monkeypatch.setattr(soundqa, "decode", lambda p, sr=sr: y)
    r = C.scene_loudness("x.wav", [1, 2, 3])
    assert [f["t"] for f in r["findings"] if f["kind"] == "scene_level"] == [2.0]


def test_new_tools_registered_and_used_by_lines():
    for n in ("words_check", "rhythm_check", "beat_frames"):
        assert n in T.TOOLS and T.TOOLS[n]["capability"] == "qa"
    ex = manifest.get("explainer")
    by = {s["id"]: s for s in ex["stages"]}
    assert "words_check" in by["script"]["tools"] and "rhythm_check" in by["scene_plan"]["tools"]
    assert "beat_frames" in {t for s in manifest.get("animation")["stages"] for t in s.get("tools", [])}


def test_sound_review_runs_the_budget(monkeypatch):
    y = (0.1 * np.sin(2 * np.pi * 300 * np.arange(soundqa.SR * 20) / soundqa.SR)).astype(np.float32)
    monkeypatch.setattr(soundqa, "decode", lambda p, sr=soundqa.SR: y)
    cues = [{"t": t, "kind": "whoosh"} for t in (1, 5, 9)]
    r = soundqa.review("x.mp4", cues=cues, total=20, lufs=(-14.0, -3.0))
    assert "too_many_whooshes" in {f["kind"] for f in r["findings"]}


def test_camera_angle_crane_rack_handheld_cards_exist_and_validate():
    from factory import recipes as R
    cs = {c["id"]: c for c in R.cards()}
    for cid in ("camera.low_angle", "camera.high_angle", "camera.crane_up", "camera.crane_down", "camera.rack_focus",
                "camera.handheld"):
        assert cid in cs, cid
    assert R.problems(R.cards()) == []
    js = open(R.os.path.join(R.ROOT, "motion", "templates", "fxlib.js"), encoding="utf-8").read()
    for fn in ("FX.angle", "FX.crane", "FX.rack", "FX.handheld"):
        assert f"{fn} = " in js, fn


@pytest.mark.parametrize("cid", ["camera.low_angle", "camera.crane_up", "camera.rack_focus", "camera.handheld"])
def test_new_camera_demos_run_without_page_errors(cid):
    import os
    from factory import recipes as R
    if not os.path.isdir(os.path.join(R.ROOT, "motion", "node_modules")):
        pytest.skip("no motion/node_modules here")
    os.makedirs(os.path.join(R.ROOT, "work", "catalog"), exist_ok=True)
    pngs, errs = R.check(cid)
    assert errs == [] and len(pngs) == 1


def test_speed_ramp_card_and_demo():
    import os
    from factory import recipes as R
    assert "camera.speed_ramp" in {c["id"] for c in R.cards()} and R.problems(R.cards()) == []
    assert "FX.ramp = " in open(os.path.join(R.ROOT, "motion", "templates", "fxlib.js"), encoding="utf-8").read()
    if not os.path.isdir(os.path.join(R.ROOT, "motion", "node_modules")):
        pytest.skip("no motion/node_modules here")
    os.makedirs(os.path.join(R.ROOT, "work", "catalog"), exist_ok=True)
    pngs, errs = R.check("camera.speed_ramp")
    assert errs == [] and len(pngs) == 1
