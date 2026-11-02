"""The explainer line's code side: timing and bundles for the HTML motion engine (bin/htmlmotion.py).

Before the voice exists, timing is drafted from the script (words per second of the video language); once the
assets stage has the real voice, its word timings replace the draft. The scene plan (the stage agent's artifact)
plus that timing becomes the bundle the renderer and the design tools (stills, layout lint, readcheck) load.
"""
import json, os, sys

from ..config import ROOT
from . import project as P

WPS = {"tr": 2.4, "en": 2.6}       # spoken words per second, for draft timing
PAUSE = 0.3                         # gap between lines in the draft
VOICE_START = 0.15
TAIL = 0.8
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


def timing(pid, d=None):
    """The real voice timing when the assets stage made it, else the draft from the script."""
    p = P.load(pid, d)
    assets = P.read_artifact(pid, "assets", d) or {}
    voice = assets.get("voice") or {}
    if voice.get("words") and voice.get("line_times"):
        return [tuple(w) for w in voice["words"]], voice["line_times"], voice["duration"], "voice"
    script = P.read_artifact(pid, "script", d) or {}
    words, lt, dur = draft_timing(script.get("lines") or [], p.get("video_lang", "tr"))
    return words, lt, dur, "draft"


def spec(pid, plan=None, d=None):
    """The htmlmotion spec (timing + scene ranges) for this project's scene plan."""
    p = P.load(pid, d)
    plan = plan or P.read_artifact(pid, "scene_plan", d) or {}
    words, line_times, dur, source = timing(pid, d)
    total = round(dur + VOICE_START + TAIL, 3)
    scenes, n = [], len(line_times)
    for i, sc in enumerate(plan.get("scenes") or []):
        a, b = (sc.get("lines") or [0, 0])[:2]
        a, b = max(0, min(a, n - 1)), max(0, min(b, n - 1))
        start = 0.0 if i == 0 else round(line_times[a]["start"] + VOICE_START, 3)
        scenes.append({"id": sc["id"], "lines": [a, b], "start": start, "hide_captions": bool(sc.get("hide_captions"))})
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
