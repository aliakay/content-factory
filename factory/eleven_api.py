"""ElevenLabs REST API for accounts connected with an API key (factory/accounts.py). The owner's account keeps using
the claude.ai connector (factory/eleven.py); both write the same credit ledger."""
import json, os, time, urllib.error, urllib.request

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


def shared_voice(key, voice_id):
    """A Voice Library voice by id -> {public_owner_id, voice_id, name}, or None (the id is not in the library)."""
    try:
        out = _req(key, f"/v1/shared-voices?page_size=30&search={voice_id}", timeout=30)
    except ApiError:
        return None
    for v in out.get("voices") or []:
        if v.get("voice_id") == voice_id and v.get("public_owner_id"):
            return {"public_owner_id": v["public_owner_id"], "voice_id": voice_id,
                    "name": v.get("name") or voice_id[:6]}
    return None


def add_shared_voice(key, public_owner_id, voice_id, name=None):
    """Add a Voice Library voice to this account -> the account's own copy {voice_id, name}."""
    out = _req(key, f"/v1/voices/add/{public_owner_id}/{voice_id}", {"new_name": (name or voice_id)[:60]}, timeout=60)
    if not out.get("voice_id"):
        raise ApiError(f"ses hesaba eklenemedi: {json.dumps(out)[:200]}")
    return {"voice_id": out["voice_id"], "name": name or voice_id}


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


# ---------------------------------------------------------------- flow generations (image, video, lip-sync)

# The REST media models we can drive. Anything else (e.g. a video-to-video lip-sync) is connector-only.
API_IMAGE_MODELS = ("gpt-image-", "gemini-", "bytedance-seedream-")
API_VIDEO_MODELS = ("bytedance-seedance-", "veo-", "creatify-")
GEN = {"image": "/v1/flows/image", "video": "/v1/flows/video"}
MAX_INLINE = 25 * 1024 * 1024          # the API's limit for an inline base64 reference
POLL_S = float(os.environ.get("CF_ELEVEN_POLL_S") or 1800)
MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
        ".mp3": "audio/mpeg", ".wav": "audio/wav", ".m4a": "audio/mp4", ".mp4": "video/mp4", ".mov": "video/quicktime"}


def _abs(url, timeout=300):
    """Download a signed URL: its signature is in the URL, so no key header is sent."""
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        raise ApiError(f"ElevenLabs indirme {e.code}: {e.reason}") from None
    except urllib.error.URLError as e:
        raise ApiError(f"ElevenLabs indirme hatası: {e.reason}") from None


def upload(key, path, name=None):
    """A local file as an API asset (`POST /v1/assets`, multipart) -> asset_id (usable as a reference)."""
    import secrets
    boundary = "factory" + secrets.token_hex(8)
    mime = MIME.get(os.path.splitext(path)[1].lower(), "application/octet-stream")
    with open(path, "rb") as f:
        data = f.read()
    head = (f'--{boundary}\r\nContent-Disposition: form-data; name="name"\r\n\r\n'
            f'{name or os.path.basename(path)}\r\n').encode()
    file_head = (f'--{boundary}\r\nContent-Disposition: form-data; name="asset"; filename="{os.path.basename(path)}"\r\n'
                 f"Content-Type: {mime}\r\n\r\n").encode()
    body = head + file_head + data + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(API + "/v1/assets", data=body, method="POST",
                                 headers={"xi-api-key": key, "Accept": "application/json",
                                          "Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            out = json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        raise ApiError(f"ElevenLabs yükleme {e.code}: {e.read().decode(errors='replace')[:300]}") from None
    except urllib.error.URLError as e:
        raise ApiError(f"ElevenLabs yükleme hatası: {e.reason}") from None
    if not out.get("asset_id"):
        raise ApiError(f"ElevenLabs yükleme yanıtı okunamadı: {json.dumps(out)[:200]}")
    return out["asset_id"]


def reference(node, kind="image"):
    """A node id from factory/eleven.py (`gen:`/`asset:`), a raw id, or a local file -> an API reference object."""
    import base64
    if isinstance(node, dict):
        return node
    s = str(node or "")
    if s.startswith("gen:"):
        return {"type": "generation", "generation_id": s[4:]}
    if s.startswith("asset:"):
        return {"type": "asset", "asset_id": s[6:]}
    if os.path.isfile(s):
        data = open(s, "rb").read()
        if len(data) > MAX_INLINE:
            raise ApiError(f"referans dosya 25 MB sınırından büyük: {s}")
        mime = MIME.get(os.path.splitext(s)[1].lower(), "image/png" if kind == "image" else "audio/mpeg")
        return {"type": "inline_base64", "content_base64": base64.b64encode(data).decode(), "mime_type": mime}
    return {"type": "asset", "asset_id": s}


def wait(kind, key, gid, timeout=None):
    """Poll one generation until its media is ready -> (bytes, mime, id)."""
    end, delay = time.time() + (timeout or POLL_S), 4.0
    while time.time() < end:
        time.sleep(delay)
        delay = min(delay * 1.35, 20.0)
        st = _req(key, f"{GEN[kind]}/{gid}", timeout=60)
        if st.get("status") == "completed":
            return _abs(st["content_url"]), st.get("content_mime_type"), gid
        if st.get("status") == "failed":
            raise ApiError(f"ElevenLabs {kind} üretilemedi ({st.get('failure_reason')}): "
                           f"{st.get('error_message') or ''}".strip())
    raise ApiError(f"ElevenLabs {kind} {int(timeout or POLL_S)} s içinde bitmedi (id {gid})")


def generation(kind, key, req, timeout=None):
    """Queue one flow generation and wait for it -> (bytes, mime, id)."""
    out = _req(key, GEN[kind], req, timeout=120)
    if not out.get("id"):
        raise ApiError(f"ElevenLabs {kind} kuyruğa alınamadı: {json.dumps(out)[:200]}")
    return wait(kind, key, out["id"], timeout)


def image(key, prompt, model, aspect="9:16", refs=(), resolution=None, quality=None, timeout=None):
    """One image -> (png bytes, mime, generation id). `refs`: node ids or local files to draw from."""
    if not model.startswith(API_IMAGE_MODELS):
        raise ApiError(f"'{model}' REST API'de yok; bu görsel modeli yalnız connector ile üretilebiliyor")
    req = {"model_id": model, "prompt": prompt, "aspect_ratio": aspect}
    if refs:
        req["images"] = [reference(r) for r in refs]
    if resolution:
        req["resolution"] = resolution
    if quality:
        req["quality"] = quality
    return generation("image", key, req, timeout)


def video(key, prompt, model, seconds, aspect="9:16", start=None, images=(), audios=(), resolution=None,
          generate_audio=None, timeout=None):
    """One generated clip -> (mp4 bytes, mime, generation id). `start`: the first-frame reference."""
    if not model.startswith(API_VIDEO_MODELS):
        raise ApiError(f"'{model}' REST API'de yok; bu video modeli yalnız connector ile üretilebiliyor")
    if model.startswith("creatify-"):
        raise ApiError("creatify-aurora bir konuşan sunucu modeli: lipsync() kullan")
    req = {"model_id": model, "prompt": prompt, "aspect_ratio": aspect,
           "duration_secs": (min((4, 6, 8), key=lambda d: abs(d - seconds)) if model.startswith("veo-")
                             else max(4, min(15, int(round(seconds)))))}
    if start:
        req["start_frame"] = reference(start)
    if images:
        req["images"] = [reference(i) for i in images]
    if audios:
        req["audios"] = [reference(a, "audio") for a in audios]
    if resolution:
        req["resolution"] = resolution
    if generate_audio is not None:
        req["generate_audio"] = bool(generate_audio)
    return generation("video", key, req, timeout)


def lipsync(key, image_node, audio_node, model="creatify-aurora", resolution=None, timeout=None):
    """A talking presenter (creatify-aurora): an image + speech -> (mp4 bytes, mime, generation id)."""
    req = {"model_id": model, "image": reference(image_node), "audio": reference(audio_node, "audio")}
    if resolution:
        req["resolution"] = resolution
    return generation("video", key, req, timeout)
