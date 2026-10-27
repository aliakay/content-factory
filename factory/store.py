"""Content Factory storage (SQLite): clips inventory, places, signals, ideas and jobs."""
import json, os, sqlite3
from datetime import datetime, timezone

from .config import ROOT
DB = os.path.join(ROOT, "data", "factory.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS clips (
  clip_id TEXT PRIMARY KEY, path TEXT, kind TEXT, album TEXT,
  captured_at TEXT, lat REAL, lon REAL, duration REAL, fps REAL, width INTEGER, height INTEGER,
  place_id INTEGER, sheet TEXT, motion TEXT, segments TEXT,
  description TEXT, tags TEXT, mood TEXT, usable INTEGER DEFAULT 1, note TEXT,
  analyzed_at TEXT, described_at TEXT
);
CREATE TABLE IF NOT EXISTS places (
  place_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, day TEXT, lat REAL, lon REAL
);
CREATE TABLE IF NOT EXISTS albums (
  link TEXT PRIMARY KEY, title TEXT, added_at TEXT, last_sync TEXT
);
CREATE TABLE IF NOT EXISTS trend_items (
  geo TEXT, title TEXT, traffic TEXT, published TEXT, news TEXT, retrieved_at TEXT,
  PRIMARY KEY (geo, title, retrieved_at)
);
CREATE TABLE IF NOT EXISTS tiktok_refs (
  url TEXT PRIMARY KEY, author TEXT, title TEXT, thumbnail TEXT, hashtags TEXT,
  views INTEGER, likes INTEGER, metrics_source TEXT, note TEXT,
  oembed_status TEXT, added_at TEXT
);
CREATE TABLE IF NOT EXISTS ideas (
  idea_id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, status TEXT,
  title TEXT, series TEXT, data TEXT, verification TEXT, output TEXT
);
CREATE TABLE IF NOT EXISTS playbook (
  id INTEGER PRIMARY KEY AUTOINCREMENT, lesson TEXT, source TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS jobs (
  job_id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, arg TEXT, status TEXT,
  started_at TEXT, finished_at TEXT, log TEXT, result TEXT
);
CREATE TABLE IF NOT EXISTS llm_usage (
  id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT, step TEXT, model TEXT, job_id INTEGER, job_kind TEXT,
  prod_id INTEGER, user TEXT, input INTEGER, cache_write INTEGER, cache_read INTEGER, output INTEGER,
  cost_usd REAL, ok INTEGER, source TEXT
);
CREATE INDEX IF NOT EXISTS llm_usage_at ON llm_usage(at);
"""


def now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def connect(path=DB):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    con = sqlite3.connect(path, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(SCHEMA)
    cols = {r[1] for r in con.execute("PRAGMA table_info(ideas)")}
    for col in ("qa", "cost_usd"):
        if col not in cols:
            con.execute(f"ALTER TABLE ideas ADD COLUMN {col} TEXT")
    return con


def jload(s, default=None):
    try:
        return json.loads(s) if s else default
    except ValueError:
        return default
