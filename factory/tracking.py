"""Publish tracking: which finished video went to which platform, and how it performs over time.

YouTube stats come from the Data API with the existing key (videos.list, 1 quota unit per 50 videos).
TikTok has no public stats API for us (oEmbed gives title/thumbnail only) and Instagram needs a Business app,
so their numbers are typed in by the creator and stored with source="manual". Never invent a number.
"""
import os, re, sys

from .store import ROOT, now

SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
  post_id INTEGER PRIMARY KEY AUTOINCREMENT, prod_id INTEGER, out_name TEXT, platform TEXT, url TEXT UNIQUE,
  ext_id TEXT, title TEXT, thumb TEXT, posted_at TEXT, added_at TEXT
);
CREATE TABLE IF NOT EXISTS post_stats (
  post_id INTEGER, at TEXT, views INTEGER, likes INTEGER, comments INTEGER, shares INTEGER, source TEXT
);
"""
PLATFORMS = ("youtube", "tiktok", "instagram")
YT_ID = re.compile(r"(?:youtube\.com/(?:shorts/|watch\?v=|live/)|youtu\.be/)([\w-]{11})")
TT_ID = re.compile(r"tiktok\.com/.*/video/(\d+)")
IG_ID = re.compile(r"instagram\.com/(?:reel|reels|p)/([\w-]+)")


def ensure(con):
    con.executescript(SCHEMA)


def detect(url):
    for platform, rx in (("youtube", YT_ID), ("tiktok", TT_ID), ("instagram", IG_ID)):
        m = rx.search(url)
        if m:
            return platform, m.group(1)
    raise ValueError("YouTube, TikTok veya Instagram video linki değil")


def add_post(con, url, out_name=None, prod_id=None, posted_at=None):
    ensure(con)
    url = url.strip()
    platform, ext = detect(url)
    title = thumb = None
    if platform == "tiktok":
        from .signals import oembed
        data, _ = oembed(url)
        title, thumb = (data or {}).get("title"), (data or {}).get("thumbnail_url")
    con.execute("""INSERT INTO posts (prod_id, out_name, platform, url, ext_id, title, thumb, posted_at, added_at)
                   VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(url) DO UPDATE SET prod_id=COALESCE(excluded.prod_id, prod_id),
                   out_name=COALESCE(excluded.out_name, out_name)""",
                (prod_id, out_name, platform, url, ext, title, thumb, posted_at or now(), now()))
    con.commit()
    pid = con.execute("SELECT post_id FROM posts WHERE url=?", (url,)).fetchone()["post_id"]
    if platform == "youtube":
        try:
            refresh_youtube(con, [pid])
        except Exception as e:  # stats can be fetched later; the post itself is saved
            print("youtube stats:", e, flush=True)
    return pid


def add_stats(con, post_id, views=None, likes=None, comments=None, shares=None, source="manual"):
    ensure(con)
    con.execute("INSERT INTO post_stats VALUES (?,?,?,?,?,?,?)",
                (post_id, now(), views, likes, comments, shares, source))
    con.commit()


def refresh_youtube(con, post_ids=None):
    """Fetch current YouTube statistics for tracked posts. Returns the number of posts updated."""
    ensure(con)
    sys.path.insert(0, ROOT)
    from radar.config import load_env
    from radar.youtube import YouTube
    q = "SELECT post_id, ext_id FROM posts WHERE platform='youtube'"
    rows = [r for r in con.execute(q) if post_ids is None or r["post_id"] in post_ids]
    if not rows:
        return 0
    yt = YouTube(load_env().get("YOUTUBE_API_KEY") or os.environ.get("YOUTUBE_API_KEY"), quota_budget=50)
    by_ext = {r["ext_id"]: r["post_id"] for r in rows}
    n = 0
    ids = list(by_ext)
    for i in range(0, len(ids), 50):
        data = yt._call("videos", part="statistics,snippet", id=",".join(ids[i:i + 50]))
        for it in data.get("items", []):
            st, sn = it.get("statistics", {}), it.get("snippet", {})
            pid = by_ext[it["id"]]
            thumb = ((sn.get("thumbnails") or {}).get("medium") or {}).get("url")
            con.execute("UPDATE posts SET title=COALESCE(title, ?), thumb=COALESCE(thumb, ?), posted_at=? WHERE post_id=?",
                        (sn.get("title"), thumb, sn.get("publishedAt") or now(), pid))
            add_stats(con, pid, _int(st.get("viewCount")), _int(st.get("likeCount")), _int(st.get("commentCount")),
                      None, "youtube_api")
            n += 1
    con.commit()
    return n


def _int(v):
    return int(v) if v not in (None, "") else None


def posts(con):
    """Every tracked post with its latest stats and a short history for sparklines."""
    ensure(con)
    out = []
    for p in con.execute("""SELECT p.*, pr.format, pr.title AS prod_title, pr.channel_id AS prod_channel FROM posts p
                            LEFT JOIN productions pr ON pr.prod_id = p.prod_id ORDER BY p.posted_at DESC"""):
        d = dict(p)
        hist = [dict(r) for r in con.execute("SELECT * FROM post_stats WHERE post_id=? ORDER BY at", (p["post_id"],))]
        d["history"] = [{"at": h["at"], "views": h["views"]} for h in hist if h["views"] is not None][-30:]
        d["latest"] = hist[-1] if hist else None
        out.append(d)
    return out


def summary(con):
    """Per format and per platform totals, for the dashboard and as feedback for idea generation."""
    rows = posts(con)
    by_format, by_platform = {}, {}
    for p in rows:
        v = (p["latest"] or {}).get("views")
        if v is None:
            continue
        for key, bucket in ((p.get("format") or "other", by_format), (p["platform"], by_platform)):
            b = bucket.setdefault(key, {"posts": 0, "views": 0, "best": 0})
            b["posts"] += 1
            b["views"] += v
            b["best"] = max(b["best"], v)
    return {"by_format": by_format, "by_platform": by_platform,
            "total_views": sum(b["views"] for b in by_platform.values()), "posts": len(rows)}


def feedback_rows(con, limit=20):
    """Own results for the idea prompt: real numbers only, labelled with their source."""
    out = []
    for p in posts(con)[:limit]:
        lt = p["latest"] or {}
        out.append({"title": p.get("prod_title") or p.get("title"), "format": p.get("format"),
                     "platform": p["platform"], "posted_at": p["posted_at"], "views": lt.get("views"),
                     "likes": lt.get("likes"), "comments": lt.get("comments"), "source": lt.get("source")})
    return out
