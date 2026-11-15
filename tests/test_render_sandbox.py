"""The render page is sandboxed: scene code is written by models (the designer, the Lab working from third-party
text), so a page may load pictures, fonts and scripts of the repo but never the keys, and nothing leaves the machine.
Plus: an approved Lab card's helper reaches a real film just by being called (recipes.lab_helpers)."""
import json, os, subprocess

import pytest

from factory import recipes
from factory.config import ROOT

PROBE = """<!doctype html><html><body><script>
window.ready = (async () => {
  const out = {};
  for (const u of %s) {
    try { const r = await fetch(u); out[u] = r.status; } catch (e) { out[u] = "blocked"; }
  }
  console.error("PROBE " + JSON.stringify(out));
})();
window.render = () => {};
</script></body></html>"""


def test_a_scene_cannot_read_keys_or_reach_the_network(tmp_path):
    if not os.path.isdir(os.path.join(ROOT, "motion", "node_modules")):
        pytest.skip("no motion/node_modules here")
    urls = ["/.env", "/data/users.json", "/.git/HEAD", "/motion/templates/fxlib.js", "https://example.com/",
            "//example.com/x.png"]
    d = os.path.join(ROOT, "work", "tests")
    os.makedirs(d, exist_ok=True)
    page, out = os.path.join(d, "sandbox_probe.html"), str(tmp_path / "o.mp4")
    with open(page, "w", encoding="utf-8") as f:
        f.write(PROBE % json.dumps(urls))
    r = subprocess.run(["node", os.path.join(ROOT, "motion", "render.mjs"), page, out, "0.1", "10", "108", "192",
                        "--opaque"], capture_output=True, text=True, timeout=120)
    line = next((x for x in (r.stderr + r.stdout).splitlines() if "PROBE " in x), None)
    assert line, (r.stderr + r.stdout)[-600:]
    got = json.loads(line.split("PROBE ", 1)[1])
    assert got["/motion/templates/fxlib.js"] == 200          # the page still gets its own files
    assert got["/.env"] == 403 and got["/data/users.json"] == 403 and got["/.git/HEAD"] == 403
    assert got["https://example.com/"] == "blocked" and got["//example.com/x.png"] == "blocked"


def _lab(tmp_path, monkeypatch, status):
    cards, js = tmp_path / "cards", tmp_path / "js"
    cards.mkdir(), js.mkdir()
    (cards / "camera.lab_sway.yaml").write_text(
        "id: camera.lab_sway\nfamily: camera\nstatus: %s\nname: {tr: a, en: a}\nuse: {tr: a, en: a}\ncall: x\n"
        "timing: {tr: a, en: a}\npitfalls: {tr: [a], en: [a]}\nseconds: 2\ndemo: FX.lab.sway(tl, root, 0)\n" % status)
    (js / "camera.lab_sway.js").write_text("FX.lab.sway = (tl, root, at) => {};\n")
    monkeypatch.setattr(recipes, "LAB", str(cards))
    monkeypatch.setattr(recipes, "LAB_JS", str(js))
    recipes._cache.update(key=None, cards=None)


def test_an_approved_lab_helper_is_put_ahead_of_the_scene_that_calls_it(tmp_path, monkeypatch):
    _lab(tmp_path, monkeypatch, "active")
    got = recipes.lab_helpers("const k = FX.lab.sway(tl, root, T.start);")
    assert got.startswith("FX.lab = FX.lab || {};") and "FX.lab.sway = " in got
    assert recipes.lab_helpers("FX.pushIn(tl, root, 0)") == ""            # the usual scene pays nothing
    assert recipes.lab_helpers("FX.lab.other(tl)") == ""                  # a name no card registers
    recipes._cache.update(key=None, cards=None)


def test_a_candidate_helper_never_reaches_a_film(tmp_path, monkeypatch):
    _lab(tmp_path, monkeypatch, "candidate")
    assert recipes.lab_helpers("FX.lab.sway(tl, root, 0)") == ""
    assert "FX.lab.sway = " in recipes.bundle("camera.lab_sway")["scenes"][0]["js"]   # its own demo still gets it
    recipes._cache.update(key=None, cards=None)
