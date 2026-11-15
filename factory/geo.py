"""Maps and flags from real data: the Python side of motion/templates/fxgeo.js (FX.geo).

What lives here:
  - the country table (assets/geo/countries.json: ISO alpha-2/3, numeric id, Turkish + English names, label point) and a
    lookup that takes a code or a name in either language: `find("Türkiye")`, `find("tur")`, `find("792")`;
  - the historical borders (F29): Cliopatria (Seshat Global History Databank, CC BY 4.0) is fetched ONCE, on first use,
    simplified and cached under work/geo/ (about 10 MB gzipped); `year_slice(1500)` writes the polities of one year as a
    small JSON the page can load (/work/geo/history/1500.json). Rendering itself never touches the network;
  - the licence entries (`ledger(plan_text)`) the attribution ledger (factory/licence.py) adds for a film that uses
    FX.geo, so the publish description carries the Cliopatria credit line.

A scene asks for a year with `FX.geo.map(tl, root, T, {region: 'Anadolu', year: 1453})`. `prepare(text)` finds every
`year:` in scene code that uses FX.geo and writes those slices (a no-op when the dataset cannot be loaded: the page
then draws coastlines only, never a border of the wrong era).
"""
import gzip, json, os, re, unicodedata, urllib.request, zipfile

from .config import ROOT

GEO = os.path.join(ROOT, "assets", "geo")
CACHE = os.path.join(ROOT, "work", "geo")
HISTORY = {
    "version": "v0.2.1",
    "url": "https://github.com/Seshat-Global-History-Databank/cliopatria/raw/v0.2.1/cliopatria.geojson.zip",
    "source": "https://github.com/Seshat-Global-History-Databank/cliopatria",
    "doi": "10.1038/s41597-025-04516-9",
    "licence": "CC BY 4.0",
}
NEAR_YEARS = 50           # a record up to 50 years off still counts (the data has steps, the script says "around 1450")
_DOWNLOAD_TIMEOUT = 300

# ---------------------------------------------------------------- countries


def fold(s):
    """'Türkiye' = 'TURKIYE' = 'turkiye': Turkish dotted/dotless i and every diacritic fold to ASCII (same as FX.geo.fold)."""
    s = str(s if s is not None else "").replace("İ", "i").replace("I", "i").replace("ı", "i").lower()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


_table = {"rows": None, "by": None}


def countries():
    """Every country the atlas draws: [{iso2, iso3, num, tr, en, alt, bbox, lat, lon, area}]."""
    if _table["rows"] is None:
        with open(os.path.join(GEO, "countries.json"), encoding="utf-8") as f:
            rows = json.load(f)
        by = {}
        for r in rows:
            for k in (r["iso2"], r["iso3"]):
                by.setdefault(fold(k), r)
            by.setdefault("num " + r["num"], r)
        for r in rows:
            for k in [r["tr"], r["en"], *r.get("alt", [])]:
                by.setdefault(fold(k), r)
        _table.update(rows=rows, by=by)
    return _table["rows"]


def find(q):
    """A country by ISO alpha-2/3, ISO numeric, or its Turkish or English name (also common short forms); None if unknown."""
    countries()
    s = str(q or "").strip()
    return _table["by"].get(("num " + s) if re.fullmatch(r"\d{3}", s) else fold(s))


def name(q, lang="tr"):
    r = find(q)
    return r[lang if lang in ("tr", "en") else "en"] if r else str(q)


def cities():
    with open(os.path.join(GEO, "cities.json"), encoding="utf-8") as f:
        return json.load(f)


def flag_path(q):
    """The vendored flag SVG for a country (4x3), or None."""
    r = find(q)
    p = os.path.join(GEO, "flags", (r["iso2"] if r else str(q)).lower() + ".svg")
    return p if os.path.isfile(p) else None


# ---------------------------------------------------------------- historical borders (Cliopatria)

def _cache_file():
    return os.path.join(CACHE, f"cliopatria-{HISTORY['version']}.json.gz")


def _rd(v):
    return round(v * 100) / 100


def _ring(points, tol=0.02):
    """Round to 0.01 degree, drop repeats, Douglas-Peucker at `tol`; [] when fewer than 4 points are left."""
    out = []
    for x, y in points:
        p = (_rd(x), _rd(y))
        if not out or out[-1] != p:
            out.append(p)
    if tol and len(out) > 8:   # a closed ring has no chord: split it at the point farthest from the start
        m = max(range(len(out)), key=lambda i: (out[i][0] - out[0][0]) ** 2 + (out[i][1] - out[0][1]) ** 2)
        out = _dp(out[:m + 1], tol)[:-1] + _dp(out[m:], tol)
    return [[x, y] for x, y in out] if len(out) >= 4 else []


def _dp(pts, tol):
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        (ax, ay), (bx, by) = pts[a], pts[b]
        dx, dy = bx - ax, by - ay
        ln = (dx * dx + dy * dy) ** 0.5 or 1e-9
        md, mi = 0.0, -1
        for i in range(a + 1, b):
            d = abs((pts[i][0] - ax) * dy - (pts[i][1] - ay) * dx) / ln
            if d > md:
                md, mi = d, i
        if md > tol and mi > 0:
            keep[mi] = True
            stack.append((a, mi))
            stack.append((mi, b))
    return [p for p, k in zip(pts, keep) if k]


def build_history(raw_geojson):
    """Cliopatria GeoJSON (parsed) -> the compact record list we cache: [{name, from, to, wikipedia, polygons}].
    RELATION rows (names in parentheses: "(Vassalage of ...)", "(Allegiance of ...)", "(Kingdom of France)") are dropped: they
    repeat the land of the polities they relate, and painting both would double every border; polygons are lists of rings, each a list of [lon, lat]."""
    out = []
    for f in raw_geojson.get("features") or []:
        pr, g = f.get("properties") or {}, f.get("geometry")
        nm = str(pr.get("Name") or "")
        if not g or not nm or nm.startswith("(") or pr.get("Type") == "RELATION":
            continue
        polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"] if g["type"] == "MultiPolygon" else []
        keep = []
        for poly in polys:
            rings = [_ring(r) for r in poly]
            if rings and rings[0]:
                keep.append([r for r in rings if r])
        if keep:
            out.append({"name": nm, "from": int(pr.get("FromYear")), "to": int(pr.get("ToYear")),
                        "wikipedia": str(pr.get("Wikipedia") or ""), "polygons": keep})
    return out


def ensure_history(download=True):
    """The cached polity records (a list), fetching and simplifying the dataset once when absent. None when the cache
    is absent and `download` is False or the fetch fails (callers then draw no historical border at all)."""
    p = _cache_file()
    if not os.path.exists(p):
        if not download:
            return None
        try:
            os.makedirs(CACHE, exist_ok=True)
            zp = os.path.join(CACHE, "cliopatria.zip")
            with urllib.request.urlopen(HISTORY["url"], timeout=_DOWNLOAD_TIMEOUT) as r, open(zp, "wb") as f:
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
            with zipfile.ZipFile(zp) as z:
                name_ = next(n for n in z.namelist() if n.endswith(".geojson"))
                raw = json.loads(z.read(name_))
            data = build_history(raw)
            del raw
            tmp = p + ".part"
            with gzip.open(tmp, "wt", encoding="utf-8", compresslevel=6) as f:
                json.dump(data, f, separators=(",", ":"))
            os.replace(tmp, p)
            os.remove(zp)
        except Exception:
            return None
    with gzip.open(p, "rt", encoding="utf-8") as f:
        return json.load(f)


def polities_in(year, data=None):
    """Polities that existed in `year` (from <= year <= to)."""
    data = ensure_history() if data is None else data
    return [x for x in data or [] if x["from"] <= year <= x["to"]]


def polity_at(name_, year, data=None):
    """One polity by name (accents and case ignored; exact first, then substring of 4+ characters), the one that
    covers `year`, else the nearest record within NEAR_YEARS."""
    data = ensure_history() if data is None else data
    want = fold(name_)
    if not want:
        return None

    def pick(match):
        hits = [x for x in data or [] if match(fold(x["name"])) or match(fold(x.get("wikipedia", "")))]
        hits.sort(key=lambda x: 0 if x["from"] <= year <= x["to"] else min(abs(year - x["from"]), abs(year - x["to"])))
        return hits[0] if hits and (hits[0]["from"] <= year <= hits[0]["to"] or min(abs(year - hits[0]["from"]), abs(year - hits[0]["to"])) <= NEAR_YEARS) else None
    return pick(lambda n: n == want) or (pick(lambda n: want in n or n in want) if len(want) >= 4 else None)


def slice_path(year):
    return os.path.join(CACHE, "history", f"{int(year)}.json")


def year_slice(year, data=None, download=True):
    """Write the polities of `year` as /work/geo/history/<year>.json for the page; -> the path, or None when the
    dataset is unavailable. The file carries the credit line so it travels with the data."""
    p = slice_path(year)
    if os.path.exists(p):
        return p
    data = ensure_history(download) if data is None else data
    if not data:
        return None
    rows = [{"name": x["name"], "wikipedia": x["wikipedia"], "from": x["from"], "to": x["to"], "polygons": x["polygons"]}
            for x in polities_in(int(year), data)]
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p + ".part", "w", encoding="utf-8") as f:
        json.dump({"year": int(year), "credit": credit_line(), "polities": rows}, f, separators=(",", ":"), ensure_ascii=False)
    os.replace(p + ".part", p)
    return p


USES_GEO = re.compile(r"\bFX\.geo\b")
YEAR = re.compile(r"\byear\s*:\s*(-?\d{1,4})\b")


def years_in(text):
    """The years a scene text asks FX.geo.map for (only when it uses FX.geo at all)."""
    if not USES_GEO.search(text or ""):
        return []
    return sorted({int(y) for y in YEAR.findall(text)})


def prepare(text):
    """Write the history slices a scene text needs. -> the years that are ready (the others will draw coastlines only)."""
    ready = []
    for y in years_in(text):
        if year_slice(y):
            ready.append(y)
    return ready


# ---------------------------------------------------------------- the licence ledger

def credit_line(lang="tr"):
    if lang == "en":
        return ("Historical borders: Cliopatria, Seshat Global History Databank (Bennett et al. 2025, "
                f"doi:{HISTORY['doi']}), {HISTORY['licence']} · {HISTORY['source']}")
    return ("Tarihî sınırlar: Cliopatria, Seshat Global History Databank (Bennett vd. 2025, "
            f"doi:{HISTORY['doi']}), {HISTORY['licence']} · {HISTORY['source']}")


def ledger(text):
    """Attribution rows for a film whose scene text uses FX.geo: the map data and flags (recorded, no credit needed:
    public domain / MIT), plus Cliopatria (CC BY 4.0: the credit is required) when a map asks for a year."""
    if not USES_GEO.search(text or ""):
        return []
    rows = [{"kind": "map data", "file": "assets/geo/countries-50m.json", "what": "Country borders (Natural Earth via world-atlas)",
             "author": "Natural Earth", "licence": "Public domain", "url": "https://www.naturalearthdata.com/", "page": "", "credit": False},
            {"kind": "flags", "file": "assets/geo/flags", "what": "Country flags (flag-icons)", "author": "Panayiotis Lipiridis",
             "licence": "MIT", "url": "https://github.com/lipis/flag-icons", "page": "", "credit": False}]
    if years_in(text):
        rows.append({"kind": "map data", "file": f"work/geo/cliopatria-{HISTORY['version']}", "what": "Historical borders (Cliopatria)",
                     "author": "Seshat Global History Databank (Bennett et al. 2025)", "licence": HISTORY["licence"],
                     "url": HISTORY["source"], "page": HISTORY["source"], "credit": True})
    return rows
