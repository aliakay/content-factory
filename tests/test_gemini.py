"""Google Gemini as the second media provider: the key, the routing per capability, and the Interactions calls.

Nothing here reaches the network: `_req` is faked with the response shape the API documents (`steps` ->
`model_output` -> the last block of the asked type), so the request bodies and the ledger are what is checked.
"""
import json, sqlite3

import pytest

from factory import accounts, credits, eleven, gemini, mediaprov


@pytest.fixture
def users(tmp_path, monkeypatch):
    f = tmp_path / "users.json"
    f.write_text(json.dumps({"secret": "x", "users": {"ali": {"name": "Ali", "role": "owner"}}}))
    monkeypatch.setattr(accounts, "USERS", str(f))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    return f


@pytest.fixture
def con(tmp_path):
    c = sqlite3.connect(tmp_path / "t.db")
    c.row_factory = sqlite3.Row
    c.executescript(credits.SCHEMA)
    credits.ensure(c)
    return c


def _resp(kind, data=b"media", mime="image/png", iid="int_1", status="completed"):
    import base64
    return {"id": iid, "status": status, "model": "m",
            "steps": [{"type": "user_input", "content": [{"type": "text", "text": "p"}]},
                      {"type": "model_output", "content": [
                          {"type": "text", "text": "here you go"},
                          {"type": kind, "mime_type": mime, "data": base64.b64encode(data).decode()}]}]}


# ---------------------------------------------------------------- the key
def test_a_key_is_saved_per_user_and_verified(users):
    assert not accounts.gemini_status("ali")["connected"]
    st = accounts.set_gemini_key("ali", "AIza" + "x" * 35)
    assert st["connected"] and st["mine"] and st["tail"].endswith("xxxx")
    assert not accounts.gemini_key("cem")
    assert accounts.set_gemini_key("ali", "")["connected"] is False
    with pytest.raises(ValueError):
        accounts.set_gemini_key("ali", "short")


def test_the_owner_may_use_an_env_key(users, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "AIza" + "y" * 35)
    st = accounts.gemini_status("ali")
    assert st["connected"] and st["env"] and not st["mine"]
    assert gemini.key("ali").endswith("yyyy")


def test_no_key_says_where_to_put_one(users):
    with pytest.raises(gemini.GeminiError) as e:
        gemini.key("ali")
    assert "Hesaplar" in str(e.value)


# ---------------------------------------------------------------- who makes what
def test_everything_stays_on_elevenlabs_by_default(users):
    assert mediaprov.settings("ali") == {k: "elevenlabs" for k in mediaprov.KINDS}
    assert mediaprov.choice("image", "ali") == "elevenlabs"


def test_gemini_needs_a_key_before_it_can_be_picked(users):
    with pytest.raises(ValueError, match="Gemini"):
        mediaprov.set_settings("ali", {"image": "gemini"})
    accounts.set_gemini_key("ali", "AIza" + "z" * 35)
    assert mediaprov.set_settings("ali", {"image": "gemini"})["image"] == "gemini"
    assert mediaprov.settings("ali")["video"] == "elevenlabs"          # the others are untouched
    assert mediaprov.ready("ali")["gemini"] is True
    with pytest.raises(ValueError):
        mediaprov.set_settings("ali", {"sound": "gemini"})             # not a capability we route


# ---------------------------------------------------------------- the calls
def test_an_image_asks_for_the_aspect_and_the_size(monkeypatch):
    seen = {}

    def fake_req(path, body=None, api_key=None, timeout=600, method=None):
        seen.update({"path": path, "body": body})
        return _resp("image", b"PNGDATA")

    monkeypatch.setattr(gemini, "_req", fake_req)
    data, mime, iid = gemini.image("a red scarf", aspect="9:16", size="2K")
    assert (data, mime, iid) == (b"PNGDATA", "image/png", "int_1")
    assert seen["path"] == "/interactions"
    assert seen["body"]["model"] == gemini.DEFAULT["image"] and seen["body"]["input"] == "a red scarf"
    assert seen["body"]["response_format"] == {"type": "image", "mime_type": "image/png",
                                               "aspect_ratio": "9:16", "image_size": "2K"}


def test_a_reference_continues_the_earlier_picture_or_goes_inline(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(gemini, "_req", lambda path, body=None, api_key=None, timeout=600, method=None:
                        seen.update({"body": body}) or _resp("image"))
    gemini.image("same girl", refs=["gen:int_7"])
    assert seen["body"]["previous_interaction_id"] == "int_7" and seen["body"]["input"] == "same girl"
    ref = tmp_path / "plate.png"
    ref.write_bytes(b"png-bytes")
    gemini.image("same girl, dusk", refs=[str(ref)])
    blocks = seen["body"]["input"]
    assert blocks[0] == {"type": "text", "text": "same girl, dusk"}
    assert blocks[1]["type"] == "image" and blocks[1]["mime_type"] == "image/png" and blocks[1]["data"]


def test_speech_sends_the_voice_and_the_style(monkeypatch):
    seen = {}
    monkeypatch.setattr(gemini, "_req", lambda path, body=None, api_key=None, timeout=600, method=None:
                        seen.update({"body": body}) or _resp("audio", b"WAV", "audio/wav"))
    data, mime, _ = gemini.tts("Merhaba dünya", voice="Kore", style="cheerful")
    assert (data, mime) == (b"WAV", "audio/wav")
    body = seen["body"]
    assert body["response_format"] == {"type": "audio"}
    assert body["generation_config"]["speech_config"] == [{"voice": "Kore"}]
    assert body["input"][0]["content"][0]["annotations"] == [{"type": "speech_metadata", "style": "cheerful"}]


def test_a_clip_asks_for_seconds_and_a_resolution(monkeypatch):
    seen = {}
    monkeypatch.setattr(gemini, "_req", lambda path, body=None, api_key=None, timeout=600, method=None:
                        seen.update({"body": body}) or _resp("video", b"MP4", "video/mp4"))
    data, mime, iid = gemini.video("the tank fills", seconds=8, aspect="9:16", start="gen:int_3")
    assert mime == "video/mp4" and iid == "int_1"
    assert seen["body"]["response_format"] == {"type": "video", "aspect_ratio": "9:16", "duration": "8s",
                                               "resolution": "1080p"}
    assert seen["body"]["previous_interaction_id"] == "int_3"


def test_music_is_one_lyria_call(monkeypatch):
    seen = {}
    monkeypatch.setattr(gemini, "_req", lambda path, body=None, api_key=None, timeout=600, method=None:
                        seen.update({"body": body}) or _resp("audio", b"MP3", "audio/mpeg"))
    data, mime, _ = gemini.music("slow piano", 20)
    assert mime == "audio/mpeg" and seen["body"] == {"model": gemini.DEFAULT["music"], "input": "slow piano"}


def test_a_reply_without_media_says_what_came_back(monkeypatch):
    monkeypatch.setattr(gemini, "_req", lambda *a, **k: {"id": "i", "status": "completed",
                                                         "steps": [{"type": "model_output",
                                                                    "content": [{"type": "text", "text": "I cannot"}]}]})
    with pytest.raises(gemini.GeminiError, match="I cannot"):
        gemini.image("x")


def test_a_failed_interaction_is_an_error(monkeypatch):
    monkeypatch.setattr(gemini, "_req", lambda *a, **k: {"id": "i", "status": "failed", "error": "moderated"})
    with pytest.raises(gemini.GeminiError, match="moderated"):
        gemini.image("x")


# ---------------------------------------------------------------- the ledger (dollars, not credits)
def test_a_picture_is_recorded_in_dollars(con):
    usd = gemini.price("image", "gemini-nano-banana-2.1", size="2K")
    assert usd == 0.067                                    # list price, 2K
    gemini.guard(con, usd)
    gemini.record(con, "image", "gemini-nano-banana-2.1", 1, "img", usd, "a red scarf")
    row = con.execute("SELECT kind, model, units, unit, usd FROM gemini_ledger").fetchone()
    assert tuple(row) == ("image", "gemini-nano-banana-2.1", 1, "img", 0.067)
    assert gemini.month_usd(con) == 0.067
    assert con.execute("SELECT COUNT(*) FROM eleven_ledger").fetchone()[0] == 0     # the credit ledger is untouched


def test_video_prices_follow_the_resolution():
    assert gemini.price("video", "gemini-omni-1.2-flash", 10, resolution="720p") == 0.7
    assert gemini.price("video", "gemini-omni-1.2-flash", 10, resolution="1080p") == 1.04
    assert gemini.price("music", "lyria-3-clip-preview") == 0.04


def test_the_monthly_ceiling_refuses_a_call(con, monkeypatch):
    monkeypatch.setattr(gemini, "MONTHLY_USD", 0.5)
    gemini.record(con, "image", "gemini-nano-banana-2.1", 1, "img", 0.4)
    gemini.guard(con, 0.05)
    with pytest.raises(gemini.GeminiError, match="aylık"):
        gemini.guard(con, 0.2)


# ---------------------------------------------------------------- the routing inside eleven.py
def test_eleven_hands_an_image_to_gemini_when_chosen(users, con, tmp_path, monkeypatch):
    accounts.set_gemini_key("ali", "AIza" + "q" * 35)
    mediaprov.set_settings("ali", {"image": "gemini"})
    monkeypatch.setattr(eleven, "OUT", str(tmp_path / "assets"))
    monkeypatch.setattr(accounts, "eleven", lambda aid=None: {"type": "connector", "owner": "ali", "shared": True})
    monkeypatch.setattr(accounts, "can_use", lambda aid=None, uid=None: True)
    monkeypatch.setattr(gemini, "image", lambda prompt, model=None, aspect="9:16", refs=(), size="2K":
                        (b"PNG", "image/png", "int_9"))
    path, cost, flow, node = eleven.image(con, "a red scarf", 200, "ali", aspect="9:16")
    assert path.endswith(".png") and open(path, "rb").read() == b"PNG"
    assert (cost, flow, node) == (0.0, None, "gen:int_9")     # Gemini: no credits deducted
    assert json.load(open(path + ".json"))["node_id"] == "gen:int_9"
    assert gemini.month_usd(con) == 0.067                     # the dollar ledger has it


def test_eleven_hands_speech_to_gemini_when_chosen(users, con, tmp_path, monkeypatch):
    accounts.set_gemini_key("ali", "AIza" + "w" * 35)
    mediaprov.set_settings("ali", {"voice": "gemini"})
    monkeypatch.setattr(eleven, "OUT", str(tmp_path / "assets"))
    monkeypatch.setattr(accounts, "eleven", lambda aid=None: {"type": "connector", "owner": "ali", "shared": True})
    monkeypatch.setattr(accounts, "can_use", lambda aid=None, uid=None: True)
    monkeypatch.setattr(gemini, "tts", lambda text, voice="Kore", model=None, style=None: (b"WAV", "audio/wav", "int_2"))
    path, cost = eleven.tts(con, "Merhaba", "some-elevenlabs-voice")
    assert path.endswith(".wav") and open(path, "rb").read() == b"WAV" and cost == 0.0
    hit, cost2 = eleven.tts(con, "Merhaba", "some-elevenlabs-voice")   # cached: no second call
    assert hit == path and cost2 == 0.0


def test_eleven_hands_a_clip_to_gemini_and_refuses_an_avatar(users, con, tmp_path, monkeypatch):
    accounts.set_gemini_key("ali", "AIza" + "e" * 35)
    mediaprov.set_settings("ali", {"video": "gemini"})
    monkeypatch.setattr(eleven, "OUT", str(tmp_path / "assets"))
    monkeypatch.setattr(accounts, "eleven", lambda aid=None: {"type": "connector", "owner": "ali", "shared": True})
    monkeypatch.setattr(accounts, "can_use", lambda aid=None, uid=None: True)
    monkeypatch.setattr(gemini, "video", lambda prompt, seconds=8, model=None, aspect="9:16", start=None,
                                              resolution="1080p": (b"MP4", "video/mp4", "int_5"))
    path, cost, flow, node = eleven.video(con, "the tank fills", 300, 5, "ali")
    assert path.endswith(".mp4") and node == "gen:int_5" and cost == 0.0
    assert gemini.month_usd(con) == 0.52                       # 5 s at 1080p = $0.104/s
    with pytest.raises(eleven.ElevenError, match="avatar"):
        eleven.avatar(con, "gen:face", "asset:voice", None, 6.0, 900, "ali")


def test_eleven_hands_music_to_gemini_when_chosen(users, con, tmp_path, monkeypatch):
    accounts.set_gemini_key("ali", "AIza" + "r" * 35)
    mediaprov.set_settings("ali", {"music": "gemini"})
    monkeypatch.setattr(eleven, "OUT", str(tmp_path / "assets"))
    monkeypatch.setattr(accounts, "eleven", lambda aid=None: {"type": "connector", "owner": "ali", "shared": True})
    monkeypatch.setattr(accounts, "can_use", lambda aid=None, uid=None: True)
    monkeypatch.setattr(gemini, "music", lambda prompt, seconds=30, model=None: (b"MP3", "audio/mpeg", "int_6"))
    path, cost = eleven.generate(con, "music", "eleven_music_v2_5", "slow piano", {"duration_seconds": 25}, 25, "s")
    assert path.endswith(".mp3") and open(path, "rb").read() == b"MP3" and cost == 0.0
    assert gemini.month_usd(con) == 0.04
