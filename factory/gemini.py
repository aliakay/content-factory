"""Google Gemini: the second media provider (voice, music, image, video) next to ElevenLabs.

One key, four kinds of media. Everything goes through the Interactions endpoint
(`POST /v1beta/interactions`): the request says what comes back (`response_format.type`) and the answer carries the
media base64-encoded in its `steps` array, in the last `model_output` block of that type — so there is no flow, no
node graph and no CLI involved:

  voice   gemini-3.8-flash-tts           input text + generation_config.speech_config.voice -> audio (wav)
  music   lyria-3-clip-preview (30 s)    input text                                            -> audio
          lyria-3.5 (full song)
  image   gemini-nano-banana-2.1         input text (+ reference images)                       -> image/png
          gemini-3.1-flash-image, gemini-3-pro-image
  video   gemini-omni-1.2-flash          input text, response_format.aspect_ratio/duration      -> video/mp4

A reference comes from `previous_interaction_id` (the id of an earlier interaction: the same character, the same
plate) or as an inline base64 image. The id we hand back is `gen:<interaction id>`, the same shape
factory/eleven.py uses, so callers do not care which provider drew the picture.

Money: Google bills dollars, not ElevenLabs credits, so spend goes to its own table (`gemini_ledger`) at the published
list prices below; the ElevenLabs credit ledger is untouched. A monthly dollar ceiling (CF_GEMINI_MONTHLY_USD, 25 by
default) refuses a call that would cross it.
"""
import base64, json, os, time, urllib.error, urllib.request

from .config import ROOT
from .store import now

API = "https://generativelanguage.googleapis.com/v1beta"
REVISION = "2026-05-20"          # the Interactions API revision these bodies are written against
MONTHLY_USD = float(os.environ.get("CF_GEMINI_MONTHLY_USD") or 25)
CACHE = os.path.join(ROOT, "data", "gemini_models.json")

MODELS = {
    "voice": ("gemini-3.8-flash-tts", "gemini-3.8-flash-lite-tts", "gemini-2.5-flash-preview-tts"),
    "music": ("lyria-3-clip-preview", "lyria-3.5", "lyria-3-pro-preview"),
    "image": ("gemini-nano-banana-2.1", "gemini-3.1-flash-image", "gemini-3-pro-image",
              "gemini-3.1-flash-lite-image"),
    "video": ("gemini-omni-1.2-flash",),
}
DEFAULT = {"voice": "gemini-3.8-flash-tts", "music": "lyria-3-clip-preview",
           "image": "gemini-nano-banana-2.1", "video": "gemini-omni-1.2-flash"}
VOICES = ("Kore", "Puck", "Charon", "Fenrir", "Aoede", "Leda", "Orus", "Zephyr", "Enceladus", "Iapetus",
          "Algieba", "Despina", "Erinome", "Algenib", "Rasalgethi", "Laomedeia", "Achernar", "Alnilam",
          "Schedar", "Gacrux", "Pulcherrima", "Achird", "Zubenelgenubi", "Vindemiatrix", "Sadachbia",
          "Sadaltager", "Sulafat")
# Published list prices (USD, 2026-11). A token price is turned into the unit we buy: chars for speech, seconds for
# video, one picture or one song for the rest.
PRICES = {
    "gemini-3.8-flash-tts": {"text_usd_per_1m_tokens": 0.50, "audio_usd_per_second": 0.000225},
    "gemini-3.8-flash-lite-tts": {"text_usd_per_1m_tokens": 0.50, "audio_usd_per_second": 0.000225},
    "gemini-2.5-flash-preview-tts": {"text_usd_per_1m_tokens": 0.50, "audio_usd_per_second": 0.000225},
    "lyria-3-clip-preview": {"usd_per_song": 0.04},
    "lyria-3.5": {"usd_per_song": 0.08},
    "lyria-3-pro-preview": {"usd_per_song": 0.08},
    "gemini-nano-banana-2.1": {"usd_per_image": {"1K": 0.0336, "2K": 0.067, "4K": 0.134}},
    "gemini-3.1-flash-image": {"usd_per_image": {"1K": 0.0336, "2K": 0.067, "4K": 0.134}},
    "gemini-3.1-flash-lite-image": {"usd_per_image": {"1K": 0.02, "2K": 0.04, "4K": 0.08}},
    "gemini-3-pro-image": {"usd_per_image": {"1K": 0.134, "2K": 0.268, "4K": 0.536}},
    "gemini-omni-1.2-flash": {"usd_per_second": {"360p": 0.023, "720p": 0.07, "1080p": 0.104, "4K": 0.209}},
}
MAX_INLINE = 25 * 1024 * 1024
MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
        ".heic": "image/heic"}

SCHEMA = """CREATE TABLE IF NOT EXISTS gemini_ledger (
  id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT, kind TEXT, model TEXT, units REAL, unit TEXT, usd REAL,
  prod_id TEXT, note TEXT, user TEXT
)"""


class GeminiError(RuntimeError):
    pass


# ---------------------------------------------------------------- key, ledger, price
def key(uid=None):
    """This user's Gemini key, else the owner's GEMINI_API_KEY from config.env."""
    from . import accounts
    k = accounts.gemini_key(uid) or os.environ.get("GEMINI_API_KEY") or ""
    if not k:
        raise GeminiError("Gemini anahtarı yok: Hesaplar → Google Gemini API bölümüne anahtarını gir "
                          "(ya da config.env'e GEMINI_API_KEY yaz)")
    return k


def ensure(con):
    con.execute(SCHEMA)
    con.commit()


def record(con, kind, model, units, unit, usd, note="", prod_id=None):
    """One row of Gemini spend in dollars (its own ledger: Google does not sell ElevenLabs credits)."""
    from . import accounts
    ensure(con)
    con.execute("INSERT INTO gemini_ledger (at, kind, model, units, unit, usd, prod_id, note, user) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (now(), kind, model, units, unit, usd, prod_id or os.environ.get("FACTORY_PROD_ID"),
                 note[:120], accounts.current()))
    con.commit()


def month_usd(con):
    ensure(con)
    start = time.strftime("%Y-%m-01")
    return float(con.execute("SELECT COALESCE(SUM(usd),0) FROM gemini_ledger WHERE at >= ?", (start,)).fetchone()[0] or 0)


def guard(con, usd, approved_usd=None):
    """Refuse a call that would cross the monthly ceiling (or the approved amount for this step, when given)."""
    if approved_usd is not None and usd > float(approved_usd) * 1.15:
        raise GeminiError(f"Gemini tahmini ${usd:.3f}, onaylanan ${float(approved_usd):.2f} tutarını aşıyor")
    spent = month_usd(con)
    if spent + usd > MONTHLY_USD:
        raise GeminiError(f"Gemini aylık sınırı: ${spent:.2f} harcandı + ${usd:.3f} > ${MONTHLY_USD:.0f}")
    return usd


def price(kind, model, units=1, unit="", resolution=None, size=None):
    """Estimated dollars for one generation (list prices; an unknown model or unit prices at 0 and records units only)."""
    p = PRICES.get(model) or {}
    if kind == "voice":
        chars = float(units or 0)
        seconds = chars / 14.0                       # ~2.4 Turkish words/s at ~6 chars a word
        return round(chars / 4 / 1e6 * float(p.get("text_usd_per_1m_tokens") or 0)
                     + seconds * float(p.get("audio_usd_per_second") or 0), 4)
    if kind == "music":
        return float(p.get("usd_per_song") or 0)
    if kind == "image":
        return float((p.get("usd_per_image") or {}).get(size or "2K") or 0)
    if kind == "video":
        return round(float(units or 0) * float((p.get("usd_per_second") or {}).get(resolution or "1080p") or 0), 4)
    return 0.0


# ---------------------------------------------------------------- the Interactions endpoint
def _req(path, body=None, api_key=None, timeout=600, method=None):
    url = API + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method or ("POST" if data else "GET"),
                                 headers={"x-goog-api-key": api_key or key(), "Accept": "application/json",
                                          "Content-Type": "application/json", "Api-Revision": REVISION})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:400]
        raise GeminiError(f"Gemini {e.code}: {detail}") from None
    except urllib.error.URLError as e:
        raise GeminiError(f"Gemini'ye ulaşılamadı: {e.reason}") from None


def check(api_key):
    """Is this key good? -> {ok, models} (one free call)."""
    try:
        out = _req("/models?pageSize=1", api_key=api_key, timeout=20)
    except GeminiError as e:
        if " 401" in str(e) or " 403" in str(e):
            raise ValueError("Gemini anahtarı geçersiz (401/403)") from None
        raise ValueError(f"Gemini anahtarı doğrulanamadı: {e}") from None
    return {"ok": True, "models": len(out.get("models") or [])}


def _media(resp, kind, timeout=900):
    """The media out of one interaction: last model_output block of `kind` -> (bytes, mime, interaction id)."""
    status = resp.get("status")
    iid = resp.get("id")
    for _ in range(int(timeout // 5)):
        if status == "completed" or status is None:
            break
        if status == "failed":
            raise GeminiError(f"Gemini {kind} üretilemedi: {resp.get('error') or status}")
        time.sleep(5)
        resp = _req(f"/interactions/{iid}", timeout=120)
        status, iid = resp.get("status"), resp.get("id") or iid
    found = None
    for step in resp.get("steps") or []:
        if not isinstance(step, dict) or step.get("type") != "model_output":
            continue
        for block in step.get("content") or []:
            if isinstance(block, dict) and block.get("type") == kind and block.get("data"):
                found = block
    if not found:
        texts = " ".join(str(b.get("text") or "") for s in resp.get("steps") or [] for b in (s.get("content") or [])
                         if isinstance(b, dict))[:300]
        raise GeminiError(f"Gemini {kind} dönmedi" + (f": {texts.strip()}" if texts.strip() else "")
                          + (f" (status {status})" if status else ""))
    return base64.b64decode(found["data"]), found.get("mime_type") or ("video/mp4" if kind == "video" else
                                                                      "image/png"), iid


def interaction(body, api_key=None, timeout=600):
    return _req("/interactions", body, api_key=api_key, timeout=timeout)


# ---------------------------------------------------------------- the four kinds
def pick_voice(voice_id=None, lang="tr"):
    """A Gemini voice name for this film. ElevenLabs voice ids mean nothing here, so a stable pick from the id keeps
    each film's narrator its own (and the same film keeps the same voice between runs)."""
    if voice_id in VOICES:
        return voice_id
    pool = VOICES[:8] if (lang or "tr").startswith("tr") else VOICES[8:]
    h = sum(ord(c) * (i + 1) for i, c in enumerate(str(voice_id or lang)))
    return pool[h % len(pool)]


def tts(text, voice="Kore", model=None, style=None, api_key=None):
    """Speech -> (audio bytes, mime, interaction id). `style` is a short acting note ("cheerful, urgent")."""
    model = model if str(model or "").startswith("gemini") else DEFAULT["voice"]
    content = [{"type": "text", "text": text}]
    if style:
        content[0]["annotations"] = [{"type": "speech_metadata", "style": str(style)[:200]}]
    body = {"model": model, "input": [{"type": "user_input", "content": content}],
            "response_format": {"type": "audio"},
            "generation_config": {"speech_config": [{"voice": voice}]}}
    data, mime, iid = _media(interaction(body, api_key), "audio")
    return data, mime or "audio/wav", iid


def music(prompt, seconds=30, model=None, api_key=None):
    """A track -> (audio bytes, mime, interaction id). The clip model is 30 s; a longer film loops it downstream."""
    model = model if str(model or "").startswith("lyria") else DEFAULT["music"]
    body = {"model": model, "input": prompt}
    data, mime, iid = _media(interaction(body, api_key, timeout=900), "audio")
    return data, mime or "audio/mpeg", iid


def image(prompt, model=None, aspect="9:16", refs=(), size="2K", api_key=None):
    """One image -> (png bytes, mime, interaction id). `refs`: `gen:<id>` continues that picture, a local file is sent
    inline as a reference image."""
    model = model if str(model or "").startswith(("gemini-", "imagen-")) else DEFAULT["image"]
    prior, inline = None, []
    for ref in refs or ():
        s = str(ref)
        if s.startswith("gen:"):
            prior = s[4:]                       # keep the character/plate: continue that interaction
        elif os.path.isfile(s):
            blob = open(s, "rb").read()
            if len(blob) <= MAX_INLINE:
                inline.append({"type": "image",
                               "mime_type": MIME.get(os.path.splitext(s)[1].lower(), "image/png"),
                               "data": base64.b64encode(blob).decode()})
    body = {"model": model,
            "input": ([{"type": "text", "text": prompt}] + inline) if inline else prompt,
            "response_format": {"type": "image", "mime_type": "image/png", "aspect_ratio": aspect, "image_size": size}}
    if prior:
        body["previous_interaction_id"] = prior
    data, mime, iid = _media(interaction(body, api_key), "image")
    return data, mime or "image/png", iid


def video(prompt, seconds=8, model=None, aspect="9:16", start=None, resolution="1080p", api_key=None):
    """One clip -> (mp4 bytes, mime, interaction id). `start` (`gen:<id>`) continues that picture as the first frame."""
    model = model if str(model or "").startswith("gemini-") else DEFAULT["video"]
    secs = int(max(3, min(15, round(float(seconds or 8)))))
    body = {"model": model, "input": prompt,
            "response_format": {"type": "video", "aspect_ratio": aspect, "duration": f"{secs}s",
                                "resolution": resolution}}
    if start and str(start).startswith("gen:"):
        body["previous_interaction_id"] = str(start)[4:]
    data, mime, iid = _media(interaction(body, api_key, timeout=1800), "video", timeout=1800)
    return data, mime or "video/mp4", iid
