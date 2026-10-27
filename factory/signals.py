"""Market signals: YouTube Viral Radar (stored), Google Trends trending-searches RSS, TikTok manual import."""
import json, os, re, sys, time, urllib.error, urllib.parse, urllib.request
import xml.etree.ElementTree as ET

from .store import now

from .config import ROOT
sys.path.insert(0, ROOT)
UA = {"User-Agent": "Mozilla/5.0 (ContentFactory; personal research)"}
TRENDS_RSS = "https://trends.google.com/trending/rss?geo={geo}"
CREATIVE_CENTER = "https://ads.tiktok.com/business/creativecenter/inspiration/popular/hashtag/pc/en"
NS = {"ht": "https://trends.google.com/trending/rss"}


# ---------- YouTube (Viral Radar database) ----------
def radar_candidates(limit=40, profile=None):
    from radar import db as rdb
    from radar.config import DB_PATH, SearchProfile, get_profile
    from radar.pipeline import load_candidates
    from radar.scoring import shortlist
    if not os.path.exists(DB_PATH):
        return [], [], []
    con = rdb.connect(DB_PATH)
    cands = load_candidates(con, get_profile(profile) if profile else SearchProfile())
    runs = [dict(r) for r in con.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 5")]
    return cands[:limit], shortlist(cands), runs


# ---------- Google Trends ----------
def fetch_trends(con, geos=("US", "GB")):
    """Daily trending searches per country from Google Trends' public RSS feed (a topic signal, not video data)."""
    ts, n = now(), 0
    for geo in geos:
        req = urllib.request.Request(TRENDS_RSS.format(geo=geo), headers=UA)
        root = ET.fromstring(urllib.request.urlopen(req, timeout=30).read())
        for it in root.iter("item"):
            news = [{"title": (x.findtext("ht:news_item_title", namespaces=NS) or ""),
                     "source": (x.findtext("ht:news_item_source", namespaces=NS) or "")}
                    for x in it.findall("ht:news_item", NS)][:3]
            con.execute("INSERT OR REPLACE INTO trend_items VALUES (?,?,?,?,?,?)",
                        (geo, it.findtext("title"), it.findtext("ht:approx_traffic", namespaces=NS),
                         it.findtext("pubDate"), json.dumps(news), ts))
            n += 1
    con.commit()
    return n


def latest_trends(con):
    row = con.execute("SELECT MAX(retrieved_at) m FROM trend_items").fetchone()
    if not row or not row["m"]:
        return [], None
    items = [dict(r) for r in con.execute("SELECT * FROM trend_items WHERE retrieved_at=? ORDER BY geo", (row["m"],))]
    return items, row["m"]


# ---------- TikTok (manual import + official oEmbed) ----------
TIKTOK_URL = re.compile(r"^https?://(www\.|vm\.|vt\.|m\.)?tiktok\.com/", re.I)


def oembed(url, retries=3):
    """Official TikTok oEmbed: title, author and thumbnail only (no view counts)."""
    q = "https://www.tiktok.com/oembed?" + urllib.parse.urlencode({"url": url})
    for attempt in range(retries):
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(q, headers=UA), timeout=20)), "ok"
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < retries - 1:
                time.sleep(3 * (attempt + 1))
                continue
            return None, f"http_{e.code}"
        except urllib.error.URLError as e:
            return None, f"network: {e.reason}"
    return None, "failed"


def import_tiktok(con, url, views=None, likes=None, note=""):
    url = url.strip()
    if not TIKTOK_URL.match(url):
        raise ValueError("not a TikTok URL")
    data, status = oembed(url)
    title = (data or {}).get("title")
    tags = " ".join(sorted(set(re.findall(r"#\w+", title or ""))))
    con.execute("""INSERT INTO tiktok_refs (url, author, title, thumbnail, hashtags, views, likes, metrics_source,
                   note, oembed_status, added_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(url) DO UPDATE SET author=COALESCE(excluded.author, author),
                   title=COALESCE(excluded.title, title), thumbnail=COALESCE(excluded.thumbnail, thumbnail),
                   hashtags=excluded.hashtags, views=COALESCE(excluded.views, views),
                   likes=COALESCE(excluded.likes, likes), metrics_source=excluded.metrics_source,
                   note=excluded.note, oembed_status=excluded.oembed_status""",
                (url, (data or {}).get("author_name"), title, (data or {}).get("thumbnail_url"), tags,
                 views, likes, "manual" if (views or likes) else None, note, status, now()))
    con.commit()
    return status
