import json, urllib.parse
from datetime import datetime, timedelta, timezone

import pytest

from radar import db
from radar.config import SearchProfile, WEIGHTS
from radar.pipeline import load_candidates, run_youtube
from radar.scoring import score_all
from radar.youtube import ConnectorError, QuotaExceeded, YouTube, parse_duration

NOW = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


class FakeAPI:
    """Stands in for the YouTube API; returns only the fixtures it is given."""

    def __init__(self, videos, search_hits=None, fail_search=None, quota_after=None):
        self.videos = {v["id"]: v for v in videos}
        self.search_hits = search_hits or list(self.videos)
        self.fail_search, self.quota_after, self.calls = fail_search, quota_after, []

    def __call__(self, url):
        ep = url.split("/v3/")[1].split("?")[0]
        q = dict(urllib.parse.parse_qsl(url.split("?", 1)[1]))
        self.calls.append(ep)
        if self.quota_after is not None and len(self.calls) > self.quota_after:
            raise QuotaExceeded("quotaExceeded")
        if ep == "search":
            if self.fail_search and q["q"] in self.fail_search:
                raise ConnectorError("HTTP 400: bad query")
            return {"items": [{"id": {"videoId": i}} for i in self.search_hits]}
        if ep == "videos":
            return {"items": [self.videos[i] for i in q["id"].split(",") if i in self.videos]}
        if ep == "channels":
            return {"items": []}
        raise AssertionError(ep)


def vid(i, dur="PT10S", age_h=48, views=1000, likes=50, comments=5, ch="c1", title="psychology fact about memory"):
    st = {"viewCount": str(views)}
    if likes is not None:
        st["likeCount"] = str(likes)
    if comments is not None:
        st["commentCount"] = str(comments)
    return {"id": i, "snippet": {"title": title, "description": "", "channelId": ch, "channelTitle": ch,
                                 "publishedAt": iso(NOW - timedelta(hours=age_h)), "thumbnails": {}},
            "contentDetails": {"duration": dur}, "statistics": st}


def profile(**kw):
    p = SearchProfile(queries=("psychology facts",), extra_view_order_queries=(), search_budget=1)
    for k, v in kw.items():
        setattr(p, k, v)
    return p


@pytest.fixture
def con(tmp_path):
    return db.connect(str(tmp_path / "t.db"))


def test_rolling_window_is_exactly_30_days():
    start, end = SearchProfile().window(NOW)
    assert end == NOW and end - start == timedelta(days=30)


@pytest.mark.parametrize("iso_d,secs", [("PT14S", 14), ("PT15S", 15), ("PT1M", 60), ("PT14.9S", 14.9),
                                         ("P0D", 0), ("PT1H2M3S", 3723), ("bogus", None)])
def test_parse_duration(iso_d, secs):
    assert parse_duration(iso_d) == secs


def test_exact_15_second_exclusion(con):
    api = FakeAPI([vid("a", "PT14S"), vid("b", "PT15S"), vid("c", "PT14.9S"), vid("d", "PT1M")])
    s = run_youtube(con, YouTube("k", fetch=api), profile(), now=NOW)
    ids = {r["video_id"] for r in con.execute("SELECT video_id FROM videos")}
    assert ids == {"a", "c"} and s["rejected_duration"] == 2


def test_outside_window_rejected(con):
    api = FakeAPI([vid("old", age_h=24 * 31), vid("new", age_h=5)])
    s = run_youtube(con, YouTube("k", fetch=api), profile(), now=NOW)
    assert s["rejected_window"] == 1 and s["verified_short"] == 1


def test_dedup_across_queries_keeps_all_sources(con):
    api = FakeAPI([vid("a")])
    p = profile(queries=("psychology facts", "human behavior facts"), search_budget=2)
    run_youtube(con, YouTube("k", fetch=api), p, now=NOW)
    rows = con.execute("SELECT sources FROM videos").fetchall()
    assert len(rows) == 1 and len(json.loads(rows[0]["sources"])) == 2


def test_hidden_likes_stay_missing_not_zero(con):
    api = FakeAPI([vid("a", likes=None, comments=None)])
    run_youtube(con, YouTube("k", fetch=api), profile(), now=NOW)
    snap = con.execute("SELECT likes, comments FROM snapshots").fetchone()
    assert snap["likes"] is None and snap["comments"] is None
    c = load_candidates(con, profile(), now=NOW)[0]
    assert "engagement" in c["missing"]


def test_score_renormalizes_missing_components():
    cands = [{"published_at": iso(NOW - timedelta(hours=40)), "views": v, "likes": None, "comments": None,
              "channel_id": f"c{v}", "title": "", "description": ""} for v in (100, 200, 300)]
    out = score_all(cands, now=NOW)
    top = out[0]
    assert set(top["components"]) == {"velocity"}
    assert top["viral_score"] == pytest.approx(100 * top["components"]["velocity"], abs=0.1)
    assert top["missing"] == [k for k in WEIGHTS if k != "velocity"]


def test_no_data_means_no_score_not_zero():
    out = score_all([{"published_at": None, "views": None, "title": "", "description": ""}], now=NOW)
    assert out[0]["viral_score"] is None


def test_velocity_compares_within_age_cohort():
    fresh = {"published_at": iso(NOW - timedelta(hours=10)), "views": 5000, "likes": None, "title": "", "description": ""}
    old = {"published_at": iso(NOW - timedelta(days=20)), "views": 500000, "likes": None, "title": "", "description": ""}
    out = {c["views"]: c for c in score_all([fresh, old], now=NOW)}
    # each is alone in its cohort, so neither is punished for age
    assert out[5000]["components"]["velocity"] == out[500000]["components"]["velocity"] == 0.5


def test_acceleration_needs_three_snapshots():
    base = {"published_at": iso(NOW - timedelta(days=3)), "views": 300, "likes": 10, "title": "", "description": ""}
    two = dict(base, snapshots=[(iso(NOW - timedelta(hours=24)), 100), (iso(NOW), 300)])
    out = score_all([two], now=NOW)
    assert "acceleration" in out[0]["missing"]


def test_confidence_lower_with_stale_snapshot():
    c1 = {"published_at": iso(NOW - timedelta(days=2)), "views": 100, "likes": 5, "title": "", "description": "",
          "snapshots": [(iso(NOW - timedelta(hours=1)), 100)]}
    c2 = dict(c1, snapshots=[(iso(NOW - timedelta(days=5)), 100)])
    a, b = score_all([c1], now=NOW)[0], score_all([c2], now=NOW)[0]
    assert a["confidence"] > b["confidence"]


def test_local_quota_budget_stops_calls():
    yt = YouTube("k", fetch=FakeAPI([vid("a")]), quota_budget=150)
    yt.search_ids("q", NOW - timedelta(days=1), NOW)
    with pytest.raises(QuotaExceeded):
        yt.search_ids("q", NOW - timedelta(days=1), NOW)


def test_quota_error_marks_run_partial(con):
    api = FakeAPI([vid("a")], quota_after=1)
    p = profile(queries=("q1", "q2"), search_budget=2)
    s = run_youtube(con, YouTube("k", fetch=api), p, now=NOW)
    assert s["status"] == "partial" and any("quota" in e for e in s["errors"])


def test_failed_query_is_reported_and_others_continue(con):
    api = FakeAPI([vid("a")], fail_search={"bad"})
    p = profile(queries=("bad", "good"), search_budget=2)
    s = run_youtube(con, YouTube("k", fetch=api), p, now=NOW)
    assert s["searches"] == 1 and s["verified_short"] == 1 and any("bad" in e for e in s["errors"])


def test_missing_key_is_not_configured():
    with pytest.raises(ConnectorError):
        YouTube("")


def test_zero_results_is_success_not_failure(con):
    api = FakeAPI([], search_hits=[])
    s = run_youtube(con, YouTube("k", fetch=api), profile(), now=NOW)
    assert s["status"] == "ok" and s["verified_short"] == 0


def test_mock_rows_hidden_unless_requested(con):
    db.upsert_video(con, {"platform": "youtube", "video_id": "m", "url": "u", "published_at": iso(NOW - timedelta(hours=3)),
                          "duration_s": 10, "duration_verified": True, "is_mock": True}, "mock")
    con.commit()
    assert load_candidates(con, profile(), now=NOW) == []
    assert len(load_candidates(con, profile(), now=NOW, include_mock=True)) == 1


def test_shortlist_limits_creator_and_ignores_hashtags():
    from radar.scoring import shortlist, subtopics
    assert subtopics("Love facts #motivation #sleep") == ["relationships"]
    cands = [{"published_at": iso(NOW - timedelta(hours=30)), "views": 1000 * i, "likes": 10 * i, "comments": 1,
              "channel_id": "same" if i < 6 else f"c{i}", "title": "memory fact", "description": ""} for i in range(1, 10)]
    picked = shortlist(score_all(cands, now=NOW), n=5)
    assert sum(1 for c in picked if c["channel_id"] == "same") <= 2


def test_icahn_flag_needs_subscribers():
    base = {"published_at": iso(NOW - timedelta(days=3)), "likes": 1, "title": "", "description": ""}
    a = dict(base, views=500_000, subscribers=40_000)    # 12.5x, small channel -> pass
    b = dict(base, views=500_000, subscribers=2_000_000)  # big channel -> fail
    c = dict(base, views=500_000)                        # unknown subs -> None, not False
    out = {id(x): x for x in score_all([a, b, c], now=NOW)}
    assert out[id(a)]["icahn"] is True and out[id(b)]["icahn"] is False and out[id(c)]["icahn"] is None
