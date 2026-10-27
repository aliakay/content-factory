"""SQLite storage: videos, daily metric snapshots, creator baselines and run logs."""
import json, os, sqlite3
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
  platform TEXT NOT NULL, video_id TEXT NOT NULL, url TEXT NOT NULL,
  title TEXT, description TEXT, channel_id TEXT, channel_title TEXT,
  published_at TEXT, duration_s REAL, duration_verified INTEGER DEFAULT 0,
  language TEXT, thumbnail TEXT, sources TEXT DEFAULT '[]',
  first_seen TEXT, last_seen TEXT, is_mock INTEGER DEFAULT 0,
  PRIMARY KEY (platform, video_id)
);
CREATE TABLE IF NOT EXISTS snapshots (
  platform TEXT NOT NULL, video_id TEXT NOT NULL, ts TEXT NOT NULL,
  views INTEGER, likes INTEGER, comments INTEGER,
  PRIMARY KEY (platform, video_id, ts)
);
CREATE TABLE IF NOT EXISTS channel_baselines (
  platform TEXT NOT NULL, channel_id TEXT NOT NULL, computed_at TEXT,
  median_views REAL, sample_size INTEGER, PRIMARY KEY (platform, channel_id)
);
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, connector TEXT, status TEXT,
  detail TEXT, results INTEGER, quota_units INTEGER
);
CREATE TABLE IF NOT EXISTS topic_signals (
  topic TEXT PRIMARY KEY, value REAL, source TEXT, recorded_at TEXT
);
"""


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def connect(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    cols = {r[1] for r in con.execute("PRAGMA table_info(channel_baselines)")}
    if "subscribers" not in cols:
        con.execute("ALTER TABLE channel_baselines ADD COLUMN subscribers INTEGER")
    vcols = {r[1] for r in con.execute("PRAGMA table_info(videos)")}
    if "topic" not in vcols:
        con.execute("ALTER TABLE videos ADD COLUMN topic TEXT DEFAULT 'psychology'")
    return con


def upsert_video(con, v, source, topic="psychology"):
    """Insert or update a video; `sources` accumulates every (connector, query) that found it."""
    row = con.execute("SELECT sources FROM videos WHERE platform=? AND video_id=?",
                      (v["platform"], v["video_id"])).fetchone()
    sources = json.loads(row["sources"]) if row else []
    if source not in sources:
        sources.append(source)
    ts = now_iso()
    con.execute("""
      INSERT INTO videos (platform, video_id, url, title, description, channel_id, channel_title,
        published_at, duration_s, duration_verified, language, thumbnail, sources, first_seen, last_seen, is_mock, topic)
      VALUES (:platform, :video_id, :url, :title, :description, :channel_id, :channel_title,
        :published_at, :duration_s, :duration_verified, :language, :thumbnail, :sources, :ts, :ts, :is_mock, :topic)
      ON CONFLICT(platform, video_id) DO UPDATE SET
        url=excluded.url, title=excluded.title, description=excluded.description,
        channel_id=excluded.channel_id, channel_title=excluded.channel_title,
        published_at=excluded.published_at, duration_s=excluded.duration_s,
        duration_verified=excluded.duration_verified, language=COALESCE(excluded.language, videos.language),
        thumbnail=excluded.thumbnail, sources=excluded.sources, last_seen=excluded.last_seen
    """, {**{k: v.get(k) for k in ("platform", "video_id", "url", "title", "description", "channel_id",
                                    "channel_title", "published_at", "duration_s", "language", "thumbnail")},
          "duration_verified": int(bool(v.get("duration_verified"))), "sources": json.dumps(sources),
          "ts": ts, "is_mock": int(bool(v.get("is_mock"))), "topic": topic})


def add_snapshot(con, platform, video_id, views, likes, comments, ts=None):
    con.execute("INSERT OR REPLACE INTO snapshots VALUES (?,?,?,?,?,?)",
                (platform, video_id, ts or now_iso(), views, likes, comments))


def log_run(con, connector, status, detail="", results=0, quota_units=0):
    con.execute("INSERT INTO runs (ts, connector, status, detail, results, quota_units) VALUES (?,?,?,?,?,?)",
                (now_iso(), connector, status, detail, results, quota_units))
    con.commit()
