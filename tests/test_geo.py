"""Maps, flags and borders from real data (motion/templates/fxgeo.js, factory/geo.py, motion/recipes/geo.yaml):
the vendored data is complete, a country is found by code or by Turkish/English name, the projection puts Istanbul in
Turkey, the recipe cards are valid and reach the designer with the kit note, every demo renders without page errors
in both aspect ratios, frames are a pure function of t, the map's names are DOM text the layout lint sees, and the
history slice + licence ledger carry the Cliopatria credit. Everything runs offline."""
import gzip, json, os, shutil, subprocess, sys, tempfile

import pytest

from factory import geo, licence, recipes as R
from factory.config import ROOT

sys.path.insert(0, os.path.join(ROOT, "bin"))
GEO = os.path.join(ROOT, "assets", "geo")
CARDS = [c for c in R.cards() if c["family"] == "geo"]
FXGEO = os.path.join(ROOT, "motion", "templates", "fxgeo.js")


def _bundle(js, w=1080, h=1920, secs=5, lang="tr"):
    from factory import catalog
    return {"palette": catalog.PALETTE, "global_css": "", "words": [], "duration": secs, "w": w, "h": h, "lang": lang,
            "captions": {}, "scenes": [{"id": "s0", "start": 0, "end": secs, "hide_captions": True, "lines_t": [], "html": "",
                                        "css": catalog.BG, "js": R.PRELUDE + js}]}


@pytest.fixture
def tmp_path():   # the render server only serves the repo: bundles live under work/
    d = tempfile.mkdtemp(dir=os.path.join(ROOT, "work"), prefix="test_geo_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


def _shots(b, times, d, lint=False):
    import htmlmotion
    p = os.path.join(d, "b.json")
    json.dump(b, open(p, "w"))
    out = tempfile.mkdtemp(dir=d)
    r = htmlmotion.shots(p, times, out, lint=lint)
    return (r[0], r[1], json.load(open(r[2]))) if lint else r


def _node(script):
    """Run fxgeo.js headless in node with the vendored d3-geo / topojson / data (no DOM: lookups, fitting, rings)."""
    pre = r"""
const Module = require('module'), path = require('path'), fs = require('fs');
const G0 = %r, V = path.join(G0, 'vendor');
const orig = Module._resolveFilename;
Module._resolveFilename = function (r, ...a) { return orig.call(this, r === 'd3-array' ? path.join(V, 'd3-array.min.js') : r, ...a); };
global.window = global; global.FX = {};
global.d3 = require(path.join(V, 'd3-geo.min.js')); global.topojson = require(path.join(V, 'topojson-client.min.js'));
require(%r);
const J = (f) => JSON.parse(fs.readFileSync(path.join(G0, f), 'utf8'));
FX.geo.language = "tr";
const G = FX.geo.init(J('countries.json'), J('cities.json'), {'110m': J('countries-110m.json'), '50m': J('countries-50m.json')});
const inside = (pt, ring) => { let c = false; for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) { const [xi, yi] = ring[i], [xj, yj] = ring[j]; if ((yi > pt[1]) !== (yj > pt[1]) && pt[0] < (xj - xi) * (pt[1] - yi) / (yj - yi) + xi) c = !c; } return c; };
""" % (GEO, FXGEO)
    p = subprocess.run(["node", "-e", pre + script], capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr[-800:]
    return json.loads(p.stdout)


# ------------------------------------------------------------------ data

def test_vendored_data_is_complete():
    rows = geo.countries()
    assert len(rows) > 200 and all(r["tr"] and r["en"] and len(r["iso2"]) == 2 and len(r["iso3"]) == 3 and r["num"] for r in rows)
    for f in ("countries-110m.json", "countries-50m.json", "cities.json", "countries.json", "build_countries.py"):
        assert os.path.getsize(os.path.join(GEO, f)) > 1000, f
    for lib in ("d3-geo.min.js", "d3-array.min.js", "topojson-client.min.js"):
        assert os.path.getsize(os.path.join(GEO, "vendor", lib)) > 5000
    flags = os.listdir(os.path.join(GEO, "flags"))
    assert len(flags) >= 250 and "tr.svg" in flags
    assert [r["iso2"] for r in rows if not geo.flag_path(r["iso2"])] == []   # every country on the map has a flag
    topo = json.load(open(os.path.join(GEO, "countries-50m.json")))
    assert topo["type"] == "Topology" and len(topo["objects"]["countries"]["geometries"]) > 200


def test_third_party_records_the_sources():
    txt = open(os.path.join(ROOT, "THIRD_PARTY.md"), encoding="utf-8").read()
    for needle in ("world-atlas", "Natural Earth", "flag-icons", "d3-geo", "topojson-client", "Cliopatria", "CC BY 4.0"):
        assert needle in txt, needle


def test_country_lookup_by_code_and_by_turkish_or_english_name():
    for q in ("TR", "tr", "TUR", "tur", "792", "Türkiye", "TURKIYE", "türkiye", "Turkey", "turkiye"):
        assert geo.find(q)["iso2"] == "TR", q
    for q, iso in (("ABD", "US"), ("Amerika Birleşik Devletleri", "US"), ("United States", "US"), ("İngiltere", "GB"),
                   ("Birleşik Krallık", "GB"), ("Almanya", "DE"), ("Germany", "DE"), ("Çekya", "CZ"), ("Çek Cumhuriyeti", "CZ"),
                   ("Kuzey Makedonya", "MK"), ("Kosova", "XK"), ("Güney Kore", "KR"), ("İSVİÇRE", "CH"), ("Fildişi Sahili", "CI")):
        assert geo.find(q)["iso2"] == iso, q
    assert geo.find("Atlantis") is None and geo.find("") is None
    assert geo.name("DE", "tr") == "Almanya" and geo.name("DE", "en") == "Germany" and geo.name("Nowhere") == "Nowhere"
    assert geo.fold("İSTANBUL ığdır") == "istanbul igdir"


def test_js_lookup_matches_python_and_cities_resolve():
    out = _node("""
const q = ['TR', 'tur', '792', 'Türkiye', 'Turkey', 'ABD', 'İngiltere', 'Atlantis'].map((x) => { const c = G.find(x); return c ? c.iso2 : null; });
const p = G.place('İstanbul'), c = G.place('Fransa'), pt = G.place([41, 29]), o = G.place({lat: 1, lon: 2, label: 'x'});
let threw = false; try { G.place('Zzyzx'); } catch (e) { threw = true; }
console.log(JSON.stringify({q, p: [p.kind, p.lat, p.lon, p.label], c: [c.kind, c.rec.iso2], pt: pt.kind, o: o.label, threw, name: G.name('DE', 'tr'), fold: G.fold('İSTANBUL')}));
""")
    assert out["q"] == ["TR", "TR", "TR", "TR", "TR", "US", "GB", None]
    assert out["p"][0] == "city" and abs(out["p"][1] - 41.0) < 0.1 and out["c"] == ["country", "FR"] and out["pt"] == "point"
    assert out["o"] == "x" and out["threw"] and out["name"] == "Almanya" and out["fold"] == "istanbul"


# ------------------------------------------------------------------ projection and rings

def test_projection_puts_istanbul_inside_turkey_and_not_in_greece():
    out = _node("""
const box = {x: 50, y: 230, w: 980, h: 1240};
const res = {};
for (const kind of ['mercator', 'equirect', 'naturalEarth', 'globe']) {
  const cam = G.fit(kind, 'Türkiye', box), P = G.project(kind, cam, box, 1080, 1920);
  const rings = FX.geo.countryRings('TR', {detail: '50m'}).map((r) => r.map(([la, lo]) => P([lo, la])));   // Thrace and Anatolia are two rings
  const hit = (pt) => rings.some((r) => inside(pt, r));
  const ci = G.place('İstanbul'), ist = P([ci.lon, ci.lat]), ank = P([32.86, 39.93]), ath = P([23.73, 37.98]);
  res[kind] = {ist: hit(ist), ank: hit(ank), ath: hit(ath), onBox: ank[0] > box.x && ank[0] < box.x + box.w && ank[1] > box.y && ank[1] < box.y + box.h};
}
const ist = G.place('İstanbul'), cn = G.place('Çanakkale');
res.ist = [G.contains('TR', ist.lat, ist.lon), G.contains('Almanya', ist.lat, ist.lon), G.contains('GR', 37.98, 23.73), G.contains('TR', 39.93, 32.86)];
res.coast = [G.contains('TR', cn.lat, cn.lon)];
res.own = FX.geo._d.cities.filter((c) => !G.contains(c.iso2, c.lat, c.lon)).map((c) => c.en);
console.log(JSON.stringify(res));
""")
    for kind in ("mercator", "equirect", "naturalEarth", "globe"):
        assert out[kind]["ist"] and out[kind]["ank"] and not out[kind]["ath"] and out[kind]["onBox"], (kind, out[kind])
    assert out["ist"] == [True, False, True, True] and out["coast"] == [True]
    assert set(out["own"]) <= {"Lisbon", "Jerusalem"}, out["own"]   # every table city sits inside its own country's 50 m shape (two coastal/disputed exceptions)


def test_country_rings_for_the_3d_kit():
    out = _node("""
const tr = FX.geo.countryRings('TR', {detail: '50m'}), simp = FX.geo.countryRings('TR', {detail: '50m', simplify: 0.1});
const all = FX.geo.countryRings('all');
const pts = (rs) => rs.reduce((n, r) => n + r.length, 0);
console.log(JSON.stringify({n: tr.length, closed: tr.every((r) => r[0][0] === r[r.length - 1][0] && r[0][1] === r[r.length - 1][1]),
  lat: tr.every((r) => r.every(([la, lo]) => la > 35 && la < 43 && lo > 25 && lo < 45)), full: pts(tr), simp: pts(simp), all: all.length,
  hasUS: all.some((c) => c.iso === 'US' && c.rings.length > 5)}));
""")
    assert out["n"] >= 2 and out["closed"] and out["lat"]            # [lat, lon], inside Turkey's box
    assert out["simp"] < out["full"] * 0.6 and out["all"] > 150 and out["hasUS"]


# ------------------------------------------------------------------ recipe cards and loading

def test_cards_are_complete_and_carry_the_kit_note():
    assert 5 <= len(CARDS) <= 8 and R.problems(CARDS) == []
    assert R.FAMILIES["geo"] == {"tr": "Harita ve bayrak", "en": "Maps and flags"}
    ids = {c["id"] for c in CARDS}
    assert {"geo.map_highlight", "geo.route", "geo.fly", "geo.flag_row", "geo.choropleth"} <= ids
    for c in CARDS:
        assert "FX.geo" in c["demo"] and "Math.random" not in c["demo"] and "Date" not in c["demo"]
        assert "FX.geo" in c["call"] or "g." in c["call"]
    txt = R.card_text(["geo.route", "geo.map_highlight"])
    assert txt.startswith("GEO KIT") and txt.count("GEO KIT") == 1 and "RECIPE geo.route" in txt and "[lat, lon]" in txt
    assert "GEO KIT" not in R.card_text(["data.bar_chart"]) and "geo.route" in R.index("en", "geo")
    assert len(open(os.path.join(R.SRC, "geo_note.md"), encoding="utf-8").read().splitlines()) < 60


def test_shell_loads_the_geo_kit_only_for_geo_scenes():
    src = open(os.path.join(ROOT, "motion", "templates", "explainer_shell.html"), encoding="utf-8").read()
    assert "motion/templates/fxgeo.js" in src and "FX\\.geo\\b" in src and "assets/geo/vendor/d3-geo.min.js" in src
    assert subprocess.run(["node", "--check", FXGEO]).returncode == 0
    code = open(FXGEO, encoding="utf-8").read()
    assert "Math.random" not in code and "Date.now" not in code and "performance.now" not in code
    assert "http://" not in code.replace("http://www.w3.org/2000/svg", "") and "https://" not in code


# ------------------------------------------------------------------ rendering

def _history_ready():
    return os.path.exists(geo._cache_file())


@pytest.mark.parametrize("cid", [c["id"] for c in CARDS])
def test_demos_render_in_both_aspects(cid, tmp_path):
    from PIL import Image
    if cid == "geo.history" and not _history_ready():
        pytest.skip("Cliopatria not cached (first use downloads it once)")
    secs = float(R.get(cid)["seconds"])
    for w, h in ((1080, 1920), (1920, 1080)):
        b = R.bundle(cid)
        b["w"], b["h"] = w, h
        pngs, errs = _shots(b, [round(secs * 0.85, 2)], str(tmp_path))
        assert pngs and not errs, (cid, w, errs)
        lo, hi = Image.open(pngs[0]).convert("L").getextrema()
        assert hi - lo > 60, f"{cid} {w}x{h}: a flat frame"


def test_frames_are_a_pure_function_of_t(tmp_path):
    """Same t twice, and after other frames in any order (a flying camera, a route, pins and a flag with a wave)."""
    js = ("const g = FX.geo.map(tl, root, T, {region: 'Türkiye', highlight: ['TR']}); g.pin(1.2, 'Ankara'); g.fly(2.0, {to: 'Yunanistan', dur: 1.4});"
          "g.route(3.6, ['Atina', 'Roma'], {dur: 1}); FX.geo.flag(tl, root, 0.5, 'GR', {wave: true, y: 300, w: 200});")
    for w, h in ((1080, 1920), (1920, 1080)):
        bb = _bundle(js, w, h, 5.5)
        one, e1 = _shots(bb, [2.7], str(tmp_path))
        many, e2 = _shots(bb, [4.4, 0.8, 2.7, 1.9, 3.3], str(tmp_path))
        again, e3 = _shots(bb, [1.9], str(tmp_path))
        assert not (e1 or e2 or e3), (e1, e2, e3)
        same = lambda p, q: open(p, "rb").read() == open(q, "rb").read()
        assert same(one[0], next(p for p in many if p.endswith("002.70.png")))
        assert same(again[0], next(p for p in many if p.endswith("001.90.png")))


def test_map_text_is_dom_text_inside_the_safe_area(tmp_path):
    js = ("const g = FX.geo.map(tl, root, T, {region: ['Türkiye', 'Yunanistan']}); g.highlight(0.5, ['Türkiye']); g.pin(0.8, 'İstanbul');"
          "g.choropleth(1.0, {values: {TR: 85, GR: 10.4}, legend: {title: 'Nüfus'}});")
    for w, h in ((1080, 1920), (1920, 1080)):
        pngs, errs, lint = _shots(_bundle(js, w, h, 4), [3.2], str(tmp_path), lint=True)
        assert not errs
        boxes = next(iter(lint.values()))["boxes"]
        texts = {x["text"].split("\n")[0] for x in boxes}
        assert {"Türkiye", "İstanbul", "Nüfus"} <= texts, texts
        for x in boxes:
            assert x["x"] >= 0 and x["x"] + x["w"] <= w and x["y"] >= 0 and x["y"] + x["h"] <= h, x
            if h > w and x["text"] in ("Türkiye", "İstanbul"):
                assert x["y"] >= 165 and x["y"] + x["h"] <= 1505 and x["size"] >= 30, x   # readable on a phone, off the caption band


def test_unknown_place_is_a_page_error_not_a_wrong_map(tmp_path):
    pngs, errs = _shots(_bundle("FX.geo.map(tl, root, T, {region: 'Zzyzx'});", 1080, 1920, 2), [1.0], str(tmp_path))
    assert errs and any("unknown" in e.lower() for e in errs)


def test_flag_for_every_code_and_a_missing_flag_is_a_plain_card(tmp_path):
    js = "FX.geo.flag(tl, root, 0.1, 'TR', {x: 300, y: 500, w: 300}); FX.geo.flag(tl, root, 0.1, 'ZZ', {x: 700, y: 500, w: 300, label: false});"
    pngs, errs, lint = _shots(_bundle(js, 1080, 1920, 2), [1.5], str(tmp_path), lint=True)
    assert "ZZ" in {x["text"] for x in next(iter(lint.values()))["boxes"]}   # a code card, never a wrong flag
    print(errs)
    assert errs and all("ZZ" in e or "404" in e for e in errs)


# ------------------------------------------------------------------ history and the licence ledger

def test_history_build_drops_relations_and_keeps_closed_rings(monkeypatch):
    """The Douglas-Peucker pass used to collapse every closed ring to a line: half the dataset vanished."""
    circle = [[round(10 + 3 * __import__("math").cos(i / 20 * 6.2832), 4), round(40 + 3 * __import__("math").sin(i / 20 * 6.2832), 4)] for i in range(21)]
    circle[-1] = circle[0]
    feat = lambda name, a, b, typ="POLITY": {"properties": {"Name": name, "FromYear": a, "ToYear": b, "Wikipedia": name, "Type": typ},
                                            "geometry": {"type": "Polygon", "coordinates": [circle]}}
    raw = {"features": [feat("Ottoman Empire", 1400, 1500), feat("(Vassalage of Wallachia to Ottoman Empire)", 1400, 1500),
                        feat("(Kingdom of France)", 1400, 1500, "RELATION"), feat("Byzantine Empire", 1300, 1453),
                        {"properties": {"Name": "Nowhere", "FromYear": 1, "ToYear": 2}, "geometry": None}]}
    data = geo.build_history(raw)
    assert [x["name"] for x in data] == ["Ottoman Empire", "Byzantine Empire"]
    ring = data[0]["polygons"][0][0]
    assert len(ring) >= 8 and ring[0] == ring[-1]
    assert [x["name"] for x in geo.polities_in(1453, data)] == ["Ottoman Empire", "Byzantine Empire"]
    assert geo.polity_at("osmanli", 1453, data) is None and geo.polity_at("Ottoman", 1453, data)["name"] == "Ottoman Empire"
    assert geo.polity_at("Byzantine Empire", 1490, data)["name"] == "Byzantine Empire"    # 37 years off: near enough
    assert geo.polity_at("Byzantine Empire", 1600, data) is None                           # 147 years off: no wrong era
    d = tempfile.mkdtemp(dir=os.path.join(ROOT, "work"), prefix="test_geo_")
    try:
        monkeypatch.setattr(geo, "CACHE", d)
        p = geo.year_slice(1453, data)
        j = json.load(open(p))
        assert j["year"] == 1453 and len(j["polities"]) == 2 and "CC BY 4.0" in j["credit"] and "Cliopatria" in j["credit"]
        assert geo.year_slice(1453, None) == p                                              # cached: no dataset needed the second time
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_year_maps_put_the_cliopatria_credit_in_the_ledger():
    js = "const g = FX.geo.map(tl, root, T, {region: 'Anadolu', year: 1453});"
    assert geo.years_in(js) == [1453] and geo.years_in("const year = 1453;") == [] and geo.years_in("FX.geo.map(tl, root, T, {year: -500, region: 'x'})") == [-500]
    rows = geo.ledger(js)
    need = licence.required(rows)
    assert len(need) == 1 and "CC BY 4.0" in need[0]["licence"] and need[0]["url"].startswith("https://github.com/Seshat")
    assert not licence.missing(rows) and "Cliopatria" in licence.block(rows, "tr") and "Cliopatria" in licence.block(rows, "en")
    plain = geo.ledger("FX.geo.map(tl, root, T, {region: 'Türkiye'})")
    assert plain and not licence.required(plain) and not licence.missing(plain) and geo.ledger("FX.pop(tl, el, 0)") == []
    plan = {"scenes": [{"id": "a", "js": js, "html": "", "css": ""}]}
    assert any(r["credit"] for r in geo.ledger(licence._plan_text(plan)))


def test_history_map_renders_with_a_slice_and_without_one_draws_coast_only(tmp_path, monkeypatch):
    """With a slice: polity shapes. Without: no polity, no modern border, and a console error that names the fix."""
    from PIL import Image
    js = "const g = FX.geo.map(tl, root, T, {region: ['Türkiye', 'Yunanistan'], year: 1453, labels: false}); g.highlight(1, ['Osmanlı']);"
    if _history_ready():
        b = _bundle(js, 1080, 1920, 3)
        geo.prepare(js)
        pngs, errs = _shots(b, [2.6], str(tmp_path))
        assert pngs and not errs
    b = _bundle(js.replace("1453", "1111"), 1080, 1920, 3)   # a year nobody prepared: no slice file
    pngs, errs = _shots(b, [2.6], str(tmp_path))
    assert pngs and any("no historical borders for 1111" in e for e in errs)
    # the map still draws (land, no wrong-era border)
    lo, hi = Image.open(pngs[0]).convert("L").getextrema()
    assert hi - lo > 20
