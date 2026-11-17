"""Upload finished videos to a YouTube channel (YouTube Data API v3, stdlib only).

Sign-in uses Google's device flow: the factory prints a short code, the owner opens google.com/device on any phone
or laptop and approves. That works over Tailscale, where a loopback redirect to the server would not.
The OAuth client ("Desktop app" or "TVs and Limited Input devices"; both worked 2026-11) comes from the environment
(YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, read from .env). Device flow does not allow the narrow
youtube.upload scope, so we ask for the `youtube` scope (manage the account), which videos.insert accepts.

Tokens live in data/youtube/<account>.json (gitignored, mode 600). Nothing here prints a secret or token.
Note: videos uploaded from an API project that has not passed Google's audit are locked to private;
the owner flips them public in YouTube Studio.
"""
from __future__ import annotations

import json
import mimetypes
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .config import ROOT

DEVICE_URL = "https://oauth2.googleapis.com/device/code"
TOKEN_URL = "https://oauth2.googleapis.com/token"
API = "https://www.googleapis.com/youtube/v3"
UPLOAD_API = "https://www.googleapis.com/upload/youtube/v3"
SCOPE = "https://www.googleapis.com/auth/youtube"
CHUNK = 8 * 1024 * 1024          # multiple of 256 KiB, as the resumable protocol requires
CATEGORIES = {"film": "1", "entertainment": "24", "education": "27", "people": "22"}
PRIVACY = ("private", "unlisted", "public")


class YouTubeError(Exception):
    """API or auth failure; the message never contains tokens."""


def token_dir() -> Path:
    return Path(os.environ.get("CF_YOUTUBE_DIR") or os.path.join(ROOT, "data", "youtube"))


@dataclass
class Response:
    status: int
    headers: dict
    body: bytes

    def json(self) -> dict:
        return json.loads(self.body or b"{}")


def _http(method: str, url: str, headers: dict | None = None, body: bytes | None = None,
          timeout: float = 120) -> Response:
    """One HTTP call; never raises for HTTP status codes (308 included), only for network errors."""
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):       # 308 is "resume incomplete" here, not a redirect
            return None

    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(req, timeout=timeout) as r:
            return Response(r.status, {k.lower(): v for k, v in r.headers.items()}, r.read())
    except urllib.error.HTTPError as e:
        return Response(e.code, {k.lower(): v for k, v in (e.headers or {}).items()}, e.read() or b"")


def _err(r: Response, what: str) -> YouTubeError:
    msg = None
    try:
        d = r.json()
        e = d.get("error")
        msg = e.get("message") if isinstance(e, dict) else (d.get("error_description") or e)
    except Exception:
        pass
    return YouTubeError(f"{what}: HTTP {r.status}" + (f" ({msg})" if msg else ""))


def _safe_json(r: Response) -> dict:
    try:
        return r.json()
    except Exception:
        return {}


@dataclass
class Client:
    client_id: str
    client_secret: str

    @classmethod
    def from_env(cls) -> "Client":
        cid = os.environ.get("YOUTUBE_CLIENT_ID", "").strip()
        sec = os.environ.get("YOUTUBE_CLIENT_SECRET", "").strip()
        if not cid or not sec:
            raise YouTubeError("YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET are not set in .env")
        return cls(cid, sec)


# ---------------------------------------------------------------- sign-in (device flow)

def start_device(client: Client, http=_http) -> dict:
    body = urllib.parse.urlencode({"client_id": client.client_id, "scope": SCOPE}).encode()
    r = http("POST", DEVICE_URL, {"Content-Type": "application/x-www-form-urlencoded"}, body)
    if r.status != 200:
        raise _err(r, "device code")
    return r.json()          # device_code, user_code, verification_url, expires_in, interval


def poll_device(client: Client, device: dict, http=_http, sleep: Callable[[float], None] = time.sleep,
                clock: Callable[[], float] = time.monotonic) -> dict:
    """Wait until the owner approves; return the token dict (with an absolute expires_at)."""
    interval = float(device.get("interval") or 5)
    deadline = clock() + float(device.get("expires_in") or 1800)
    body = urllib.parse.urlencode({
        "client_id": client.client_id, "client_secret": client.client_secret,
        "device_code": device["device_code"],
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code"}).encode()
    while clock() < deadline:
        sleep(interval)
        r = http("POST", TOKEN_URL, {"Content-Type": "application/x-www-form-urlencoded"}, body)
        if r.status == 200:
            return _stamp(r.json())
        code = _safe_json(r).get("error")
        if code == "authorization_pending":
            continue
        if code == "slow_down":
            interval += 5
            continue
        if code == "access_denied":
            raise YouTubeError("sign-in was declined")
        raise _err(r, "device sign-in")
    raise YouTubeError("sign-in code expired before it was approved")


def _stamp(tok: dict) -> dict:
    tok = dict(tok)
    tok["expires_at"] = time.time() + float(tok.get("expires_in") or 3600) - 60
    return tok


def save_token(account: str, tok: dict) -> Path:
    d = token_dir()
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{account}.json"
    tmp = p.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(tok, f)
    os.replace(tmp, p)
    return p


def load_token(account: str) -> dict:
    p = token_dir() / f"{account}.json"
    if not p.exists():
        raise YouTubeError(f"account '{account}' is not signed in yet (run: bin/youtube.py auth {account})")
    return json.loads(p.read_text())


class Session:
    """Authorized calls for one signed-in account; refreshes the access token when needed."""

    def __init__(self, account: str, client: Client | None = None, http=_http):
        self.account, self.http = account, http
        self.client = client or Client.from_env()
        self.tok = load_token(account)

    def access_token(self) -> str:
        if self.tok.get("access_token") and time.time() < float(self.tok.get("expires_at") or 0):
            return self.tok["access_token"]
        if not self.tok.get("refresh_token"):
            raise YouTubeError("no refresh token stored; sign in again")
        body = urllib.parse.urlencode({
            "client_id": self.client.client_id, "client_secret": self.client.client_secret,
            "refresh_token": self.tok["refresh_token"], "grant_type": "refresh_token"}).encode()
        r = self.http("POST", TOKEN_URL, {"Content-Type": "application/x-www-form-urlencoded"}, body)
        if r.status != 200:
            raise _err(r, "token refresh")
        new = _stamp(r.json())
        new.setdefault("refresh_token", self.tok["refresh_token"])
        self.tok = new
        save_token(self.account, new)
        return new["access_token"]

    def call(self, method: str, url: str, params: dict | None = None, payload=None,
             headers: dict | None = None, raw: bytes | None = None) -> Response:
        if params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
        h = {"Authorization": f"Bearer {self.access_token()}", **(headers or {})}
        body = raw
        if payload is not None:
            body = json.dumps(payload).encode()
            h["Content-Type"] = "application/json; charset=UTF-8"
        return self.http(method, url, h, body)

    def api(self, method: str, path: str, params: dict | None = None, payload=None) -> dict:
        r = self.call(method, f"{API}/{path}", params, payload)
        if r.status not in (200, 201, 204):
            raise _err(r, f"{method} {path}")
        return r.json() if r.body else {}

    # ------------------------------------------------------------ reads

    def channel(self) -> dict:
        items = self.api("GET", "channels", {"part": "snippet,status", "mine": "true"}).get("items") or []
        if not items:
            raise YouTubeError("this Google account has no YouTube channel")
        return items[0]

    def playlist_id(self, title: str, create: bool = True, privacy: str = "public") -> str | None:
        token = None
        while True:
            params = {"part": "snippet", "mine": "true", "maxResults": 50}
            if token:
                params["pageToken"] = token
            d = self.api("GET", "playlists", params)
            for it in d.get("items") or []:
                if it["snippet"]["title"].strip().lower() == title.strip().lower():
                    return it["id"]
            token = d.get("nextPageToken")
            if not token:
                break
        if not create:
            return None
        d = self.api("POST", "playlists", {"part": "snippet,status"},
                     {"snippet": {"title": title}, "status": {"privacyStatus": privacy}})
        return d["id"]

    # ------------------------------------------------------------ writes

    def upload(self, path: str, meta: dict, chunk: int = CHUNK,
               progress: Callable[[int, int], None] | None = None, retries: int = 6) -> dict:
        """Resumable upload; returns the created video resource."""
        size = os.path.getsize(path)
        ctype = mimetypes.guess_type(path)[0] or "video/mp4"
        r = self.call("POST", f"{UPLOAD_API}/videos", {"uploadType": "resumable", "part": ",".join(meta)},
                      meta, {"X-Upload-Content-Length": str(size), "X-Upload-Content-Type": ctype})
        if r.status != 200 or not r.headers.get("location"):
            raise _err(r, "start upload")
        loc = r.headers["location"]
        pos, fails = 0, 0
        with open(path, "rb") as f:
            while True:
                f.seek(pos)
                data = f.read(chunk)
                end = pos + len(data) - 1
                try:
                    r = self.call("PUT", loc, headers={"Content-Length": str(len(data)),
                                                       "Content-Range": f"bytes {pos}-{end}/{size}"}, raw=data)
                except OSError:
                    r = Response(0, {}, b"")
                if r.status in (200, 201):
                    if progress:
                        progress(size, size)
                    return r.json()
                if r.status == 308:
                    pos = _next_byte(r)
                    fails = 0
                    if progress:
                        progress(pos, size)
                    continue
                if r.status in (0, 500, 502, 503, 504) and fails < retries:
                    fails += 1
                    time.sleep(min(60, 2 ** fails))
                    try:
                        q = self.call("PUT", loc, headers={"Content-Length": "0", "Content-Range": f"bytes */{size}"})
                    except OSError:
                        continue
                    if q.status in (200, 201):
                        return q.json()
                    if q.status == 308:
                        pos = _next_byte(q)
                        continue
                raise _err(r, "upload")

    def set_thumbnail(self, video_id: str, image: str) -> dict:
        ctype = mimetypes.guess_type(image)[0] or "image/jpeg"
        raw = Path(image).read_bytes()
        if len(raw) > 2 * 1024 * 1024:
            raise YouTubeError("thumbnail is over 2 MB")
        r = self.call("POST", f"{UPLOAD_API}/thumbnails/set", {"videoId": video_id},
                      headers={"Content-Type": ctype}, raw=raw)
        if r.status != 200:
            raise _err(r, "thumbnail (the channel must be phone-verified for custom thumbnails)")
        return r.json()

    def add_to_playlist(self, playlist_id: str, video_id: str, position: int | None = None) -> dict:
        snip = {"playlistId": playlist_id, "resourceId": {"kind": "youtube#video", "videoId": video_id}}
        if position is not None:
            snip["position"] = position
        return self.api("POST", "playlistItems", {"part": "snippet"}, {"snippet": snip})


def _next_byte(r: Response) -> int:
    rng = r.headers.get("range")          # "bytes=0-12345"
    return int(rng.rsplit("-", 1)[1]) + 1 if rng else 0


# ---------------------------------------------------------------- upload spec

@dataclass
class Spec:
    """What to publish. Loaded from a JSON file; relative paths resolve next to that file."""
    file: str
    title: str
    description: str = ""
    tags: list = field(default_factory=list)
    category: str = "film"
    privacy: str = "private"
    language: str = "en"
    thumbnail: str | None = None
    playlist: str | None = None
    publish_at: str | None = None          # RFC 3339, needs privacy "private"
    made_for_kids: bool = False
    synthetic: bool | None = None          # status.containsSyntheticMedia (realistic altered/synthetic content)

    @classmethod
    def load(cls, path: str) -> "Spec":
        d = json.loads(Path(path).read_text())
        base = Path(path).resolve().parent
        for k in ("file", "thumbnail"):
            if d.get(k) and not os.path.isabs(d[k]):
                d[k] = str(base / d[k])
        known = set(cls.__dataclass_fields__)
        extra = set(d) - known
        if extra:
            raise YouTubeError(f"unknown fields in spec: {', '.join(sorted(extra))}")
        return cls(**d)

    def problems(self) -> list[str]:
        out = []
        if not os.path.isfile(self.file):
            out.append(f"video file not found: {self.file}")
        if not self.title.strip():
            out.append("title is empty")
        if len(self.title) > 100:
            out.append(f"title is {len(self.title)} chars (max 100)")
        if "<" in self.title + self.description or ">" in self.title + self.description:
            out.append("title/description may not contain < or >")
        if len(self.description.encode()) > 5000:
            out.append("description is over 5000 bytes")
        if sum(len(t) + (2 if " " in t else 0) for t in self.tags) + max(0, len(self.tags) - 1) > 500:
            out.append("tags are over 500 characters together")
        if self.category not in CATEGORIES and not str(self.category).isdigit():
            out.append(f"unknown category '{self.category}' (use {', '.join(CATEGORIES)} or a numeric id)")
        if self.privacy not in PRIVACY:
            out.append(f"privacy must be one of {', '.join(PRIVACY)}")
        if self.publish_at and self.privacy != "private":
            out.append("publish_at needs privacy 'private'")
        if self.thumbnail and not os.path.isfile(self.thumbnail):
            out.append(f"thumbnail not found: {self.thumbnail}")
        return out

    def resource(self) -> dict:
        status = {"privacyStatus": self.privacy, "selfDeclaredMadeForKids": bool(self.made_for_kids),
                  "embeddable": True}
        if self.publish_at:
            status["publishAt"] = self.publish_at
        if self.synthetic is not None:
            status["containsSyntheticMedia"] = bool(self.synthetic)
        return {"snippet": {"title": self.title, "description": self.description, "tags": list(self.tags),
                            "categoryId": CATEGORIES.get(self.category, str(self.category)),
                            "defaultLanguage": self.language, "defaultAudioLanguage": self.language},
                "status": status}


def publish(session: Session, spec: Spec, progress=None) -> dict:
    """Upload + thumbnail + playlist. Thumbnail/playlist failures are reported, not fatal."""
    bad = spec.problems()
    if bad:
        raise YouTubeError("; ".join(bad))
    video = session.upload(spec.file, spec.resource(), progress=progress)
    vid = video["id"]
    out = {"id": vid, "url": f"https://youtu.be/{vid}", "studio": f"https://studio.youtube.com/video/{vid}/edit",
           "privacy": (video.get("status") or {}).get("privacyStatus"), "warnings": []}
    if spec.thumbnail:
        try:
            session.set_thumbnail(vid, spec.thumbnail)
        except YouTubeError as e:
            out["warnings"].append(str(e))
    if spec.playlist:
        try:
            session.add_to_playlist(session.playlist_id(spec.playlist), vid)
        except YouTubeError as e:
            out["warnings"].append(str(e))
    if out["privacy"] != spec.privacy:
        out["warnings"].append(f"YouTube set the video to '{out['privacy']}' (unaudited API project); "
                               "make it public in YouTube Studio")
    log = token_dir() / "uploads.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "a") as f:
        f.write(json.dumps({"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "account": session.account,
                            "file": spec.file, "title": spec.title, **out}) + "\n")
    return out
