"""The localization & dub line's code side: a finished video (uploaded to raw/talk/) gets a version in the project's
video language: transcript, a timed translation, a dub in the creator's voice placed on the original timing,
captions in the new language and, when asked for, lip-sync on the picture (sync-lipsync-v3).

  idea      transcribe the source, cut it into timed lines, price the dub -> proposal (gate)
  script    the translation, one line per source line, sized to its time slot -> script (gate; a note redoes it)
  assets    the voice (one TTS take), word timing, the dub track on the source timing, optional lip-sync, a captioned
            preview -> assets (gate)
  compose   the final with captions, technical QA and covers -> render
  publish   caption and hashtags in the new language -> publish (gate)
The original sound is replaced (there is no stem separation yet), so music under the voice is lost; the proposal
says so. Lip-sync prices are not in the learned rates yet: an unknown price reserves LIPSYNC_CEILING a second.
"""
import os, re, shutil, subprocess

from ..config import FFMPEG, ROOT
from . import project as P
from .explainer import remaining_budget, _con, _rel   # noqa: F401
from .footage import _ui
from .avatar import captions

LIPSYNC_MODEL = "sync-lipsync-v3"
LIPSYNC_CEILING = 1000         # credits a second reserved while the lip-sync price is unknown
LIP = re.compile(r"dudak|lip.?sync|lipsync", re.I)
GAP = 0.6                      # a pause this long ends a line
MAX_WORDS = 14
CPS = {"tr": 14.0, "en": 15.0}  # characters a second a voice says comfortably
MAX_TEMPO = 1.25
NAMES = {"tr": "Turkish", "en": "English"}


def _source(p):
    src = p.get("source") or ""
    full = os.path.realpath(os.path.join(ROOT, src))
    if not src or not full.startswith(os.path.realpath(os.path.join(ROOT, "raw", "talk")) + os.sep) or not os.path.isfile(full):
        raise P.GateError("the source video is not an uploaded file (raw/talk/)")
    return full


def _langs(p):
    to = p.get("video_lang") or "en"
    frm = p.get("source_lang") if p.get("source_lang") in NAMES else ("en" if to == "tr" else "tr")
    return frm, to


def _lipsync(p):
    return bool(p.get("lipsync")) or bool(LIP.search(p.get("brief") or ""))


def segments(words, dur):
    """Whisper words [[w, start, end, prob]] -> timed lines [{n, start, end, slot, text}]: a line ends at a sentence end,
    a pause of GAP s or MAX_WORDS words; `slot` is the time until the next line starts (what the dub may fill)."""
    out, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        if not nxt or re.search(r"[.!?…]$", w[0]) or nxt[1] - w[2] >= GAP or len(cur) >= MAX_WORDS:
            out.append({"start": round(cur[0][1], 2), "end": round(cur[-1][2], 2), "text": " ".join(x[0] for x in cur)})
            cur = []
    for i, s in enumerate(out):
        s["n"] = i + 1
        s["slot"] = round((out[i + 1]["start"] if i + 1 < len(out) else max(dur, s["end"])) - s["start"], 2)
    return out


def _cost(p, chars, secs):
    from .. import credits, formats
    items = [{"kind": "tts", "model": formats.VOICE_MODEL, "units": chars, "unit": "char", "label": "dub voice"}]
    if _lipsync(p):
        items.append({"kind": "video", "model": LIPSYNC_MODEL, "units": secs, "unit": "s", "label": f"lip-sync · {secs:.0f} s"})
    est = credits.estimate(items)
    lines = [{"label": x["label"] + (" (ceiling)" if x["credits"] is None else ""),
              "credits": x["credits"] if x["credits"] is not None else round(LIPSYNC_CEILING * secs)} for x in est["lines"]]
    return {"credits": sum(x["credits"] for x in lines), "lines": lines, "unknown": est["unknown"]}


def _ask(prompt):
    from .. import llm
    data, meta = llm.ask(prompt, tools=(), timeout=900)
    return (data if isinstance(data, dict) else {}), float((meta or {}).get("cost_usd") or 0)


def _transcribe(path, lang):
    from .. import talk
    return talk.transcribe(path, lang)


def _duration(path):
    from .. import media
    return float(media.probe_video(path)["duration"])


def idea(pid, s, note=None, d=None):
    """What is said in the source, when, and what the dub costs. Nothing is paid here."""
    p = P.load(pid, d)
    src = _source(p)
    frm, to = _langs(p)
    if frm == to:
        raise P.GateError("the source and the target language are the same")
    dur = _duration(src)
    segs = segments(_transcribe(src, frm), dur)
    if not segs:
        raise P.GateError("no speech found in the source video")
    chars = round(sum(len(x["text"]) for x in segs) * 1.15)      # a translation runs a little longer
    cost = _cost(p, chars, round(dur, 1))
    ui = _ui(p)
    lip = _lipsync(p)
    summary = {"tr": f"{dur:.0f} sn, {len(segs)} satır {NAMES[frm]} → {NAMES[to]}; ~{cost['credits']} kredi."
                     f"{' Dudak senkronu dahil.' if lip else ''} Orijinal ses (müzik dahil) dublajla değişir.",
               "en": f"{dur:.0f} s, {len(segs)} lines {NAMES[frm]} → {NAMES[to]}; ~{cost['credits']} credits."
                     f"{' Lip-sync included.' if lip else ''} The original sound (music too) is replaced by the dub."}[ui]
    if cost["unknown"]:
        summary += {"tr": " Dudak senkronu fiyatı henüz bilinmiyor: tavan ayrıldı.",
                    "en": " The lip-sync price is not known yet: a ceiling is reserved."}[ui]
    concept = {"id": "A", "title": p["title"], "hook": segs[0]["text"], "look": {"tr": "aynı görüntü", "en": "the same picture"}[ui],
               "structure": f"{len(segs)} lines · {dur:.0f} s · {frm}→{to}", "lines": [x["text"] for x in segs]}
    art = {"concepts": [concept], "chosen": "A", "seconds": round(dur, 1), "from": frm, "to": to, "segments": segs,
           "lipsync": lip, "voice": {"use": True}, "music": {"use": False}, "cost": cost, "summary": summary}
    return {"artifact": art, "summary": summary}


def _translate_prompt(p, segs, frm, to, note=None, cur=None):
    rows = "\n".join(f'{x["n"]}. [{x["slot"]:.1f} s, at most {int(x["slot"] * CPS[to])} characters] {x["text"]}' for x in segs)
    return f"""Translate a video's spoken lines from {NAMES[frm]} to {NAMES[to]} for a dub. Each translated line is
spoken in the same time slot as the original, so keep it within its character limit: shorten, never pad. Spoken,
natural {NAMES[to]}; numbers written as people say them; keep names; no stage directions, no emoji.
Lines (number, time slot, limit, original):
{rows}
{f"Current translation: {cur}" if cur else ""}
{f"The creator's note: <<<{note}>>>" if note else ""}
Reply ONLY JSON: {{"lines": ["one translated line per original line, same count and order"], "title": "the video
title in {NAMES[to]}", "caption": "a post caption in {NAMES[to]}", "hashtags": ["#..."]}}"""


def script(pid, s, note=None, d=None):
    p = P.load(pid, d)
    prop = P.read_artifact(pid, "proposal", d) or {}
    segs, frm, to = prop.get("segments") or [], prop.get("from"), prop.get("to")
    if not segs:
        raise P.GateError("no transcript yet; redo the idea")
    cur = (P.read_artifact(pid, "script", d) or {}).get("lines") if note else None
    data, usd = _ask(_translate_prompt(p, segs, frm, to, note, cur))
    lines = [str(x).strip() for x in data.get("lines") or []]
    if len(lines) != len(segs) or not all(lines):
        raise P.GateError(f"the translation came back with {len(lines)} lines for {len(segs)}; give a note and redo")
    tight = [x["n"] for x, l in zip(segs, lines) if len(l) > x["slot"] * CPS[to] * MAX_TEMPO]
    ui = _ui(p)
    summary = {"tr": f"{len(lines)} satır çevrildi.", "en": f"{len(lines)} lines translated."}[ui]
    if tight:
        summary += {"tr": f" Şu satırlar zamanına sığmayabilir: {', '.join(map(str, tight))}.",
                    "en": f" These lines may not fit their time: {', '.join(map(str, tight))}."}[ui]
    art = {"title": data.get("title") or p["title"], "hook": lines[0], "lines": lines, "source": [x["text"] for x in segs],
           "claims": [], "caption": data.get("caption") or "", "hashtags": data.get("hashtags") or [], "tight": tight,
           "summary": summary}
    return {"artifact": art, "summary": summary, "cost": {"usd": usd}}


def placements(segs, times, total):
    """Where each dubbed line goes: [{n, at, from, to, tempo}] — the line's piece of the voice file (`from`-`to`),
    placed at the source line's start and sped up (at most MAX_TEMPO) when it is longer than the slot."""
    out = []
    for x, (a, b) in zip(segs, times):
        b = min(b, total)
        tempo = round(min(MAX_TEMPO, max(1.0, (b - a) / max(0.1, x["slot"]))), 3)
        out.append({"n": x["n"], "at": x["start"], "from": round(a, 3), "to": round(b, 3), "tempo": tempo})
    return out


def retime(words, places):
    """Voice-file word timings -> timings on the video's timeline (for the captions)."""
    out = []
    for w, a, b in words:
        pl = next((x for x in places if x["from"] - 0.05 <= a < x["to"] + 0.05), None)
        if pl:
            f = lambda t: pl["at"] + (min(t, pl["to"]) - pl["from"]) / pl["tempo"]
            out.append((w, round(f(a), 3), round(f(b), 3)))
    return out


def dub_track(voice, places, dur, out):
    """The dub: each line's piece of the voice at its place on the timeline, one audio file as long as the video."""
    parts, labels = [], []
    for i, x in enumerate(places):
        parts.append(f"[0:a]atrim=start={x['from']}:end={x['to']},asetpts=PTS-STARTPTS,atempo={x['tempo']},"
                     f"adelay={int(x['at'] * 1000)}:all=1[a{i}]")
        labels.append(f"[a{i}]")
    fc = ";".join(parts) + f";{''.join(labels)}amix=inputs={len(labels)}:normalize=0,asetpts=N/SR/TB,apad=whole_dur={dur},atrim=end={dur}[out]"
    subprocess.run([FFMPEG, "-y", "-v", "error", "-i", voice, "-filter_complex", fc, "-map", "[out]", "-ar", "48000", out],
                   check=True)
    return out


def _mux(video, audio, words, out, aspect="9:16", final=False):
    """The picture with the dub, captions burned in, voice levelled to -14 LUFS."""
    from ..formats import ASPECTS
    w, h = ASPECTS.get(aspect, (1080, 1920))
    ass = os.path.splitext(out)[0] + ".ass"
    open(ass, "w").write(captions(words, (w, h)))
    vf = (f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,"
          f"subtitles='{ass.replace(chr(39), '')}'")
    subprocess.run([FFMPEG, "-y", "-v", "error", "-i", video, "-i", audio, "-map", "0:v", "-map", "1:a", "-vf", vf,
                    "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-c:v", "libx264", "-preset", "medium" if final else "veryfast",
                    "-crf", "18" if final else "26", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                    "-shortest", "-movflags", "+faststart", out], check=True)
    return out


def assets(pid, s, note=None, d=None):
    """One voice take -> word timing -> the dub on the source timing -> lip-sync if asked -> a captioned preview."""
    from .. import accounts, eleven, formats, productions
    con, p = _con(), P.load(pid, d)
    prop = P.read_artifact(pid, "proposal", d) or {}
    sc = P.read_artifact(pid, "script", d) or {}
    segs, lines, to = prop.get("segments") or [], sc.get("lines") or [], prop.get("to")
    if len(lines) != len(segs):
        raise P.GateError("the translation does not match the transcript; redo the translation")
    src = _source(p)
    dur = _duration(src)
    acc = p.get("eleven_account") or accounts.default_eleven(p.get("created_by"))
    voice_id = p.get("voice_id") or formats.default_voice(to, acc)
    vpath, vcost = eleven.tts(con, " ".join(lines), voice_id, formats.VOICE_MODEL, approved=remaining_budget(pid, d),
                              account=acc)
    times, total, words = productions.align(vpath, lines, to)
    places = placements(segs, times, total)
    track = dub_track(vpath, places, dur, P.path(pid, "assets", "dub.wav", d=d))
    picture, lcost = src, 0.0
    if prop.get("lipsync"):
        flow = eleven.new_flow(acc, name=f"dub {pid}")
        vnode, anode = eleven.upload(src, flow, acc), eleven.upload(track, flow, acc)
        prompt = "Re-lip-sync the speaker's mouth to the new speech; change nothing else." + (f" {note}" if note else "")
        picture, lcost, _, _ = eleven.video(con, prompt, max(0, remaining_budget(pid, d) - round(vcost)), round(dur, 1),
                                            acc, p.get("aspect", "9:16"), flow, model=LIPSYNC_MODEL,
                                            inputs={vnode: "the video to re-lip-sync", anode: "the new speech audio"})
    timed = retime(words, places)
    os.makedirs(P.path(pid, "renders", d=d), exist_ok=True)
    if picture != src:
        shutil.copy2(picture, P.path(pid, "renders", "lipsync.mp4", d=d))
        picture = P.path(pid, "renders", "lipsync.mp4", d=d)
    prev = _mux(picture, track, timed, P.path(pid, "renders", "preview.mp4", d=d), p.get("aspect", "9:16"))
    fast = [x["n"] for x in places if x["tempo"] > 1.0]
    total_cost = round(vcost + lcost)
    ui = _ui(p)
    summary = {"tr": f"Dublaj hazır ({total_cost} kredi). Ses yerine oturuyor mu?", "en": f"The dub is ready ({total_cost} credits). Does the voice sit right?"}[ui]
    if fast:
        summary += {"tr": f" Hızlandırılan satırlar: {', '.join(map(str, fast))}; çeviride kısaltabilirsin.",
                    "en": f" Lines sped up: {', '.join(map(str, fast))}; shorten them in the translation."}[ui]
    art = {"voice": {"file": _rel(vpath), "voice_id": voice_id, "duration": dur, "credits": round(vcost),
                     "line_times": times, "words": [list(w) for w in timed]},
           "dub": {"file": _rel(track), "places": places}, "picture": _rel(picture),
           "lipsync": {"model": LIPSYNC_MODEL, "credits": round(lcost)} if prop.get("lipsync") else None,
           "music": None, "preview": _rel(prev), "summary": summary}
    return {"artifact": art, "summary": summary, "cost": {"credits": total_cost}}


def compose(pid, s, note=None, d=None):
    from .. import qa, thumbs
    p = P.load(pid, d)
    a = P.read_artifact(pid, "assets", d) or {}
    if not (a.get("dub") or {}).get("file"):
        raise P.GateError("no dub yet")
    out = _mux(os.path.join(ROOT, a["picture"]), os.path.join(ROOT, a["dub"]["file"]), a["voice"]["words"],
               P.path(pid, "renders", "final.mp4", d=d), p.get("aspect", "9:16"), final=True)
    tech = qa.technical(out, a["voice"]["duration"])
    title = (P.read_artifact(pid, "script", d) or {}).get("title") or p["title"]
    covers = thumbs.make(out, P.path(pid, "renders", d=d), title, p.get("aspect", "9:16"), lang=p.get("video_lang", "en"))
    probs = tech.get("problems", [])
    summary = ({"tr": "Final hazır; teknik kontrol temiz.", "en": "Final ready; technical checks clean."} if not probs else
               {"tr": f"Final hazır; {len(probs)} teknik bulgu var.", "en": f"Final ready; {len(probs)} technical findings."})[_ui(p)]
    art = {"final": _rel(out), "qa": {"technical": tech, "pass": not probs}, "covers": [_rel(c) for c in covers],
           "summary": summary}
    return {"artifact": art, "summary": summary}


def publish(pid, s, note=None, d=None):
    p = P.load(pid, d)
    sc = P.read_artifact(pid, "script", d) or {}
    tags = sc.get("hashtags") or []
    tags = tags.split() if isinstance(tags, str) else [t if t.startswith("#") else "#" + t for t in tags]
    lip = (P.read_artifact(pid, "assets", d) or {}).get("lipsync")
    notes = {"tr": "Ses yapay zekâ ile dublajlandı" + (" ve dudaklar yeniden senkronlandı" if lip else "") +
                   ": TikTok'ta \"Yapay zekâ ile oluşturuldu\" etiketini aç.",
             "en": "The voice is an AI dub" + (" and the lips were re-synced" if lip else "") +
                   ": turn on TikTok's \"AI-generated content\" label."}[_ui(p)]
    summary = {"tr": "Açıklama ve etiketler hazır.", "en": "Caption and hashtags ready."}[_ui(p)]
    art = {"caption": sc.get("caption") or sc.get("title") or p["title"], "hashtags": tags or ["#dub"], "notes": notes,
           "summary": summary}
    return {"artifact": art, "summary": summary}
