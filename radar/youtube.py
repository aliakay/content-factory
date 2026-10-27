"""YouTube Data API v3 connector (official endpoints only)."""
import json, re, statistics, urllib.error, urllib.parse, urllib.request

API = "https://www.googleapis.com/youtube/v3/"
COST = {"search": 100, "videos": 1, "channels": 1, "playlistItems": 1}  # quota units per call
DAILY_QUOTA = 10_000


class QuotaExceeded(RuntimeError):
    pass


class ConnectorError(RuntimeError):
    pass


def parse_duration(iso):
    """ISO 8601 duration (PT1M5S, P0D, PT14.5S ...) -> seconds, or None if unparseable."""
    if not iso:
        return None
    m = re.fullmatch(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?)?", iso)
    if not m:
        return None
    d, h, mi, s = m.groups()
    return int(d or 0) * 86400 + int(h or 0) * 3600 + int(mi or 0) * 60 + float(s or 0)


def http_get(url):
    try:
        return json.load(urllib.request.urlopen(url, timeout=30))
    except urllib.error.HTTPError as e:
        body = e.read()
        try:
            err = json.loads(body).get("error", {})
        except ValueError:
            err = {"message": body[:200].decode(errors="replace")}
        reasons = {x.get("reason") for x in err.get("errors", [])}
        if e.code == 403 and reasons & {"quotaExceeded", "dailyLimitExceeded"}:
            raise QuotaExceeded(err.get("message", "quota exceeded"))
        raise ConnectorError(f"HTTP {e.code}: {err.get('message')}")
    except urllib.error.URLError as e:
        raise ConnectorError(f"network error: {e.reason}")


class YouTube:
    def __init__(self, api_key, fetch=http_get, quota_budget=DAILY_QUOTA):
        if not api_key:
            raise ConnectorError("YOUTUBE_API_KEY is not configured")
        self.key, self.fetch, self.budget, self.used = api_key, fetch, quota_budget, 0

    def _call(self, endpoint, **params):
        cost = COST[endpoint]
        if self.used + cost > self.budget:
            raise QuotaExceeded(f"local budget reached ({self.used}/{self.budget} units)")
        params = {k: v for k, v in params.items() if v is not None}
        url = API + endpoint + "?" + urllib.parse.urlencode({**params, "key": self.key})
        data = self.fetch(url)
        self.used += cost
        return data

    def search_ids(self, q, published_after, published_before, language=None, region=None,
                   order="relevance", max_results=50):
        data = self._call("search", part="snippet", type="video", q=q, order=order,
                          publishedAfter=published_after.strftime("%Y-%m-%dT%H:%M:%SZ"),
                          publishedBefore=published_before.strftime("%Y-%m-%dT%H:%M:%SZ"),
                          videoDuration="short",  # broad prefilter only: means < 4 minutes
                          relevanceLanguage=language, regionCode=region, maxResults=max_results)
        return [it["id"]["videoId"] for it in data.get("items", []) if it.get("id", {}).get("videoId")]

    def video_details(self, ids):
        """Full details for up to any number of ids (batched by 50). Only real API fields are used."""
        out = []
        for i in range(0, len(ids), 50):
            data = self._call("videos", part="snippet,contentDetails,statistics", id=",".join(ids[i:i + 50]))
            for it in data.get("items", []):
                sn, cd, st = it.get("snippet", {}), it.get("contentDetails", {}), it.get("statistics", {})
                dur = parse_duration(cd.get("duration"))
                as_int = lambda k: int(st[k]) if k in st else None  # hidden counts stay None
                out.append({
                    "platform": "youtube", "video_id": it["id"],
                    "url": f"https://www.youtube.com/shorts/{it['id']}",
                    "title": sn.get("title"), "description": sn.get("description"),
                    "channel_id": sn.get("channelId"), "channel_title": sn.get("channelTitle"),
                    "published_at": sn.get("publishedAt"), "duration_s": dur,
                    "duration_verified": dur is not None,
                    "language": sn.get("defaultAudioLanguage") or sn.get("defaultLanguage"),
                    "thumbnail": (sn.get("thumbnails", {}).get("high") or {}).get("url"),
                    "views": as_int("viewCount"), "likes": as_int("likeCount"), "comments": as_int("commentCount"),
                })
        return out

    def channel_subscribers(self, channel_ids):
        """{channel_id: subscriber count or None if hidden} via channels.list (1 unit per 50 channels)."""
        out = {}
        ids = sorted({c for c in channel_ids if c})
        for i in range(0, len(ids), 50):
            for it in self._call("channels", part="statistics", id=",".join(ids[i:i + 50])).get("items", []):
                st = it.get("statistics", {})
                out[it["id"]] = None if st.get("hiddenSubscriberCount") else int(st.get("subscriberCount", 0))
        return out

    def channel_median_views(self, channel_id, exclude_id=None, comparable_max_s=60, n=10):
        """Median views of the creator's latest `n` comparable shorts (excluding the candidate)."""
        ch = self._call("channels", part="contentDetails", id=channel_id).get("items", [])
        if not ch:
            return None, 0
        uploads = ch[0]["contentDetails"]["relatedPlaylists"]["uploads"]
        items = self._call("playlistItems", part="contentDetails", playlistId=uploads, maxResults=50).get("items", [])
        ids = [x["contentDetails"]["videoId"] for x in items if x["contentDetails"]["videoId"] != exclude_id]
        vids = [v for v in self.video_details(ids)
                if v["duration_s"] is not None and v["duration_s"] < comparable_max_s and v["views"] is not None][:n]
        if len(vids) < 3:
            return None, len(vids)
        return statistics.median(v["views"] for v in vids), len(vids)
