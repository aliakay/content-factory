"""The texture kit (FX.texture, F26), the paper base under translucent drawings (F27), the declarative build-in (F37) and
the ambience particles (F43) — ported from AI-Video-Factory into motion/templates/fxlib.js.

Everything here renders the real shell in headless Chromium (free): a texture is only right if the still says so, and a
drawn layer is only safe if the layout lint keeps reading the same text boxes and the same contrast.
"""
import hashlib, json, os, re, shutil, tempfile

import pytest

from factory import capabilities, filmstyles, layoutlint, recipes as R, typography
from factory.config import ROOT

FX = os.path.join(ROOT, "motion", "templates", "fxlib.js")
KINDS = ["paper", "watercolor", "chalk", "halftone", "hatching", "grain", "scanlines"]


def _bundle(js, dur=4, css=None):
    from factory import catalog
    return {"palette": catalog.PALETTE, "global_css": "", "words": [], "duration": dur, "w": 1080, "h": 1920, "lang": "en",
            "captions": {}, "scenes": [{"id": "demo", "start": 0, "end": dur, "hide_captions": True, "lines_t": [],
                                        "html": "", "css": css or catalog.BG, "js": R.PRELUDE + js}]}


_TMP = {"dir": None}


@pytest.fixture(scope="module", autouse=True)
def _cleanup():
    """The stills of a lint test must outlive the render (the layout lint samples the pixels around each text box)."""
    yield
    if _TMP["dir"]:
        shutil.rmtree(_TMP["dir"], ignore_errors=True)
        _TMP["dir"] = None


def _render(js, times=(1.6,), lint=False, dur=4, css=None):
    """Stills of a one-scene bundle -> (png paths, js errors, lint payload or None)."""
    os.makedirs(R.DIR, exist_ok=True)
    if _TMP["dir"] is None:
        _TMP["dir"] = tempfile.mkdtemp(prefix="_texture_", dir=R.DIR)
    d = tempfile.mkdtemp(dir=_TMP["dir"])
    bp = os.path.join(d, "b.json")
    json.dump(_bundle(js, dur, css), open(bp, "w"))
    out = os.path.join(d, "o")
    os.makedirs(out)
    hm = R._hm()
    if lint:
        paths, errs, lp = hm.shots(bp, list(times), out, lint=True)
        return paths, errs, json.load(open(lp))
    paths, errs = hm.shots(bp, list(times), out)
    return paths, errs, None


def _px(path, xy):
    from PIL import Image
    return Image.open(path).convert("RGB").getpixel(xy)


def _distinct(path, box):
    from PIL import Image
    return len(Image.open(path).convert("RGB").crop(box).getcolors(maxcolors=1 << 16) or [])


GROUND = "D('', 'inset:0;background:#f4eee2');\n"


def test_the_kit_has_the_new_recipes():
    js = open(FX, encoding="utf-8").read()
    names = set(re.findall(r"FX\.(\w+) = ", js))
    assert {"texture", "textureFor", "textureCanvas", "textureUrl", "texNoise", "texFbm", "paperBase", "paperOf",
            "paperShare", "build", "buildPlan", "ambience", "ambienceFrame", "pace"} <= names
    for dead in ("Math.random", "Date.now", "performance.now", "requestAnimationFrame", "new Date"):
        assert dead not in js


def test_cards_are_valid_and_cover_the_texture_family():
    assert "texture" in R.FAMILIES
    mine = [c for c in R.cards() if c["family"] == "texture"]
    assert len(mine) >= 8 and R.problems(mine) == []
    assert {"texture.paper", "texture.watercolor", "texture.chalk", "texture.halftone", "texture.hatching",
            "texture.grain", "texture.scanlines", "texture.paper_base"} <= {c["id"] for c in mine}
    for cid in ("rhythm.build_in", "rhythm.pace_cap"):
        assert R.get(cid) and "FX." in R.get(cid)["call"]
    for cid in ("living.ambience_weather", "living.ambience_motes", "living.ambience_fog", "living.ambience_flicker",
                "living.ambience_confetti"):
        assert R.get(cid) and "FX.ambience" in R.get(cid)["call"]
    # the designer gets the whole card, in both languages
    txt = R.card_text(["texture.paper", "texture.paper_base"], "tr")
    assert "RECIPE texture.paper" in txt and "FX.texture" in txt and "FX.paperBase" in txt


def test_every_styles_texture_is_the_one_its_bible_describes():
    """data/film_styles.json (the bible the designer reads) and fxlib.js (what a scene calls) must agree."""
    styles = {s["id"]: s.get("texture") or "" for s in capabilities._film_styles() if not s["id"].startswith("own_")}
    js = open(FX, encoding="utf-8").read()
    block = re.search(r"FX\.STYLE_TEXTURE = \{(.*?)\};", js, re.S).group(1)
    js_map = dict(re.findall(r"(\w+):\s*\"(\w*)\"", block))
    assert js_map == {k: v for k, v in styles.items() if v}, (js_map, styles)
    for sid in ("riso_print", "ink_wash", "cut_paper", "blueprint", "archive_film", "hologram_hud", "woodcut"):
        assert styles[sid] in KINDS, sid
        assert filmstyles.texture(sid) == styles[sid]
    assert filmstyles.texture("swiss_grid") == "" and filmstyles.texture("nope") == ""


def test_the_style_bible_and_the_preview_bundle_carry_the_texture():
    bible = capabilities.CAPS["style.riso_print"]["designer"]
    assert "FX.texture(root, 'halftone'" in bible
    assert "TEXTURE" not in capabilities.CAPS["style.swiss_grid"]["designer"]
    b, _ = filmstyles._bundle({"seconds": 3})
    filmstyles.with_texture(b, "ink_wash")
    assert b["scenes"][0]["js"].startswith("FX.texture(root, 'watercolor'")
    b, _ = filmstyles._bundle({"seconds": 3})
    filmstyles.with_texture(b, "swiss_grid")   # a pack with no medium keeps its JS untouched
    assert not b["scenes"][0]["js"].startswith("FX.texture")


@pytest.mark.parametrize("kind", KINDS)
def test_the_layer_mounts_over_the_scene_and_the_lint_cannot_see_it(kind):
    """The overlay carries no text, is aria-hidden and marked data-tex; the layout lint's readings stay the same."""
    probe = ("const l = root.querySelector('[data-tex]');"
             "D((l ? l.dataset.tex + ' aria=' + l.getAttribute('aria-hidden') + ' kids=' + l.children.length + ' text='"
             " + JSON.stringify((l.textContent || '').trim()) : 'MISSING'), 'left:80px;top:300px;font:700 46px Inter Tight;color:#141a24');")
    text = "D('RISO BASKI', 'left:80px;top:420px;font:900 110px Inter Tight;color:#141a24');"
    js = GROUND + text + f"FX.texture(root, '{kind}', {{dark: false}});" + probe
    paths, errs, lint = _render(js, lint=True)
    assert errs == []
    boxes = [b for shot in lint.values() for b in shot["boxes"]]
    probe_box = next(b for b in boxes if "aria=" in b["text"])
    assert probe_box["text"] == f'{kind} aria=true kids=0 text=""'   # one bitmap, no text nodes, hidden from the a11y tree
    assert any(b["text"] == "RISO BASKI" for b in boxes)          # the scene's own text is still what the lint measures
    assert all(b["text"] != "" for b in boxes)


def test_a_texture_does_not_change_the_lints_findings():
    """Same still, with and without the overlay: same findings from the same text (a marginal grey line keeps it honest)."""
    scene = (GROUND +
             "D('MARGINAL GREY ON PAPER', 'left:80px;top:300px;font:900 96px Inter Tight;color:#9a9a9a');"
             "D('readable body line on the paper', 'left:80px;top:470px;font:600 44px Inter Tight;color:#3b3b3b');")
    plain_paths, errs0, plain = _render(scene, lint=True)
    plain_found = layoutlint.check(plain, "9:16") + typography.check(plain, "9:16")
    assert errs0 == [] and any(f["kind"] == "contrast" for f in plain_found)   # the scene really is a marginal one
    for kind in ("paper", "grain", "halftone", "scanlines"):
        paths, errs, lint = _render(scene + f"FX.texture(root, '{kind}', {{dark: false}});", lint=True)
        found = layoutlint.check(lint, "9:16") + typography.check(lint, "9:16")
        assert errs == []
        assert [(f["kind"], f.get("text")) for f in found] == [(f["kind"], f.get("text")) for f in plain_found], kind


def test_texture_frames_are_a_pure_function_of_the_seed():
    """The same scene at the same t in a fresh page gives the same bytes; a different seed gives different pixels."""
    js = GROUND + "D('GRAIN', 'left:80px;top:300px;font:900 110px Inter Tight;color:#141a24');"
    a, errs_a, _ = _render(js + "FX.texture(root, 'grain', {dark: false, seed: 4});")
    b, errs_b, _ = _render(js + "FX.texture(root, 'grain', {dark: false, seed: 4});")
    c, errs_c, _ = _render(js + "FX.texture(root, 'grain', {dark: false, seed: 9});")
    assert errs_a == errs_b == errs_c == []
    hs = lambda p: hashlib.sha1(open(p, "rb").read()).hexdigest()
    assert hs(a[0]) == hs(b[0]) and hs(a[0]) != hs(c[0])
    plain, _, _ = _render(js)
    assert _distinct(plain[0], (60, 900, 1020, 1850)) < _distinct(a[0], (60, 900, 1020, 1850))


def test_the_paper_base_hides_the_room_behind_a_wash():
    """A translucent figure over a striped room: without the base the stripes show through the body."""
    js = ("D('', 'inset:0;background:repeating-linear-gradient(45deg,#1b2233 0 46px,#33456b 46px 92px)');"
          "const svg = FX.svg(root, 1080, 1920);"
          "const g = FX.el(svg, 'g', {transform: 'translate(360,520)'});"
          "FX.el(g, 'rect', {x: 0, y: 0, width: 420, height: 620, fill: 'rgba(0,120,191,0.55)'});"
          "BASE")
    plain, e1, _ = _render(js.replace("BASE", ""))
    paper, e2, _ = _render(js.replace("BASE", "FX.paperBase(svg, {color: '#f4eee2'});"))
    assert e1 == e2 == []
    body = (560, 900)
    inside = (420, 640, 730, 1040)                                 # strictly inside the washed rectangle
    assert _distinct(plain[0], inside) == 2                        # the two stripe tones show through the wash
    assert _distinct(paper[0], inside) == 1                        # one wash colour over paper, no room behind it
    r, g, b = _px(paper[0], body)
    assert abs(b - 207) < 12 and r < 130                            # blue wash over paper, not over the stripes
    assert _distinct(paper[0], (60, 60, 1020, 500)) == 2            # the room itself is untouched (still striped)


def test_an_opaque_drawing_gets_no_paper_and_shares_are_counted():
    """FX.paperShare decides whether a base is needed: a fully opaque drawing stays as it is."""
    js = ("const svg = FX.svg(root, 1080, 1920);"
          "const g = FX.el(svg, 'g', {});"
          "FX.el(g, 'rect', {x: 100, y: 100, width: 200, height: 200, fill: '#0078bf'});"
          "const w = FX.el(g, 'rect', {x: 400, y: 100, width: 200, height: 200, fill: 'rgba(0,120,191,0.55)'});"
          "D('opaque=' + FX.paperShare(svg).toFixed(2), 'left:80px;top:300px;font:700 46px Inter Tight;color:#fff');")
    paths, errs, lint = _render(js, lint=True)
    assert errs == []
    boxes = [b for shot in lint.values() for b in shot["boxes"]]
    box = next(b for b in boxes if "opaque=" in b["text"])
    assert box["text"] == "opaque=0.50"


def test_the_build_in_runs_in_order_and_fits_the_shot():
    js = ("const room = [D('', 'left:0;right:0;top:1180px;height:740px;background:#1b2233')];"
          "const furn = [D('', 'left:110px;top:900px;width:320px;height:220px;background:#3b4a6b')];"
          "const people = [D('', 'left:520px;top:700px;width:120px;height:420px;background:#e8dfc8')];"
          "const labels = [D('BUILT', 'left:90px;top:300px;font:900 84px Inter Tight;color:#f4efe6')];"
          "const r = FX.build(tl, T.start, [{els: room, kind: 'room'}, {els: furn, kind: 'object'}, "
          "{els: people, kind: 'person'}, {els: labels, kind: 'label'}], {dur: T.dur});"
          "D(r.plan.map((p) => p.kind[0] + p.at.toFixed(2)).join(' '), "
          "'left:60px;top:1560px;width:960px;font:600 34px Inter Tight;color:#9aa3b5');")
    paths, errs, lint = _render(js, times=(0.4, 0.7, 2.0), lint=True)
    assert errs == []
    box = next(b for shot in lint.values() for b in shot["boxes"] if b["text"].startswith("r0.15"))
    assert box["text"] == "r0.15 o0.30 p0.45 l0.80"   # the groups enter in order, 0.15/0.15/0.35 s apart


@pytest.mark.parametrize("cid", ["texture.paper", "texture.halftone", "texture.paper_base", "living.ambience_weather",
                                 "rhythm.build_in"])
def test_new_demos_render_without_page_errors(cid):
    if not os.path.isdir(os.path.join(ROOT, "motion", "node_modules")):
        pytest.skip("no motion/node_modules here")
    pngs, errs = R.check(cid)
    assert errs == [] and len(pngs) == 1
