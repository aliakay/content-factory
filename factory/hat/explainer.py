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


def draft_timing(lines, lang="tr"):
    """Words [(w, s, e)] and line times for `lines` at the language's speaking rate."""
    wps = WPS.get(lang, 2.5)
    t, words, line_times = 0.0, [], []
    for line in lines:
        ws = line.split()
        start, span = t, len(ws) / wps                 # the line lasts words / rate ...
        weight = sum(len(w) + 1 for w in ws) or 1
        for w in ws:                                    # ... shared by word length
            dur = span * (len(w) + 1) / weight
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


def timing(pid, d=None):
    """The real voice timing when the assets stage made it, else the draft from the script."""
    p = P.load(pid, d)
    assets = P.read_artifact(pid, "assets", d) or {}
    voice = assets.get("voice") or {}
    if voice.get("words") and voice.get("line_times"):
        return [tuple(w) for w in voice["words"]], voice["line_times"], voice["duration"], "voice"
    script = P.read_artifact(pid, "script", d) or {}
    if not narrated(script):
        words, lt, dur = beat_timing(script.get("lines") or [], script.get("holds"))
        return words, lt, dur, "beats"
    words, lt, dur = draft_timing(script.get("lines") or [], p.get("video_lang", "tr"))
    return words, lt, dur, "draft"


def spec(pid, plan=None, d=None):
    """The htmlmotion spec (timing + scene ranges) for this project's scene plan."""
    p = P.load(pid, d)
    plan = plan or P.read_artifact(pid, "scene_plan", d) or {}
    words, line_times, dur, source = timing(pid, d)
    silent = source == "beats" or not narrated(P.read_artifact(pid, "script", d))
    total = round(dur + VOICE_START + TAIL, 3)
    scenes, n = [], len(line_times)
    for i, sc in enumerate(plan.get("scenes") or []):
        a, b = (sc.get("lines") or [0, 0])[:2]
        a, b = max(0, min(a, n - 1)), max(0, min(b, n - 1))
        start = 0.0 if i == 0 else round(line_times[a]["start"] + VOICE_START, 3)
        scenes.append({"id": sc["id"], "lines": [a, b], "start": start, "hide_captions": silent or bool(sc.get("hide_captions"))})
    for i, sc in enumerate(scenes):
        sc["end"] = scenes[i + 1]["start"] if i + 1 < len(scenes) else total
    return {"name": pid, "words": words, "line_times": line_times, "voice_start": VOICE_START, "duration": total,
            "scenes": scenes, "aspect": p.get("aspect", "9:16"), "lang": p.get("video_lang", "tr"),
            "captions": plan.get("captions") or CAPTIONS, "timing": source}


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
    return sum((cp.get("cost") or {}).get("credits", 0) for _, cp in P.stages(pid, d))


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
              music={"file": mu["file"], "db": mu.get("db", -22)} if mu and mu.get("file") else None,
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
    text = " ".join(lines)
    path, cost = eleven.tts(con, text, voice_id, formats.VOICE_MODEL, approved=remaining_budget(pid, d), account=account)
    times, dur, words = productions.align(path, lines, lang)
    P.decision(pid, "voice", voice_id, reason="proposal voice or channel default", d=d, model=formats.VOICE_MODEL)
    voice = {"file": _rel(path), "voice_id": voice_id, "model": formats.VOICE_MODEL, "credits": round(cost),
             "duration": dur, "line_times": times, "words": [list(w) for w in words]}
    music, mcost = None, 0.0
    mu = prop.get("music") or {}
    if mu.get("use"):
        secs = round(dur + VOICE_START + TAIL + 1.5, 1)
        prompt = mu.get("prompt") or "Instrumental, no vocals. Subtle, steady pulse under a spoken explainer."
        if "instrumental" not in prompt.lower():
            prompt = "Instrumental, no vocals. " + prompt
        mpath, mcost = eleven.generate(con, "music", productions.MUSIC_MODEL, prompt, {"duration_seconds": secs,
                                       "instrumental": True}, secs, "s", ext="mp3",
                                       approved=max(0, remaining_budget(pid, d) - round(cost)), account=account)
        music = {"file": _rel(mpath), "prompt": prompt, "credits": round(mcost), "db": -22}
    art = {"voice": voice, "music": music}
    P.write_artifact(pid, "assets", art, d)          # the preview reads the real timing from here
    res, sp = _render(pid, final=False, d=d)
    total = round(cost + mcost)
    art.update(preview=_rel(res["file"]), duration=sp["duration"],
               summary={"tr": f"Ses hazır ({dur:.1f} sn, {total} kredi){', müzikle' if music else ''}. Önizlemeyi izle.",
                        "en": f"Voice ready ({dur:.1f} s, {total} credits){', with music' if music else ''}. Watch the preview."
                        }[p.get("ui_lang", "tr") if p.get("ui_lang") in ("tr", "en") else "tr"])
    return {"artifact": art, "summary": art["summary"], "cost": {"credits": total}}


def _music_only(pid, p, prop, con, account, d=None):
    from .. import eleven, productions
    _, _, dur, _ = timing(pid, d)
    secs = round(dur + VOICE_START + TAIL + 1.5, 1)
    mu = prop.get("music") or {}
    prompt = mu.get("prompt") or "Instrumental, no vocals. A confident pulse with clear accents for motion graphics."
    if "instrumental" not in prompt.lower():
        prompt = "Instrumental, no vocals. " + prompt
    mpath, mcost = eleven.generate(con, "music", productions.MUSIC_MODEL, prompt, {"duration_seconds": secs,
                                   "instrumental": True}, secs, "s", ext="mp3",
                                   approved=remaining_budget(pid, d), account=account)
    art = {"voice": None, "music": {"file": _rel(mpath), "prompt": prompt, "credits": round(mcost), "db": -10}}
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
    P.decision(pid, "edit", "sound full, voice chain clean" + (", film post" if post else ""), d=d)
    return {"artifact": art, "summary": ""}


def compose(pid, s, note=None, d=None):
    """Final render + technical and sound QA + cover candidates."""
    from .. import qa, soundqa, thumbs
    p = P.load(pid, d)
    res, sp = _render(pid, final=True, d=d)
    tech = qa.technical(res["file"], sp["duration"])
    try:
        snd = soundqa.review(res["file"], total=sp["duration"])
        sound = {"findings": snd.get("findings", []), "metrics": snd.get("metrics", {})}
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
           "covers": [_rel(c) for c in covers], "render": {k: res[k] for k in ("cues", "music_cuts", "capture_s")},
           "summary": summary}
    return {"artifact": art, "summary": summary}
