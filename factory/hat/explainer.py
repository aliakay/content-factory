"""The code side of the HTML motion lines (explainer, animation): timing and bundles for bin/htmlmotion.py.

Before the voice exists, timing is drafted from the script (words per second of the video language); once the
assets stage has the real voice, its word timings replace the draft. A script with `narrate: false` (motion
graphics led by music) has no voice: each line is an on-screen beat held for `holds[i]` seconds, and the captions
are off because the text is the motion itself. The scene plan (the stage agent's artifact)
plus that timing becomes the bundle the renderer and the design tools (stills, layout lint, readcheck) load.
"""
import json, os, sys

from ..config import ROOT
from . import project as P

WPS = {"tr": 2.4, "en": 2.6}       # spoken words per second, for draft timing
PAUSE = 0.3                         # gap between lines in the draft
VOICE_START = 0.15
TAIL = 0.8
HOLD = 2.5                          # seconds an on-screen beat stays when the script gives no hold
CAPTIONS = {"mode": "chunk", "pos": "low", "energy": "talk"}


def _htmlmotion():
    sys.path.insert(0, os.path.join(ROOT, "bin"))
    import htmlmotion
    return htmlmotion


def _word_weight(w):
    """How much of a line's time a word takes: its letters (at least two) plus the pause its punctuation asks for.

    A long word is not just longer on screen, it is spoken longer; a full stop carries a breath a comma does not. The
    line's total time stays the speaking rate's — the weights only decide where inside the line each word lands, which
    is what a cue (and the caption block) reads (`motionforge tools/word_timings.py` does the same for its fallback)."""
    letters = max(2, sum(1 for c in w if c.isalnum()))
    tail = w[-1] if w else ""
    return letters + 1.5 + (1.2 if tail in ".!?…" else 0.6 if tail in ",;:" else 0.0)


def draft_timing(lines, lang="tr"):
    """Words [(w, s, e)] and line times for `lines` at the language's speaking rate, weighted per word."""
    wps = WPS.get(lang, 2.5)
    t, words, line_times = 0.0, [], []
    for line in lines:
        ws = line.split()
        start, span = t, len(ws) / wps                 # the line lasts words / rate ...
        weight = sum(_word_weight(w) for w in ws) or 1
        for w in ws:                                    # ... shared by weight, not equally
            dur = span * _word_weight(w) / weight
            words.append((w, round(t, 3), round(t + dur, 3)))
            t += dur
        line_times.append({"start": round(start, 3), "end": round(t, 3)})
        t += PAUSE
    return words, line_times, round(max(t - PAUSE, 0.0), 3)


def narrated(script):
    return (script or {}).get("narrate", True) is not False


def beat_timing(lines, holds=None):
    """Words and line times for unnarrated beats: line i is held holds[i] seconds (words spread across it, so scene
    triggers still find their word)."""
    t, words, line_times = 0.0, [], []
    for i, line in enumerate(lines):
        hold = float((holds or [])[i]) if holds and i < len(holds) and holds[i] else HOLD
        ws = line.split() or ["·"]
        for j, w in enumerate(ws):
            words.append((w, round(t + hold * j / len(ws), 3), round(t + hold * (j + 1) / len(ws), 3)))
        line_times.append({"start": round(t, 3), "end": round(t + hold, 3)})
        t += hold
    return words, line_times, round(t, 3)


def _music_bpm(pid, d=None):
    """The tempo a music-led film is cut to: the generated track's measured bpm, else the proposal's declared one."""
    if narrated(P.read_artifact(pid, "script", d) or {}):
        return None, 0.0
    assets = P.read_artifact(pid, "assets", d) or {}
    mu = assets.get("music") or {}
    if mu.get("bpm"):
        return float(mu["bpm"]), float(mu.get("offset") or 0.0)
    prop = P.read_artifact(pid, "proposal", d) or {}
    pm = prop.get("music") or {}
    try:
        bpm = float(pm.get("bpm") or 0)
    except (TypeError, ValueError):
        bpm = 0.0
    return (bpm, float(pm.get("offset") or 0.0)) if bpm > 0 else (None, 0.0)


def timing(pid, d=None):
    """The real voice timing when the assets stage made it, else the draft from the script.

    A music-led film's holds are snapped to the track's beat grid (factory/beats.snap_holds) as soon as a tempo is
    known, so every scene starts on a beat; the total length moves by at most half a beat."""
    p = P.load(pid, d)
    assets = P.read_artifact(pid, "assets", d) or {}
    voice = assets.get("voice") or {}
    if voice.get("words") and voice.get("line_times"):
        return [tuple(w) for w in voice["words"]], voice["line_times"], voice["duration"], "voice"
    script = P.read_artifact(pid, "script", d) or {}
    if not narrated(script):
        holds = script.get("holds")
        bpm, offset = _music_bpm(pid, d)
        if bpm and holds:
            from .. import beats
            holds = beats.snap_holds(holds, bpm, offset)
        words, lt, dur = beat_timing(script.get("lines") or [], holds)
        return words, lt, dur, "beats"
    words, lt, dur = draft_timing(script.get("lines") or [], p.get("video_lang", "tr"))
    return words, lt, dur, "draft"


def spec(pid, plan=None, d=None):
    """The htmlmotion spec (timing + scene ranges) for this project's scene plan."""
    p = P.load(pid, d)
    plan = plan or P.read_artifact(pid, "scene_plan", d) or {}
    words, line_times, dur, source = timing(pid, d)
    silent = source == "beats" or not narrated(P.read_artifact(pid, "script", d))
    voice_start = 0.0 if silent else VOICE_START
    total = round(dur + voice_start + TAIL, 3)
    scenes, n = [], len(line_times)
    for i, sc in enumerate(plan.get("scenes") or []):
        a, b = (sc.get("lines") or [0, 0])[:2]
        a, b = max(0, min(a, n - 1)), max(0, min(b, n - 1))
        start = 0.0 if i == 0 else round(line_times[a]["start"] + voice_start, 3)
        scenes.append({"id": sc["id"], "lines": [a, b], "start": start, "hide_captions": silent or bool(sc.get("hide_captions"))})
    for i, sc in enumerate(scenes):
        sc["end"] = scenes[i + 1]["start"] if i + 1 < len(scenes) else total
    chapters = [{"title": c["title"], "start": 0.0 if not c["line"] else round(line_times[c["line"]]["start"] + voice_start, 3)}
                for c in plan.get("chapters") or [] if 0 <= c.get("line", -1) < n]     # long form (factory/hat/longform.py)
    from .. import captions as _cap
    return {"name": pid, "words": words, "line_times": line_times, "voice_start": voice_start, "duration": total,
            "caption_blocks": _cap.blocks(words, p.get("aspect", "9:16")),
            "scenes": scenes, "aspect": p.get("aspect", "9:16"), "lang": p.get("video_lang", "tr"),
            "captions": plan.get("captions") or CAPTIONS, "timing": source, "chapters": chapters,
            "chrome": plan.get("chrome") or {}}


def design(plan):
    """Scene plan -> the design dict htmlmotion.make_bundle expects."""
    return {"meta": {"palette": plan.get("palette") or {}, "concept": plan.get("concept", "")},
            "global_css": plan.get("global_css", ""),
            "scenes": {sc["id"]: {k: sc.get(k, "") for k in ("html", "css", "js")} for sc in plan.get("scenes") or []}}


def bundle(pid, plan=None, d=None):
    """Write projects/<pid>/work/bundle.json for the current scene plan and timing; returns its path."""
    plan = plan or P.read_artifact(pid, "scene_plan", d)
    if not plan:
        raise P.GateError("no scene plan yet")
    sp = spec(pid, plan, d)
    out = P.path(pid, "work", d=d)
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, "bundle.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_htmlmotion().make_bundle(sp, design(plan)), f, ensure_ascii=False)
    return path


def scene_times(pid, plan=None, d=None):
    """One settled moment per scene (70 % in), for stills and review sheets."""
    return [round(s["start"] + (s["end"] - s["start"]) * 0.7, 2) for s in spec(pid, plan, d)["scenes"]]


# ---------------------------------------------------------------- texts the stage briefs include
# Stage briefs (skills/pipelines/explainer/*.md) pull these with {{include:factory.hat.explainer:<name>}} so the craft
# rules have one source: the motion designer's and writer's existing rules, minus their old output formats.

def design_rules(p):
    from .. import motiondesign as M
    out = M.rules(p.get("aspect", "9:16"), CAPTIONS).replace(M.FORMAT, "").rstrip()
    return out.replace('(use them as <img src="{{img:ID}}">)',
                       '(find each with the stock_search tool and use it as <img src="/<file>"> with the returned file)')


def design_kit(p):
    from .. import motiondesign as M
    return "\n\n".join([M.fx_doc(), M.TASTE, M.MOTION_DOCTRINE, M.SOUND_RULES])


def grammars(p):
    from .. import motiondesign as M
    return "\n".join(f"- {k}: {v}" for k, v in M.GRAMMARS.items())


def lang_rule(p):
    from .. import explainer as X
    return X.LANG_RULE.get(p.get("video_lang"), X.LANG_RULE["en"])


def words_per_second(p):
    return f"{WPS.get(p.get('video_lang'), 2.5)} words per second"


# ---------------------------------------------------------------- code stages: assets -> edit -> compose
# Each is `fn(pid, stage, note=None, d=None) -> {artifact, summary, cost}` (factory/hat/runner.py calls it).

def _con():
    from ..store import connect
    return connect()


def _rel(path):
    return os.path.relpath(path, ROOT)


def spent_credits(pid, d=None):
    """Credits every stage of the project has spent so far (a line may spend before its assets stage)."""
    from . import minimax
    return sum((cp.get("cost") or {}).get("credits", 0) for _, cp in P.stages(pid, d)) + minimax.spent(pid, d)


def remaining_budget(pid, d=None):
    """Credits still allowed by the approved proposal. Raises when nothing was approved (no budget, no spending)."""
    b = (P.load(pid, d).get("budget") or {})
    if not b or b.get("credits") is None:
        raise P.GateError("no approved budget: approve the proposal first")
    return max(0, int(b["credits"]) - int(spent_credits(pid, d)))


def _render_spec(pid, plan, d=None, final=False):
    """The bundle spec plus what render_bundle needs for the sound."""
    sp = spec(pid, plan, d)
    assets = P.read_artifact(pid, "assets", d) or {}
    edit = P.read_artifact(pid, "edit", d) or {}
    v, mu = assets.get("voice") or {}, assets.get("music")
    sp.update(name=pid, voice={"file": v["file"]} if v.get("file") else None,
              music={"file": mu["file"], "db": mu.get("db", -22), "seek": mu.get("seek", 0),
                     "auto": bool(v.get("file"))} if mu and mu.get("file")
              else None,
              sound=edit.get("sound") or {"level": "full"}, voice_chain=edit.get("voice_chain") or "clean",
              post_fx=edit.get("post_fx") if final else None, motion_blur=edit.get("motion_blur") if final else None)
    return sp


def _render(pid, final, d=None):
    plan = P.read_artifact(pid, "scene_plan", d)
    sp = _render_spec(pid, plan, d, final)
    out = P.path(pid, "work", "final" if final else "preview", d=d)
    os.makedirs(out, exist_ok=True)
    b = os.path.join(out, "bundle.json")
    with open(b, "w", encoding="utf-8") as f:
        json.dump(_htmlmotion().make_bundle(sp, design(plan)), f, ensure_ascii=False)
    dst = P.path(pid, "renders", "final.mp4" if final else "preview.mp4", d=d)
    return _htmlmotion().render_bundle(b, sp, out, dst, preview=not final), sp


def pretrim_voice(pid, path, lines, lang, p, d=None):
    """Cut the fillers and restarts the script does not have from a fresh take (t512), before the alignment, so captions
    and scenes follow the trimmed file. Off with project.pretrim = false; a failure keeps the take as it is."""
    if p.get("pretrim") is False:
        return path, None
    from .. import pretrim
    try:
        out, info = pretrim.trim(path, lines, lang)
    except Exception as e:                       # never lose a paid take to the trimmer
        P.decision(pid, "pretrim", "skipped", reason=f"pre-trim failed: {e}"[:300], d=d)
        return path, None
    if info["cuts"]:
        P.decision(pid, "pretrim", f"{len(info['cuts'])} cuts", reason=", ".join(c[2] for c in info["cuts"])[:300], d=d)
    return out, info if info["cuts"] else None


def assets(pid, s, note=None, d=None):
    """Narration (inside the approved budget), word alignment, optional music, then a preview of the whole video.
    An unnarrated script skips the voice and must have music."""
    from .. import accounts, eleven, formats, productions
    con, p = _con(), P.load(pid, d)
    script = P.read_artifact(pid, "script", d) or {}
    prop = P.read_artifact(pid, "proposal", d) or {}
    lines = script.get("lines") or []
    if not lines:
        raise P.GateError("the script has no lines")
    lang = p.get("video_lang", "tr")
    account = p.get("eleven_account") or accounts.default_eleven(p.get("created_by"))
    if not narrated(script):
        return _music_only(pid, p, prop, con, account, d)
    voice_id = (prop.get("voice") or {}).get("voice_id") or p.get("voice_id") or formats.default_voice(lang, account)
    path, cost = narrate(pid, con, lines, voice_id, account, [c.get("line") for c in script.get("chapters") or []], d)
    path, trimmed = pretrim_voice(pid, path, lines, lang, p, d)
    times, dur, words = productions.align(path, lines, lang)
    P.decision(pid, "voice", voice_id, reason="proposal voice or channel default", d=d, model=formats.VOICE_MODEL)
    voice = {"file": _rel(path), "voice_id": voice_id, "model": formats.VOICE_MODEL, "credits": round(cost),
             "duration": dur, "line_times": times, "words": [list(w) for w in words]}
    if trimmed:
        voice["pretrim"] = trimmed
    music, mcost = None, 0.0
    mu = prop.get("music") or {}
    if mu.get("use"):
        secs = round(dur + VOICE_START + TAIL + 1.5, 1)
        prompt = mu.get("prompt") or "Instrumental, no vocals. Subtle, steady pulse under a spoken explainer."
        if "instrumental" not in prompt.lower():
            prompt = "Instrumental, no vocals. " + prompt
        if composed(mu):
            music = compose_music(pid, prompt, secs, times, True, d)
        else:
            gen = min(secs, MUSIC_MAX)
            mpath, mcost = eleven.generate(con, "music", productions.MUSIC_MODEL, prompt, {"duration_seconds": gen,
                                           "instrumental": True}, gen, "s", ext="mp3",
                                           approved=max(0, remaining_budget(pid, d) - round(cost)), account=account)
            if secs > gen:
                mpath = loop_music(mpath, secs, P.path(pid, "work", "music-long.m4a", d=d))
            music = end_on_card(pid, {"file": _rel(mpath), "prompt": prompt, "credits": round(mcost), "db": -22},
                                times, d)
        music = _tempo(music)
    art = {"voice": voice, "music": music}
    P.write_artifact(pid, "assets", art, d)          # the preview reads the real timing from here
    res, sp = _render(pid, final=False, d=d)
    total = round(cost + mcost)
    art.update(preview=_rel(res["file"]), duration=sp["duration"],
               summary={"tr": f"Ses hazır ({dur:.1f} sn, {total} kredi){', müzikle' if music else ''}. Önizlemeyi izle.",
                        "en": f"Voice ready ({dur:.1f} s, {total} credits){', with music' if music else ''}. Watch the preview."
                        }[p.get("ui_lang", "tr") if p.get("ui_lang") in ("tr", "en") else "tr"])
    return {"artifact": art, "summary": art["summary"], "cost": {"credits": total}}


TTS_MAX = 2400        # characters per narration request: a long script is voiced in pieces (and re-voiced piece by piece)
PIECE_GAP = 0.45      # silence between two pieces
MUSIC_MAX = 240       # seconds of music generated at most; a longer video loops it with a crossfade
LOOP_FADE = 4.0


def pieces(lines, starts=()):
    """Line ranges [a, b] voiced in one request each: a new piece at every chapter start and before TTS_MAX characters."""
    out, a, size = [], 0, 0
    cut = {int(x) for x in starts or () if x}
    for i, ln in enumerate(lines):
        if i > a and (i in cut or size + len(ln) + 1 > TTS_MAX):
            out.append([a, i - 1])
            a, size = i, 0
        size += len(ln) + 1
    if lines:
        out.append([a, len(lines) - 1])
    return out


def narrate(pid, con, lines, voice_id, account, starts=(), d=None):
    """The narration of `lines` inside the approved budget -> (audio path, credits). One request for a short script
    (same cache key as always); a long one piece by piece, joined with PIECE_GAP of silence."""
    from .. import eleven, formats
    ps = pieces(lines, starts)
    if len(ps) == 1:
        return eleven.tts(con, " ".join(lines), voice_id, formats.VOICE_MODEL, approved=remaining_budget(pid, d), account=account)
    files, cost = [], 0.0
    for a, b in ps:
        path, c = eleven.tts(con, " ".join(lines[a:b + 1]), voice_id, formats.VOICE_MODEL,
                             approved=max(0, remaining_budget(pid, d) - round(cost)), account=account)
        files.append(path)
        cost += c
    out = P.path(pid, "work", "voice.m4a", d=d)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    join_audio(files, out, PIECE_GAP)
    return out, cost


def join_audio(files, out, gap):
    import subprocess
    from ..config import FFMPEG
    ins = sum((["-i", f] for f in files), [])
    pads = "".join(f"[{i}:a]aresample=48000,aformat=channel_layouts=mono,apad=pad_dur={gap if i + 1 < len(files) else 0}[p{i}];"
                   for i in range(len(files)))
    fc = pads + "".join(f"[p{i}]" for i in range(len(files))) + f"concat=n={len(files)}:v=0:a=1[a]"
    subprocess.run([FFMPEG, "-y", "-v", "error", *ins, "-filter_complex", fc, "-map", "[a]", "-c:a", "aac", "-b:a", "192k",
                    out], check=True)
    return out


def loop_music(path, secs, out):
    """Repeat a music track with a LOOP_FADE crossfade at each seam until it lasts `secs`."""
    import subprocess
    from ..config import FFMPEG
    from .. import fftools
    one = fftools.measure(path)["duration"]
    n = max(2, int((secs - LOOP_FADE) // max(1.0, one - LOOP_FADE)) + 1)
    ins = sum((["-i", path] for _ in range(n)), [])
    chain, prev = "", "[0:a]"
    for i in range(1, n):
        chain += f"{prev}[{i}:a]acrossfade=d={LOOP_FADE}:c1=tri:c2=tri[x{i}];"
        prev = f"[x{i}]"
    subprocess.run([FFMPEG, "-y", "-v", "error", *ins, "-filter_complex", chain.rstrip(";"), "-map", prev, "-t", f"{secs:.2f}",
                    "-c:a", "aac", "-b:a", "192k", out], check=True)
    return out


def composed(mu):
    """The proposal chose our own composer (no credits) instead of ElevenLabs music."""
    return (mu or {}).get("source") == "composer"


def cut_facts(path, sp, pid=None, d=None):
    """The sound around every cut of a rendered film (qa.audio_facts): a 3 s window per cut, not the whole file."""
    from .. import qa
    out = os.path.join(ROOT, "work", "cut-facts.json")
    try:
        if not path or not os.path.exists(path):
            return []
        facts = [qa.audio_facts(path, round(s["start"], 2)) for s in (sp.get("scenes") or [])[1:]]
        os.makedirs(os.path.dirname(out), exist_ok=True)
        json.dump(facts, open(out, "w"), ensure_ascii=False)
        return facts
    except Exception as e:
        P.event(pid, "cut_facts_skipped", d=d, error=f"{type(e).__name__}: {e}"[:160])
        return []


def compose_music(pid, prompt, secs, line_times, narrated, d=None):
    """An original score on the scene cues (t513), played locally: the music artifact entry, 0 credits."""
    from .. import compose
    plan = P.read_artifact(pid, "scene_plan", d) or {}
    cues = []
    for i, sc in enumerate(plan.get("scenes") or []):
        a = (sc.get("lines") or [0])[0]
        if i and 0 <= a < len(line_times):
            lt = line_times[a]
            cues.append({"label": f"scene {sc.get('id', i)}", "t": round((lt["start"] if isinstance(lt, dict) else lt[0])
                                                                         + VOICE_START, 2)})
    out = P.path(pid, "work", "music-composed.m4a", d=d)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    end_at = cues[-1]["t"] if cues else None           # the last scene is the end card: the piece ends on it (t518)
    res = compose.compose(prompt, secs, cues, out, narrated=narrated, end_at=end_at)
    P.decision(pid, "music", "composer" if res["agent"] else "composer (plain score)", d=d, bpm=res["bpm"],
               reason=res.get("why") or f"{len(cues)} cues")
    return {"file": _rel(out), "prompt": prompt, "credits": 0, "db": -22, "source": "composer", "bpm": res["bpm"],
            "agent": res["agent"], "score": _rel(os.path.splitext(out)[0] + ".score.json"),
            "ending": {"end_card": end_at, "hit": end_at, "seek": 0.0, "fits": end_at is not None}}


def end_card_at(pid, line_times, d=None):
    """When the end card (the last scene) starts in the video, or None with one scene."""
    plan = P.read_artifact(pid, "scene_plan", d) or {}
    scenes = plan.get("scenes") or []
    if len(scenes) < 2:
        return None
    a = (scenes[-1].get("lines") or [0])[0]
    if not 0 <= a < len(line_times):
        return None
    lt = line_times[a]
    return round((lt["start"] if isinstance(lt, dict) else lt[0]) + VOICE_START, 2)


ENDING_MIN = 0.8      # seconds of the track that must be left after its final hit for the ending to count


def end_on_card(pid, music, line_times, d=None):
    """Place a bought track so its own ending (audiofx.final_hit) lands on the end card (t518): seek into it by the
    difference. A track whose ending comes before the end card is left as it is (logged). Mutates and returns music."""
    from .. import audiofx
    t = end_card_at(pid, line_times, d)
    f = os.path.join(ROOT, music["file"])
    hit = audiofx.final_hit(f) if t is not None and os.path.exists(f) else None
    fits = hit is not None and hit >= t
    music["ending"] = {"end_card": t, "hit": hit, "seek": round(hit - t, 2) if fits else 0.0, "fits": fits}
    if fits:
        music["seek"] = music["ending"]["seek"]
    P.decision(pid, "music_ending", "aligned" if fits else "not aligned", d=d, **music["ending"],
               reason="the track's final hit lands on the end card" if fits
               else "the track ends before the end card (or no clear ending)")
    return music


def _tempo(music):
    """Measure a generated track and record its tempo and first-beat offset, so the cut can snap to its grid."""
    from .. import beats
    if not music or not music.get("file"):
        return music
    info = beats.bpm_of(os.path.join(ROOT, music["file"]))
    if not info or not info.get("bpm"):
        return music
    step = 60.0 / info["bpm"]
    first = (info.get("beats") or [0.0])[0]
    music.update(bpm=round(info["bpm"], 1), offset=round(first % step, 3), measured=info.get("duration"))
    return music


def _music_only(pid, p, prop, con, account, d=None):
    from .. import eleven, productions
    _, _, dur, _ = timing(pid, d)
    secs = round(dur + VOICE_START + TAIL + 1.5, 1)
    mu = prop.get("music") or {}
    prompt = mu.get("prompt") or "Instrumental, no vocals. A confident pulse with clear accents for motion graphics."
    if "instrumental" not in prompt.lower():
        prompt = "Instrumental, no vocals. " + prompt
    if composed(mu):
        mcost = 0.0
        music = {**compose_music(pid, prompt, secs, timing(pid, d)[1], False, d), "db": -10}
    else:
        mpath, mcost = eleven.generate(con, "music", productions.MUSIC_MODEL, prompt, {"duration_seconds": secs,
                                       "instrumental": True}, secs, "s", ext="mp3",
                                       approved=remaining_budget(pid, d), account=account)
        music = end_on_card(pid, {"file": _rel(mpath), "prompt": prompt, "credits": round(mcost), "db": -10},
                            timing(pid, d)[1], d)
    music = _tempo(music)
    art = {"voice": None, "music": music}
    P.write_artifact(pid, "assets", art, d)
    res, sp = _render(pid, final=False, d=d)
    ui = p.get("ui_lang") if p.get("ui_lang") in ("tr", "en") else "tr"
    art.update(preview=_rel(res["file"]), duration=sp["duration"],
               summary={"tr": f"Müzik hazır ({secs:.0f} sn, {round(mcost)} kredi). Önizlemeyi izle.",
                        "en": f"Music ready ({secs:.0f} s, {round(mcost)} credits). Watch the preview."}[ui])
    return {"artifact": art, "summary": art["summary"], "cost": {"credits": round(mcost)}}


def edit(pid, s, note=None, d=None):
    """Final edit decisions (deterministic for the explainer): sound level, voice chain, film post from the look."""
    prop = P.read_artifact(pid, "proposal", d) or {}
    from .. import capabilities
    look = (capabilities.get(prop.get("look") or "") or {}).get("data") or {}   # a film style carries its post and blur
    post, blur = look.get("post_fx") or None, look.get("motion_blur")
    art = {"sound": {"level": "full"}, "voice_chain": "clean", "post_fx": post, "motion_blur": blur,
           "summary": "", "note": note}
    from .. import beats
    bpm, offset = _music_bpm(pid, d)
    if bpm:
        starts = [sc["start"] for sc in spec(pid, None, d)["scenes"]][1:]
        fit = beats.grid_fit(starts, beats.grid(bpm, max(starts or [0]) + 1, offset))
        art["beat_fit"] = fit | {"bpm": bpm}
        art["findings"] = beats.problems(starts, beats.grid(bpm, max(starts or [0]) + 1, offset))
    P.decision(pid, "edit", "sound full, voice chain clean" + (", film beat grid" if bpm else "")
               + (", film post" if post else ""), d=d)
    return {"artifact": art, "summary": ""}


def compose(pid, s, note=None, d=None):
    """Final render + technical and sound QA + cover candidates."""
    from .. import qa, soundqa, thumbs
    p = P.load(pid, d)
    res, sp = _render(pid, final=True, d=d)
    tech = qa.technical(res["file"], sp["duration"])
    try:
        starts = [sc["start"] for sc in sp.get("scenes") or []][1:]
        snd = soundqa.review(res["file"], cues=res.get("placed") or None, total=sp["duration"], cuts=starts)
        sound = {"findings": snd.get("findings", []), "metrics": snd.get("metrics", {})}
        if len(starts) >= 2:
            from .. import craftcheck
            sl = craftcheck.scene_loudness(res["file"], starts)
            sound["findings"] += sl["findings"]
            sound["metrics"]["scenes"] = sl["scenes"]
        cuts = cut_facts(res["file"], sp, pid, d)
        if cuts:                                   # each cut: is there a hole, is anyone speaking
            sound["cuts"] = cuts
            silent = [c for c in cuts if c["silent_s"] > 1.0]
            if silent:
                sound["findings"].append({"kind": "cut_hole",
                                          "detail": f"{len(silent)} kesimde >1 s sessizlik: "
                                                    f"{[c['at'] for c in silent][:4]}"})
    except Exception as e:
        sound = {"error": f"{type(e).__name__}: {e}"[:300]}
    script = P.read_artifact(pid, "script", d) or {}
    plan = P.read_artifact(pid, "scene_plan", d) or {}
    covers = thumbs.make(res["file"], P.path(pid, "renders", d=d), script.get("title") or p["title"], p.get("aspect", "9:16"),
                         (plan.get("palette") or {}).get("accent", "#FFD93D"), lang=p.get("video_lang", "tr"))
    problems = tech.get("problems", [])
    ui = p.get("ui_lang", "tr")
    summary = ({"tr": "Final hazır; teknik kontrol temiz.", "en": "Final ready; technical checks clean."} if not problems else
               {"tr": f"Final hazır; {len(problems)} teknik bulgu var.", "en": f"Final ready; {len(problems)} technical findings."}
               )[ui if ui in ("tr", "en") else "tr"]
    art = {"final": _rel(res["file"]), "duration": sp["duration"], "qa": {"technical": tech, "sound": sound},
           "covers": [_rel(c) for c in covers], "render": {k: res[k] for k in ("cues", "music_cuts", "capture_s", "parts") if k in res},
           "summary": summary}
    from .. import determinism
    from .. import originality
    edit = P.read_artifact(pid, "edit", d) or {}
    art["fingerprint"] = determinism.fingerprint(sp, design(plan))
    art["originality_signature"] = originality.signature(plan, script.get("lines") or [])
    if edit.get("beat_fit"):
        art["beat_fit"] = edit["beat_fit"]
    if edit.get("findings"):
        art["qa"]["beat_grid"] = edit["findings"]
    return {"artifact": art, "summary": summary}
