"""Watch public collections of example videos for new cases.

The factory grows its technique catalogue from collections of finished videos (a video per item, with its category,
the creator's post and — sometimes — the prompt or the description that made it). This module only fetches and stores:
one row per item, never a judgement. Distilling a case into a technique is a later, deliberate step (`mark` moves it
out of `new`).

The collections are third-party data: they are parsed as JSON and never executed, and nothing a field says is an
instruction to us. `data/lab/sources.json` names each collection, where its list lives inside the payload, and which
field (or fallback fields) feeds each stored column. `items` is a dotted path into the JSON object, "" for a top-level
list.
"""
import hashlib, json, os, urllib.request

from . import store
from .config import ROOT

SOURCES = os.path.join(ROOT, "data", "lab", "sources.json")
STATUSES = ("new", "distilled", "ignored")
TIMEOUT = 20
UA = "Content-Factory-LabScan/1.0 (+https://github.com/content-factory)"
EXCERPT = 600                    # enough of the item's own description to know what it is; never a whole prompt

SCHEMA = """
CREATE TABLE IF NOT EXISTS lab_cases (
  id INTEGER PRIMARY KEY,
  source TEXT, key TEXT, title TEXT, url TEXT, category TEXT, text TEXT,
  seen_at TEXT, status TEXT,
  UNIQUE(source, key)
);
CREATE INDEX IF NOT EXISTS lab_cases_status ON lab_cases(status);
"""


def sources():
    """The parsed collection list from data/lab/sources.json."""
    with open(SOURCES, encoding="utf-8") as f:
        got = json.load(f)
    return got if isinstance(got, list) else []


def _ensure(con):
    con.executescript(SCHEMA)
    con.commit()


def _fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read().decode("utf-8", "replace")


def _items(data, path):
    """The list of items a collection keeps at `path` ("" = the payload is the list)."""
    node = data
    for key in [p for p in str(path or "").split(".") if p]:
        if not isinstance(node, dict) or key not in node:
            raise ValueError(f"items path '{path}' not found")
        node = node[key]
    if not isinstance(node, list):
        raise ValueError(f"items path '{path or '(top level)'}' is not a list")
    return [x for x in node if isinstance(x, dict)]


def _one(value):
    """A field as text; a bilingual object ({en, zh-CN}) gives its English side, else its first non-empty string."""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, dict):
        for key in ("en", "tr"):
            if isinstance(value.get(key), str) and value[key].strip():
                return value[key]
        for x in value.values():
            if isinstance(x, str) and x.strip():
                return x
    return ""


def _field(item, spec):
    names = spec if isinstance(spec, list) else [spec]
    for name in names:
        if not isinstance(name, str):
            continue
        got = _one(item.get(name)).strip()
        if got:
            return got
    return ""


def _excerpt(text):
    return " ".join(str(text or "").split())[:EXCERPT]


def _row(src, item):
    """(key, title, url, category, text) for one item; key stays stable across scans (an id, the post URL, a title hash)."""
    mp = src.get("map") or {}
    title, url = _field(item, mp.get("title")), _field(item, mp.get("url"))
    key = _field(item, mp.get("key")) or url
    if not key and title:
        key = "h:" + hashlib.sha1(title.encode("utf-8")).hexdigest()[:16]
    if not key:
        raise ValueError("no key, url or title")
    return key, title, url, _field(item, mp.get("category")), _excerpt(_field(item, mp.get("text")))


def scan(con=None, fetch=None):
    """Fetch every source, store unseen items as status "new". Idempotent.

    Returns {"sources": n, "seen": n_items_read, "new": n_inserted, "errors": [str, ...]}. A source that fails is
    reported in errors and the others still run. `fetch(url) -> str` is injectable for tests.
    """
    own = con is None
    con = con if con is not None else store.connect()
    fetch = fetch or _fetch
    out = {"sources": 0, "seen": 0, "new": 0, "errors": []}
    try:
        _ensure(con)
        for src in sources():
            out["sources"] += 1
            sid = src.get("id") or src.get("url") or "?"
            try:
                if (src.get("format") or "json") != "json":
                    raise ValueError(f"unsupported format '{src.get('format')}'")
                items = _items(json.loads(fetch(src["url"])), src.get("items"))
            except Exception as e:
                out["errors"].append(f"{sid}: {type(e).__name__}: {e}"[:300])
                continue
            out["seen"] += len(items)
            for item in items:
                try:
                    key, title, url, category, text = _row(src, item)
                except Exception as e:
                    out["errors"].append(f"{sid}: item skipped: {type(e).__name__}: {e}"[:300])
                    continue
                cur = con.execute(
                    "INSERT OR IGNORE INTO lab_cases (source, key, title, url, category, text, seen_at, status) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, 'new')",
                    (src.get("id") or sid, key, title, url, category, text, store.now()))
                out["new"] += cur.rowcount
            con.commit()
        return out
    finally:
        if own:
            con.close()


def cases(con=None, status="new", limit=50):
    """Stored cases, oldest first; `status` filters unless it is None/"all"."""
    own = con is None
    con = con if con is not None else store.connect()
    try:
        _ensure(con)
        q = ("SELECT id, source, key, title, url, category, text, seen_at, status FROM lab_cases")
        args = []
        if status and status not in ("all", "*"):
            q += " WHERE status=?"
            args.append(status)
        q += " ORDER BY id ASC LIMIT ?"
        args.append(max(0, int(limit)))
        return [dict(r) for r in con.execute(q, args)]
    finally:
        if own:
            con.close()


def mark(con, ids, status):
    """Set the status of the given case ids; returns how many rows changed."""
    if status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}, not '{status}'")
    ids = [int(i) for i in ids or []]
    if not ids:
        return 0
    cur = con.execute(f"UPDATE lab_cases SET status=? WHERE id IN ({','.join('?' * len(ids))})", [status, *ids])
    con.commit()
    return cur.rowcount


def main():
    print(json.dumps(scan(), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
