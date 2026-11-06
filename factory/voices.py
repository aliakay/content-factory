"""Voice suggestions: 2-3 narrators that fit a video's language (and kind), each with a listenable sample, so the
creator picks by ear instead of from a bare dropdown.

Sources, best first: the curated seed below (voices a real listing/ad was produced with), then a live refresh of the
ElevenLabs library through the connector (`refresh`, cached in data/voice_suggestions.json for TTL days), then the
built-in narrator of formats.DEFAULT_VOICES. Samples live in assets/voice_samples/<voice_id>.mp3 and are served by
the Studio under /media/assets/voice_samples/; a remote preview_url is downloaded there on first use.
"""
import json, os, re, time, urllib.request

from . import formats, llm
from .config import ROOT

SAMPLES = os.path.join(ROOT, "assets", "voice_samples")
CACHE = os.path.join(ROOT, "data", "voice_suggestions.json")
TTL = 14 * 86400
T = "mcp__claude_ai_ElevenLabs__"
KINDS = ("ad", "story", "explainer", "social")
KIND_TR = {"ad": "reklam / ilan", "story": "hikaye", "explainer": "anlatım", "social": "sosyal medya"}

# curated, verified with real generations (2026-11); `kinds` = what the voice suits best
SEED = {
    "tr": [
        {"voice_id": "c9eIhSvMHBxtYhLX4oBt", "name": "Orçun Togan", "gender": "male", "kinds": ["ad", "social"],
         "note": "enerjik ve güven veren erkek sesi; Reels / reklam"},
        {"voice_id": "uxXY4QvpsdWFe6Yigtlq", "name": "Mustafa", "gender": "male", "kinds": ["ad", "social"],
         "note": "enerjik, ticari tonda İstanbul erkek sesi"},
        {"voice_id": "IuRRIAcbQK5AQk1XevPj", "name": "Doğa", "gender": "male", "kinds": ["explainer", "story"],
         "note": "derin ve net erkek sesi; anlatım / belgesel"},
        {"voice_id": "bGmbiluBMaeupKCFxoOk", "name": "Gülsu Çağıran", "gender": "female", "kinds": ["social", "ad"],
         "note": "genç, canlı kadın sesi"},
    ],
    "en": [
        {"voice_id": "JBFqnCBsd6RMkjVDRZzb", "name": "George", "gender": "male", "kinds": ["story", "explainer"],
         "note": "warm British storyteller"},
    ],
}


def kind_for(text="", mode=""):
    """Rough video kind from a brief / mode name: ad (listing, product, promo), story, explainer or social."""
    s = f"{mode} {text}".lower()
    if re.search(r"ilan|kiral|satılık|reklam|ürün|kampanya|promo|\bad\b|listing|product|sale", s):
        return "ad"
    if re.search(r"hikaye|story|belgesel|documentary|karakter|character", s):
        return "story"
    if re.search(r"explain|anlat|eğitim|tutorial|nasıl|demo", s):
        return "explainer"
    return "social"


def _cache():
    try:
        return json.load(open(CACHE))
    except (OSError, ValueError):
        return {}


def _sample_path(voice_id):
    return os.path.join(SAMPLES, re.sub(r"[^\w-]", "", voice_id) + ".mp3")


def _fetch(voice):
    """Make sure the voice's sample is on disk (download its preview_url once). Returns the file path or None."""
    p = _sample_path(voice["voice_id"])
    if os.path.exists(p):
        return p
    url = voice.get("preview_url") or ""
    if not url.startswith("https://"):
        return None
    try:
        os.makedirs(SAMPLES, exist_ok=True)
        req = urllib.request.Request(url, headers={"User-Agent": "content-factory"})
        data = urllib.request.urlopen(req, timeout=30).read()
        if len(data) < 2000:
            return None
        open(p + ".part", "wb").write(data)
        os.replace(p + ".part", p)
        return p
    except (OSError, ValueError):
        return None


def _score(v, kind, gender):
    s = 0
    if kind in (v.get("kinds") or []):
        s += 2 - (v["kinds"].index(kind) > 0)   # primary kind beats secondary
    if gender and v.get("gender") == gender:
        s += 1
    return s


def suggest(lang, kind="social", gender=None, n=3):
    """Up to n voices for `lang`, best match first, mixed on purpose (not three near-identical male voices):
    after the best match come the best voices of a different gender / tone. Each: voice_id, name, gender, note,
    sample (URL path under /media, or None when no sample is available yet)."""
    lang = lang if lang in dict(formats.ELEVEN_LANGUAGES) else "en"
    pool = [dict(v, lang=lang) for v in SEED.get(lang, [])]
    seen = {v["voice_id"] for v in pool}
    pool += [dict(v, lang=lang) for v in (_cache().get(lang) or {}).get("voices", []) if v["voice_id"] not in seen]
    if not pool:
        d = formats.DEFAULT_VOICES.get(lang) or formats.DEFAULT_VOICES["en"]
        pool = [{"voice_id": d["voice_id"], "name": d["name"], "note": d.get("note", ""), "lang": lang}]
    pool.sort(key=lambda v: -_score(v, kind, gender))
    picked = pool[:1]
    for v in pool[1:]:   # variety: prefer another gender, then anything
        if len(picked) >= n:
            break
        if v.get("gender") not in {p.get("gender") for p in picked}:
            picked.append(v)
    for v in pool:
        if len(picked) >= n:
            break
        if v not in picked:
            picked.append(v)
    out = []
    for v in picked[:n]:
        has = _fetch(v)
        out.append({"voice_id": v["voice_id"], "name": v["name"], "gender": v.get("gender") or "",
                    "note": v.get("note") or "", "language": lang,
                    "sample": f"/media/assets/voice_samples/{os.path.basename(has)}" if has else None})
    return out


def known(voice_id):
    """The suggestion record for a voice_id (seed or cache), or None."""
    for lang, vs in SEED.items():
        for v in vs:
            if v["voice_id"] == voice_id:
                return dict(v, language=lang)
    for lang, c in _cache().items():
        for v in c.get("voices", []):
            if v["voice_id"] == voice_id:
                return dict(v, language=lang)
    return None


def stale(lang):
    c = _cache().get(lang)
    return not c or time.time() - c.get("at", 0) > TTL


def refresh(lang):
    """Ask the ElevenLabs library (connector, read-only, no credits) for voices that speak `lang`, keep the ones with
    a preview, cache them. Needs the connector, so it runs as a job (see jobs 'voice_suggest')."""
    name = dict(formats.ELEVEN_LANGUAGES).get(lang, lang)
    prompt = f"""Use the ElevenLabs tools to READ only. Call creative_list_voices to find LIBRARY voices that speak
{name} ({lang}) well and have a preview sample; prefer ones suited to narration, ads and short social videos, and
pick a mix of male and female voices. Return at most 8.
Reply ONLY JSON: {{"voices": [{{"voice_id": "...", "name": "...", "gender": "male|female", "kinds": ["ad"|"story"|"explainer"|"social"],
"note": "short description in English", "preview_url": "https://..."}}]}}"""
    data, _ = llm.ask(prompt, tools=(T + "creative_list_voices",), timeout=600, mcp=True, model="sonnet")
    vs = data.get("voices") if isinstance(data, dict) else data
    keep = []
    for v in vs or []:
        if isinstance(v, dict) and v.get("voice_id") and str(v.get("preview_url", "")).startswith("https://"):
            v["kinds"] = [k for k in v.get("kinds") or [] if k in KINDS]
            if _fetch(v):
                keep.append({k: v.get(k) for k in ("voice_id", "name", "gender", "kinds", "note")})
    c = _cache()
    c[lang] = {"at": time.time(), "voices": keep}
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    json.dump(c, open(CACHE, "w"), ensure_ascii=False, indent=1)
    return keep


def adopt(aid, voice_id):
    """A suggested library voice joins the account's voice list when the creator picks it: library voices work by id on
    any connector, so no check call is needed. API-key accounts list their own ElevenLabs library, so the voice has to
    be added there first. Returns True when the voice is (now) in the list."""
    from . import accounts
    v = known(voice_id)
    acc = accounts.eleven(aid) or {}
    if not v or not acc or acc.get("type") == "apikey":
        return False
    rec = {"voice_id": voice_id, "name": v["name"], "language": v.get("language", "en"), "category": "library",
           "note": v.get("note", "")}
    if aid == "ali":
        try:
            prof = json.load(open(formats.PROFILE))
        except (OSError, ValueError):
            prof = {"voices": [], "defaults": {}, "avatar": {}}
        prof["voices"] = [x for x in prof.get("voices", []) if x["voice_id"] != voice_id] + [rec]
        os.makedirs(os.path.dirname(formats.PROFILE), exist_ok=True)
        json.dump(prof, open(formats.PROFILE, "w"), ensure_ascii=False, indent=1)
    else:
        accounts.set_voices(aid, [x for x in acc.get("voices") or [] if x["voice_id"] != voice_id] + [rec])
    return True
