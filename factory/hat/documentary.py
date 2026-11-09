"""The documentary montage line: a theme told in beats, each beat a real open-licence clip found by meaning in the
public archives (factory.archive: Wikimedia Commons, NASA, the Internet Archive), narrated or carried by music.
Footage is free; only the narration and the music cost credits.

  idea        the beats (what each one says and shows, how to search for it), narration and music, the cost -> proposal (gate)
  scene_plan  per beat the best clips by meaning, the first one downloaded and a still at its in-point -> plates (gate;
              "3: 2" takes the 2nd clip, "3: other" searches again, "3: search harbour at night", "3: start 12")
  assets      the voice timed to its words, the music, the cut with captions -> assets (gate)
  edit        the cut itself: in-points and the transition -> edit (gate; "3: start 12", "transition: soft|cut")
  compose     the final, technical QA, covers -> render
  publish     caption, hashtags and the footage credits (CC BY needs them) -> publish (gate)
"""
import json, os, re, subprocess

from ..config import FFMPEG, ROOT
from . import project as P
from .avatar import captions
from .explainer import remaining_budget, _con, _rel   # noqa: F401
from .footage import _ui

WPS = {"tr": 2.3, "en": 2.5}
BEATS = (4, 14)
HOLD = (2.5, 7.0)              # an unnarrated beat's length range
FADE = 0.4                     # a soft transition
MIN_SPEED = 0.6                # a clip shorter than its beat plays at most this slow, then holds its last frame
MUSIC_DB = {"under": 0.18, "alone": 0.9}
SILENT = re.compile(r"\b(sessiz|anlatımsız|seslendirmesiz|yalnız\s*müzik|sadece\s*müzik|no\s*voice|"
                    r"no\s*narration|music\s*only|without\s*narration)\b", re.I)


def _ask(prompt):
    from .. import llm
    data, meta = llm.ask(prompt, tools=(), timeout=900)
    return (data if isinstance(data, dict) else {}), float((meta or {}).get("cost_usd") or 0)


def _size(p):
    from ..formats import ASPECTS
    return ASPECTS.get(p.get("aspect", "9:16"), (1080, 1920))


def _beats(raw, narrated):
    out = []
    for x in raw or []:
        look = str(x.get("look") or "").strip()
        qs = [str(q).strip() for q in (x.get("queries") or []) if str(q).strip()][:3]
        if not look or not qs:
            continue
        say = str(x.get("say") or "").strip()
        if narrated and not say:
            continue
        try:
            secs = float(x.get("seconds") or 4)
        except (TypeError, ValueError):
            secs = 4.0
        out.append({"n": len(out) + 1, "say": say if narrated else "", "text": str(x.get("text") or "").strip(),
                    "look": look, "queries": qs, "seconds": round(min(HOLD[1], max(HOLD[0], secs)), 1)})
    return out[:BEATS[1]]


def _lengths(beats, narrated, lang):
    """The planned length of each beat (narrated: its line's spoken time)."""
    if narrated:
        return [round(max(HOLD[0], len(b["say"].split()) / WPS.get(lang, 2.5) + 0.4), 1) for b in beats]
    return [b["seconds"] for b in beats]


def _cost(beats, narrated, music, lang):
    from .. import credits, formats, productions
    secs = round(sum(_lengths(beats, narrated, lang)) + 1, 1)
    items = []
    if narrated:
        items.append({"kind": "tts", "model": formats.VOICE_MODEL, "units": len(" ".join(b["say"] for b in beats)),
                      "unit": "char", "label": "voice"})
    if music:
        items.append({"kind": "music", "model": productions.MUSIC_MODEL, "units": secs, "unit": "s", "label": "music"})
    if not items:
        return {"credits": 0, "lines": [], "unknown": []}, secs
    est = credits.estimate(items)
    return {"credits": est["total"], "lines": [{"label": x["label"], "credits": x["credits"] or 0} for x in est["lines"]],
            "unknown": est["unknown"]}, secs


def _prompt(p, note=None, cur=None):
    return f"""You plan a documentary montage for a vertical short video, cut only from REAL open-licence archive
footage (Wikimedia Commons, NASA, the Internet Archive: city views, nature, space, historical film, people at work).
Nothing is generated, so every beat must show something such archives really hold. The creator's brief (theme and
tone): <<<{p.get('brief') or ''}>>>
Video language: {p.get('video_lang') or 'en'}. {BEATS[0]}-{BEATS[1]} beats, 45-120 s in total.
Each beat: say (one spoken narration sentence in the video language; beat 1 is the hook), text (2-6 words on screen,
video language, used when there is no narration), look (in English: what the footage shows, concrete and visual),
queries (2-3 short English archive searches, plain nouns: "bosphorus ferry", "istanbul skyline night"), seconds (2.5-7,
used when there is no narration). narrated: false when the brief asks for no voice / music only. music: whether a
score helps (always true without narration) and its prompt (instrumental, mood, instruments, tempo).
No claims you are unsure of; no current events.
{f"Current plan (JSON): {json.dumps(cur, ensure_ascii=False)}" if cur else ""}
{f"The creator's note: <<<{note}>>>" if note else ""}
Reply ONLY JSON: {{"title": "...", "narrated": true, "music": {{"use": true, "prompt": "..."}}, "beats": [{{"say": "...",
"text": "...", "look": "...", "queries": ["..."], "seconds": 4}}], "caption": "post caption", "hashtags": ["#..."]}}"""


def idea(pid, s, note=None, d=None):
    p = P.load(pid, d)
    cur = None
    if note:
        prev = P.read_artifact(pid, "proposal", d) or {}
        cur = {"beats": ((prev.get("concepts") or [{}])[0]).get("beats"), "music": prev.get("music"),
               "narrated": (prev.get("voice") or {}).get("use")}
    data, usd = _ask(_prompt(p, note, cur))
    narrated = data.get("narrated") is not False and not SILENT.search(p.get("brief") or "")
    beats = _beats(data.get("beats"), narrated)
    if len(beats) < BEATS[0]:
        raise P.GateError("the plan came back too short; give a note and redo")
    mu = data.get("music") or {}
    music = bool(mu.get("use")) or not narrated
    lang = p.get("video_lang", "tr")
    cost, secs = _cost(beats, narrated, music, lang)
    ui = _ui(p)
    how = ({"tr": "anlatımlı", "en": "narrated"} if narrated else {"tr": "anlatımsız", "en": "unnarrated"})[ui]
    how += ({"tr": ", müzikli", "en": ", with music"} if music else {"tr": "", "en": ""})[ui]
    summary = {"tr": f"{len(beats)} bölümlük {how} montaj, ~{secs:.0f} sn; görüntü ücretsiz, ~{cost['credits']} kredi.",
               "en": f"A {len(beats)}-beat montage, {how}, ~{secs:.0f} s; footage free, ~{cost['credits']} credits."}[ui]
    lines = [b["say"] or b["text"] for b in beats]
    concept = {"id": "A", "title": data.get("title") or p["title"], "hook": lines[0], "lines": lines, "beats": beats,
               "structure": f"{len(beats)} beats · ~{secs:.0f} s", "look": how, "key_frame": beats[0]["look"],
               "post": {"caption": data.get("caption") or "", "hashtags": data.get("hashtags") or []}}
    art = {"concepts": [concept], "chosen": "A", "seconds": secs, "look": how, "voice": {"use": narrated},
           "music": {"use": music, "prompt": str(mu.get("prompt") or "")}, "cost": cost, "summary": summary}
    return {"artifact": art, "summary": summary, "cost": {"usd": usd}}


def _plan(pid, d):
    prop = P.read_artifact(pid, "proposal", d) or {}
    return prop, ((prop.get("concepts") or [{}])[0]).get("beats") or []


def _notes(note):
    """{beat: {"pick": k} | {"other": True} | {"search": "..."} | {"start": s}}"""
    out = {}
    for m in re.finditer(r"(\d+)\s*[:.)-]\s*([^\n;,]+)", note or ""):
        n, v = int(m.group(1)), m.group(2).strip()
        x = out.setdefault(n, {})
        if re.fullmatch(r"\d", v):
            x["pick"] = int(v)
        elif re.match(r"(başka|baska|other|another|farklı)\b", v, re.I):
            x["other"] = True
        elif mm := re.match(r"(ara|search)\s+(.+)", v, re.I):
            x["search"] = mm.group(2).strip()
        elif mm := re.match(r"(başla|basla|start|from)\s*(\d+(?:[.,]\d+)?)", v, re.I):
            x["start"] = float(mm.group(2).replace(",", "."))
        elif re.match(r"(sığdır|sigdir|fit)\b", v, re.I):
            x["fit"] = True
        elif re.match(r"(doldur|kırp|kirp|fill|crop)\b", v, re.I):
            x["fit"] = False
    return out


def _default_in(dur, need):
    return round(min(max(0.0, dur - need), dur * 0.15) if dur and dur > need * 3 else 0.0, 2)


def _take(pid, d, cands, want, used, start, prev, need, n, still_size):
    """The first usable candidate (the wanted one first): downloaded, its in-point and a still -> row fields or None."""
    from .. import archive
    order = list(range(len(cands)))
    if 0 <= want < len(cands):
        order = [want] + [i for i in order if i != want]
    for i in order:
        if cands[i]["key"] in used:
            continue
        try:
            c = archive.resolve(cands[i])
            if not c:
                continue
            src, info = archive.fetch(c)
        except Exception:
            continue
        if start is None and prev and prev.get("pick") == i + 1:
            start = prev.get("start")
        at = _default_in(info["duration"], need) if start is None else max(0.0, min(start, info["duration"] - 0.5))
        out = P.path(pid, "plates", f"beat_{n}.jpg", d=d)
        archive.still(src, at + min(need, info["duration"] - at) / 2, out, still_size)
        return {"pick": i + 1, "start": round(at, 2), "still": _rel(out),
                "clip": {**{k: c.get(k) for k in ("key", "source", "title", "author", "license", "page", "url")},
                         "file": _rel(src), **info}}
    return None


def scene_plan(pid, s, note=None, d=None):
    """The best clips by meaning per beat; the chosen one downloaded and a still at its in-point."""
    from .. import archive
    p = P.load(pid, d)
    prop, beats = _plan(pid, d)
    lens = _lengths(beats, (prop.get("voice") or {}).get("use"), p.get("video_lang", "tr"))
    old = {x["n"]: x for x in (P.read_artifact(pid, "plates", d) or {}).get("beats") or []}
    notes = _notes(note)
    con = _con()
    rows, files, used = [], [], set()
    w, h = _size(p)
    for b, need in zip(beats, lens):
        n, prev, nt = b["n"], old.get(b["n"]), notes.get(b["n"], {})
        cands = (prev or {}).get("candidates")
        queries = [nt["search"]] if nt.get("search") else (prev or {}).get("queries") or b["queries"]
        if cands is None or nt.get("other") or nt.get("search"):
            skip = {c["key"] for c in cands or []} if nt.get("other") else set()
            cands = archive.find(b["look"] + (f" {nt['search']}" if nt.get("search") else ""), queries, con, k=4,
                                 exclude=used | skip)
            prev = None
        want = nt.get("pick", (prev or {}).get("pick", 1)) - 1
        got = _take(pid, d, cands, want, used, nt.get("start"), prev, need, n, (w // 3, h // 3))
        if not got:                               # every candidate is taken or broken: one fresh search without them
            cands = archive.find(b["look"], queries, con, k=4, exclude=used | {c["key"] for c in cands})
            got = _take(pid, d, cands, 0, used, nt.get("start"), None, need, n, (w // 3, h // 3))
        row = {"n": n, "look": b["look"], "queries": queries, "need": need, "candidates": cands, "pick": None,
               "clip": None, "start": None, "still": None, **(got or {})}
        if got:
            used.add(got["clip"]["key"])
            files.append(got["still"])
        rows.append(row)
    missing = [r["n"] for r in rows if not r["clip"]]
    ui = _ui(p)
    summary = {"tr": "Her bölüm için anlamca en yakın arşiv görüntüsü. Değiştirmek için \"3: 2\" (2. aday), \"3: başka\", "
                     "\"3: ara liman gece\" ya da \"3: başla 12\" yaz.",
               "en": "For each beat the archive clip closest in meaning. To change one write \"3: 2\" (2nd candidate), "
                     "\"3: other\", \"3: search harbour at night\" or \"3: start 12\"."}[ui]
    if missing:
        summary += {"tr": f" {', '.join(map(str, missing))}. bölüm için görüntü bulunamadı: \"N: ara ...\" ile başka bir arama yaz.",
                    "en": f" No footage for beat {', '.join(map(str, missing))}: write another search with \"N: search ...\"."}[ui]
    art = {"concept": "", "plates": files, "beats": rows, "missing": missing, "summary": summary}
    return {"artifact": art, "summary": summary}


def _slots(times, total, n):
    """Narrated: each beat lasts from its line's start to the next line's start (the first from 0)."""
    starts = [0.0] + [times[i]["start"] for i in range(1, n)]
    return [round((starts[i + 1] if i + 1 < n else total) - starts[i], 3) for i in range(n)]


def cut(rows, lens, size, out, workdir, soft=True, fits=None):
    """The beats' clips fitted to their lengths and joined (a short cross-fade when `soft`). Video only."""
    from .. import archive
    os.makedirs(workdir, exist_ok=True)
    f = FADE if soft and len(rows) > 1 else 0.0
    inputs, fc = [], []
    for i, (r, ln) in enumerate(zip(rows, lens)):
        want = ln + (f if i + 1 < len(rows) else 0.0)
        src = os.path.join(ROOT, r["clip"]["file"])
        got = max(0.1, min(want, r["clip"]["duration"] - r["start"]))
        piece = archive.grab(src, r["start"], got, os.path.join(workdir, f"beat_{r['n']}.mp4"), size,
                             fit=(fits or {}).get(r["n"], False))
        speed = max(MIN_SPEED, min(1.0, got / want))
        inputs += ["-i", piece]
        fc.append(f"[{i}:v]setpts=(PTS-STARTPTS)/{speed:.4f},tpad=stop_mode=clone:stop_duration={want:.3f},"
                  f"trim=end={want:.3f},setpts=PTS-STARTPTS,fps=30,settb=1/30,format=yuv420p[p{i}]")
    if f:
        cur, length = "[p0]", lens[0] + f
        for i in range(1, len(rows)):
            nxt = f"[x{i}]" if i + 1 < len(rows) else "[v]"
            fc.append(f"{cur}[p{i}]xfade=transition=fade:duration={f}:offset={length - f:.3f}{nxt}")
            length += lens[i] + (f if i + 1 < len(rows) else 0.0) - f
            cur = nxt
    else:
        fc.append("".join(f"[p{i}]" for i in range(len(rows))) + f"concat=n={len(rows)}:v=1:a=0[v]")
    subprocess.run([FFMPEG, "-y", "-v", "error", *inputs, "-filter_complex", ";".join(fc), "-map", "[v]",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-an", out], check=True, timeout=1800)
    return out


def _beat_words(rows, lens, texts):
    """Unnarrated captions: each beat's on-screen line for the whole beat."""
    words, t = [], 0.0
    for text, ln in zip(texts, lens):
        if text:
            words.append([text, round(t + 0.2, 2), round(t + ln - 0.2, 2)])
        t += ln
    return words


def _mix(video, a, size, out, final=False):
    """Captions burned in; voice and/or music mixed and levelled to -14 LUFS."""
    ass = os.path.splitext(out)[0] + ".ass"
    per = a.get("per") or (4 if a.get("voice") else 1)
    open(ass, "w").write(captions(a["words"], size, per=per))
    ins, chains, labels = ["-i", video], [], []
    k = 1
    if a.get("voice"):
        ins += ["-i", os.path.join(ROOT, a["voice"]["file"])]
        chains.append(f"[{k}:a]aresample=48000,apad[vo]")
        labels.append("[vo]")
        k += 1
    if a.get("music"):
        vol = MUSIC_DB["under" if a.get("voice") else "alone"]
        dur = a["duration"]
        ins += ["-i", os.path.join(ROOT, a["music"]["file"])]
        chains.append(f"[{k}:a]aresample=48000,volume={vol},afade=t=in:d=0.5,afade=t=out:st={max(0, dur - 1.5):.2f}:d=1.5,apad[mu]")
        labels.append("[mu]")
    if labels:
        chains.append("".join(labels) + f"amix=inputs={len(labels)}:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11[a]")
        amap = ["-map", "[a]"]
    else:
        ins += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
        amap = ["-map", f"{k}:a"]
    cmd = [FFMPEG, "-y", "-v", "error", *ins]
    if chains:
        cmd += ["-filter_complex", ";".join(chains)]
    cmd += ["-map", "0:v", *amap, "-vf", f"subtitles='{ass.replace(chr(39), '')}'", "-t", str(a["duration"]),
            "-c:v", "libx264", "-preset", "medium" if final else "veryfast", "-crf", "18" if final else "24",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", out]
    subprocess.run(cmd, check=True, timeout=1800)
    return out


def _render(pid, d, a, final=False, ed=None):
    p = P.load(pid, d)
    rows = (P.read_artifact(pid, "plates", d) or {}).get("beats") or []
    ed = ed if ed is not None else P.read_artifact(pid, "edit", d) or {}
    starts = {int(k): v for k, v in (ed.get("starts") or {}).items()}
    rows = [{**r, "start": starts.get(r["n"], r["start"])} for r in rows]
    size = _size(p)
    vid = cut(rows, a["lengths"], size, P.path(pid, "assets", "cut.mp4", d=d), P.path(pid, "assets", "pieces", d=d),
              soft=ed.get("transition", "soft") == "soft", fits={int(k): v for k, v in (ed.get("fits") or {}).items()})
    return _mix(vid, a, size, P.path(pid, "renders", "final.mp4" if final else "preview.mp4", d=d), final)


def assets(pid, s, note=None, d=None):
    """The voice and its word timing, the music, then the cut with captions."""
    from .. import accounts, eleven, formats, productions
    p = P.load(pid, d)
    prop, beats = _plan(pid, d)
    rows = (P.read_artifact(pid, "plates", d) or {}).get("beats") or []
    if not rows or any(not r.get("clip") for r in rows):
        raise P.GateError("some beats have no footage yet; fix them at the scene plan")
    narrated, music = (prop.get("voice") or {}).get("use"), (prop.get("music") or {}).get("use")
    lang = p.get("video_lang", "tr")
    con = _con()
    acc = p.get("eleven_account") or accounts.default_eleven(p.get("created_by"))
    voice, mus, vcost, mcost = None, None, 0.0, 0.0
    if narrated:
        lines = [b["say"] for b in beats]
        voice_id = p.get("voice_id") or formats.default_voice(lang, acc)
        vpath, vcost = eleven.tts(con, " ".join(lines), voice_id, formats.VOICE_MODEL, approved=remaining_budget(pid, d),
                                  account=acc)
        times, dur, words = productions.align(vpath, lines, lang)
        total = round(dur + 0.8, 2)
        lens = _slots(times, total, len(beats))
        voice = {"file": _rel(vpath), "voice_id": voice_id, "duration": dur, "credits": round(vcost), "line_times": times}
        words = [list(x)[:3] for x in words]
    else:
        lens = _lengths(beats, False, lang)
        total = round(sum(lens), 2)
        words = _beat_words(rows, lens, [b["text"] for b in beats])
    if music:
        prompt = (prop.get("music") or {}).get("prompt") or "calm documentary score, strings and piano"
        if "instrumental" not in prompt.lower():
            prompt = "Instrumental, no vocals. " + prompt
        if note:
            prompt += f" {note}"
        mpath, mcost = eleven.generate(con, "music", productions.MUSIC_MODEL, prompt,
                                       {"duration_seconds": round(total + 1, 1), "instrumental": True}, round(total + 1, 1),
                                       "s", ext="mp3", approved=max(0, remaining_budget(pid, d) - round(vcost)), account=acc)
        mus = {"file": _rel(mpath), "prompt": prompt, "credits": round(mcost)}
    art = {"voice": voice, "music": mus, "duration": total, "lengths": lens, "words": words}
    prev = _render(pid, d, art)
    cost = round(vcost + mcost)
    ui = _ui(p)
    summary = {"tr": f"Montaj hazır ({total:.0f} sn, {cost} kredi). Görüntü ile anlatım uyuyor mu? Kesimleri bir sonraki adımda ayarlarsın.",
               "en": f"The montage is ready ({total:.0f} s, {cost} credits). Do the pictures match the words? You tune the cuts next."}[ui]
    art.update(preview=_rel(prev), summary=summary)
    return {"artifact": art, "summary": summary, "cost": {"credits": cost}}


def edit(pid, s, note=None, d=None):
    """The cut: each beat's in-point in its clip and the transition. A note changes them and re-renders the preview."""
    p = P.load(pid, d)
    a = P.read_artifact(pid, "assets", d) or {}
    rows = (P.read_artifact(pid, "plates", d) or {}).get("beats") or []
    cur = P.read_artifact(pid, "edit", d) or {}
    starts = {int(k): v for k, v in (cur.get("starts") or {}).items()} or {r["n"]: r["start"] for r in rows}
    fits = {int(k): v for k, v in (cur.get("fits") or {}).items()}
    trans = cur.get("transition") or "soft"
    for n, x in _notes(note).items():
        r = next((r for r in rows if r["n"] == n), None)
        if r and "start" in x:
            starts[n] = round(max(0.0, min(x["start"], r["clip"]["duration"] - 0.5)), 2)
        if r and "fit" in x:
            fits[n] = x["fit"]
    m = re.search(r"(geçiş|gecis|transition)\s*[:=]?\s*(\w+)", note or "", re.I)
    if m:
        trans = "cut" if m.group(2).lower() in ("kesme", "sert", "cut", "hard") else "soft"
    timeline, t = [], 0.0
    for r, ln in zip(rows, a.get("lengths") or []):
        timeline.append({"n": r["n"], "at": round(t, 2), "seconds": ln, "clip": r["clip"]["title"],
                         "source": r["clip"]["source"], "start": starts.get(r["n"], r["start"]),
                         "frame": "fit" if fits.get(r["n"]) else "fill"})
        t += ln
    art = {"starts": {str(k): v for k, v in starts.items()}, "fits": {str(k): v for k, v in fits.items()},
           "transition": trans, "timeline": timeline}
    ui = _ui(p)
    summary = {"tr": f"Kurgu: {len(timeline)} kesim, geçiş {'yumuşak' if trans == 'soft' else 'sert'}. Bir kesimin "
                     f"başlangıcı için \"3: başla 12\", tüm kareyi göstermek için \"3: sığdır\", geçiş için \"geçiş: kesme\" ya da \"geçiş: yumuşak\" yaz.",
               "en": f"The cut: {len(timeline)} shots, {trans} transitions. For a shot's in-point write \"3: start 12\", to show its whole frame \"3: fit\"; "
                     f"for the transition \"transition: cut\" or \"transition: soft\"."}[ui]
    art["summary"] = summary
    if note:                                      # show the change in a new preview
        art["preview"] = _rel(_render(pid, d, a, ed=art))
    return {"artifact": art, "summary": summary}


def compose(pid, s, note=None, d=None):
    from .. import qa, thumbs
    p = P.load(pid, d)
    a = P.read_artifact(pid, "assets", d) or {}
    if not a.get("lengths"):
        raise P.GateError("no montage yet")
    out = _render(pid, d, a, final=True)
    tech = qa.technical(out, a["duration"])
    title = ((P.read_artifact(pid, "proposal", d) or {}).get("concepts") or [{}])[0].get("title") or p["title"]
    covers = thumbs.make(out, P.path(pid, "renders", d=d), title, p.get("aspect", "9:16"), lang=p.get("video_lang", "tr"))
    probs = tech.get("problems", [])
    summary = ({"tr": "Final hazır; teknik kontrol temiz.", "en": "Final ready; technical checks clean."} if not probs else
               {"tr": f"Final hazır; {len(probs)} teknik bulgu var.", "en": f"Final ready; {len(probs)} technical findings."})[_ui(p)]
    art = {"final": _rel(out), "qa": {"technical": tech, "pass": not probs}, "covers": [_rel(c) for c in covers],
           "summary": summary}
    return {"artifact": art, "summary": summary}


def publish(pid, s, note=None, d=None):
    from .. import archive
    p = P.load(pid, d)
    c = ((P.read_artifact(pid, "proposal", d) or {}).get("concepts") or [{}])[0]
    post = c.get("post") or {}
    tags = post.get("hashtags") or []
    tags = tags.split() if isinstance(tags, str) else [t if t.startswith("#") else "#" + t for t in tags]
    rows = (P.read_artifact(pid, "plates", d) or {}).get("beats") or []
    clips = list({r["clip"]["key"]: r["clip"] for r in rows if r.get("clip")}.values())
    ui = _ui(p)
    short = {"tr": "Görüntüler: ", "en": "Footage: "}[ui] + "; ".join(
        f"{x.get('author') or x['source']} ({x['source']}, {x['license']})" for x in clips)
    caption = (post.get("caption") or c.get("title") or p["title"]).strip()
    notes = {"tr": "CC BY / CC BY-SA görüntüler kaynak ister: açıklamadaki satırı silme. Tam liste aşağıda.",
             "en": "CC BY / CC BY-SA footage needs credit: keep the line in the caption. The full list is below."}[ui]
    summary = {"tr": "Açıklama, etiketler ve görüntü kaynakları hazır.", "en": "Caption, hashtags and footage credits ready."}[ui]
    art = {"caption": f"{caption}\n\n{short}"[:2200], "hashtags": tags or ["#belgesel"], "notes": notes,
           "credits": "\n".join(archive.credit(x) for x in clips), "summary": summary}
    return {"artifact": art, "summary": summary}
