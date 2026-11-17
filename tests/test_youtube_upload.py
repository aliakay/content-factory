import json
import time

import pytest

from factory import youtube_upload as yt
from factory.youtube_upload import Response


def J(status, d, headers=None):
    return Response(status, headers or {}, json.dumps(d).encode())


class FakeHTTP:
    """Replays queued responses and records requests."""

    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def __call__(self, method, url, headers=None, body=None, timeout=120):
        self.calls.append((method, url, dict(headers or {}), body))
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


@pytest.fixture
def tokdir(tmp_path, monkeypatch):
    monkeypatch.setenv("CF_YOUTUBE_DIR", str(tmp_path / "yt"))
    monkeypatch.setattr(yt.time, "sleep", lambda s: None)
    return tmp_path / "yt"


CLIENT = yt.Client("cid", "sec")


def test_device_flow_waits_and_slows_down():
    http = FakeHTTP([J(428, {"error": "authorization_pending"}), J(403, {"error": "slow_down"}),
                     J(200, {"access_token": "a", "refresh_token": "r", "expires_in": 3600})])
    waits = []
    tok = yt.poll_device(CLIENT, {"device_code": "d", "interval": 5, "expires_in": 600}, http=http,
                         sleep=waits.append, clock=lambda: 0)
    assert tok["refresh_token"] == "r" and tok["expires_at"] > time.time()
    assert waits == [5.0, 5.0, 10.0]


def test_device_flow_declined():
    http = FakeHTTP([J(403, {"error": "access_denied"})])
    with pytest.raises(yt.YouTubeError, match="declined"):
        yt.poll_device(CLIENT, {"device_code": "d"}, http=http, sleep=lambda s: None, clock=lambda: 0)


def test_token_saved_private_and_refreshed(tokdir):
    p = yt.save_token("troia", {"access_token": "old", "refresh_token": "r", "expires_at": 0})
    assert (p.stat().st_mode & 0o777) == 0o600
    http = FakeHTTP([J(200, {"access_token": "new", "expires_in": 3600}), J(200, {"items": [{"id": "UC1"}]})])
    s = yt.Session("troia", CLIENT, http=http)
    assert s.channel()["id"] == "UC1"
    assert http.calls[1][2]["Authorization"] == "Bearer new"
    saved = yt.load_token("troia")
    assert saved["access_token"] == "new" and saved["refresh_token"] == "r"


def test_not_signed_in(tokdir):
    with pytest.raises(yt.YouTubeError, match="not signed in"):
        yt.Session("nobody", CLIENT)


def _session(tokdir, replies):
    yt.save_token("troia", {"access_token": "a", "refresh_token": "r", "expires_at": time.time() + 999})
    http = FakeHTTP(replies)
    return yt.Session("troia", CLIENT, http=http), http


def test_resumable_upload_chunks_and_recovers(tokdir, tmp_path):
    f = tmp_path / "v.mp4"
    f.write_bytes(b"x" * 10)
    s, http = _session(tokdir, [
        Response(200, {"location": "https://up/1"}, b""),
        Response(308, {"range": "bytes=0-3"}, b""),          # first 4 bytes stored
        Response(503, {}, b""),                               # server hiccup
        Response(308, {"range": "bytes=0-5"}, b""),           # status query: 6 bytes stored
        J(200, {"id": "VID", "status": {"privacyStatus": "private"}}),
    ])
    v = s.upload(str(f), {"snippet": {}, "status": {}}, chunk=4)
    assert v["id"] == "VID"
    start = http.calls[0]
    assert "uploadType=resumable" in start[1] and "part=snippet%2Cstatus" in start[1]
    assert start[2]["X-Upload-Content-Length"] == "10"
    ranges = [c[2].get("Content-Range") for c in http.calls[1:]]
    assert ranges == ["bytes 0-3/10", "bytes 4-7/10", "bytes */10", "bytes 6-9/10"]


def test_spec_validation_and_resource(tmp_path):
    (tmp_path / "v.mp4").write_bytes(b"x")
    p = tmp_path / "spec.json"
    p.write_text(json.dumps({"file": "v.mp4", "title": "Ep 1", "tags": ["a b"], "playlist": "S"}))
    spec = yt.Spec.load(str(p))
    assert spec.problems() == [] and spec.file == str(tmp_path / "v.mp4")
    r = spec.resource()
    assert r["status"] == {"privacyStatus": "private", "selfDeclaredMadeForKids": False, "embeddable": True}
    assert r["snippet"]["categoryId"] == "1" and r["snippet"]["defaultAudioLanguage"] == "en"
    bad = yt.Spec(file="nope.mp4", title="<x>" + "y" * 100, privacy="public", publish_at="2026-12-01T18:00:00Z")
    msgs = " | ".join(bad.problems())
    assert "not found" in msgs and "max 100" in msgs and "< or >" in msgs and "publish_at" in msgs
    p.write_text(json.dumps({"file": "v.mp4", "title": "t", "colour": 1}))
    with pytest.raises(yt.YouTubeError, match="unknown fields"):
        yt.Spec.load(str(p))


def test_publish_adds_playlist_and_warns_on_lock(tokdir, tmp_path):
    (tmp_path / "v.mp4").write_bytes(b"x" * 3)
    spec = yt.Spec(file=str(tmp_path / "v.mp4"), title="Ep 1", privacy="public", playlist="The Unopened Letter")
    s, http = _session(tokdir, [
        Response(200, {"location": "https://up/1"}, b""),
        J(200, {"id": "VID", "status": {"privacyStatus": "private"}}),
        J(200, {"items": [{"id": "PL9", "snippet": {"title": "the unopened letter"}}]}),
        J(200, {"id": "PI1"}),
    ])
    out = yt.publish(s, spec)
    assert out["id"] == "VID" and out["url"] == "https://youtu.be/VID"
    assert json.loads(http.calls[-1][3])["snippet"]["playlistId"] == "PL9"
    assert any("public in YouTube Studio" in w for w in out["warnings"])
    assert [json.loads(x)["id"] for x in (tokdir / "uploads.jsonl").read_text().splitlines()] == ["VID"]


def test_playlist_created_when_missing(tokdir):
    s, http = _session(tokdir, [J(200, {"items": []}), J(200, {"id": "PLnew"})])
    assert s.playlist_id("New Series") == "PLnew"
    assert json.loads(http.calls[1][3])["snippet"]["title"] == "New Series"


def test_error_message_has_no_token(tokdir):
    s, _ = _session(tokdir, [J(403, {"error": {"message": "quotaExceeded"}})])
    with pytest.raises(yt.YouTubeError) as e:
        s.channel()
    assert "quotaExceeded" in str(e.value) and "Bearer" not in str(e.value)
