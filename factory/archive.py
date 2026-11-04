"""Open-licence real footage: search Wikimedia Commons, NASA and the Internet Archive, keep every clip seen in a local
archive (data/footage_archive.json) and rank by meaning (factory.embed) against what a shot should show.

Licences: Wikimedia per file (the same rules as factory.stock: PD, CC0, CC BY, CC BY-SA; never NC/ND/fair use),
Internet Archive only PD/CC0/CC BY/CC BY-SA items, NASA media is public domain (items that credit a third party are
skipped). Only the chosen clips are downloaded (a smaller transcode when the archive has one, at most MAX_BYTES, only
from the archives' own hosts) into assets/footage/, kept for reuse; shots are cut from those copies.
"""
import hashlib, html, json, os, re, subprocess, urllib.parse, urllib.request

from .config import FFMPEG, ROOT
from .stock import UA, licence_ok

STORE = os.path.join(ROOT, "data", "footage_archive.json")
FILES = os.path.join(ROOT, "assets", "footage")
MAX_BYTES = 400 * 1024 * 1024
HOSTS = ("upload.wikimedia.org", "images-assets.nasa.gov", "archive.org")
MIN_W = 640
IA_LICENCE = re.compile(r"creativecommons\.org/(publicdomain/|licenses/by(-sa)?/)", re.I)
THIRD_PARTY = re.compile(r"©|copyright|courtesy of|all rights reserved", re.I)


def _get(url, timeout=40):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _json(url):
    return json.loads(_get(url))


def _plain(s):
    return html.unescape(re.sub(r"<[^>]+>", " ", str(s or ""))).replace("\n", " ").strip()


def _clean(s, n=300):
    return re.sub(r"\s+", " ", _plain(s))[:n]


def load():
    try:
        return json.load(open(STORE))
    except (OSError, ValueError):
        return {}


def save(store):
    os.makedirs(os.path.dirname(STORE), exist_ok=True)
    tmp = STORE + ".tmp"
    json.dump(store, open(tmp, "w"), ensure_ascii=False)
    os.replace(tmp, STORE)


# ---------- sources ----------

def wikimedia(q, n=8):
    params = {"action": "query", "generator": "search", "gsrnamespace": 6, "gsrsearch": q + " filetype:video",
              "gsrlimit": n, "prop": "videoinfo", "viprop": "url|size|mime|extmetadata|derivatives",
              "viurlwidth": 480, "format": "json"}
    data = _json("https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params))
    out = []
    for pg in (data.get("query") or {}).get("pages", {}).values():
        v = (pg.get("videoinfo") or [{}])[0]
        meta = v.get("extmetadata") or {}
        lic = (meta.get("LicenseShortName") or {}).get("value", "")
        if not licence_ok(lic) or (meta.get("NonFree") or {}).get("value", "").lower() == "true":
            continue
        if (v.get("width") or 0) < MIN_W:
            continue
        ders = [x for x in v.get("derivatives") or [] if (x.get("height") or 0) <= 1080 and "audio" not in x.get("type", "")]
        best = max(ders, key=lambda x: x.get("height") or 0)["src"] if ders else v.get("url")
        out.append({"key": "wm:" + pg["title"], "source": "Wikimedia Commons", "title": pg["title"].replace("File:", ""),
                    "text": _clean((meta.get("ImageDescription") or {}).get("value")),
                    "tags": _clean((meta.get("Categories") or {}).get("value"), 200).replace("|", ", "),
                    "license": lic, "author": _clean((meta.get("Artist") or {}).get("value"), 80),
                    "page": v.get("descriptionurl", ""), "thumb": v.get("thumburl", ""), "url": best,
                    "duration": float(v.get("duration") or 0) or None, "w": v.get("width"), "h": v.get("height")})
    return out


def nasa(q, n=8):
    data = _json("https://images-api.nasa.gov/search?" + urllib.parse.urlencode({"q": q, "media_type": "video",
                                                                                  "page_size": n}))
    out = []
    for it in (data.get("collection") or {}).get("items", [])[:n]:
        x = (it.get("data") or [{}])[0]
        desc = _clean(x.get("description"))
        if THIRD_PARTY.search(desc + " " + str(x.get("secondary_creator") or "")):
            continue
        out.append({"key": "nasa:" + x.get("nasa_id", ""), "source": "NASA", "title": _clean(x.get("title"), 120),
                    "text": desc, "tags": ", ".join(x.get("keywords") or [])[:200], "license": "Public domain (NASA)",
                    "author": "NASA" + (f"/{x['center']}" if x.get("center") else ""),
                    "page": f"https://images.nasa.gov/details/{urllib.parse.quote(x.get('nasa_id', ''))}",
                    "thumb": next((l["href"] for l in it.get("links") or [] if l.get("render") == "image"), ""),
                    "collection": it.get("href"), "url": None, "duration": None, "w": None, "h": None})
    return out


def internet_archive(q, n=8):
    lic = "(licenseurl:*publicdomain* OR licenseurl:*licenses/by/* OR licenseurl:*licenses/by-sa/*)"
    params = [("q", f"({q}) AND mediatype:movies AND {lic}"), ("rows", n), ("output", "json")]
    params += [("fl[]", f) for f in ("identifier", "title", "description", "licenseurl", "creator", "subject")]
    data = _json("https://archive.org/advancedsearch.php?" + urllib.parse.urlencode(params))
    out = []
    for x in (data.get("response") or {}).get("docs", []):
        if not IA_LICENCE.search(str(x.get("licenseurl") or "")):
            continue
        sub = x.get("subject")
        out.append({"key": "ia:" + x["identifier"], "source": "Internet Archive", "title": _clean(x.get("title"), 120),
                    "text": _clean(x.get("description")), "tags": _clean(", ".join(sub) if isinstance(sub, list) else sub, 200),
                    "license": x["licenseurl"], "author": _clean(x.get("creator"), 80),
                    "page": f"https://archive.org/details/{x['identifier']}",
                    "thumb": f"https://archive.org/services/img/{x['identifier']}", "url": None,
                    "duration": None, "w": None, "h": None})
    return out


SOURCES = {"wikimedia": wikimedia, "nasa": nasa, "archive": internet_archive}


def search(queries, sources=None):
    """Every source for every query -> new clips (also added to the local archive). A source that fails is skipped."""
    store, found = load(), {}
    for q in queries:
        for name, fn in SOURCES.items():
            if sources and name not in sources:
                continue
            try:
                for c in fn(q):
                    found.setdefault(c["key"], c)
            except Exception:              # one archive being down must not stop the others
                continue
    for k, c in found.items():
        store[k] = {**c, **{x: store[k][x] for x in ("url", "duration", "w", "h") if store.get(k, {}).get(x)}}
    if found:
        save(store)
    return [store[k] for k in found]


def rank(look, cands, con=None, k=5):
    """The clips whose title, description and tags mean what `look` describes, best first, with their score."""
    from . import embed
    if not cands:
        return []
    texts = [look] + [" ".join(x for x in (c.get("title"), c.get("text"), c.get("tags")) if x)[:600] for c in cands]
    vecs = embed.vectors(texts, con)
    sims = vecs[1:] @ vecs[0]
    order = sorted(range(len(cands)), key=lambda i: -float(sims[i]))
    return [{**cands[i], "score": round(float(sims[i]), 3)} for i in order[:k]]


def find(look, queries, con=None, k=5, exclude=()):
    """Search the archives, then rank the new clips together with the ones already in the local archive."""
    fresh = search(queries)
    seen = {c["key"] for c in fresh}
    pool = fresh + [c for key, c in load().items() if key not in seen]
    return [c for c in rank(look, [c for c in pool if c["key"] not in exclude], con, k + len(exclude))][:k]


# ---------- the file itself ----------

def allowed(url):
    host = urllib.parse.urlparse(url or "").hostname or ""
    return urllib.parse.urlparse(url).scheme in ("http", "https") and any(host == h or host.endswith("." + h) for h in HOSTS)


def _seconds(v):
    """'1768.32' or '29:28' -> seconds; None when unreadable."""
    try:
        parts = [float(x) for x in str(v).split(":")]
    except ValueError:
        return None
    return sum(x * 60 ** i for i, x in enumerate(reversed(parts))) or None


def resolve(c):
    """Fill in the clip's file URL, size and length (looked up only when the clip is actually chosen)."""
    c = dict(c)
    if not c.get("url") and c.get("collection"):
        files = _json(c["collection"].replace(" ", "%20"))
        pick = next((f for want in ("~medium.mp4", "~mobile.mp4", "~large.mp4", "~orig.mp4") for f in files
                     if f.endswith(want)), None)
        c["url"] = pick.replace("http://", "https://").replace(" ", "%20") if pick else None
    if not c.get("url") and c["key"].startswith("ia:"):
        ident = c["key"][3:]
        files = _json(f"https://archive.org/metadata/{urllib.parse.quote(ident)}").get("files") or []
        vids = [f for f in files if f.get("name", "").lower().endswith((".mp4", ".ogv", ".webm"))
                and int(f.get("width") or 0) >= MIN_W]
        vids = [f for f in vids or [f for f in files if f.get("name", "").lower().endswith((".mp4", ".ogv"))]
                if int(f.get("size") or 0) <= MAX_BYTES]
        if vids:
            f = min(vids, key=lambda f: int(f.get("size") or 1e12))
            c["url"] = f"https://archive.org/download/{urllib.parse.quote(ident)}/{urllib.parse.quote(f['name'])}"
            c["duration"] = _seconds(f.get("length"))
    if not c.get("url") or not allowed(c["url"]):
        return None
    store = load()
    if c["key"] in store:
        store[c["key"]].update({x: c[x] for x in ("url", "duration", "w", "h")})
        save(store)
    return c


def fetch(c):
    """The clip's file on disk (downloaded once, at most MAX_BYTES), with its real size and length filled in."""
    from .talk import probe
    url = c.get("url")
    if not url or not allowed(url):
        raise ValueError(f"not an archive address: {url}")
    ext = os.path.splitext(urllib.parse.urlparse(url).path)[1].lower() or ".mp4"
    path = os.path.join(FILES, hashlib.sha1(url.encode()).hexdigest()[:16] + ext)
    if not os.path.isfile(path):
        os.makedirs(FILES, exist_ok=True)
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            if not allowed(r.geturl()):
                raise ValueError(f"redirected away from the archive: {r.geturl()}")
            if int(r.headers.get("Content-Length") or 0) > MAX_BYTES:
                raise ValueError("the file is too large")
            tmp, n = path + ".part", 0
            with open(tmp, "wb") as f:
                while chunk := r.read(1 << 20):
                    n += len(chunk)
                    if n > MAX_BYTES:
                        raise ValueError("the file is too large")
                    f.write(chunk)
        os.replace(tmp, path)
    info = probe(path)
    return path, {"w": info["w"], "h": info["h"], "duration": info["duration"]}


def frame_filter(size, fit=False):
    """Cover the frame (crop), or `fit`: the whole picture in the middle over a blurred, darker copy of itself."""
    w, h = size
    if not fit:
        return f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1"
    return (f"split[bg][fg];[bg]scale={w // 4}:{h // 4}:force_original_aspect_ratio=increase,crop={w // 4}:{h // 4},"
            f"boxblur=8:2,eq=brightness=-0.12,scale={w}:{h}[bb];[fg]scale={w}:{h}:force_original_aspect_ratio=decrease[ff];"
            f"[bb][ff]overlay=(W-w)/2:(H-h)/2,setsar=1")


def grab(src, start, secs, out, size, fit=False):
    """`secs` seconds from `start` of a local clip, cropped to cover `size` (or fitted on a blur), 30 fps, no sound."""
    os.makedirs(os.path.dirname(out), exist_ok=True)
    subprocess.run([FFMPEG, "-y", "-v", "error", "-ss", str(round(start, 2)), "-i", src, "-t", str(round(secs, 2)),
                    "-vf", frame_filter(size, fit) + ",fps=30", "-an",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", out],
                   check=True, timeout=600)
    return out


def still(src, at, out, size=(360, 640)):
    """One frame at `at` seconds, cropped like the final."""
    w, h = size
    os.makedirs(os.path.dirname(out), exist_ok=True)
    subprocess.run([FFMPEG, "-y", "-v", "error", "-ss", str(round(at, 2)), "-i", src, "-frames:v", "1",
                    "-vf", f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}", out], check=True, timeout=180)
    return out


def credit(c):
    return f"{c.get('title')} · {c.get('author') or c.get('source')} · {c.get('license')} · {c.get('page')}"

