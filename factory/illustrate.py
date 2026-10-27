"""Illustrated look ("çizimli"): every scene stands on its own AI illustration ("plate") in one locked art style, and
Opus animates on top of it in HTML/GSAP: camera moves on the plate (push-in, pan, zoom into a detail), zoom-through
from one plate to the next when two scenes share a place, and annotations drawn over the art (boxes that draw
themselves, arrows, pins with labels, underlines, a highlighted word in the title) - the explainer register of
channels like whyrd / Vox / Kurzgesagt-lite.

Flow inside the normal production steps:
  script (explainer.generate or series.write_episode) writes `art_style` + per scene `plate` {prompt, camera, focus,
  annotations, same_place_as, cast}  ->  "Çizimler" card: credit estimate (scenes x image rate), creator approves  ->
  job p_plates: eleven.image per scene on ONE ElevenLabs flow (a plate that shares a place, or shows a series character,
  is made FROM that node so the art stays the same)  ->  motiondesign.build animates the plates  ->  voice, preview,
  render (engine "html"). Nothing is generated without the approval; plates are cached by prompt.
"""
import os

from . import credits, eleven

from .config import ROOT

CAMERAS = ("push_in", "pull_out", "pan_left", "pan_right", "tilt_up", "tilt_down", "zoom_to", "hold")
ANNOTATIONS = ("box", "arrow", "pin", "label", "underline", "circle", "path")

SCRIPT_RULES = """ILLUSTRATED LOOK: every scene stands on ONE illustration (made later by an image model in a single locked art
style) and the motion designer animates camera moves and annotations over it. Write:
- "art_style": one paragraph that locks the look for every image: medium (e.g. flat vector illustration with thick
  dark outlines and soft cel shading), palette (4-6 named colours), lighting, level of detail, camera height, mood.
  Never name an artist or a brand. Images contain NO text, letters, logos or UI.
- per scene "plate": {"prompt": "<what the image shows: concrete subject, setting, composition, where the key thing sits
  (e.g. 'a phone held in a hand in the lower middle, rainy terraced street behind')>", "camera": "push_in|pull_out|
  pan_left|pan_right|tilt_up|tilt_down|zoom_to|hold", "focus": [x, y] (0..1, where the camera heads / the key detail),
  "same_place_as": "<earlier scene id when this is the same place seen closer or from above, else null>",
  "annotations": [{"type": "box|arrow|pin|label|underline|circle|path", "text": "<short, from the script>", "at":
  "<trigger word>", "where": [x, y, w, h] (0..1 of the frame)}] (0-3 per scene; they EXPLAIN: mark the square the
  forecast covers, pin 'YOU' on the map)}.
  Good sequences move the camera through ONE world: street level -> top-down map of the same street -> zoom into a
  detail. Prefer that over unrelated pictures. The hook plate must read instantly at frame 0."""

DESIGN_RULES = """ILLUSTRATED SCENES: each scene has a ready illustration (its "plate") that MUST be the scene's full-bleed base:
<img src="{{plate:SCENE_ID}}"> (object-fit: cover; make it ~115% of the frame so the camera can move). Animate:
- camera: the plate's "camera" + "focus" with slow, continuous GSAP scale/x/y on a wrapper (power1.inOut / sine.inOut,
  the whole scene long, never static); "zoom_to" = a decisive push into the focus point on the trigger word.
- transitions: when a scene has "same_place_as", continue the camera INTO the next plate (scale the old one up toward
  the focus while the new one fades/zooms in from the matching point) so it reads as one camera move.
- annotations: SVG over the plate, drawn on (stroke-dashoffset), at their trigger words: boxes trace their outline with
  a small tab label ("ONE FORECAST SQUARE"), pins drop with a line to a label ("YOU"), arrows grow, underlines swipe.
  Off-white or the accent colour with a dark hairline so they read on any art; 4-6 px strokes.
- title words: big condensed sans at the top with ONE word in the accent colour, cut in word by word on the voice.
Keep annotation positions from "where" (fractions of the frame); nothing in the caption band."""


def clean_plate(pl, scene_ids=()):
    """Shape a model-written plate; None when it has no usable prompt."""
    if not isinstance(pl, dict) or not str(pl.get("prompt") or "").strip():
        return None
    f = pl.get("focus") if isinstance(pl.get("focus"), list) and len(pl.get("focus")) == 2 else [0.5, 0.5]
    try:
        focus = [max(0.0, min(float(f[0]), 1.0)), max(0.0, min(float(f[1]), 1.0))]
    except (TypeError, ValueError):
        focus = [0.5, 0.5]
    ann = []
    for a in pl.get("annotations") or []:
        if not isinstance(a, dict) or a.get("type") not in ANNOTATIONS:
            continue
        w = a.get("where") if isinstance(a.get("where"), list) and len(a.get("where")) == 4 else None
        try:
            w = [max(0.0, min(float(x), 1.0)) for x in w] if w else None
        except (TypeError, ValueError):
            w = None
        ann.append({"type": a["type"], "text": str(a.get("text") or "")[:40], "at": a.get("at", 0.3), "where": w})
    same = pl.get("same_place_as")
    return {"prompt": str(pl["prompt"]).strip()[:700], "camera": pl.get("camera") if pl.get("camera") in CAMERAS else "push_in",
            "focus": focus, "annotations": ann[:3], "same_place_as": same if same in scene_ids else None,
            "cast": [str(c)[:30] for c in (pl.get("cast") or []) if str(c).strip()][:4]}


def needs_plates(d):
    return (d or {}).get("look_pack") == "illustrated" or bool((d or {}).get("illustrated"))


def missing(d):
    """Scene ids whose plate image does not exist yet."""
    have = d.get("plates") or {}
    return [sc["id"] for sc in d.get("scenes") or [] if sc.get("plate")
            and not (have.get(sc["id"]) and os.path.exists(os.path.join(ROOT, have[sc["id"]]["file"])))]


def estimate(con, d, account):
    n = len(missing(d))
    est = credits.estimate([{"kind": "image", "model": eleven.IMAGE_MODEL, "units": n, "unit": "img",
                             "label": "illustrations"}])
    return {"images": n, "credits": est["total"], "unknown": est["unknown"],
            "budget": credits.check_budget(con, est["total"], account), "account": account}


def plate_prompt(d, sc, characters=None):
    """Locked style + the scene + the characters it shows (their fixed descriptions)."""
    pl = sc["plate"]
    who = ""
    if characters and pl.get("cast"):
        desc = [f"{c['name']}: {c['look']}" for c in characters if c["id"] in pl["cast"]]
        who = (" Characters in this image (draw them exactly like this every time): " + " | ".join(desc)) if desc else ""
    return (f"{d.get('art_style') or 'Flat vector illustration, thick dark outlines, soft cel shading, muted palette.'} "
            f"Scene: {pl['prompt']}.{who} No text, letters, numbers, logos or user-interface elements in the image.")


def make_plates(con, p, approved, characters=None, flow_id=None):
    """Generate every missing plate (one image each) on one flow. Mutates p['data']; the caller saves.
    A plate with same_place_as is made FROM that scene's plate; series characters come from their sheet nodes."""
    d = p["data"]
    todo = missing(d)
    if not todo:
        return 0.0
    from .productions import eleven_account
    account = eleven_account(d)
    per = max(1, round(approved / len(todo)))
    plates = d.setdefault("plates", {})
    flow = d.get("art_flow") or flow_id
    sheets = {c["id"]: c.get("sheet") or {} for c in characters or []}
    spent = 0.0
    for sc in d["scenes"]:
        if sc["id"] not in todo:
            continue
        pl = sc["plate"]
        refs = []
        if pl.get("same_place_as") and plates.get(pl["same_place_as"], {}).get("node_id"):
            refs.append(plates[pl["same_place_as"]]["node_id"])
        refs += [sheets[c]["node_id"] for c in pl.get("cast") or [] if sheets.get(c, {}).get("node_id")]
        path, cost, flow, node = eleven.image(con, plate_prompt(d, sc, characters), per + max(1, per // 7), account,
                                              d.get("aspect", "9:16"), flow, refs[:3], p.get("prod_id"))
        plates[sc["id"]] = {"file": os.path.relpath(path, ROOT), "node_id": node, "prompt": pl["prompt"]}
        d["art_flow"] = flow
        spent += cost
    return spent


def plate_urls(d):
    """{scene id: url path the HTML shell can load} for the motion designer's {{plate:ID}} placeholders."""
    return {sid: "/" + v["file"] for sid, v in (d.get("plates") or {}).items() if v.get("file")}


def brief(d):
    """What the motion designer gets about each plate."""
    return {sc["id"]: {k: sc["plate"].get(k) for k in ("prompt", "camera", "focus", "annotations", "same_place_as")}
            for sc in d.get("scenes") or [] if sc.get("plate")}
