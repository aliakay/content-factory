"""ElevenLabs through its REST API (an API-key account). The CLI connector path was removed.

Everything a film needs is here and needs no CLI session: speech, music, sound effects, images, generated video,
talking presenters (image + speech) and asset uploads. Each call is guarded by the approved credit amount
(`credits.guard`), measured against the account's real balance, and written to the credit ledger. Files are cached by
their inputs, so a re-run of a stage never pays twice for the same take.

A capability can be pointed at Google Gemini instead (Hesaplar → Medya üreticisi, factory/mediaprov.py): the same
functions hand the work to factory/gemini.py and return the same shapes, so no caller knows which provider made the
file. Node ids we hand back are `gen:<generation id>` / `asset:<asset id>` for the REST path.
"""
import hashlib, json, os, subprocess

from . import accounts, credits, eleven_api

from .config import FFPROBE, ROOT
OUT = os.path.join(ROOT, "assets", "eleven")
IMAGE_MODEL = "gpt-image-2"
EDIT_MODEL = "gpt-image-2.5-sunburst"   # the model for an image made from reference images
VIDEO_MODEL = "bytedance-seedance-v2.5"
AVATAR_MODEL = "creatify-aurora"
PROFILE = os.path.join(ROOT, "data", "eleven_profile.json")
MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".mp3": "audio/mpeg",
        ".wav": "audio/wav", ".m4a": "audio/mp4", ".mp4": "video/mp4", ".mov": "video/quicktime"}
# ElevenLabs errors the user can act on (the raw text stays in the job log after the explanation)
KNOWN_ERRORS = (
    ("free_tier_image_limit", "ElevenLabs hesabı ücretsiz planda ve günlük görsel limiti doldu; yarın tekrar dene "
                              "ya da planı yükselt"),
    ("does not resolve", "seçili ses bu ElevenLabs hesabında yok; üretim sayfasında hesabın seslerinden birini seç"),
    ("quota_exceeded", "ElevenLabs hesabının kredisi bitti"),
    ("rate_limit", "ElevenLabs şu an istek sınırında; birkaç dakika sonra tekrar dene"),
)


class ElevenError(RuntimeError):
    pass


def explain(error):
    text = str(error)
    for needle, why in KNOWN_ERRORS:
        if needle in text:
            return f"{why} ({text[:300]})"
    return text[:400]


def _account(account=None):
    """The account this call spends from, checked: it must exist, be usable, and be an API-key account."""
    account = account or accounts.default_eleven()
    acc = accounts.eleven(account)
    if not acc or not accounts.can_use(account):
        raise ElevenError(f"ElevenLabs hesabı kullanılamıyor: {account}")
    if acc.get("type") != "apikey":
        raise ElevenError("bu ElevenLabs hesabı connector tipinde; connector kaldırıldı — Hesaplar → ElevenLabs API "
                          "anahtarı ekle ve hesabı varsayılan yap")
    return account, acc


def _write(data, ext, key):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"{key}.{ext}")
    with open(path + ".part", "wb") as f:
        f.write(data)
    os.replace(path + ".part", path)
    return path


def _node(prefix, ident):
    """A reference id our own ids and the API's ids can share: 'gen:<generation id>' / 'asset:<asset id>'."""
    return f"{prefix}:{ident}" if ident else None


def _pick_ext(mime, fallback):
    m = str(mime or "").lower()
    for needle, ext in (("wav", "wav"), ("mpeg", "mp3"), ("mp3", "mp3"), ("mp4", "mp4"), ("png", "png")):
        if needle in m:
            return ext
    return fallback


def _gemini_on(kind):
    """Did the creator point this capability at Gemini? (Hesaplar → Medya üreticisi)"""
    from . import mediaprov
    return mediaprov.choice(kind) == "gemini"


def _gemini_cost(con, kind, model, units, unit, usd, note):
    from . import gemini
    gemini.guard(con, usd)
    gemini.record(con, kind, model, units, unit, usd, note)
    return 0.0        # Gemini bills dollars: nothing is deducted from the ElevenLabs credit budget


def _estimated(kind, model, units, approved):
    """Credits to write in the ledger for a REST generation: the learned rate, else what the creator approved.

    The REST API reports no `credit_cost`, so the ledger keeps the estimate; an unmeasured model records the approved
    amount, which is exactly the ceiling credits.guard enforced."""
    est = credits.estimate([{"kind": kind, "model": model, "units": units, "unit": ""}])
    return float(est["total"]) if not est["unknown"] else float(approved or 0)


# ---------------------------------------------------------------- voice
def tts(con, text, voice_id, model="eleven_v4", idea_id=None, approved=None, account=None):
    """Speech for `text` (one take). Returns (mp3_path, credit_cost). Cached by (text, voice, model).
    `approved`: the credit amount the user approved; credits.guard refuses without it."""
    if _gemini_on("voice"):
        from . import gemini
        gmodel = gemini.DEFAULT["voice"]
        gkey = "gtts_" + hashlib.sha1(f"{gmodel}|{voice_id}|{text}".encode()).hexdigest()[:16]
        for ext in ("wav", "mp3"):
            hit = os.path.join(OUT, f"{gkey}.{ext}")
            if os.path.exists(hit):
                return hit, 0.0
        data, mime, _ = gemini.tts(text, voice=gemini.pick_voice(voice_id))
        path = _write(data, _pick_ext(mime, "wav"), gkey)
        _gemini_cost(con, "voice", gmodel, len(text), "char", gemini.price("voice", gmodel, len(text)), text[:60])
        return path, 0.0
    key = "tts_" + hashlib.sha1(f"{model}|{voice_id}|{text}".encode()).hexdigest()[:16]
    cached = os.path.join(OUT, f"{key}.mp3")
    if os.path.exists(cached):
        return cached, 0.0
    account, acc = _account(account)
    credits.guard(con, "tts", model, len(text), approved, account)
    before = eleven_api.subscription(acc["key"])["used"]
    data, chars = eleven_api.tts(acc["key"], text, voice_id, model)
    path = _write(data, "mp3", key)
    cost = float(max(0, eleven_api.subscription(acc["key"])["used"] - before)) or float(chars)   # measured, else reported
    credits.record(con, "tts", model, len(text), "char", cost, idea_id, text[:60], account)
    return path, cost


# ---------------------------------------------------------------- music and sound effects
def generate(con, kind, model, prompt_text, params, units, unit, idea_id=None, ext="mp3", approved=None, account=None):
    """Music or a sound effect through the REST API, with the given model params.
    `approved`: credits the user approved for this call; credits.guard refuses without it."""
    key = f"{kind}_" + hashlib.sha1((f"{model}|{prompt_text}|{json.dumps(params, sort_keys=True)}").encode()).hexdigest()[:16]
    if kind == "music" and _gemini_on("music"):
        from . import gemini
        gmodel, secs = gemini.DEFAULT["music"], float(params.get("duration_seconds") or units or 30)
        gkey = "gmusic_" + hashlib.sha1(f"{gmodel}|{prompt_text}|{secs}".encode()).hexdigest()[:16]
        hit = next((os.path.join(OUT, f"{gkey}.{e}") for e in ("mp3", "wav") if os.path.exists(os.path.join(OUT, f"{gkey}.{e}"))), None)
        if hit:
            return hit, 0.0
        data, mime, _ = gemini.music(prompt_text, secs, gmodel)
        path = _write(data, _pick_ext(mime, "mp3"), gkey)
        _gemini_cost(con, "music", gmodel, 1, "song", gemini.price("music", gmodel), prompt_text[:60])
        return path, 0.0
    cached = os.path.join(OUT, f"{key}.{ext}")
    if os.path.exists(cached):
        return cached, 0.0
    if kind == "video":
        raise ElevenError("bu video modeli yalnız connector ile üretilebiliyordu; connector kaldırıldı — "
                          "Medya üreticisi → video için ElevenLabs (API) veya Gemini kullan")
    account, acc = _account(account)
    credits.guard(con, kind, model, units, approved, account)
    secs = float(params.get("duration_seconds") or units)
    before = eleven_api.subscription(acc["key"])["used"]
    data = (eleven_api.music if kind == "music" else eleven_api.sound)(acc["key"], prompt_text, secs)
    path = _write(data, ext, key)
    cost = float(max(0, eleven_api.subscription(acc["key"])["used"] - before))
    credits.record(con, kind, model, units, unit, cost, idea_id, prompt_text[:60], account)
    return path, cost


# ---------------------------------------------------------------- images
def image_model(refs=()):
    return EDIT_MODEL if refs else IMAGE_MODEL


def image(con, prompt_text, approved, account=None, aspect="9:16", flow_id=None, refs=(), idea_id=None, model=None):
    """One illustration (png). `refs`: earlier ids (`gen:`/`asset:`, or a local file) to keep characters and style
    the same. Returns (path, cost, flow_id (None), node id). Cached by (prompt, refs, aspect)."""
    model = model or image_model(refs)
    key = "img_" + hashlib.sha1(f"{model}|{aspect}|{','.join(map(str, refs))}|{prompt_text}".encode()).hexdigest()[:16]
    cached = os.path.join(OUT, f"{key}.png")
    meta_path = cached + ".json"
    if os.path.exists(cached) and os.path.exists(meta_path):
        m = json.load(open(meta_path))
        return cached, 0.0, m.get("flow_id"), m.get("node_id")
    account, acc = _account(account)
    ratio = "9:16" if aspect == "9:16" else "16:9"
    if _gemini_on("image"):                             # Gemini's own image model (Nano Banana / Imagen)
        from . import gemini
        gmodel = gemini.DEFAULT["image"]
        data, mime, iid = gemini.image(prompt_text, gmodel, aspect=ratio, refs=refs)
        path = _write(data, "png", key)
        node = _node("gen", iid)
        json.dump({"flow_id": None, "node_id": node, "prompt": prompt_text, "refs": [str(r) for r in refs]},
                  open(meta_path, "w"))
        cost = _gemini_cost(con, "image", gmodel, 1, "img", gemini.price("image", gmodel), prompt_text[:60])
        return path, cost, None, node
    credits.guard(con, "image", model, 1, approved, account)
    data, _, gid = eleven_api.image(acc["key"], prompt_text, model, aspect=ratio, refs=refs)
    path = _write(data, "png", key)
    cost = _estimated("image", model, 1, approved)
    node = _node("gen", gid)
    json.dump({"flow_id": None, "node_id": node, "prompt": prompt_text, "refs": [str(r) for r in refs]},
              open(meta_path, "w"))
    credits.record(con, "image", model, 1, "img", cost, idea_id, prompt_text[:60], account)
    return path, cost, None, node


# ---------------------------------------------------------------- generated clips and presenters
def video(con, prompt_text, approved, seconds, account=None, aspect="9:16", flow_id=None, start=None, model=None,
          audio=False, idea_id=None, inputs=None, resolution=None, rate_model=None, frame_aspect=False):
    """One generated clip (mp4). `start` = an earlier `gen:`/`asset:` id used as the first frame; `inputs` =
    {id: what it is} for models fed by several references (an avatar: the presenter image and the voice).
    Returns (path, cost, flow_id (None), node id). Cached by every input."""
    model = model or VIDEO_MODEL
    rate_model = rate_model or model
    inputs = dict(inputs or ({start: "the clip's start frame"} if start else {}))
    key = "vid_" + hashlib.sha1((f"{model}|{aspect}|{sorted(inputs)}|{seconds}|{audio}|{prompt_text}"
                                 + (f"|{resolution}" if resolution else "")).encode()).hexdigest()[:16]
    cached = os.path.join(OUT, f"{key}.mp4")
    meta_path = cached + ".json"
    if os.path.exists(cached) and os.path.exists(meta_path):
        m = json.load(open(meta_path))
        return cached, 0.0, m.get("flow_id"), m.get("node_id")
    account, acc = _account(account)
    if _gemini_on("video"):
        from . import gemini
        if model == AVATAR_MODEL:
            raise ElevenError("konuşan sunucu (avatar) Gemini'de yok: Medya üreticisi → video'yu ElevenLabs yap")
        gmodel = gemini.DEFAULT["video"]
        data, mime, iid = gemini.video(prompt_text, seconds, gmodel, aspect=aspect, start=start,
                                       resolution=resolution or "1080p")
        path = _write(data, "mp4", key)
        node = _node("gen", iid)
        json.dump({"flow_id": None, "node_id": node, "prompt": prompt_text, "inputs": inputs}, open(meta_path, "w"))
        cost = _gemini_cost(con, "video", gmodel, seconds, "s",
                            gemini.price("video", gmodel, seconds, resolution=resolution or "1080p"), prompt_text[:60])
        return path, cost, None, node
    credits.guard(con, "video", rate_model, seconds, approved, account)
    if model == AVATAR_MODEL:                           # a talking presenter: the image speaks the audio
        img = next((n for n, what in inputs.items() if "audio" not in str(what).lower()), None)
        aud = next((n for n, what in inputs.items() if "audio" in str(what).lower()), None)
        data, _, gid = eleven_api.lipsync(acc["key"], img, aud, model)
    else:
        data, _, gid = eleven_api.video(acc["key"], prompt_text, model, seconds, aspect, start=start,
                                        images=[n for n in inputs if n != start], audios=[], resolution=resolution,
                                        generate_audio=audio)
    path = _write(data, "mp4", key)
    cost = _estimated("video", rate_model, seconds, approved)
    node = _node("gen", gid)
    json.dump({"flow_id": None, "node_id": node, "prompt": prompt_text, "inputs": inputs}, open(meta_path, "w"))
    credits.record(con, "video", rate_model, seconds, "s", cost, idea_id, prompt_text[:60], account)
    return path, cost, None, node


def avatar(con, image_node, audio_node, flow_id, seconds, approved, account=None, aspect="9:16", model=None,
           prompt_text="The presenter speaks to camera, natural head movement and blinking, steady framing."):
    """A talking presenter: an image and a speech reference -> (path, cost)."""
    path, cost, _, _ = video(con, prompt_text, approved, seconds, account, aspect, flow_id, model=model or AVATAR_MODEL,
                             inputs={image_node: "the presenter image", audio_node: "the speech audio to lip-sync"})
    return path, cost


# ---------------------------------------------------------------- references and voices
def new_flow(account=None, name="factory"):
    """Flows were a connector concept; the REST path needs none (kept so callers do not branch)."""
    return None


def upload(path, flow_id=None, account=None, put=None):
    """A local file as an API asset (free) -> `asset:<id>`, usable as a reference by later generations."""
    _, acc = _account(account)
    return _node("asset", eleven_api.upload(acc["key"], path))


def asset_node(asset_id, flow_id=None, modality="image", account=None):
    """An already-uploaded asset id as a reference node."""
    return _node("asset", asset_id)


def media_duration(path):
    out = subprocess.run([FFPROBE, "-v", "error", "-show_entries",
                          "format=duration", "-of", "csv=p=0", path], capture_output=True, text=True).stdout
    return float(out.strip() or 0)


def avatar_node(flow_id=None):
    """The old avatar picker read a connector flow; with the REST path there is nothing to read."""
    return {"avatar_nodes": [], "node_count": 0}


def check_voice(voice_id, flow_id=None):
    """Does this account have `voice_id`? Read from the account's own voice list (free)."""
    _, acc = _account()
    return {"ok": any(v["voice_id"] == voice_id for v in eleven_api.info(acc["key"], fresh=True)["voices"])}


def add_voice(voice_id, language, name=None, check=check_voice):
    """Save a voice the creator picked in the Studio to `data/eleven_profile.json` after the account confirms it."""
    res = check(voice_id)
    if not res.get("ok"):
        raise ElevenError(explain("does not resolve") + f" ({voice_id})")
    try:
        prof = json.load(open(PROFILE))
    except (OSError, ValueError):
        prof = {"voices": [], "defaults": {}, "avatar": {}}
    voice = {"voice_id": voice_id, "name": (name or "").strip()[:60] or f"Ses {language.upper()} · {voice_id[:6]}",
             "language": language, "category": "custom", "note": "Studio'dan eklendi"}
    prof["voices"] = [v for v in prof.get("voices", []) if v.get("voice_id") != voice_id] + [voice]
    os.makedirs(os.path.dirname(PROFILE), exist_ok=True)
    json.dump(prof, open(PROFILE, "w"), ensure_ascii=False, indent=1)
    return voice


def list_voices():
    """The current account's own voices, straight from the API (with their preview URLs)."""
    _, acc = _account()
    return eleven_api.info(acc["key"], fresh=True)["voices"]
