"""Subject and action QC: does the picture show what the line says, and does it show it DOING something?

A scene plan can be beautiful and still be wrong: a frame that shows a gas pipeline for the line "the price crossed a
hundred euros", or three scenes of the same pile of objects with different labels. Layout lint cannot see that, and a
human reviewer only catches it if they read every line against every frame.

Two layers, both cheap:
- `problems()` is deterministic and blocking. Every scene declares `shows`: the subject and what it does, in one
  line. The check refuses a `shows` that names no action, that leaves out a figure the line says (a line with a
  number must show a number), that leaves out a name the line names, that is just the line repeated, or that is the
  same picture three scenes in a row.
- `vision()` asks a model what the frame really shows and compares it with the line and the declaration. It runs from
  the `subject_check` tool, which the designer and the reviewer both have; it never runs inside the deterministic
  path, so a plan can be submitted and tested without a model or a render.
"""
import json

from . import words

BRIEF = """SUBJECT AND ACTION (binding: every scene says what its picture shows and what happens in it)
Give each scene a `shows` line: "the subject, doing something" — "a price line climbing past a 100-euro line",
"the map filling from the east", "three bars splitting off one block". Then check it against the line:
- the subject of the line must be in the picture (the named thing, not a stand-in for the idea);
- if the line says a figure, the figure is on screen;
- something must MOVE or CHANGE in the scene: the verb in `shows` is what the motion does;
- never the same picture three scenes in a row, even with new labels.
Run `subject_check` before you submit: it looks at your stills and tells you which scene shows something else.
"""


def _scene_text(scene, lines):
    a, b = (scene.get("lines") or [0, 0])[:2]
    return " ".join(str(lines[i]) for i in range(a, b + 1) if 0 <= i < len(lines))


def problems(scenes, lines, lang="tr"):
    """What `submit_artifact` refuses: a scene with no declared picture, a picture with no action, a picture that
    drops the line's figure or name, the line copied into `shows`, or the same picture three scenes running."""
    out, shows_seen = [], []
    for i, sc in enumerate(scenes or []):
        sid = sc.get("id") or i
        shows = str(sc.get("shows") or "").strip()
        text = _scene_text(sc, lines or [])
        shows_seen.append(words.fold(shows))
        if not shows:
            out.append(f"scene {sid}: say what its picture shows (`shows`: the subject and what it does)")
            continue
        if len(shows) < 12:
            out.append(f"scene {sid}: `shows` is too short to judge; name the subject and the action")
        if not words.has_action(shows):
            out.append(f"scene {sid}: `shows` names no action; say what changes in the frame "
                       f"(rises, splits, fills, travels, appears ...)")
        if text and words.fold(shows) == words.fold(text):
            out.append(f"scene {sid}: `shows` is the line copied; say what the PICTURE does with it")
        if text and words.has_number(text) and not words.has_number(shows):
            out.append(f"scene {sid}: the line says a figure and `shows` has none; put the number in the picture")
        for name in words.proper_nouns(text):
            if words.fold(name) not in words.fold(shows) and len(name) > 2:
                out.append(f"scene {sid}: the line names '{name}'; the picture must be about it (name it in `shows`)")
                break
    for i in range(len(shows_seen) - 2):
        if shows_seen[i] and shows_seen[i] == shows_seen[i + 1] == shows_seen[i + 2]:
            out.append(f"scenes {i + 1}-{i + 3} show the same picture: change what happens in the middle one")
            break
    return out


def _ask(prompt, image):
    from . import llm
    return llm.ask(prompt, tools=("Read",), timeout=600, model="sonnet")[0]


VISION = """Look at the frame at {image} (open it with Read). It is scene '{scene}' of a short explainer.
The line it must explain, in the video language: "{line}"
The designer says the frame shows: "{shows}"

Answer only what the picture itself proves:
- subject: what is the main thing on screen (a noun phrase)
- action: what is happening to it (a verb phrase; "nothing moves" is a valid answer)
- explains: does this frame, at a glance, explain that line to someone who only sees the frame? true/false
- missing: what the line says that the picture does not show (empty when nothing is missing)
Reply with ONLY JSON: {{"subject": "...", "action": "...", "explains": true, "missing": ""}}"""


def vision(still, line, shows, scene="", ask=None):
    """Ask a vision model what one still shows and whether it is the scene's line. `ask` is injectable for tests.

    Returns {ok, subject, action, explains, missing, problems}. `ok` is false when the model says the frame does not
    explain the line or names an action the declared `shows` did not promise."""
    ask = ask or _ask
    prompt = VISION.format(image=json.dumps(still), scene=scene, line=str(line or "")[:400],
                           shows=str(shows or "")[:300])
    try:
        out = ask(prompt, still) or {}
    except Exception as e:                  # a broken vision call is a missing check, never a failed stage
        return {"ok": None, "error": f"{type(e).__name__}: {e}"[:200], "problems": []}
    problems = []
    if out.get("explains") is False:
        problems.append(f"scene {scene}: the frame does not explain its line"
                        + (f" (missing: {out['missing']})" if out.get("missing") else ""))
    action = str(out.get("action") or "").strip()
    if action and not words.has_action(action) and words.fold(action) not in ("nothing", "nothing moves", "static"):
        problems.append(f"scene {scene}: the frame shows '{action}', which is not an action the line asks for")
    return {"ok": bool(out.get("explains")) and not problems, "subject": out.get("subject"),
            "action": action, "explains": out.get("explains"), "missing": out.get("missing"), "problems": problems}


def motion_pair(first, second, size=96):
    """Separate a global camera move from local subject change in two rendered frames.

    A small translation/scale search aligns the second frame to the first. If most of the change disappears under
    that one global transform, the camera moved while the subject did not. Returns measurements only; callers decide
    whether the scene's declared camera move makes that result a problem.
    """
    import numpy as np
    from PIL import Image

    def gray(path):
        resampling = getattr(Image, "Resampling", Image)
        return np.asarray(Image.open(path).convert("L").resize((size, size), resampling.BILINEAR), dtype=np.float32)

    try:
        a, b = gray(first), gray(second)
    except (OSError, ValueError):
        return {"ok": False, "error": "could not read the two scene frames"}
    yy, xx = np.indices((size, size), dtype=np.float32)
    c = (size - 1) / 2
    best = None
    # A fit wider than this is not a camera move a normal explainer should use between two nearby samples.
    for scale in np.arange(0.94, 1.061, 0.02):
        for dy in range(-8, 9, 2):
            for dx in range(-8, 9, 2):
                sx = (xx - c - dx) / scale + c
                sy = (yy - c - dy) / scale + c
                ix, iy = np.rint(sx).astype(int), np.rint(sy).astype(int)
                valid = (ix >= 0) & (ix < size) & (iy >= 0) & (iy < size)
                if valid.sum() < size * size * 0.65:
                    continue
                diff = np.abs(a[valid] - b[iy[valid], ix[valid]])
                score = float(np.median(diff) + 0.25 * np.mean(diff))
                if best is None or score < best[0]:
                    best = (score, dx, dy, float(scale), float(np.mean(diff > 20)))
    if best is None:
        return {"ok": False, "error": "global camera fit had too few overlapping pixels"}
    score, dx, dy, scale, residual = best
    raw = float(np.mean(np.abs(a - b) > 20))
    return {"ok": True, "camera_px": [dx, dy], "zoom": round(scale, 3),
            "global_change": round(raw, 3), "residual_change": round(residual, 3), "fit_error": round(score, 2)}


def motion_problem(scene, measurement):
    """A camera move that explains the frame change while no local subject action remains."""
    if not (measurement or {}).get("ok"):
        return None
    from . import camera
    c = camera.parse((scene or {}).get("camera"))
    if not c.get("move") or c["move"] == "hold":
        return None
    dx, dy = measurement.get("camera_px") or (0, 0)
    camera_shift = (dx * dx + dy * dy) ** 0.5
    camera_zoom = abs(float(measurement.get("zoom") or 1) - 1)
    if (camera_shift >= 3 or camera_zoom >= 0.035) and measurement.get("residual_change", 1) <= 0.025:
        return (f"scene {scene.get('id')}: the frame changes mainly because the camera moves "
                f"({camera_shift:.0f}px, {camera_zoom * 100:.0f}% scale); the subject itself barely changes")
    return None


def brief(p=None):
    return BRIEF
