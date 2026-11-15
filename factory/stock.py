"""Open-licence stock images for explainer backgrounds, from Wikimedia Commons only (no API key, licence per file).

Allowed: public domain, CC0, CC BY, CC BY-SA (these need credit; the credit line travels with the production).
Never used: NC / ND licences, fair-use files, SVG/GIF/video, tiny images. Every pick is cached in
data/stock_cache.json (query -> chosen file) so a revision never downloads or changes an image by accident.
"""
import hashlib, html, json, os, re, time, urllib.parse, urllib.request

from .config import ROOT
DIR = os.path.join(ROOT, "assets", "stock")
CACHE = os.path.join(ROOT, "data", "stock_cache.json")
API = "https://commons.wikimedia.org/w/api.php"
UA = "ContentFactory/1.0 (personal short-video studio; aliakay8@gmail.com)"
OK_LICENSE = re.compile(r"^(cc0|public domain|pd\b|cc[- ]by(?![- ]?(nc|nd))(?:[- ]sa)?\b)", re.I)
MIN_W = 1000


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read()


def _plain(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


def _cache():
    try:
        return json.load(open(CACHE))
    except (OSError, ValueError):
        return {}


def licence_ok(name):
    n = (name or "").strip()
    return bool(OK_LICENSE.match(n)) and not re.search(r"\b(nc|nd)\b|non-?commercial|no ?deriv|fair use", n, re.I)


def find(query):
    """Best open-licence image for `query` -> {file, title, author, license, url, query} or None."""
    key = " ".join(query.lower().split())
    cache = _cache()
    hit = cache.get(key)
    if hit and os.path.exists(os.path.join(ROOT, hit["file"])):
        return dict(hit, query=query)
    params = {"action": "query", "generator": "search", "gsrnamespace": 6, "gsrsearch": query + " filetype:bitmap",
              "gsrlimit": 12, "prop": "imageinfo", "iiprop": "url|size|mime|extmetadata", "iiurlwidth": 1600,
              "format": "json"}
    data = json.loads(_get(API + "?" + urllib.parse.urlencode(params)))
    pages = sorted((data.get("query") or {}).get("pages", {}).values(), key=lambda p: p.get("index", 99))
    for pg in pages:
        info = (pg.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata") or {}
        lic = _plain((meta.get("LicenseShortName") or {}).get("value", ""))
        if info.get("mime") not in ("image/jpeg", "image/png", "image/webp") or info.get("width", 0) < MIN_W:
            continue
        if not licence_ok(lic) or (meta.get("NonFree") or {}).get("value", "").lower() == "true":
            continue
        os.makedirs(DIR, exist_ok=True)
        rel = os.path.join("assets", "stock", hashlib.sha1(pg["title"].encode()).hexdigest()[:16] + ".jpg")
        path = os.path.join(ROOT, rel)
        if not os.path.exists(path):
            from PIL import Image
            tmp = path + ".part"
            open(tmp, "wb").write(_get(info.get("thumburl") or info["url"]))
            Image.open(tmp).convert("RGB").save(path, quality=90)
            os.remove(tmp)
        res = {"file": rel, "title": pg["title"].replace("File:", ""), "author": _plain((meta.get("Artist") or {}).get("value"))[:80],
               "license": lic, "url": info.get("descriptionurl", ""), "query": query}
        cache[key] = res
        json.dump(cache, open(CACHE, "w"), ensure_ascii=False, indent=1)
        return res
    return None


def credit_line(b):
    return f"{b['title']} · {b.get('author') or 'unknown'} · {b['license']} · {b['url']}"


# ---------------------------------------------------------------- CC0 / public-domain vectors (F15)
# A ready-made Commons SVG is usually more accurate and cheaper than a drawn prop, but only if it is an object: not a
# diagram, logo, map or a calendar made of text nodes. The licence rule is stricter than for photos (PD/CC0 only by
# default), because a prop often ends up on screen without room for an attribution line.
SVG_DIR = os.path.join(ROOT, "assets", "stock")
MAX_SVG_BYTES = 300_000
MAX_ELEMENTS = 600
FREE_LICENSE = re.compile(r"public domain|^pd\b|cc0|no restrictions", re.I)
CC_BY_LICENSE = re.compile(r"cc[- ]by(?![- ]?sa)\b", re.I)
NOT_OBJECT = re.compile(r"diagram|schema|scheme|схема|logo|icon|coat of arms|bcoab|emblem|flag|mapb|font|sample|"
                        r"layout|keyboard|pattern|chart|graph|plot|point|signb|cypher|seal|badge|symbol|network|"
                        r"axle|crease", re.I)
STOP = {"the", "a", "an", "of", "and", "with", "in", "on", "for", "to", "front", "view", "side"}

ALLOWED_TAGS = {
    "svg", "g", "defs", "path", "rect", "circle", "ellipse", "line", "polyline", "polygon", "use", "symbol",
    "lineargradient", "radialgradient", "stop", "clippath", "mask", "pattern", "marker", "title", "desc",
    "filter", "fegaussianblur", "feoffset", "feblend", "fecolormatrix", "femerge", "femergenode", "feflood",
    "fecomposite", "fedropshadow",
}
ALLOWED_ATTRS = {
    "id", "xmlns", "xmlns:xlink", "viewbox", "preserveaspectratio", "width", "height", "x", "y", "x1", "y1", "x2",
    "y2", "cx", "cy", "r", "rx", "ry", "fx", "fy", "d", "points", "transform", "fill", "fill-opacity", "fill-rule",
    "stroke", "stroke-width", "stroke-linecap", "stroke-linejoin", "stroke-dasharray", "stroke-dashoffset",
    "stroke-opacity", "stroke-miterlimit", "opacity", "clip-path", "clip-rule", "mask", "filter", "offset",
    "stop-color", "stop-opacity", "gradientunits", "gradienttransform", "spreadmethod", "href", "xlink:href",
    "patternunits", "patterntransform", "maskunits", "clippathunits", "stddeviation", "in", "in2", "result", "mode",
    "values", "type", "dx", "dy", "flood-color", "flood-opacity", "operator", "k1", "k2", "k3", "k4", "visibility",
    "display", "style", "marker-start", "marker-mid", "marker-end", "markerwidth", "markerheight", "markerunits",
    "refx", "refy", "orient", "pathlength",
}
STYLE_PROPS = {"fill", "fill-opacity", "fill-rule", "stroke", "stroke-width", "stroke-linecap", "stroke-linejoin",
               "stroke-dasharray", "stroke-dashoffset", "stroke-opacity", "stroke-miterlimit", "opacity",
               "stop-color", "stop-opacity", "display", "visibility", "clip-path", "mask", "filter"}
_DANGER = re.compile(r"javascript:|vbscript:|data:|expression\(|@import|behavior:|image-set|src\(|-moz-binding", re.I)
_TAG = re.compile(r'<(\/?)([a-zA-Z][\w:-]*)((?:\s+[^\s=>/"\']+(?:\s*=\s*(?:"[^"]*"|\'[^\']*\'|[^\s"\'=<>/]+))?)*)\s*(\/?)>',
                  re.S)
_ATTR = re.compile(r'([^\s=>/"\']+)(?:\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|([^\s"\'=<>/]+)))?')


def _words(text):
    return re.findall(r"[^\W_]+", html.unescape(text or "").lower(), re.UNICODE)


def _safe_value(name, value):
    if re.search(r"[\\&]", value):
        return False
    v = re.sub(r"\s+", "", value).lower()
    if _DANGER.search(v):
        return False
    for u in re.findall(r"url\([^)]*\)?", v):
        if not re.fullmatch(r"url\(['\"]?#[\w.:-]+['\"]?\)", u):
            return False
    if name in ("href", "xlink:href") and not value.strip().startswith("#"):
        return False
    return True


def _safe_style(value):
    out = []
    for decl in value.split(";"):
        prop, _, val = decl.partition(":")
        prop, val = prop.strip().lower(), val.strip()
        if prop in STYLE_PROPS and val and _safe_value("style", val):
            out.append(f"{prop}:{val}")
    return ";".join(out)


def _normalize_urls(value):
    return re.sub(r"url\(\s*['\"]?#([^'\")\s]+)['\"]?\s*\)", r"url(#\1)", value)


def _with_view_box(svg):
    """A missing viewBox is rebuilt from width/height (otherwise the object renders at its file pixel size)."""
    m = re.match(r"^<svg((?:\s[^\s=]+=\"[^\"]*\")*)", svg, re.I)
    attrs = m.group(1) if m else ""
    if re.search(r"\sviewBox=\"", attrs, re.I):
        return svg
    def size(name):
        x = re.search(rf"\s{name}=\"\s*(\d+(?:\.\d+)?)\s*(?:px)?\s*\"", attrs, re.I)
        return float(x.group(1)) if x else 0.0
    w, h = size("width"), size("height")
    if not (w > 0 and h > 0):
        return svg
    return f'<svg viewBox="0 0 {w:g} {h:g}"' + svg[4:]


def sanitize_svg(raw):
    """Keep only drawing tags/attributes from an SVG: scripts, <foreignObject>, <text>, <image> and external hrefs go."""
    raw = str(raw or "")
    m = re.search(r"<svg[\s>]", raw, re.I)
    if not m:
        raise ValueError("SVG bulunamadı")
    start, end = m.start(), raw.lower().rfind("</svg>")
    if end < start:
        raise ValueError("SVG bulunamadı")
    body = raw[start:end + len("</svg>")]
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    body = re.sub(r"<!\[CDATA\[.*?\]\]>", "", body, flags=re.S)
    body = re.sub(r"<(script|style|foreignObject|text|textPath|iframe|object|embed|audio|video|animate\w*|set)\b"
                  r"[\s\S]*?</\1\s*>", "", body, flags=re.I)
    body = re.sub(r"<(script|style|foreignObject|iframe|object|embed|audio|video|animate\w*|set)\b[^>]*/>", "",
                  body, flags=re.I)
    out = []
    for m in _TAG.finditer(body):
        closing, raw_name, raw_attrs, self_closing = m.groups()
        name = raw_name.lower()
        if name not in ALLOWED_TAGS:
            continue
        if closing:
            out.append(f"</{raw_name}>")
            continue
        attrs = []
        for a in _ATTR.finditer(raw_attrs or ""):
            attr_name = a.group(1).lower()
            value = a.group(2) if a.group(2) is not None else (a.group(3) if a.group(3) is not None else (a.group(4) or ""))
            if attr_name not in ALLOWED_ATTRS:
                continue
            if attr_name == "style":
                value = _safe_style(value)
                if not value:
                    continue
            elif not _safe_value(attr_name, value):
                continue
            value = _normalize_urls(value).replace('"', "&quot;").replace("<", "&lt;")
            attrs.append(f'{a.group(1)}="{value}"')
        out.append(f"<{raw_name}{(' ' + ' '.join(attrs)) if attrs else ''}{'/' if self_closing else ''}>")
    svg = "".join(out)
    if not re.match(r"^<svg[\s>]", svg, re.I):
        raise ValueError("SVG bulunamadı")
    return _with_view_box(svg)


def svg_size(svg):
    """(width, height) from the viewBox, else from width/height; raises when neither is usable."""
    vb = re.search(r'viewBox="\s*[-\d.]+[\s,]+[-\d.]+[\s,]+([\d.]+)[\s,]+([\d.]+)\s*"', svg)
    if vb:
        return float(vb.group(1)), float(vb.group(2))
    w = re.search(r'\bwidth="([\d.]+)', svg)
    h = re.search(r'\bheight="([\d.]+)', svg)
    if w and h:
        return float(w.group(1)), float(h.group(1))
    raise ValueError("SVG boyutu yok (viewBox gerekli)")


def _vector_license_ok(lic, allow_cc_by):
    name = (lic or "").strip()
    bad = re.search(r"\b(nc|nd)\b|non-?commercial|no ?deriv|fair use", name, re.I)
    if bad:
        return False
    if FREE_LICENSE.search(name):
        return True
    return bool(allow_cc_by and CC_BY_LICENSE.search(name))


def _save_cache(cache):
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    tmp = CACHE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=1)
    os.replace(tmp, CACHE)


def search_vectors(query, n=2, allow_cc_by=False, http=None, api=None):
    """Up to `n` ready-made public-domain/CC0 SVG objects for `query` (cache first, then Wikimedia Commons).

    Each hit: {file, title, author, license, url, query, width, height, elements, shapes, credit}. `allow_cc_by`
    also accepts CC BY (credit required); CC BY-SA, NC and ND are never used. Files land in assets/stock/ and the
    record goes into data/stock_cache.json, so factory/licence.py owes the credit automatically.
    """
    q = " ".join(str(query or "").split())
    if len(q) < 2:
        raise ValueError("vector search needs a query")
    n = max(1, int(n or 1))
    key = q.lower()
    cache = _cache()
    index = cache.get("vector_index:" + key)
    if isinstance(index, dict) and isinstance(index.get("files"), list):
        by_file = {os.path.normpath(v["file"]): v for v in cache.values()
                   if isinstance(v, dict) and v.get("file")}
        hits = []
        for rel in index["files"]:
            hit = by_file.get(os.path.normpath(rel))
            if hit and os.path.exists(os.path.join(ROOT, rel)):
                hits.append(dict(hit, query=query))
        if len(hits) == len(index["files"]):
            return hits[:n]

    http = http or _get
    wanted = [w for w in _words(q) if w not in STOP and not w.isdigit()]
    params = {"action": "query", "format": "json", "generator": "search", "gsrnamespace": 6, "gsrlimit": 10,
              "prop": "imageinfo", "iiprop": "url|size|mime|extmetadata", "iiextmetadatafilter": "LicenseShortName",
              "gsrsearch": f"filetype:drawing {q}"}
    url = (api or API) + "?" + urllib.parse.urlencode(params)
    failed = False
    try:
        data = json.loads(http(url))
    except Exception:
        return []                                   # no network, no negative cache: the next call tries again
    pages = sorted(((data.get("query") or {}).get("pages") or {}).values(), key=lambda p: p.get("index", 99))
    hits = []
    for page in pages:
        if len(hits) >= n:
            break
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata") or {}
        lic = _plain((meta.get("LicenseShortName") or {}).get("value", ""))
        title = (page.get("title") or "").replace("File:", "")
        if (not info.get("url") or info.get("mime") != "image/svg+xml"
                or int(info.get("size") or 0) > MAX_SVG_BYTES or not _vector_license_ok(lic, allow_cc_by)
                or (meta.get("NonFree") or {}).get("value", "").lower() == "true"):
            continue
        title_words = set(_words(title))
        if not wanted or not any(w in title_words for w in wanted) or NOT_OBJECT.search(title):
            continue
        try:
            raw = http(info["url"]).decode("utf-8", "replace")
            svg = sanitize_svg(raw)
            width, height = svg_size(svg)
            if svg.count("<") > MAX_ELEMENTS:
                continue
            shapes = len(re.findall(r"<(?:path|rect|circle|ellipse|polygon|polyline|line|image)\b", svg, re.I))
            texts = len(re.findall(r"<text\b", raw, re.I))
            if not shapes or texts > shapes:          # a calendar or a table is not an object
                continue
        except ValueError:
            continue                                  # broken or viewBox-less drawing: skip it, not the whole search
        except Exception:
            failed = True                             # a network error must not be cached as "nothing found"
            continue
        sha = hashlib.sha1(f"{title}|{info.get('descriptionurl') or info['url']}".encode()).hexdigest()[:16]
        rel = os.path.join("assets", "stock", sha + ".svg")
        path = os.path.join(ROOT, rel)
        os.makedirs(SVG_DIR, exist_ok=True)
        if not os.path.exists(path):
            with open(path + ".part", "w", encoding="utf-8") as f:
                f.write(svg)
            os.replace(path + ".part", path)
        hit = {"file": rel, "title": title, "author": _plain((meta.get("Artist") or {}).get("value"))[:80],
               "license": lic, "url": info.get("descriptionurl", ""), "query": query, "kind": "vector",
               "query_key": key, "width": round(width, 2), "height": round(height, 2),
               "elements": svg.count("<"), "shapes": shapes,
               "credit": bool(allow_cc_by and not FREE_LICENSE.search(lic) and CC_BY_LICENSE.search(lic))}
        hits.append(hit)
    if not failed:
        for i, hit in enumerate(hits):
            cache["vector:" + hashlib.sha1(hit["file"].encode()).hexdigest()[:16]] = dict(hit, order=i)
        cache["vector_index:" + key] = {"kind": "vector_index", "query_key": key,
                                        "files": [h["file"] for h in hits], "at": int(time.time())}
        _save_cache(cache)
    return hits[:n]
