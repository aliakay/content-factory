"""ElevenLabs without a CLI: the REST transport (API key account) next to the CLI connector.

A connector lives inside a Claude Code or Codex login; an API model (OpenRouter) has none, so the creator picks the
transport on Hesaplar: `api` (our own REST client, needs an API key account), `codex`, `claude`, or `auto`. These
tests pin that choice down, and the REST paths of image / video / lip-sync / upload without touching the network.
"""
import json, os, sqlite3

import pytest

from factory import accounts, credits, eleven, eleven_api, llm
from factory.store import now

PID = "001-film"


@pytest.fixture
def users(tmp_path, monkeypatch):
    f = tmp_path / "users.json"
    f.write_text(json.dumps({"secret": "x", "users": {"ali": {"name": "Ali", "role": "owner"}}}))
    monkeypatch.setattr(accounts, "USERS", str(f))
    return f


@pytest.fixture
def con(tmp_path):
    c = sqlite3.connect(tmp_path / "t.db")
    c.row_factory = sqlite3.Row
    c.executescript(credits.SCHEMA)
    credits.ensure(c)
    return c


@pytest.fixture
def apikey(monkeypatch, tmp_path, users):
    """An API-key ElevenLabs account plus a scratch output folder; nothing reaches the network."""
    acc = {"id": "ali-key", "name": "Ali API", "type": "apikey", "key": "k", "owner": "ali", "shared": True}
    monkeypatch.setattr(accounts, "eleven", lambda aid=None: acc)
    monkeypatch.setattr(accounts, "can_use", lambda aid=None, uid=None: True)
    monkeypatch.setattr(credits, "check_budget", lambda con, need, account="ali": {"ok": True, "why": "", "spent": 0,
                                                                                  "cap": 10 ** 6, "after": need})
    monkeypatch.setattr(eleven, "OUT", str(tmp_path / "assets"))
    monkeypatch.setattr(credits, "rates", lambda: {})       # no measured price yet: the approval is the cap
    monkeypatch.setattr(credits, "RATES_PATH", str(tmp_path / "rates.json"))   # never write the real ledger's prices
    return acc


@pytest.fixture
def connector(monkeypatch, tmp_path, users):
    acc = {"id": "ali", "name": "Ali connector", "type": "connector", "owner": "ali", "shared": True}
    monkeypatch.setattr(accounts, "eleven", lambda aid=None: acc)
    monkeypatch.setattr(accounts, "can_use", lambda aid=None, uid=None: True)
    monkeypatch.setattr(credits, "check_budget", lambda con, need, account="ali": {"ok": True, "why": "", "spent": 0,
                                                                                  "cap": 10 ** 6, "after": need})
    monkeypatch.setattr(eleven, "OUT", str(tmp_path / "assets"))
    return acc


# ---------------------------------------------------------------- the choice
def test_the_choice_is_remembered_per_user(users):
    assert accounts.eleven_settings("ali") == {"via": "auto"}
    accounts.set_eleven_settings("ali", "codex")
    assert accounts.eleven_settings("ali")["via"] == "codex" and llm.eleven_via("ali") == "codex"
    with pytest.raises(ValueError):
        accounts.set_eleven_settings("ali", "openrouter")


def test_transports_are_reported_for_the_picker(users, monkeypatch):
    monkeypatch.setattr(llm, "codex_elevenlabs_status", lambda: {"connected": True})
    monkeypatch.setattr(accounts, "claude_status", lambda uid=None: {"connectors": False})
    monkeypatch.setattr(accounts, "eleven_accounts", lambda: {"accounts": {"ali": {"type": "connector"}}})
    assert accounts.eleven_transports("ali") == {"api": False, "codex": True, "claude": False}


def test_an_api_key_account_never_needs_a_cli(apikey):
    assert eleven.transport("ali-key") == "api"


def test_a_connector_account_asks_a_cli(connector):
    assert eleven.transport("ali") == "cli"                     # 'auto': a CLI runs the connector


def test_asking_for_the_api_with_a_connector_account_says_what_to_do(connector, users):
    accounts.set_eleven_settings("ali", "api")
    with pytest.raises(eleven.ElevenError, match="API"):
        eleven.transport("ali")


def test_the_choice_decides_which_cli_runs_the_connector(users, monkeypatch):
    accounts.set_llm_settings("ali", "openrouter", {})
    monkeypatch.setattr(accounts, "claude_status", lambda uid=None: {"connectors": True})
    monkeypatch.setattr(llm, "codex_elevenlabs_status", lambda: {"connected": True})
    accounts.set_eleven_settings("ali", "claude")
    assert llm.connector_provider() == "claude"                 # the creator's word beats auto-detection
    accounts.set_eleven_settings("ali", "codex")
    assert llm.connector_provider() == "codex"
    accounts.set_eleven_settings("ali", "auto")
    assert llm.connector_provider() == "codex"                  # auto: the connected CLI (Codex here)


def test_the_selected_cli_still_wins_outside_openrouter(users, monkeypatch):
    accounts.set_llm_settings("ali", "claude", {})
    accounts.set_eleven_settings("ali", "api")
    assert llm.connector_provider() == "claude"                 # agents on a CLI: that CLI's connector is used


# ---------------------------------------------------------------- the REST paths
def test_an_image_comes_from_the_api_and_keeps_its_id(apikey, con, monkeypatch):
    seen = {}
    monkeypatch.setattr(eleven_api, "image", lambda key, prompt, model, aspect="9:16", refs=(), **kw:
                        seen.update(dict(key=key, prompt=prompt, model=model, aspect=aspect, refs=refs))
                        or (b"\x89PNG data", "image/png", "gen123"))
    path, cost, flow, node = eleven.image(con, "a red scarf", 200, "ali-key", aspect="9:16")
    assert path.endswith(".png") and open(path, "rb").read() == b"\x89PNG data"
    assert (flow, node) == (None, "gen:gen123") and cost == 200        # no measured price yet: the approval is the cap
    assert seen["aspect"] == "9:16" and seen["model"] == eleven.IMAGE_MODEL and seen["key"] == "k"
    meta = json.load(open(path + ".json"))
    assert meta == {"flow_id": None, "node_id": "gen:gen123", "prompt": "a red scarf", "refs": []}


def test_a_later_image_can_be_drawn_from_the_first(apikey, con, monkeypatch):
    got = {}

    def fake_image(key, prompt, model, aspect="9:16", refs=(), **kw):
        got["refs"] = list(refs)
        return b"png", "image/png", "gen456"

    monkeypatch.setattr(eleven_api, "image", fake_image)
    eleven.image(con, "same girl, dusk", 200, "ali-key", refs=["gen:gen123"])
    assert got["refs"] == ["gen:gen123"]


def test_a_measured_price_is_what_the_ledger_records(apikey, con, monkeypatch, tmp_path):
    monkeypatch.setattr(eleven_api, "image", lambda *a, **k: (b"png", "image/png", "g"))
    monkeypatch.setattr(credits, "rates", lambda: {"image:gpt-image-2": {"unit": "img", "rate": 150.0, "samples": 3}})
    _, cost, _, _ = eleven.image(con, "x", 400, "ali-key")
    assert cost == 150.0
    row = con.execute("SELECT kind, model, credits, account FROM eleven_ledger").fetchone()
    assert (row["kind"], row["model"], row["credits"], row["account"]) == ("image", "gpt-image-2", 150.0, "ali-key")


def test_a_clip_comes_from_the_api_with_its_duration(apikey, con, monkeypatch):
    seen = {}
    monkeypatch.setattr(eleven_api, "video", lambda key, prompt, model, seconds, aspect="9:16", start=None,
                                            images=(), audios=(), **kw:
                        seen.update(dict(seconds=seconds, start=start, images=list(images), model=model))
                        or (b"mp4", "video/mp4", "vid1"))
    path, cost, flow, node = eleven.video(con, "the tank fills", 300, 5, "ali-key", start="gen:gen456")
    assert path.endswith(".mp4") and node == "gen:vid1" and flow is None
    assert seen["seconds"] == 5 and seen["start"] == "gen:gen456" and seen["model"] == eleven.VIDEO_MODEL


def test_a_presenter_speaks_through_lipsync(apikey, con, monkeypatch):
    seen = {}
    monkeypatch.setattr(eleven_api, "lipsync", lambda key, image, audio, model="creatify-aurora", **kw:
                        seen.update(dict(image=image, audio=audio, model=model)) or (b"mp4", "video/mp4", "lip1"))
    path, cost = eleven.avatar(con, "gen:face", "asset:voice", None, 6.0, 900, "ali-key")
    assert path.endswith(".mp4") and seen == {"image": "gen:face", "audio": "asset:voice",
                                              "model": eleven.AVATAR_MODEL}


def test_a_model_the_rest_api_cannot_drive_says_so(apikey, con, monkeypatch):
    def boom(key, prompt, model, seconds, aspect="9:16", **kw):
        raise eleven_api.ApiError(f"'{model}' REST API'de yok; bu video modeli yalnız connector ile üretilebiliyor")

    monkeypatch.setattr(eleven_api, "video", boom)
    with pytest.raises(eleven_api.ApiError, match="connector"):
        eleven.video(con, "re-lip-sync", 300, 5, "ali-key", model="sync-lipsync-v3")


def test_uploads_become_assets_and_flows_are_skipped(apikey, tmp_path, monkeypatch):
    monkeypatch.setattr(eleven_api, "upload", lambda key, path, name=None: "asset9")
    clip = tmp_path / "voice.mp3"
    clip.write_bytes(b"ID3")
    assert eleven.new_flow("ali-key") is None                       # the REST path needs no flow
    assert eleven.upload(str(clip), None, "ali-key") == "asset:asset9"
    assert eleven.asset_node("asset9", None, "image", "ali-key") == "asset:asset9"


def test_a_reference_understands_our_ids_and_local_files(tmp_path):
    f = tmp_path / "plate.png"
    f.write_bytes(b"png")
    assert eleven_api.reference("gen:abc") == {"type": "generation", "generation_id": "abc"}
    assert eleven_api.reference("asset:xyz") == {"type": "asset", "asset_id": "xyz"}
    inline = eleven_api.reference(str(f))
    assert inline["type"] == "inline_base64" and inline["mime_type"] == "image/png" and inline["content_base64"]


def test_a_generation_polls_until_the_media_is_ready(monkeypatch):
    calls = []

    def fake_req(key, path, body=None, timeout=120, raw=False):
        calls.append((path, body))
        if body is not None:
            return {"id": "g1", "status": "pending"}
        return {"id": "g1", "status": "completed", "content_url": "https://cdn/x.png",
                "content_mime_type": "image/png"}

    monkeypatch.setattr(eleven_api, "_req", fake_req)
    monkeypatch.setattr(eleven_api, "_abs", lambda url, timeout=300: b"png-bytes")
    monkeypatch.setattr(eleven_api.time, "sleep", lambda s: None)
    data, mime, gid = eleven_api.image("k", "a scarf", "gpt-image-2", aspect="9:16")
    assert (data, mime, gid) == (b"png-bytes", "image/png", "g1")
    assert calls[0][1] == {"model_id": "gpt-image-2", "prompt": "a scarf", "aspect_ratio": "9:16"}


def test_a_failed_generation_reports_the_reason(monkeypatch):
    def fake_req(key, path, body=None, timeout=120, raw=False):
        if body is not None:
            return {"id": "g2"}
        return {"id": "g2", "status": "failed", "failure_reason": "moderated", "error_message": "nope"}

    monkeypatch.setattr(eleven_api, "_req", fake_req)
    monkeypatch.setattr(eleven_api.time, "sleep", lambda s: None)
    with pytest.raises(eleven_api.ApiError, match="moderated"):
        eleven_api.image("k", "x", "gpt-image-2")
