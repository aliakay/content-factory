"""Who generates each kind of media: ElevenLabs or Google Gemini, per user (Hesaplar → Medya üreticisi).

The production code asks this module and nothing else: `choice("image")` decides whether factory/eleven.py runs a
connector/REST generation or hands the same call to factory/gemini.py. The two return the same shapes, so a stage, a
line or a tool never knows which provider made the file — only the ledger does (`eleven_ledger` for credits,
`gemini_ledger` for dollars).

Defaults are ElevenLabs for everything, so nothing changes for a user who never opens the setting. A capability may
only be set to Gemini while a Gemini key exists (`ready()`); the Studio offers the choice and the API refuses
otherwise.

Failover (F05): `dispatch(kind, attempt, ...)` tries the chosen provider for one request and, when that request fails
(network, 5xx, 429/quota, auth), asks the next configured provider for the same capability. The caller supplies
`attempt(provider)` — so the language of a voice, the approved credits and the exact provider call stay with the
caller — and may pin a provider (`pinned=`) to opt out. Three failures inside ten minutes cool a provider down for ten
minutes (`data/provider_health.json`, atomic write); a budget guard is consulted for every candidate, including the
fallback. Content rejection is not a provider outage: it tries the next provider but does not count against health.
A fallback is logged to `data/provider_failover.log`; for voice the line says the voice changed and that the language
was kept.
"""
import json
import os
import re
import tempfile
import time
import urllib.error
from collections import namedtuple

from .config import ROOT
from . import accounts

KINDS = accounts.MEDIA_KINDS
PROVIDERS = accounts.MEDIA_PROVIDERS
LABELS = {
    "voice": {"tr": "Ses (anlatım)", "en": "Voice (narration)"},
    "music": {"tr": "Müzik", "en": "Music"},
    "image": {"tr": "Görsel / fotoğraf", "en": "Image / photo"},
    "video": {"tr": "Video (üretilen klip)", "en": "Video (generated clip)"},
}

# ---------------------------------------------------------------- health (persisted, atomic)
HEALTH_PATH = os.path.join(ROOT, "data", "provider_health.json")
FAILOVER_LOG = os.path.join(ROOT, "data", "provider_failover.log")
FAIL_THRESHOLD = 3          # 3 failures...
FAIL_WINDOW = 10 * 60       # ...inside 10 minutes...
COOLDOWN = 10 * 60          # ...cool the provider down for 10 minutes.
_now = time.time


def settings(uid=None):
    return accounts.media_settings(uid)


def choice(kind, uid=None):
    """'elevenlabs' | 'gemini' for one capability. An unknown kind stays on ElevenLabs."""
    if kind not in KINDS:
        return "elevenlabs"
    return accounts.media_settings(uid).get(kind, "elevenlabs")


def set_settings(uid, mapping):
    """Save the choice; Gemini needs a key (`accounts.gemini_status`)."""
    wanted = {k: v for k, v in (mapping or {}).items() if k in KINDS}
    if any(v == "gemini" for v in wanted.values()) and not accounts.gemini_status(uid)["connected"]:
        raise ValueError("Gemini seçmek için önce Hesaplar → Google Gemini API anahtarını gir")
    return accounts.set_media_settings(uid, wanted)


def ready(uid=None):
    """Which providers can run right now (for the Studio's picker): an ElevenLabs API-key account, or a Gemini key."""
    return {"elevenlabs": any(a.get("type") == "apikey" and a.get("usable", True) for a in accounts.usable_eleven(uid)),
            "gemini": accounts.gemini_status(uid)["connected"]}


def _health():
    try:
        with open(HEALTH_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("providers"), dict):
            return data
    except (OSError, ValueError):
        pass
    return {"version": 1, "providers": {}}


def _save_health(data):
    """Best effort, but atomic: a half-written health file must never hide a provider or invent an outage."""
    try:
        d = os.path.dirname(HEALTH_PATH)
        os.makedirs(d, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=d, prefix=".provider_health-", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, HEALTH_PATH)
    except OSError:
        pass


def _entry(data, provider):
    e = data["providers"].setdefault(provider, {})
    if not isinstance(e.get("fails"), list):
        e["fails"] = []
    e["cooldown_until"] = float(e.get("cooldown_until") or 0)
    return e


def health(provider=None):
    """One provider's health record, or all of them: {fails:[epoch...], cooldown_until: epoch}."""
    data = _health()
    if provider is not None:
        return dict(_entry(data, provider))
    return {p: dict(_entry(data, p)) for p in data["providers"]}


def available(provider, at=None):
    """False while a provider is in its cooldown; an expired cooldown is cleared here (and persisted)."""
    at = _now() if at is None else at
    data = _health()
    e = _entry(data, provider)
    old = (list(e["fails"]), e["cooldown_until"])
    e["fails"] = [float(t) for t in e["fails"] if at - float(t) <= FAIL_WINDOW]
    if e["cooldown_until"] and at >= e["cooldown_until"]:
        e["cooldown_until"] = 0
        e["fails"] = []
    if (e["fails"], e["cooldown_until"]) != old:
        _save_health(data)
    return not e["cooldown_until"] or at >= e["cooldown_until"]


def record_failure(provider, at=None):
    """One failed request. The third inside the window starts a cooldown; returns the new record."""
    at = _now() if at is None else at
    data = _health()
    e = _entry(data, provider)
    e["fails"] = [float(t) for t in e["fails"] if at - float(t) <= FAIL_WINDOW] + [at]
    if len(e["fails"]) >= FAIL_THRESHOLD:
        e["cooldown_until"] = at + COOLDOWN
    _save_health(data)
    return dict(e)


def record_success(provider):
    """A good request clears the provider's failures (and any cooldown)."""
    data = _health()
    e = _entry(data, provider)
    if e["fails"] or e["cooldown_until"]:
        e["fails"], e["cooldown_until"] = [], 0
        _save_health(data)


def reset_health(providers=None):
    """Forget failures (the Studio's "retry now" / a test fixture)."""
    data = _health()
    for p in (providers or list(data["providers"])):
        data["providers"].pop(p, None)
    _save_health(data)


# ---------------------------------------------------------------- a request-level fallback
# A provider error is worth trying elsewhere; a content rejection is not an outage (and a 400 says the request itself
# is wrong). The strings cover urllib/eleven_api.ApiError/gemini.GeminiError/openrouter wording.
_RETRY = re.compile(r"(?:\b(?:401|403|408|429|5\d\d)\b|quota|rate.?limit|too many requests|timeout|timed out|"
                    r"connection|temporar|unavailable|overload|network|bağlantı|ulaşılamadı|geçici|sunucu hatası)", re.I)
_NO_RETRY = re.compile(r"(?:moderat|content polic|safety|policy violation|reddedil|rejected|invalid|bad request|"
                       r"\b400\b|\b404\b|not found|unsupported|avatar)", re.I)


class FailoverError(RuntimeError):
    """Every configured provider failed (or was blocked); carries each attempt's reason."""

    def __init__(self, kind, failures):
        self.kind, self.failures = kind, failures
        detail = "; ".join(f"{p}: {str(e)[:120] or why}" for p, e, why in failures) or "no provider available"
        super().__init__(f"{kind}: bütün sağlayıcılar başarısız ({detail})")


Outcome = namedtuple("Outcome", "provider value failures")


def provider_error(exc):
    """Is this exception a provider outage/limit (retry elsewhere) rather than a bad request or a content rejection?"""
    if isinstance(exc, (urllib.error.URLError, TimeoutError, ConnectionError, OSError)):
        return True
    text = str(exc)
    return bool(_RETRY.search(text)) and not _NO_RETRY.search(text)


def candidates(kind, uid=None, allow_fallback=True, pinned=None):
    """The provider order for one request: the chosen one, then the other configured one when fallback is allowed."""
    primary = pinned if pinned in PROVIDERS else choice(kind, uid)
    if not allow_fallback or pinned in PROVIDERS:
        return [primary]
    up = ready(uid)
    return [primary] + [p for p in PROVIDERS if p != primary and up.get(p)]


def _log_event(event):
    try:
        os.makedirs(os.path.dirname(FAILOVER_LOG), exist_ok=True)
        row = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), **event}
        with open(FAILOVER_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        pass


def dispatch(kind, attempt, uid=None, allow_fallback=True, pinned=None, check=None, log=None, outages_only=False):
    """Run one media request with failover.

    `attempt(provider)` performs the real call for that provider (keeping voice/language, refs, aspect and the exact
    model), `check(provider)` is the budget guard for that provider (called before every attempt; a refusal skips the
    candidate without counting as an outage), `pinned` opts out of fallback for a project that fixed its provider,
    `log(event)` replaces the JSON-lines log (tests). `outages_only`: a non-outage error (budget refusal, bad request,
    content rejection) is raised at once instead of trying the next provider. Returns `Outcome(provider, value, failures)`.
    """
    order = candidates(kind, uid, allow_fallback=allow_fallback, pinned=pinned)
    primary = order[0] if order else choice(kind, uid)
    emit = log or _log_event
    failures = []
    for provider in order:
        if not available(provider):
            failures.append((provider, None, "cooldown"))
            emit({"kind": kind, "provider": provider, "event": "cooldown", "from": primary,
                  "message": f"{provider} bekleme süresinde" if kind != "voice" else f"ses: {provider} bekleme süresinde"})
            continue
        if check is not None:
            try:
                check(provider)
            except Exception as e:                       # the budget (or another guard) refused this candidate
                failures.append((provider, e, "guard"))
                emit({"kind": kind, "provider": provider, "event": "budget", "from": primary,
                      "error": str(e)[:200]})
                continue
        try:
            value = attempt(provider)
        except Exception as e:
            if provider_error(e):
                record_failure(provider)
            elif outages_only:
                raise
            failures.append((provider, e, "error"))
            emit({"kind": kind, "provider": provider, "event": "failed", "from": primary,
                  "error": f"{type(e).__name__}: {str(e)[:180]}"})
            continue
        record_success(provider)
        if provider != primary:
            msg = (f"ses değişti: {primary} → {provider} (dil korunur)" if kind == "voice"
                   else f"sağlayıcı değişti: {primary} → {provider}")
            emit({"kind": kind, "provider": provider, "event": "fallback", "from": primary, "message": msg})
        return Outcome(provider, value, failures)
    raise FailoverError(kind, failures)


request = dispatch          # a request-level name for the same wrapper
