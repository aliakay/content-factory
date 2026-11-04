"""The motion recipe cards and the shotbook (t510): the cards are complete in both languages, a planner gets an index
and full cards, an outline cannot name a recipe that does not exist, and sample demos run without page errors."""
import json, os, re

import pytest

from factory import recipes as R
from factory.config import ROOT


def test_cards_are_complete_and_cover_every_family():
    cs = R.cards()
    assert R.problems(cs) == []
    assert len(cs) >= 100
    assert {c["family"] for c in cs} == set(R.FAMILIES)
    for c in cs:
        assert c["id"].startswith(c["family"] + ".") and float(c["seconds"]) > 0
        assert all(c["name"][l] and c["use"][l] and c["timing"][l] and c["pitfalls"][l] for l in R.LANGS)


def test_problems_name_what_is_wrong():
    good = R.cards()[0]
    bad = [{**good, "id": "camera.wrong_family"}, {k: v for k, v in good.items() if k != "call"},
           {**good, "name": {"tr": "yalnız türkçe"}}, good]
    probs = " ".join(R.problems(bad))
    assert "family" in probs and "call" in probs and "en" in probs and "repeated" in probs


def test_index_and_cards_for_a_planner_in_both_languages():
    en, tr = R.index("en"), R.index("tr")
    assert "data.bar_chart" in en and "[rhythm] Rhythm" in en and "[rhythm] Ritim" in tr
    assert "camera.push_in" not in R.index("en", "data")
    txt = R.card_text(["data.bar_chart", "nope.card", "data.bar_chart"])
    assert txt.count("RECIPE data.bar_chart") == 1 and "nope" not in txt
    assert "call: FX.chart" in txt and "pitfalls:" in txt and "example (" in txt
    assert R.unknown(["data.bar_chart", "nope.card"]) == ["nope.card"]


def test_listing_gives_the_shotbook_in_the_ui_language():
    d = R.listing("tr")
    assert len(d["cards"]) == len(R.cards()) and len(d["families"]) == len(R.FAMILIES)
    c = next(x for x in d["cards"] if x["id"] == "living.rain")
    assert c["family_name"] == "Canlı dünya" and c["name"] == "Yağmur" and c["demo_js"]
    assert c["demo"] is None or c["demo"].startswith("/media/work/recipes/living.rain.mp4?v=")


def test_bundle_carries_bpm_and_math_only_when_needed():
    b = R.bundle("rhythm.slam")
    assert b["bpm"] == 120 and b["scenes"][0]["js"].startswith(R.PRELUDE)
    assert "bpm" not in R.bundle("text.blur_in")
    assert R.bundle("data.equation").get("math") is True


def test_fxlib_shine_keeps_the_text_and_brush_wipe_uncovers():
    src = open(os.path.join(ROOT, "motion", "templates", "fxlib.js"), encoding="utf-8").read()
    assert "o.base || getComputedStyle(el).color" in src
    assert re.search(r"if \(!o\.hold\) tl\.to\(p, \{ strokeDashoffset: -p\.getTotalLength\(\)", src)


def test_recipes_tool_and_pipeline_wiring():
    from factory.hat import manifest, tools as T
    r = T.TOOLS["recipes"]["fn"](None)
    assert "living.rain" in r["index"]
    r = T.TOOLS["recipes"]["fn"](None, ids=["camera.shake", "x.y"])
    assert "RECIPE camera.shake" in r["cards"] and r["unknown"] == ["x.y"]
    for line, stage in [("explainer", "scene_plan"), ("animation", "scene_plan"), ("long_explainer", "outline"),
                        ("long_explainer", "scene_plan")]:
        assert "recipes" in manifest.stage(manifest.get(line), stage)["tools"]


def test_outline_refuses_unknown_recipes_and_hands_cards_to_the_designer():
    from factory.hat import longform as LF
    from tests.test_longform import OUTLINE, SCRIPT
    ok = {**OUTLINE, "scenes": [{**OUTLINE["scenes"][0], "recipes": ["data.line_chart"]}] + OUTLINE["scenes"][1:]}
    assert LF.outline_problems(SCRIPT, ok) == []
    bad = {**OUTLINE, "scenes": [{**OUTLINE["scenes"][0], "recipes": ["data.pie_magic"]}] + OUTLINE["scenes"][1:]}
    assert any("unknown recipes ['data.pie_magic']" in x for x in LF.outline_problems(SCRIPT, bad))
    txt = LF._recipe_cards(ok["scenes"])
    assert "RECIPE data.line_chart" in txt and "1920x1080" in txt
    assert LF._recipe_cards(OUTLINE["scenes"]) == ""


def test_recipe_demos_job_and_api(monkeypatch):
    import sys
    sys.path.insert(0, os.path.join(ROOT, "studio"))
    import hat_api
    queued = []
    r = hat_api.post(None, "/api/hat/recipes", {"ids": ["text.shine", "bogus"]}, lambda k, a: queued.append((k, a)) or 7)
    assert r == {"job_id": 7} and queued[0][0] == "recipe_demos"
    assert json.loads(queued[0][1]) == {"ids": ["text.shine"], "force": False}
    assert len(hat_api.get(None, "/api/hat/recipes", {})["cards"]) == len(R.cards())


@pytest.mark.parametrize("cid", ["text.shine", "transition.brush_wipe", "data.bar_chart", "character.crowd",
                                 "living.rain", "rhythm.cut_run"])
def test_sample_demos_run_without_page_errors(cid):
    if not os.path.isdir(os.path.join(ROOT, "motion", "node_modules")):
        pytest.skip("no motion/node_modules here")
    pngs, errs = R.check(cid)
    assert errs == [] and len(pngs) == 1
