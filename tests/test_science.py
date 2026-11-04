"""Maths and science scenes (t509): equations, plots and 3D spaces drawn by the motion engine (no Manim, no GPU)."""
import json, os, subprocess, sys, tempfile

import pytest

from factory import capabilities, catalog
from factory.config import FFMPEG, ROOT

MOTION = os.path.join(ROOT, "motion")
FXLIB = open(os.path.join(MOTION, "templates", "fxlib.js")).read()
SHELL = open(os.path.join(MOTION, "templates", "explainer_shell.html")).read()


def test_devices_techniques_and_demos_are_wired():
    for name in ("FX.tex = ", "FX.math = ", "FX.eqSteps = ", "FX.plot = ", "FX.space = ", "k.surface = ", "k.curve = ",
                 "k.arrow = ", "k.label = "):
        assert name in FXLIB, name
    assert "katex.min.js" in SHELL and "FX\\.(math|eqSteps|tex)" in SHELL
    assert '"katex"' in open(os.path.join(MOTION, "package.json")).read()
    for cid, fx in (("look.math", "FX.plot"), ("look.space3d", "FX.space")):
        assert fx in capabilities.get(cid)["designer"] and cid in catalog.DEMOS
    from factory import motiondesign
    assert "FX.eqSteps" in motiondesign.FX_DOC and "k.surface" in motiondesign.FX_DOC
    js = catalog._bundle("look.math")[0]["scenes"][0]["js"]
    assert "\\\\int_0" in js and "\\\\hl{" in js        # the JS source keeps its LaTeX backslashes


@pytest.mark.skipif(not os.path.isdir(os.path.join(MOTION, "node_modules", "katex")), reason="motion/ needs npm install")
def test_equation_plot_and_surface_render(tmp_path):
    js = """
FX.math(tl, root, 0, 'E = \\\\hl{mc^2}', {y: 300, size: 110, mark: 0.2});
FX.plot(tl, root, {box: [100, 520, 880, 560], x: [-3, 3, 1], y: [-1, 1, 0.5], at: 0, fns: [{f: Math.sin, at: 0, dur: 0.4}]});
const k = FX.space(root, T, {range: 3, turn: 0.2}); k.surface((x, y) => Math.cos(x) * Math.sin(y), {at: 0, dur: 0.3});"""
    b = {"palette": catalog.PALETTE, "global_css": "", "words": [], "duration": 1, "w": 1080, "h": 1920, "lang": "en",
         "captions": {}, "scenes": [{"id": "s", "start": 0, "end": 1, "hide_captions": True, "lines_t": [], "html": "",
                                     "css": catalog.BG, "js": js}]}
    os.makedirs(os.path.join(ROOT, "work", "tests"), exist_ok=True)
    with tempfile.TemporaryDirectory(dir=os.path.join(ROOT, "work", "tests")) as d:   # the renderer serves files under ROOT
        bp, out = os.path.join(d, "b.json"), os.path.join(d, "o.mp4")
        json.dump(b, open(bp, "w"))
        sys.path.insert(0, os.path.join(ROOT, "bin"))
        import htmlmotion
        r = htmlmotion._node(bp, out, 1, ["--opaque", "--scale=0.25"], 8)
        assert r.returncode == 0 and "page error" not in r.stderr and "katex" not in r.stderr.lower(), r.stderr[-400:]
        png = str(tmp_path / "f.png")
        subprocess.run([FFMPEG, "-v", "error", "-y", "-sseof", "-0.2", "-i", out, "-frames:v", "1", png], check=True)
    from PIL import Image
    im = Image.open(png).convert("RGB")
    w, h = im.size
    def lit(box, test):
        c = im.crop((int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h)))
        return sum(1 for x in range(c.width) for y in range(c.height) if test(c.getpixel((x, y))))
    ink = lambda p: min(p) > 170                                  # the equation's light ink
    accent = lambda p: p[0] > 180 and 120 < p[1] < 210 and p[2] < 120   # the highlighted mc², the sine curve
    assert lit((0.1, 0.12, 0.9, 0.2), ink) > 20 and lit((0.1, 0.12, 0.9, 0.2), accent) > 10
    assert lit((0.08, 0.27, 0.92, 0.57), accent) > 30
    violet = lambda p: p[2] > 140 and p[2] > p[1] + 40                 # the surface, coloured by height
    assert lit((0, 0.55, 1, 1), violet) > 200
