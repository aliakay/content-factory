"""Open-licence stock images for explainer backgrounds, from Wikimedia Commons only (no API key, licence per file).

Allowed: public domain, CC0, CC BY, CC BY-SA (these need credit; the credit line travels with the production).
Never used: NC / ND licences, fair-use files, SVG/GIF/video, tiny images. Every pick is cached in
data/stock_cache.json (query -> chosen file) so a revision never downloads or changes an image by accident.
"""
import hashlib, html, json, os, re, urllib.parse, urllib.request

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
        lic = (meta.get("LicenseShortName") or {}).get("value", "")
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
