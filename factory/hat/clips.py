"""The clip factory line's code side: one long video (uploaded to raw/talk/) becomes a ranked batch of standalone
shorts, each with its own hook, framing and captions. Everything runs locally: no credits.

  idea        transcribe, cut into timed lines, the model picks and scores the strongest moments -> proposal (gate)
  scene_plan  framing: where the 9:16 crop sits for each clip (face-tracked), one still each -> plates (gate;
              "2: sol" / "2: left" moves clip 2's crop)
  assets      cut, crop, captions and the hook title for every clip -> assets (gate; a preview of each)
  edit        nothing to decide by hand
  compose     every clip at full quality, technical QA, covers -> render
  publish     a caption and hashtags per clip -> publish (gate)
"""
import json, os, re, subprocess

from ..config import FFMPEG, ROOT
from . import project as P
from .explainer import _rel
from .footage import _ui
from .avatar import captions
from .localize import segments

MIN_S, MAX_S = 15.0, 60.0
DEFAULT_N, MAX_N = 5, 10
SHIFT = {"sol": -0.2, "left": -0.2, "sağ": 0.2, "sag": 0.2, "right": 0.2, "orta": 0.0, "center": 0.0, "centre": 0.0}


def _source(p):
    src = p.get("source") or ""
    full = os.path.realpath(os.path.join(ROOT, src))
    if not src or not full.startswith(os.path.realpath(os.path.join(ROOT, "raw", "talk")) + os.sep) or not os.path.isfile(full):
        raise P.GateError("the source video is not an uploaded file (raw/talk/)")
    return full


def _count(brief):
    m = re.search(r"(\d+)\s*(?:adet\s*)?(klip|clip|kısa|short|video)", brief or "", re.I)
    return max(1, min(MAX_N, int(m.group(1)))) if m else DEFAULT_N


def _ask(prompt):
    from .. import llm
    data, meta = llm.ask(prompt, tools=(), timeout=900)
    return (data if isinstance(data, dict) else {}), float((meta or {}).get("cost_usd") or 0)


def _transcribe(path, lang):
    from .. import talk
    return talk.transcribe(path, lang)


def _probe(path):
    from .. import talk
    return talk.probe(path)


def _faces(path, dur):
    from .. import talk
    return talk.faces(path, dur, fps=0.5)


def pick(segs, raw, n):
    """The model's picks -> clean clips: line ranges snapped to the transcript, grown or shrunk into MIN_S..MAX_S,
    no overlaps (the higher score wins), best first, numbered."""
    by_n = {s["n"]: s for s in segs}
    out = []
    for c in sorted(raw, key=lambda c: -float(c.get("score") or 0)):
        try:
            a, b = int(c.get("from")), int(c.get("to"))
        except (TypeError, ValueError):
            continue
        if a not in by_n or b not in by_n or b < a:
            continue
        taken = lambda i: any(x["start"] < by_n[i]["end"] and by_n[i]["start"] < x["end"] for x in out)
        while by_n[b]["end"] - by_n[a]["start"] < MIN_S:      # grow into free lines, forward first
            if b + 1 in by_n and not taken(b + 1):
                b += 1
            elif a - 1 in by_n and not taken(a - 1):
                a -= 1
            else:
                break
        while by_n[b]["end"] - by_n[a]["start"] > MAX_S and b > a:
            b -= 1
        start, end = by_n[a]["start"], by_n[b]["end"]
        if end - start < MIN_S * 0.66 or any(start < x["end"] and x["start"] < end for x in out):
            continue
        out.append({"from": a, "to": b, "start": round(start, 2), "end": round(end, 2), "seconds": round(end - start, 1),
                    "hook": str(c.get("hook") or "").strip() or by_n[a]["text"][:60], "why": c.get("why") or "",
                    "score": round(float(c.get("score") or 0), 1), "caption": c.get("caption") or "",
                    "hashtags": c.get("hashtags") or [], "text": " ".join(by_n[i]["text"] for i in range(a, b + 1))})
    for i, c in enumerate(out):
        c["n"] = i + 1
    return out


def _pick_prompt(p, segs, n, note=None, cur=None):
    rows = "\n".join(f'{s["n"]}. [{s["start"]:.0f}-{s["end"]:.0f} s] {s["text"]}' for s in segs)
    return f"""You cut a long video into standalone vertical shorts. Pick the {n} strongest moments: each must make
sense without the rest (a clear point, story, answer or reveal), start strong and end on a finished thought,
{MIN_S:.0f}-{MAX_S:.0f} s long, not overlapping. Score each 1-10 for how well it holds a scrolling viewer.
The creator's brief: <<<{p.get('brief') or ''}>>>
Transcript lines (number, time, text):
{rows}
{f"Current picks: {json.dumps(cur, ensure_ascii=False)}" if cur else ""}
{f"The creator's note on the picks: <<<{note}>>>" if note else ""}
Write hook, caption and hashtags in the video's language ({p.get('video_lang') or 'tr'}).
Reply ONLY JSON: {{"clips": [{{"from": <first line number>, "to": <last line number>, "hook": "an on-screen title,
max 6 words", "why": "one sentence", "score": <1-10>, "caption": "post caption", "hashtags": ["#..."]}}]}}"""


def idea(pid, s, note=None, d=None):
    """The ranked list of clips. A note re-picks them. No credits."""
    p = P.load(pid, d)
    src = _source(p)
    tpath = P.path(pid, "assets", "transcript.json", d=d)
    if os.path.isfile(tpath):
        tr = json.load(open(tpath))
    else:
        info = _probe(src)
        words = _transcribe(src, p.get("video_lang", "tr"))
        tr = {"words": words, "duration": info["duration"], "w": info["w"], "h": info["h"]}
        os.makedirs(os.path.dirname(tpath), exist_ok=True)
        json.dump(tr, open(tpath, "w"), ensure_ascii=False)
    segs = segments(tr["words"], tr["duration"])
    if tr["duration"] < MIN_S * 2 or not segs:
        raise P.GateError("the source is too short or has no speech for a batch of clips")
    n = _count(p.get("brief"))
    cur = None
    if note:
        cur = [{k: c[k] for k in ("n", "from", "to", "hook", "score")}
               for c in (P.read_artifact(pid, "proposal", d) or {}).get("clips") or []]
    data, usd = _ask(_pick_prompt(p, segs, n, note, cur))
    clips = pick(segs, data.get("clips") or [], n)[:n]
    if not clips:
        raise P.GateError("no usable clip came back; give a note and redo")
    ui = _ui(p)
    summary = {"tr": f"{tr['duration'] / 60:.0f} dk kaynaktan {len(clips)} klip, puana göre sıralı. Kredi harcanmaz.",
               "en": f"{len(clips)} clips from a {tr['duration'] / 60:.0f} min source, ranked by score. No credits."}[ui]
    if len(clips) < n:
        summary += {"tr": f" İstenen {n}; ayakta duran {len(clips)} an bulundu.",
                    "en": f" {n} asked; {len(clips)} moments stand on their own."}[ui]
    concepts = [{"id": str(c["n"]), "title": c["hook"], "hook": c["hook"], "structure": f'{c["seconds"]:.0f} s · {c["score"]}/10',
                 "look": c["why"]} for c in clips]
    art = {"concepts": concepts, "chosen": "1", "clips": clips, "segments": segs, "seconds": sum(c["seconds"] for c in clips),
           "voice": {"use": False}, "music": {"use": False}, "cost": {"credits": 0, "lines": []}, "summary": summary}
    return {"artifact": art, "summary": summary, "cost": {"usd": usd}}


def crop_x(faces, t0, t1, shift=0.0):
    """Where a 9:16 crop is centred across the clip (fraction of the width): the median face, else the middle."""
    xs = sorted(f[1] for f in faces if t0 - 1 <= f[0] <= t1 + 1)
    x = xs[len(xs) // 2] if xs else 0.5
    return round(min(1.0, max(0.0, x + shift)), 3)


def _vf(info, cx, aspect, size):
    w, h = size
    if aspect == "9:16" and info["w"] > info["h"]:
        cw = int(info["h"] * 9 / 16) // 2 * 2
        x = int(min(max(0, cx * info["w"] - cw / 2), info["w"] - cw))
        return f"crop={cw}:{info['h']}:{x}:0,scale={w}:{h},setsar=1"
    return f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1"


def scene_plan(pid, s, note=None, d=None):
    """One crop per clip, a still of each so the creator sees who stays in frame."""
    from ..formats import ASPECTS
    p = P.load(pid, d)
    src = _source(p)
    tr = json.load(open(P.path(pid, "assets", "transcript.json", d=d)))
    clips = (P.read_artifact(pid, "proposal", d) or {}).get("clips") or []
    old = {f["n"]: f for f in (P.read_artifact(pid, "plates", d) or {}).get("frames") or []}
    fpath = P.path(pid, "assets", "faces.json", d=d)
    if not os.path.isfile(fpath):
        json.dump(_faces(src, tr["duration"]), open(fpath, "w"))
    faces = json.load(open(fpath))
    moves = {}
    for m in re.finditer(r"(\d+)\s*[:.)-]\s*(\w+)", note or ""):
        if m.group(2).lower() in SHIFT:
            moves[int(m.group(1))] = SHIFT[m.group(2).lower()]
    aspect = p.get("aspect", "9:16")
    frames, files = [], []
    os.makedirs(P.path(pid, "plates", d=d), exist_ok=True)
    for c in clips:
        prev = old.get(c["n"], {})
        shift = max(-0.5, min(0.5, prev.get("shift", 0.0) + moves.get(c["n"], 0.0)))
        cx = crop_x(faces, c["start"], c["end"], shift)
        out = P.path(pid, "plates", f"clip_{c['n']}.jpg", d=d)
        vf = _vf(tr, cx, aspect, tuple(v // 3 for v in ASPECTS.get(aspect, (1080, 1920))))
        subprocess.run([FFMPEG, "-y", "-v", "error", "-ss", str(round((c["start"] + c["end"]) / 2, 2)), "-i", src,
                        "-frames:v", "1", "-vf", vf, out], check=True)
        frames.append({"n": c["n"], "file": _rel(out), "cx": cx, "shift": round(shift, 2)})
        files.append(_rel(out))
    summary = {"tr": "Her klibin kadrajı. Konuşan kişi kadrajda mı? Değilse \"2: sol\" ya da \"2: sağ\" yaz.",
               "en": "Each clip's framing. Is the speaker in frame? If not, write \"2: left\" or \"2: right\"."}[_ui(p)]
    art = {"concept": "", "plates": files, "frames": frames, "summary": summary}
    return {"artifact": art, "summary": summary}


def _ass(words, hook, size):
    """Captions for the clip plus the hook as a title on top for its first 3 seconds."""
    w, h = size
    body = captions(words, size)
    style = (f"Style: Hook,Montserrat,{round(h * 0.042)},&H0000D9FF,&H00000000,&H64000000,-1,7,0,8,{round(h * 0.12)}\n")
    body = body.replace("Style: Cap,", style + "Style: Cap,", 1)
    text = str(hook).replace("{", "(").replace("}", ")")
    return body + f"Dialogue: 1,0:00:00.00,0:00:03.00,Hook,{text}\n"


def cut(src, info, clip, words, cx, out, aspect="9:16", final=False):
    """One short: the clip's span, cropped, captions and hook burned in, levelled to -14 LUFS."""
    from ..formats import ASPECTS
    size = ASPECTS.get(aspect, (1080, 1920))
    local = [(x[0], round(x[1] - clip["start"], 3), round(x[2] - clip["start"], 3)) for x in words
             if x[1] >= clip["start"] - 0.05 and x[2] <= clip["end"] + 0.3]
    ass = os.path.splitext(out)[0] + ".ass"
    open(ass, "w").write(_ass(local, clip["hook"], size))
    vf = _vf(info, cx, aspect, size) + f",subtitles='{ass.replace(chr(39), '')}'"
    subprocess.run([FFMPEG, "-y", "-v", "error", "-ss", str(clip["start"]), "-t", str(round(clip["end"] - clip["start"] + 0.3, 2)),
                    "-i", src, "-vf", vf, "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-c:v", "libx264",
                    "-preset", "medium" if final else "veryfast", "-crf", "18" if final else "26", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", out], check=True)
    return out


def _all(pid, d, final):
    p = P.load(pid, d)
    src = _source(p)
    tr = json.load(open(P.path(pid, "assets", "transcript.json", d=d)))
    clips = (P.read_artifact(pid, "proposal", d) or {}).get("clips") or []
    cx = {f["n"]: f["cx"] for f in (P.read_artifact(pid, "plates", d) or {}).get("frames") or []}
    os.makedirs(P.path(pid, "renders", d=d), exist_ok=True)
    out = []
    for c in clips:
        f = P.path(pid, "renders", f"{'clip' if final else 'preview'}_{c['n']}.mp4", d=d)
        cut(src, tr, c, tr["words"], cx.get(c["n"], 0.5), f, p.get("aspect", "9:16"), final)
        out.append({"n": c["n"], "file": _rel(f), "hook": c["hook"], "seconds": c["seconds"]})
    return p, clips, out


def assets(pid, s, note=None, d=None):
    p, clips, out = _all(pid, d, final=False)
    if not out:
        raise P.GateError("no clips to cut")
    summary = {"tr": f"{len(out)} klip kesildi; altyazı ve başlık yakıldı. İzle; kadraj için sahne planına dön.",
               "en": f"{len(out)} clips cut with captions and titles. Watch them; go back to the scene plan for framing."}[_ui(p)]
    art = {"clips": out, "preview": out[0]["file"], "voice": None, "music": None, "summary": summary}
    return {"artifact": art, "summary": summary}


def edit(pid, s, note=None, d=None):
    P.decision(pid, "edit", "each clip: face-tracked 9:16 crop, 4-word captions, hook for 3 s, -14 LUFS", d=d)
    return {"artifact": {"sound": {"level": "full"}, "summary": "", "note": note}, "summary": ""}


def compose(pid, s, note=None, d=None):
    from .. import qa, thumbs
    p, clips, out = _all(pid, d, final=True)
    probs = 0
    for c, o in zip(clips, out):
        full = os.path.join(ROOT, o["file"])
        o["qa"] = qa.technical(full, c["seconds"])
        probs += len(o["qa"].get("problems", []))
        cdir = P.path(pid, "renders", f"clip_{c['n']}", d=d)
        os.makedirs(cdir, exist_ok=True)
        o["covers"] = [_rel(x) for x in thumbs.make(full, cdir, c["hook"], p.get("aspect", "9:16"),
                                                     lang=p.get("video_lang", "tr"))]
    summary = ({"tr": f"{len(out)} klip hazır; teknik kontrol temiz.", "en": f"{len(out)} clips ready; technical checks clean."}
               if not probs else {"tr": f"{len(out)} klip hazır; {probs} teknik bulgu var.",
                                  "en": f"{len(out)} clips ready; {probs} technical findings."})[_ui(p)]
    art = {"final": out[0]["file"], "finals": out, "qa": {"technical": out[0]["qa"], "pass": not probs},
           "covers": out[0]["covers"], "summary": summary}
    return {"artifact": art, "summary": summary}


def _tags(t):
    t = t.split() if isinstance(t, str) else t or []
    return [x if x.startswith("#") else "#" + x for x in t]


def publish(pid, s, note=None, d=None):
    p = P.load(pid, d)
    clips = (P.read_artifact(pid, "proposal", d) or {}).get("clips") or []
    finals = {o["n"]: o["file"] for o in (P.read_artifact(pid, "render", d) or {}).get("finals") or []}
    posts = [{"n": c["n"], "file": finals.get(c["n"]), "caption": c.get("caption") or c["hook"],
              "hashtags": _tags(c.get("hashtags")) or ["#shorts"]} for c in clips]
    summary = {"tr": f"{len(posts)} klibin açıklaması hazır; bir günde hepsini değil, birer birer paylaş.",
               "en": f"Captions for {len(posts)} clips are ready; post them one at a time, not all in a day."}[_ui(p)]
    art = {"caption": posts[0]["caption"] if posts else p["title"], "hashtags": posts[0]["hashtags"] if posts else [],
           "posts": posts, "notes": summary, "summary": summary}
    return {"artifact": art, "summary": summary}
