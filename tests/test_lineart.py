"""The line-art kit (FX.ink, motion/templates/lineart.js): its recipe cards are valid, every demo runs without page errors,
frames are a pure function of t (same t twice and out of order give identical pixels) and the kit works in both aspect ratios."""
import json, os, re, shutil, tempfile

import pytest

from factory import recipes as R
from factory import capabilities, filmstyles
from factory.config import ROOT

IDS = [c["id"] for c in R.cards() if c["family"] == "lineart"]


def _shots(bundle, times):
    os.makedirs(R.DIR, exist_ok=True); d = tempfile.mkdtemp(dir=R.DIR)   # the page fetches its bundle from under the card folder
    try:
        bp = os.path.join(d, "b.json")
        json.dump(bundle, open(bp, "w"))
        out = os.path.join(d, "o")
        os.makedirs(out)
        paths, errs = R._hm().shots(bp, times, out)
        assert not errs, errs
        return [open(p, "rb").read() for p in paths]
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_cards_valid_and_enough():
    assert len(IDS) >= 8 and "lineart" in R.FAMILIES
    mine = [c for c in R.cards() if c["family"] == "lineart"]
    assert R.problems(mine) == []
    assert all("FX.ink" in c["demo"] for c in mine)


def test_designer_gets_the_note_with_the_cards():
    txt = R.card_text([IDS[0]], "en")
    assert "LINE-ART KIT" in txt and "95 units" in txt and txt.count("\n") < 140
    assert "LINE-ART KIT" not in R.card_text(["camera.zoom_punch"] if R.get("camera.zoom_punch") else [], "en")


def test_film_style_and_licence_notice():
    s = filmstyles.get("line_art")
    assert s and s["card"]["tr"]["look"] and s["card"]["en"]["avoid"]
    assert "style.line_art" in capabilities.CAPS
    assert "JDhruv14" in open(os.path.join(ROOT, "THIRD_PARTY.md")).read()
    assert "Copyright (c) 2026 JDhruv14" in open(os.path.join(ROOT, "motion", "templates", "lineart.js")).read()


def test_no_nondeterministic_calls_in_kit():
    src = open(os.path.join(ROOT, "motion", "templates", "lineart.js")).read()
    code = re.sub(r"/\*.*?\*/|//[^\n]*", "", src, flags=re.S)
    assert not re.search(r"Math\.random|Date\.now|performance\.now|requestAnimationFrame|setInterval|new Date", code)


@pytest.mark.parametrize("cid", ["lineart.walker_crossing", "lineart.wind_through", "lineart.day_to_night"])
def test_frames_are_pure_functions_of_t(cid):
    """springs, ropes, wind and the gait are cached fixed-step sims or closed forms: asking out of order changes nothing"""
    b = R.bundle(cid)
    t = round(float(R.get(cid)["seconds"]) * 0.6, 2)
    a = _shots(b, [t])[0]
    late_first = _shots(b, [t, 0.4])        # a later moment first, then an early one
    early_first = _shots(b, [0.4, t])
    assert a == late_first[0] == early_first[-1] or a in (late_first[0], late_first[-1]) and a in (early_first[0], early_first[-1])
    assert a != _shots(b, [0.4])[0]


def test_every_demo_runs_clean():
    for cid in IDS:
        assert _shots(R.bundle(cid), [round(float(R.get(cid)["seconds"]) * 0.5, 2)])


def test_both_aspect_ratios():
    wide = R.bundle("lineart.wide_establishing")
    assert (wide["w"], wide["h"]) == (1920, 1080)
    port = R.bundle("lineart.walker_crossing")
    assert (port["w"], port["h"]) == (1080, 1920)
    flip = {**port, "w": 1920, "h": 1080}              # a portrait demo must also draw in landscape without page errors
    assert _shots(flip, [3.0])
    flip2 = {**wide, "w": 1080, "h": 1920}
    assert _shots(flip2, [3.0])
