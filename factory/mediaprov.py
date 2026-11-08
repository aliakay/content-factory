"""Who generates each kind of media: ElevenLabs or Google Gemini, per user (Hesaplar → Medya üreticisi).

The production code asks this module and nothing else: `choice("image")` decides whether factory/eleven.py runs a
connector/REST generation or hands the same call to factory/gemini.py. The two return the same shapes, so a stage, a
line or a tool never knows which provider made the file — only the ledger does (`eleven_ledger` for credits,
`gemini_ledger` for dollars).

Defaults are ElevenLabs for everything, so nothing changes for a user who never opens the setting. A capability may
only be set to Gemini while a Gemini key exists (`ready()`); the Studio offers the choice and the API refuses
otherwise.
"""
from . import accounts

KINDS = accounts.MEDIA_KINDS
PROVIDERS = accounts.MEDIA_PROVIDERS
LABELS = {
    "voice": {"tr": "Ses (anlatım)", "en": "Voice (narration)"},
    "music": {"tr": "Müzik", "en": "Music"},
    "image": {"tr": "Görsel / fotoğraf", "en": "Image / photo"},
    "video": {"tr": "Video (üretilen klip)", "en": "Video (generated clip)"},
}


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
    """Which providers can run right now (for the Studio's picker)."""
    from . import llm
    return {"elevenlabs": bool(accounts.eleven_transports(uid)["api"] or accounts.eleven_transports(uid)["codex"]
                               or accounts.eleven_transports(uid)["claude"]),
            "gemini": accounts.gemini_status(uid)["connected"]}
