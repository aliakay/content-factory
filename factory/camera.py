"""The camera vocabulary: a move is a word with one meaning, named as move + seconds + easing + target.

`motiongrammar` already says a camera move has to be named as numbers, not adjectives ("push in, 3 s, slow
ease-in-out, on the number"). This module is the vocabulary that naming draws on: every scene of an HTML line says
which move it uses, how long it lasts, how it eases and what it lands on, and `problems()` refuses a plan that leaves
any of that out, invents a move, starts the film on an ease-in, or spends the disorienting moves twice.

The vocabulary is the same one factory/illustrate.py uses for plate cameras (push_in, pull_out, pan_left, pan_right,
tilt_up, tilt_down, zoom_to, hold) plus the three the HTML renderer can do on its own (orbit, dolly_zoom, rack_focus)
and `follow`, which is a pan that keeps a moving subject framed. Keeping one list means a scene cannot invent a
camera the renderer has no word for.
"""

# id -> (what the move means, what it must land on / the trap)
MOVES = {
    "push_in": ("focus: this detail matters now",
                "must land on the thing the voice names; a push in that lands on nothing is a zoom"),
    "pull_out": ("context: here is where it sits",
                 "must reveal something new in the wider frame, not just make the same picture smaller"),
    "pan_left": ("travel: the next thing is back along the way time came from",
                 "the frame must arrive somewhere; a pan that ends on empty ground wasted the move"),
    "pan_right": ("travel: the next thing is ahead, in the direction time flows",
                  "the frame must arrive somewhere; a pan that ends on empty ground wasted the move"),
    "tilt_up": ("more: the value, the stack, the thing that grew",
                "never tilt up on a number that fell"),
    "tilt_down": ("less: the loss, the floor, the thing that sank",
                  "never tilt down on a number that rose"),
    "zoom_to": ("here, exactly: a named point inside the frame",
                "the target point must be where the detail is, not the centre by default"),
    "hold": ("nothing moves: the idea stands still and is read",
             "at most 2.5 s; a longer hold is a still frame, not a shot"),
    "follow": ("the camera keeps a moving subject framed",
               "the subject must actually move, or the camera is drifting for nothing"),
    "rack_focus": ("attention moves from one plane to another",
                   "the new plane must carry the new information"),
    "orbit": ("the same thing seen from another side (a turn in the argument)",
              "once per video; it disorients if it repeats"),
    "dolly_zoom": ("the ground shifts under the subject (dread, scale shock)",
                   "once per video and only on a beat; it is a stunt, not a transition"),
}

EASINGS = ("linear", "ease_in", "ease_out", "ease_in_out", "steps")
BIG = ("orbit", "dolly_zoom")                 # once per video
HOLD_MAX = 2.5                                # a hold longer than this is a still, not a shot
SECONDS = (0.5, 8.0)                          # a camera move shorter than this is a cut; longer is a drone shot
LINES = ("explainer", "long_explainer", "animation")

# free text -> canonical id (folded with factory.words.fold, longest match wins)
SYNONYMS = {
    "push in": "push_in", "push_in": "push_in", "pushin": "push_in", "yaklas": "push_in", "iceri it": "push_in",
    "pull out": "pull_out", "pull_out": "pull_out", "pullout": "pull_out", "geri cekil": "pull_out",
    "pan left": "pan_left", "pan_left": "pan_left", "sola kay": "pan_left",
    "pan right": "pan_right", "pan_right": "pan_right", "saga kay": "pan_right",
    "tilt up": "tilt_up", "tilt_up": "tilt_up", "yukari eg": "tilt_up",
    "tilt down": "tilt_down", "tilt_down": "tilt_down", "asagi eg": "tilt_down",
    "zoom": "zoom_to", "zoom to": "zoom_to", "zoom_to": "zoom_to", "yakinlas": "zoom_to",
    "hold": "hold", "still": "hold", "sabit": "hold",
    "follow": "follow", "takip": "follow",
    "rack focus": "rack_focus", "rack_focus": "rack_focus", "odak kaydir": "rack_focus",
    "orbit": "orbit", "etrafinda don": "orbit",
    "dolly zoom": "dolly_zoom", "dolly_zoom": "dolly_zoom", "vertigo": "dolly_zoom",
}
EASING_ALIASES = {
    "linear": "linear", "none": "linear",
    "ease in": "ease_in", "ease_in": "ease_in", "easein": "ease_in", "ease-in": "ease_in", "power2.in": "ease_in",
    "ease out": "ease_out", "ease_out": "ease_out", "easeout": "ease_out", "ease-out": "ease_out",
    "power2.out": "ease_out",
    "ease in out": "ease_in_out", "ease_in_out": "ease_in_out", "easeinout": "ease_in_out",
    "ease-in-out": "ease_in_out", "power2.inout": "ease_in_out",
    "steps": "steps", "step": "steps", "stepped": "steps",
}

BRIEF = """CAMERA VOCABULARY (binding: every scene names one camera move as a number, not an adjective)
Give each scene a `camera` object: {"move": id, "seconds": number, "easing": id, "target": "what it lands on"}.
- move (one primary per scene): push_in focus · pull_out context · pan_left / pan_right travel · tilt_up more /
  tilt_down less · zoom_to a named point · hold nothing moves (max 2.5 s) · follow a moving subject ·
  rack_focus attention changes plane · orbit another side (once per video) · dolly_zoom scale shock (once per video).
- seconds: 0.5-8. The move must be over before the scene's idea is.
- easing: linear (machines) · ease_in (gathers force, never the first scene) · ease_out (opens a hook) ·
  ease_in_out (deliberate, self-contained) · steps (a cut inside the move).
- target: what it lands on, in words ("the number", "the second bar", "the map's border"). A move that lands on
  nothing is a zoom for its own sake.
- Adjacent scenes must differ in move or length; the same move may not run three scenes in a row.
"""


def _fold(text):
    from .words import fold
    return fold(text)


def _move_id(value):
    if not value:
        return None
    v = _fold(value).strip().replace("-", " ").replace("_", " ")
    if v.replace(" ", "_") in MOVES:
        return v.replace(" ", "_")
    best = None
    for word, mid in SYNONYMS.items():
        w = _fold(word)
        if w in v and (best is None or len(w) > best[0]):
            best = (len(w), mid)
    return best[1] if best else None


def _easing_id(value):
    if not value:
        return None
    v = _fold(value).strip()
    if v.replace(" ", "_") in EASINGS:
        return v.replace(" ", "_")
    best = None                       # longest alias wins, so "ease-in-out" is not read as "ease in"
    for word, eid in EASING_ALIASES.items():
        w = _fold(word)
        if w in v and (best is None or len(w) > best[0]):
            best = (len(w), eid)
    return best[1] if best else None


def parse(camera):
    """A scene's `camera` (dict or free text) -> {move, seconds, easing, target}, whatever could be read.

    Free text is read as "move, seconds, easing, on the target": the move is matched by its longest synonym, the
    seconds by the number before s / sn / sec, the easing by its name, and the target is what follows "on" / "üzerinde"
    / "hedef". Nothing raises: `problems()` is what refuses a half-read move."""
    import re
    if isinstance(camera, dict):
        return {"move": _move_id(camera.get("move")),
                "seconds": _seconds(camera.get("seconds")),
                "easing": _easing_id(camera.get("easing")),
                "target": str(camera.get("target") or "").strip() or None}
    text = str(camera or "").strip()
    if not text:
        return {"move": None, "seconds": None, "easing": None, "target": None}
    parts = [p.strip() for p in re.split(r"[,;]", text) if p.strip()]
    target = None
    for i, p in enumerate(parts):
        m = re.match(r"^(?:on|onto|üzerinde|uzerinde|hedef|hedefi)\b[:,]?\s*(.+)$", p, re.I)
        if m:
            target = m.group(1).strip()
            parts = parts[:i] + parts[i + 1:]
            break
    rest = ", ".join(parts)
    return {"move": _move_id(rest), "seconds": _seconds(rest), "easing": _easing_id(rest), "target": target}


def _seconds(value):
    import re
    if isinstance(value, (int, float)):
        return float(value)
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:s\b|sn\b|sec|saniye|second)", _fold(value), re.I)
    if m:
        return float(m.group(1).replace(",", "."))
    m = re.fullmatch(r"\s*(\d+(?:[.,]\d+)?)\s*", str(value or ""))
    return float(m.group(1).replace(",", ".")) if m else None


def problems(scenes):
    """What `submit_artifact` refuses on a scene plan: a camera that is missing, unreadable, out of range, landing on
    nothing, or repeated until it stops meaning anything. Returns short strings naming the scene and the fix."""
    out, cams = [], []
    for i, sc in enumerate(scenes or []):
        sid = sc.get("id") or i
        raw = sc.get("camera")
        if not raw:
            out.append(f"scene {sid}: name its `camera` (move, seconds, easing, target)")
            cams.append(None)
            continue
        c = parse(raw)
        cams.append(c)
        if not c["move"]:
            out.append(f"scene {sid}: unknown camera move; use one of {', '.join(list(MOVES)[:6])}, ...")
        if c["seconds"] is None:
            out.append(f"scene {sid}: say how many seconds the move takes")
        elif not SECONDS[0] <= c["seconds"] <= SECONDS[1]:
            out.append(f"scene {sid}: {c['seconds']:g} s is outside {SECONDS[0]}-{SECONDS[1]:g} s for a camera move")
        if not c["easing"]:
            out.append(f"scene {sid}: name its easing ({', '.join(EASINGS)})")
        if not c["target"] or len(c["target"]) < 3:
            out.append(f"scene {sid}: say what the move lands on (`target`)")
        if c["move"] == "hold" and c["seconds"] and c["seconds"] > HOLD_MAX:
            out.append(f"scene {sid}: a hold of {c['seconds']:g} s is a still frame (max {HOLD_MAX:g} s); move something")
        if i == 0 and c["easing"] == "ease_in":
            out.append(f"scene {sid}: the first scene never starts on an ease-in (it opens on an ease-out)")
        if i and c["move"] and cams[i - 1] and c["move"] == cams[i - 1]["move"] \
                and c["seconds"] == cams[i - 1]["seconds"]:
            out.append(f"scene {sid}: the same move and length as the scene before it; change the move or the size")
    ids = [c["move"] if c else None for c in cams]
    for i in range(len(ids) - 2):
        if ids[i] and ids[i] == ids[i + 1] == ids[i + 2]:
            out.append(f"scenes {i + 1}-{i + 3} all use '{ids[i]}': change the middle one")
            break
    for big in BIG:
        if ids.count(big) > 1:
            out.append(f"'{big}' is used {ids.count(big)} times: spend it once per video")
    return out


def text_of(camera):
    """A scene's camera as one readable line, for summaries and the animatic artifact."""
    c = parse(camera)
    if not c["move"]:
        return ""
    return f"{c['move']} {c['seconds'] or '?'} s {c['easing'] or '?'} on {c['target'] or '?'}"


def brief(p=None):
    return BRIEF
