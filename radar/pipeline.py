"""Search orchestration: run connectors, verify, store, snapshot and score."""
import json
from datetime import datetime, timedelta, timezone

from . import db
from .scoring import parse_ts, score_all
from .youtube import ConnectorError, QuotaExceeded


def run_youtube(con, yt, profile, now=None, baseline_top=15):
    start, end = profile.window(now)
    summary = {"connector": "youtube", "status": "ok", "searches": 0, "ids": 0, "verified_short": 0,
               "rejected_duration": 0, "rejected_window": 0, "unverified_duration": 0, "errors": []}
    found = {}  # video_id -> list of source labels

    plan = [(q, lang, "relevance") for q in profile.queries for lang in profile.languages]
    plan += [(q, lang, o) for q in profile.extra_view_order_queries for lang in profile.languages
             for o in profile.orders if o != "relevance"] + \
            [(q, lang, "viewCount") for q in profile.extra_view_order_queries for lang in profile.languages]
    seen_plan = []
    for p in plan:
        if p not in seen_plan:
            seen_plan.append(p)
    for q, lang, order in seen_plan[:profile.search_budget]:
        try:
            ids = yt.search_ids(q, start, end, language=lang, region=profile.region, order=order)
            summary["searches"] += 1
        except QuotaExceeded as e:
            summary["status"] = "partial"
            summary["errors"].append(f"quota: {e}")
            break
        except ConnectorError as e:
            summary["errors"].append(f"{q!r}: {e}")
            continue
        for vid in ids:
            found.setdefault(vid, []).append(f"youtube:search:{order}:{lang}:{q}")
    summary["ids"] = len(found)

    try:
        details = yt.video_details(list(found))
    except (QuotaExceeded, ConnectorError) as e:
        summary["status"] = "failed" if not summary["searches"] else "partial"
        summary["errors"].append(f"videos.list: {e}")
        details = []

    kept = []
    for v in details:
        pub = parse_ts(v["published_at"])
        if v["duration_s"] is None:
            summary["unverified_duration"] += 1
            continue
        if v["duration_s"] >= profile.max_duration_s:  # strictly under 15 s
            summary["rejected_duration"] += 1
            continue
        if not pub or not (start <= pub <= end):
            summary["rejected_window"] += 1
            continue
        for src in found[v["video_id"]]:
            db.upsert_video(con, v, src, topic=profile.name)
        db.add_snapshot(con, "youtube", v["video_id"], v["views"], v["likes"], v["comments"])
        kept.append(v)
    summary["verified_short"] = len(kept)
    con.commit()

    # subscriber counts for every candidate's channel (1 unit per 50 channels) -> small-channel outliers
    try:
        subs = yt.channel_subscribers(v["channel_id"] for v in kept)
        for ch, n in subs.items():
            con.execute("""INSERT INTO channel_baselines (platform, channel_id, subscribers) VALUES ('youtube',?,?)
                           ON CONFLICT(platform, channel_id) DO UPDATE SET subscribers=excluded.subscribers""", (ch, n))
    except (QuotaExceeded, ConnectorError) as e:
        summary["errors"].append(f"subscribers: {e}")

    # creator baselines for the most promising candidates (cheap: ~3 units per channel)
    kept.sort(key=lambda v: -(v["views"] or 0) / max((end - parse_ts(v["published_at"])).total_seconds() / 3600, 1))
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    done = set()
    for v in kept:
        if len(done) >= baseline_top:
            break
        ch = v["channel_id"]
        if not ch or ch in done:
            continue
        done.add(ch)
        row = con.execute("SELECT computed_at FROM channel_baselines WHERE platform='youtube' AND channel_id=?",
                          (ch,)).fetchone()
        if row and row["computed_at"] and row["computed_at"] > week_ago:
            continue
        try:
            med, n = yt.channel_median_views(ch, exclude_id=v["video_id"])
        except QuotaExceeded as e:
            summary["errors"].append(f"baseline quota: {e}")
            break
        except ConnectorError as e:
            summary["errors"].append(f"baseline {ch}: {e}")
            continue
        con.execute("""INSERT INTO channel_baselines (platform, channel_id, computed_at, median_views, sample_size)
                       VALUES ('youtube',?,?,?,?) ON CONFLICT(platform, channel_id) DO UPDATE SET
                       computed_at=excluded.computed_at, median_views=excluded.median_views,
                       sample_size=excluded.sample_size""", (ch, db.now_iso(), med, n))
    con.commit()
    summary["quota_units"] = yt.used
    db.log_run(con, "youtube", summary["status"], json.dumps(summary["errors"])[:2000],
               summary["verified_short"], yt.used)
    return summary


def refresh_snapshots(con, yt, profile, now=None):
    """Re-measure tracked videos still inside the window (1 quota unit per 50 videos)."""
    start, _ = profile.window(now)
    ids = [r["video_id"] for r in con.execute(
        "SELECT video_id FROM videos WHERE platform='youtube' AND is_mock=0 AND published_at >= ? "
        "AND COALESCE(topic,'psychology')=?", (start.isoformat().replace("+00:00", "Z"), profile.name))]
    details = yt.video_details(ids) if ids else []
    for v in details:
        db.add_snapshot(con, "youtube", v["video_id"], v["views"], v["likes"], v["comments"])
    con.commit()
    db.log_run(con, "youtube:snapshot", "ok", "", len(details), yt.used)
    return len(details)


def load_candidates(con, profile, now=None, include_mock=False):
    start, end = profile.window(now)
    rows = con.execute("""
      SELECT v.*, b.median_views AS channel_median, b.subscribers AS subscribers FROM videos v
      LEFT JOIN channel_baselines b ON b.platform=v.platform AND b.channel_id=v.channel_id
      WHERE v.duration_verified=1 AND v.duration_s < ? AND (v.is_mock=0 OR ?) AND COALESCE(v.topic,'psychology')=?""",
                       (profile.max_duration_s, int(include_mock), profile.name)).fetchall()
    cands = []
    for r in rows:
        pub = parse_ts(r["published_at"])
        if not pub or not (start <= pub <= end):
            continue
        snaps = con.execute("SELECT ts, views, likes, comments FROM snapshots WHERE platform=? AND video_id=? "
                            "ORDER BY ts", (r["platform"], r["video_id"])).fetchall()
        last = snaps[-1] if snaps else None
        c = dict(r)
        c.update(views=last["views"] if last else None, likes=last["likes"] if last else None,
                 comments=last["comments"] if last else None,
                 snapshots=[(s["ts"], s["views"]) for s in snaps], sources=json.loads(r["sources"]))
        cands.append(c)
    signals = {r["topic"]: r["value"] for r in con.execute("SELECT topic, value FROM topic_signals")}
    return score_all(cands, now=now, topic_signals=signals)


def enrich(con, yt, profile, baseline_top=15, now=None):
    """Subscribers + creator baselines for stored candidates, without new searches (cheap)."""
    cands = load_candidates(con, profile, now=now)
    chans = {c["channel_id"] for c in cands if c.get("channel_id")}
    for ch, n in yt.channel_subscribers(chans).items():
        con.execute("""INSERT INTO channel_baselines (platform, channel_id, subscribers) VALUES ('youtube',?,?)
                       ON CONFLICT(platform, channel_id) DO UPDATE SET subscribers=excluded.subscribers""", (ch, n))
    con.commit()
    done = 0
    for c in sorted(cands, key=lambda c: -(c.get("velocity_raw") or 0)):
        if done >= baseline_top:
            break
        row = con.execute("SELECT median_views FROM channel_baselines WHERE platform='youtube' AND channel_id=?",
                          (c["channel_id"],)).fetchone()
        if row and row["median_views"]:
            continue
        try:
            med, n = yt.channel_median_views(c["channel_id"], exclude_id=c["video_id"])
        except (QuotaExceeded, ConnectorError):
            break
        con.execute("""INSERT INTO channel_baselines (platform, channel_id, computed_at, median_views, sample_size)
                       VALUES ('youtube',?,?,?,?) ON CONFLICT(platform, channel_id) DO UPDATE SET
                       computed_at=excluded.computed_at, median_views=excluded.median_views,
                       sample_size=excluded.sample_size""", (c["channel_id"], db.now_iso(), med, n))
        done += 1
    con.commit()
    return yt.used
