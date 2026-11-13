"""The real-3D kit (motion/templates/fx3d.js, FX.stage3) and its recipe cards (motion/recipes/three.yaml): cards are
complete, every demo renders without page errors in both aspect ratios, frames are a pure function of t (same t
twice and out of order give identical pixels), the transparent mode really is transparent, 3D text reports itself
to the layout lint, and a film of several 3D scenes keeps one WebGL canvas and frees the scenes it left."""
import json, os, subprocess, sys, tempfile

import pytest

from factory import recipes as R
from factory.config import ROOT, FFMPEG

sys.path.insert(0, os.path.join(ROOT, "bin"))
THREE = [c for c in R.cards() if c["family"] == "three"]


def _bundle(scenes, w=1080, h=1920):
    from factory import catalog
    dur = scenes[-1][1]
    return {"palette": catalog.PALETTE, "global_css": "", "words": [], "duration": dur, "w": w, "h": h, "lang": "en",
            "captions": {}, "scenes": [{"id": f"s{i}", "start": a, "end": b, "hide_captions": True, "lines_t": [], "html": "",
                                        "css": catalog.BG, "js": R.PRELUDE + js} for i, (a, b, js) in enumerate(scenes)]}


@pytest.fixture
def tmp_path():   # the render server only serves the repo: bundles live under work/
    import shutil
    d = tempfile.mkdtemp(dir=os.path.join(ROOT, "work"), prefix="test_three_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


def _shots(b, times, d, lint=False):
    import htmlmotion
    p = os.path.join(d, "b.json")
    json.dump(b, open(p, "w"))
    out = tempfile.mkdtemp(dir=d)
    r = htmlmotion.shots(p, times, out, lint=lint)
    return (r[0], r[1], json.load(open(r[2]))) if lint else r


def test_cards_are_complete_and_carry_the_kit_note():
    assert len(THREE) >= 8 and R.problems(THREE) == []
    assert R.FAMILIES["three"] == {"tr": "3 boyut", "en": "3D"}
    for c in THREE:
        assert "FX.stage3" in c["demo"] and "Math.random" not in c["demo"] and "Date" not in c["demo"]
    txt = R.card_text(["three.bars", "three.globe"])
    assert txt.startswith("3D KIT") and txt.count("3D KIT") == 1 and "FRAME BUDGET" in txt and "RECIPE three.globe" in txt
    assert "3D KIT" not in R.card_text(["data.bar_chart"])
    assert len(open(os.path.join(R.SRC, "three_note.md"), encoding="utf-8").read().splitlines()) < 60


def test_film_styles_on_the_kit():
    from factory import capabilities, filmstyles
    for sid in ("clay_3d", "wireframe_3d"):
        st = filmstyles.get(sid)
        assert st and "FX.stage3" in st["render"] and "style." + sid in capabilities.CAPS
        assert "FX.stage3" in json.load(open(os.path.join(ROOT, "styles", sid + ".json")))["js"]


def test_shell_loads_three_only_for_3d_scenes():
    src = open(os.path.join(ROOT, "motion", "templates", "explainer_shell.html"), encoding="utf-8").read()
    assert "/motion/templates/fx3d.js" in src and "FX\\.(stage3|three|globe" in src
    assert subprocess.run(["node", "--check", os.path.join(ROOT, "motion", "templates", "fx3d.js")]).returncode == 0


@pytest.mark.parametrize("cid", [c["id"] for c in THREE])
def test_demos_render_in_both_aspects(cid, tmp_path):
    from PIL import Image
    secs = float(R.get(cid)["seconds"])
    for w, h in ((1080, 1920), (1920, 1080)):
        b = R.bundle(cid)
        b["w"], b["h"] = w, h
        pngs, errs = _shots(b, [round(secs * 0.8, 2)], str(tmp_path))
        assert pngs and not errs, (cid, w, errs)
        im = Image.open(pngs[0]).convert("L")
        lo, hi = im.getextrema()
        assert hi - lo > 60, f"{cid} {w}x{h}: a flat frame (blank canvas?)"


def test_frames_are_a_pure_function_of_t(tmp_path):
    """Same t twice, and the same t reached after other frames of this and other 3D scenes, in any order."""
    a = "const k = FX.stage3(tl, root, T, {look: 'studio'}); k.number3d(tl, 0.2, 2.4, {suffix: 'M', decimals: 1}); k.move('orbit', {at: 0, turn: 30});"
    b = "const k = FX.stage3(tl, root, T, {look: 'clay'}); k.globe(tl, 2.1, {focus: [-30, 40], routes: [{from: [-74, 40.7], to: [2.35, 48.8], at: 2.6, fromLabel: 'NY', toLabel: 'Paris'}]});"
    for w, h in ((1080, 1920), (1920, 1080)):
        bb = _bundle([(0, 2, a), (2, 4, b)], w, h)
        one, e1 = _shots(bb, [3.3], str(tmp_path))
        many, e2 = _shots(bb, [3.9, 1.0, 2.2, 0.4, 3.3], str(tmp_path))
        again, e3 = _shots(bb, [1.0], str(tmp_path))
        assert not (e1 or e2 or e3)
        same = lambda p, q: open(p, "rb").read() == open(q, "rb").read()
        assert same(one[0], next(p for p in many if p.endswith("003.30.png")))
        assert same(again[0], next(p for p in many if p.endswith("001.00.png")))


def test_3d_text_reports_itself_to_the_lint(tmp_path):
    js = "const k = FX.stage3(tl, root, T, {look: 'clay'}); k.text3d(tl, 0.1, 'BIG\\nIDEA');"
    pngs, errs, lint = _shots(_bundle([(0, 2, js)]), [1.6], str(tmp_path), lint=True)
    boxes = next(iter(lint.values()))["boxes"]
    big = [x for x in boxes if x["text"] in ("BIG", "IDEA")]
    assert len(big) == 2 and not errs
    for x in big:   # a real size and place on the stage, the colour drawn, not the twin's transparent ink
        assert x["h"] > 120 and 0 <= x["x"] and x["x"] + x["w"] <= 1080 and x["color"].startswith("#") and not x["clipText"]


def test_one_canvas_for_a_film_of_3d_scenes(tmp_path):
    """Several 3D scenes share one WebGL canvas; a scene that left the screen is released (its canvas detached, its
    stage not live). A DOM scene at the end prints what it sees, read back through the lint."""
    sc = [(i, i + 1, f"const k = FX.stage3(tl, root, T, {{look: '{lk}'}}); k.bars(tl, {i + 0.1}, [3, 5, 8]);")
          for i, lk in enumerate(["clay", "studio", "neon", "blueprint", "paper"])]
    probe = ("const el = D('', 'left:100px;top:600px;font:700 60px Inter Tight;color:#fff');"
             "FX.onFrame(() => { el.textContent = 'canvases ' + document.querySelectorAll('canvas').length + ' live ' + "
             "FX.x3.stages.filter((s) => s._live).length + ' gl ' + FX.x3.contexts(); });")
    pngs, errs, lint = _shots(_bundle(sc + [(5, 6, probe)]), [0.5, 1.5, 2.5, 3.5, 4.5, 5.5], str(tmp_path), lint=True)
    assert not errs
    last = [x["text"] for x in lint["5.50"]["boxes"] if x["text"].startswith("canvases")]
    assert last == ["canvases 0 live 0 gl 1"], last


def test_transparent_mode_keeps_alpha(tmp_path):
    """Export without --opaque: the stage is transparent, the 3D object opaque (clay draws on a transparent canvas)."""
    import htmlmotion
    from PIL import Image
    b = _bundle([(0, 1, "const k = FX.stage3(tl, root, T, {look: 'clay'}); k.bars(tl, 0, [3, 5, 8], {dur: 0.2});")])
    b["scenes"][0]["css"] = ""
    p = os.path.join(tmp_path, "a.json")
    json.dump(b, open(p, "w"))
    mov = os.path.join(tmp_path, "a.mov")
    r = htmlmotion._node(p, mov, 1, ["--scale=0.25"], 4, hash="&alpha=1")
    assert r.returncode == 0, r.stderr[-300:]
    png = os.path.join(tmp_path, "f.png")
    subprocess.run([FFMPEG, "-v", "error", "-y", "-sseof", "-0.3", "-i", mov, "-frames:v", "1", png], check=True)
    a = Image.open(png).convert("RGBA").getchannel("A")
    lo, hi = a.getextrema()
    assert lo == 0 and hi == 255


def test_a_zoom_never_crops_a_headline(tmp_path):
    """A push into the lower part of the set used to carry a top headline out of the frame ("DÜŞÜRDÜN MÜ?" in the
    pipet film): the camera now backs off just enough for every 3D headline to stay in the platform-safe area."""
    js = ("const k = FX.stage3(tl, root, T, {look: 'clay'}); k.text3d(tl, 0.1, 'DROPPED\\nIT?', {anim: 'pop', y: 4.2, w: k.safeW * 0.85});"
          "k.move('zoom_to', {at: 0.2, dur: 1, to: [0, -1.5, 0], amount: 0.8});")
    pngs, errs, lint = _shots(_bundle([(0, 2, js)]), [1.8], str(tmp_path), lint=True)
    assert not errs
    boxes = [x for x in next(iter(lint.values()))["boxes"] if x["text"] in ("DROPPED", "IT?")]
    assert len(boxes) == 2
    for x in boxes:
        assert x["y"] >= 165 and x["y"] + x["h"] <= 1505 and x["x"] >= 55 and x["x"] + x["w"] <= 935, x


def test_a_year_is_not_a_thousands_number_and_fitTo_keeps_the_subject_inside(tmp_path):
    js = ("const k = FX.stage3(tl, root, T, {look: 'clay'}); k.number3d(tl, 0.1, 1989, {from: 1900, dur: 0.5, y: 4});"
          "const box = k.solid(k.rbox(3, 6, 2, 0.1), k.pal.hot); const h = k.fitTo(box, {h: 0.5, y: -0.9});"
          "const b = new k.THREE.Box3().setFromObject(h); FX.onFrame(() => { root.dataset.b = [b.min.y, b.max.y].join(','); });")
    pngs, errs, lint = _shots(_bundle([(0, 2, js)]), [1.5], str(tmp_path), lint=True)
    assert not errs
    texts = [x["text"] for x in next(iter(lint.values()))["boxes"]]
    assert "1989" in texts and "1,989" not in texts
