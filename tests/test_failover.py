"""Request-level provider failover: the next configured provider is tried, health cools a flapping provider down,
the budget guard runs for every candidate, and a pinned provider never falls back."""
import json
import os
import urllib.error

import pytest

from factory import mediaprov


@pytest.fixture
def health(tmp_path, monkeypatch):
    monkeypatch.setattr(mediaprov, "HEALTH_PATH", str(tmp_path / "provider_health.json"))
    monkeypatch.setattr(mediaprov, "FAILOVER_LOG", str(tmp_path / "provider_failover.log"))
    monkeypatch.setattr(mediaprov, "_now", lambda: 1000.0)
    monkeypatch.setattr(mediaprov, "choice", lambda kind, uid=None: "elevenlabs")
    monkeypatch.setattr(mediaprov, "ready", lambda uid=None: {"elevenlabs": True, "gemini": True})
    return tmp_path


def test_three_failures_cool_a_provider_down(health):
    assert mediaprov.available("elevenlabs") is True
    for _ in range(2):
        mediaprov.record_failure("elevenlabs")
    assert mediaprov.available("elevenlabs") is True          # two is not a pattern yet
    mediaprov.record_failure("elevenlabs")
    assert mediaprov.available("elevenlabs") is False
    saved = json.load(open(health / "provider_health.json"))
    assert saved["providers"]["elevenlabs"]["cooldown_until"] == 1000.0 + mediaprov.COOLDOWN
    assert not list(health.glob("*.tmp"))                    # atomic write leaves no half file behind
    mediaprov._now = lambda: 1000.0 + mediaprov.COOLDOWN + 1
    assert mediaprov.available("elevenlabs") is True          # the cooldown expires
    assert json.load(open(health / "provider_health.json"))["providers"]["elevenlabs"]["cooldown_until"] == 0


def test_a_success_clears_the_record(health):
    mediaprov.record_failure("gemini")
    mediaprov.record_success("gemini")
    assert mediaprov.health("gemini")["fails"] == []


def test_dispatch_falls_back_and_says_the_voice_changed(health):
    events = []
    tried = []

    def attempt(provider):
        tried.append(provider)
        if provider == "elevenlabs":
            raise urllib.error.URLError("connection reset")
        return "wav:gemini:tr"

    out = mediaprov.dispatch("voice", attempt, log=events.append)
    assert tried == ["elevenlabs", "gemini"]
    assert out.provider == "gemini" and out.value == "wav:gemini:tr"
    assert out.failures[0][0] == "elevenlabs"
    fallback = [e for e in events if e.get("event") == "fallback"][0]
    assert "ses değişti" in fallback["message"] and "dil korunur" in fallback["message"]
    assert mediaprov.health("elevenlabs")["fails"]             # the outage is on the health record


def test_a_pinned_provider_never_falls_back(health):
    tried = []

    def attempt(provider):
        tried.append(provider)
        raise urllib.error.URLError("down")

    with pytest.raises(mediaprov.FailoverError) as e:
        mediaprov.dispatch("image", attempt, pinned="elevenlabs")
    assert tried == ["elevenlabs"] and "bütün sağlayıcılar" in str(e.value)


def test_the_budget_guard_runs_for_the_fallback_and_is_not_an_outage(health):
    checked, tried = [], []

    def check(provider):
        checked.append(provider)
        if provider == "gemini":
            raise RuntimeError("Gemini aylık sınırı")

    def attempt(provider):
        tried.append(provider)
        raise urllib.error.URLError("elevenlabs down")

    with pytest.raises(mediaprov.FailoverError) as e:
        mediaprov.dispatch("image", attempt, check=check)
    assert checked == ["elevenlabs", "gemini"]
    assert tried == ["elevenlabs"]                           # the fallback was refused before it was called
    assert "Gemini" in str(e.value)
    assert mediaprov.health("gemini")["fails"] == []          # a budget refusal is not a provider failure


def test_a_content_rejection_tries_elsewhere_but_is_not_an_outage(health):
    def attempt(provider):
        if provider == "elevenlabs":
            raise RuntimeError("content moderated by safety policy")
        return "png"

    out = mediaprov.dispatch("image", attempt)
    assert out.provider == "gemini" and out.value == "png"
    assert mediaprov.health("elevenlabs")["fails"] == []


def test_a_cooled_provider_is_skipped_before_it_is_called(health):
    for _ in range(mediaprov.FAIL_THRESHOLD):
        mediaprov.record_failure("elevenlabs")
    tried = []

    def attempt(provider):
        tried.append(provider)
        return provider

    out = mediaprov.dispatch("music", attempt)
    assert tried == ["gemini"] and out.provider == "gemini"


def test_fallback_only_goes_to_a_configured_provider(health, monkeypatch):
    monkeypatch.setattr(mediaprov, "choice", lambda kind, uid=None: "gemini")
    monkeypatch.setattr(mediaprov, "ready", lambda uid=None: {"elevenlabs": False, "gemini": True})
    assert mediaprov.candidates("video") == ["gemini"]
    monkeypatch.setattr(mediaprov, "ready", lambda uid=None: {"elevenlabs": True, "gemini": True})
    assert mediaprov.candidates("video") == ["gemini", "elevenlabs"]
    assert mediaprov.candidates("video", allow_fallback=False) == ["gemini"]
    assert mediaprov.candidates("video", pinned="elevenlabs") == ["elevenlabs"]


def test_outages_only_raises_a_refusal_without_trying_the_next_provider(monkeypatch, tmp_path):
    from factory import mediaprov as M
    monkeypatch.setattr(M, "candidates", lambda *a, **k: ["elevenlabs", "gemini"])
    monkeypatch.setattr(M, "available", lambda p, at=None: True)
    monkeypatch.setattr(M, "record_failure", lambda p, at=None: None)
    monkeypatch.setattr(M, "record_success", lambda p: None)
    tried = []

    def attempt(p):
        tried.append(p)
        raise RuntimeError("bütçe onayı yok")
    import pytest
    with pytest.raises(RuntimeError, match="bütçe"):
        M.dispatch("music", attempt, log=lambda e: None, outages_only=True)
    assert tried == ["elevenlabs"]


def test_music_falls_over_to_gemini_on_an_outage(monkeypatch):
    from factory import eleven as E, mediaprov as M
    monkeypatch.setattr(M, "candidates", lambda *a, **k: ["elevenlabs", "gemini"])
    monkeypatch.setattr(M, "available", lambda p, at=None: True)
    monkeypatch.setattr(M, "record_failure", lambda p, at=None: None)
    monkeypatch.setattr(M, "record_success", lambda p: None)
    monkeypatch.setattr(M, "_log_event", lambda e: None)

    def fake(con, provider, *a):
        if provider == "elevenlabs":
            raise ConnectionError("503 overloaded")
        return "/tmp/x.mp3", 0.0
    monkeypatch.setattr(E, "_music", fake)
    assert E.generate(None, "music", "m", "calm", {"duration_seconds": 10}, 10, "s") == ("/tmp/x.mp3", 0.0)
