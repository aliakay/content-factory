"""ElevenLabs REST API for accounts connected with an API key (factory/accounts.py). The owner's account keeps using
the claude.ai connector (factory/eleven.py); both write the same credit ledger."""
import json, time, urllib.error, urllib.request

API = "https://api.elevenlabs.io"
_cache = {}


class ApiError(RuntimeError):
    pass


def _req(key, path, body=None, timeout=120, raw=False):
    req = urllib.request.Request(API + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"xi-api-key": key, "Content-Type": "application/json",
                                          "Accept": "*/*"}, method="POST" if body is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read()
            return (data, dict(r.headers)) if raw else json.loads(data)
    except urllib.error.HTTPError as e:
        msg = e.read().decode(errors="replace")[:300]
        raise ApiError(f"ElevenLabs {e.code}: {msg}") from None
    except urllib.error.URLError as e:
        raise ApiError(f"ElevenLabs bağlantı hatası: {e.reason}") from None


def subscription(key):
    s = _req(key, "/v1/user/subscription", timeout=30)
    used, limit = s.get("character_count") or 0, s.get("character_limit") or 0
    return {"tier": s.get("tier"), "used": used, "limit": limit, "left": max(0, limit - used),
            "resets": s.get("next_character_count_reset_unix")}


def voices(key):
    v = _req(key, "/v2/voices?page_size=100&include_total_count=false", timeout=30)
    out = []
    for x in v.get("voices", []):
        labels = x.get("labels") or {}
        lang = (labels.get("language") or (x.get("fine_tuning") or {}).get("language") or "en")[:2].lower()
        out.append({"voice_id": x["voice_id"], "name": x.get("name"), "category": x.get("category"),
                    "language": lang, "note": ", ".join(str(labels[k]) for k in ("accent", "age", "gender") if labels.get(k)),
                    "preview_url": x.get("preview_url")})
    order = {"cloned": 0, "professional": 1, "generated": 2}
    return sorted(out, key=lambda x: (order.get(x["category"], 3), x["name"] or ""))


def info(key, fresh=False):
    """Voices + balance of an API-key account, cached for 10 minutes (a new key is read at once)."""
    k = key[-12:]
    hit = _cache.get(k)
    if hit and not fresh and time.time() - hit[0] < 600:
        return hit[1]
    data = {"subscription": subscription(key), "voices": voices(key)}
    _cache[k] = (time.time(), data)
    return data


def tts(key, text, voice_id, model):
    """mp3 bytes + the character cost the API reports (falls back to the text length)."""
    data, headers = _req(key, f"/v1/text-to-speech/{voice_id}?output_format=mp3_44100_128",
                         {"text": text, "model_id": model}, timeout=300, raw=True)
    h = {k.lower(): v for k, v in headers.items()}
    try:
        cost = float(h.get("character-cost") or h.get("x-character-count") or len(text))
    except ValueError:
        cost = float(len(text))
    return data, cost


def music(key, prompt, seconds):
    data, _ = _req(key, "/v1/music?output_format=mp3_44100_128",
                   {"prompt": prompt, "music_length_ms": int(seconds * 1000), "model_id": "music_v1"},
                   timeout=900, raw=True)
    return data


def sound(key, prompt, seconds):
    data, _ = _req(key, "/v1/sound-generation", {"text": prompt, "duration_seconds": seconds}, timeout=300, raw=True)
    return data
