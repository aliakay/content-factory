"""Automatic layout check for HTML scenes (the "check before you render" step of the shared workflows): the renderer
reports every visible text run with its tight box, colour and size at each still (motion/render.mjs --lint, via
window.lintBoxes in the shell); this module turns that into findings the motion designer must fix:

  safe      text outside the platform-safe area (TikTok / Shorts / Reels buttons and tabs) or clipped by the frame
  caption   scene text inside the caption band while the shell's captions are showing
  overlap   two text runs drawn over each other
  contrast  text vs what is really behind it (measured on the still: a ring of pixels around the text box)
  tiny      text too small to read on a phone

and the slop lint (t519): the patterns that make a video look like a slide deck put through a template --
corner labels, counters ("01 / 05", "Step 2"), the same headline slot on the left in every scene, headlines typed
letter by letter, a flat one-colour ground in every scene, empty frames and a fade on every transition.

Free and deterministic (Pillow on the stills Chromium already made), so it runs on every design round.
"""
import json, os, re

SAFE = {"9:16": {"x": (60, 930), "y": (170, 1500), "cap": (1540, 1710), "size": (1080, 1920)},
        "16:9": {"x": (80, 1840), "y": (60, 850), "cap": (880, 1030), "size": (1920, 1080)}}
MIN_PX = {"9:16": 24, "16:9": 22}


def _rgb(css):
    m = re.match(r"rgba?\(([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?\)", css or "")
    if not m:
        return None
    if m.group(4) is not None and float(m.group(4)) < 0.2:
        return None
    return tuple(float(m.group(i)) for i in (1, 2, 3))


def luminance(rgb):
    def ch(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def ring_color(img, box, pad=8):
    """Median colour of a thin ring around the text box: what the text really sits on."""
    W, H = img.size
    x, y, w, h = box
    import numpy as np
    arr, parts = np.asarray(img), []
    for (a, b, c, d) in ((x - pad, y - pad, x + w + pad, y), (x - pad, y + h, x + w + pad, y + h + pad),
                         (x - pad, y, x, y + h), (x + w, y, x + w + pad, y + h)):
        a, b, c, d = max(0, int(a)), max(0, int(b)), min(W, int(c)), min(H, int(d))
        if c > a and d > b:
            parts.append(arr[b:d, a:c, :3].reshape(-1, 3))
    if not parts:
        return None
    px = np.concatenate(parts)
    order = np.argsort(px.sum(axis=1))
    return tuple(int(v) for v in px[order[len(order) // 2]])


def _inter(a, b):
    w = min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"])
    h = min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"])
    return max(0, w) * max(0, h)


def check(lint, aspect="9:16", hide_caps=()):
    """Findings from a render.mjs --lint file (dict t -> {file, boxes, cap}). `hide_caps` = scene ids whose captions
    are hidden on purpose (their text may use the band)."""
    from PIL import Image
    z = SAFE.get(aspect, SAFE["9:16"])
    W, H = z["size"]
    out, seen = [], set()

    def add(t, b, kind, detail):
        key = (b.get("scene"), b.get("text"), kind)
        if key not in seen:
            seen.add(key)
            out.append({"t": float(t), "scene": b.get("scene"), "kind": kind, "text": b.get("text"), "detail": detail})

    for t, shot in sorted(lint.items(), key=lambda kv: float(kv[0])):
        boxes = shot.get("boxes") or []
        img = None
        if shot.get("file") and os.path.exists(shot["file"]):
            try:
                img = Image.open(shot["file"]).convert("RGB")
                if img.size != (W, H):   # a --scale render: boxes are CSS px, the still is scaled
                    img = img.resize((W, H))
            except OSError:
                img = None
        for b in boxes:
            area = max(1, b["w"] * b["h"])
            if b["x"] < 0 or b["y"] < 0 or b["x"] + b["w"] > W or b["y"] + b["h"] > H:
                add(t, b, "safe", "clipped by the frame edge")
            else:
                ix = max(0, min(b["x"] + b["w"], z["x"][1]) - max(b["x"], z["x"][0]))
                iy = max(0, min(b["y"] + b["h"], z["y"][1]) - max(b["y"], z["y"][0]))
                outside = 1 - ix * iy / area
                if outside > 0.25 and b.get("size", 40) >= 26:
                    add(t, b, "safe", f"{round(outside * 100)} % outside the safe area x {z['x'][0]}-{z['x'][1]}, "
                                      f"y {z['y'][0]}-{z['y'][1]} (platform buttons cover it)")
            if shot.get("cap") and b.get("scene") not in hide_caps:
                cy = (max(b["y"], z["cap"][0]), min(b["y"] + b["h"], z["cap"][1]))
                if cy[1] - cy[0] > b["h"] * 0.3:
                    add(t, b, "caption", f"sits in the caption band y {z['cap'][0]}-{z['cap'][1]} under the captions")
            if b.get("size", 99) < MIN_PX.get(aspect, 24) and len(b.get("text") or "") > 3:
                add(t, b, "tiny", f"{b['size']:.0f} px text is hard to read on a phone (min {MIN_PX.get(aspect, 24)} px)")
            fg = _rgb(b.get("color"))
            if img is not None and fg and not b.get("clipText"):
                bg = ring_color(img, (b["x"], b["y"], b["w"], b["h"]))
                if bg:
                    c = contrast(fg, bg)
                    need = 3.0 if b.get("size", 40) >= 40 else 4.5
                    if c < need:
                        add(t, b, "contrast", f"contrast {c:.1f}:1 against what is behind it (needs {need}:1)")
        for i, a in enumerate(boxes):
            for b in boxes[i + 1:]:
                if a.get("scene") != b.get("scene") or a.get("text") == b.get("text") or a.get("flip") or b.get("flip"):
                    continue
                inter = _inter(a, b)
                if inter > 0.2 * min(a["w"] * a["h"], b["w"] * b["h"]):
                    add(t, a, "overlap", f"drawn over '{b.get('text')}'")
    return out


def hold_needed(text, lang="en"):
    """How long a line must stay readable: ~0.3 s a word + 0.5 s (letters / 15 + 1.5 s for long lines), at least 1.2 s."""
    words = len(str(text).split())
    return max(1.2, min(4.0, max(0.3 * words + 0.5, len(str(text)) / 15 + 0.6 if words > 6 else 0)))


def readcheck(data, lang="en", min_chars=4):
    """Texts that are on screen too briefly to read + the timeline's own motion findings (render.mjs --readcheck)."""
    step = data.get("step", 0.2)
    spans, open_ = {}, {}
    for t, boxes in data.get("samples") or []:
        now = {(sc, tx) for sc, tx in boxes if len(tx) >= min_chars}
        for key in now:
            open_.setdefault(key, t)
        for key in list(open_):
            if key not in now:
                spans.setdefault(key, []).append((open_.pop(key), t))
    end = (data.get("samples") or [[0]])[-1][0] + step
    for key, a in open_.items():
        spans.setdefault(key, []).append((a, end))
    out = []
    for (sc, tx), ss in spans.items():
        best = max(b - a for a, b in ss)
        need = hold_needed(tx, lang)
        if best + step / 2 < need:
            out.append({"t": round(ss[0][0], 2), "scene": sc, "kind": "unread", "text": tx,
                        "detail": f"readable for {best:.1f} s, needs ~{need:.1f} s"})
    for m in data.get("motion") or []:
        if m.get("kind") in ("entry", "ease"):      # how a scene comes in, how each move eases: inputs, not findings
            continue
        out.append({"t": m.get("t", 0), "scene": m.get("scene"), "kind": m.get("kind"), "text": "", "detail": m.get("detail")})
    return sorted(out, key=lambda f: f["t"])


SLOP = ("corner", "counter", "template", "typed", "flat", "empty", "fades")
SLOP_BRIEF = """SLOP LINT (measured on your stills; render_stills reports each hit as `slop <kind>` and you fix it):
- corner: no small running labels pinned in a corner scene after scene (a deck's header).
- counter: no "01 / 05", "Step 2", "Adım 3" on screen; show the order with the picture (a path, a stack).
- template: the headline does not sit in the same slot on the left in every scene (title + card slide layout).
- typed: no headline typed letter by letter (FX.typewriter); bring words in by word or line, on the voice.
- flat: not every scene on a flat one-colour ground; give depth, texture or a picture.
- empty: no frame with nothing drawn on it. Timing `dead` = > 3 s with nothing moving.
- fades: not every scene change a fade; cut, push, match or wipe so the transition says something."""
COUNTER = re.compile(r"^\s*(?:#?0?\d{1,2}\s*(?:/|\||of|z)\s*0?\d{1,2}|0\d|(?:step|part|scene|chapter|adım|bölüm|sahne|"
                     r"kısım)\s*\d{1,2}(?:\s*(?:/|of)\s*\d{1,2})?|\d{1,2}\s*\.\s*(?:adım|bölüm))\s*[.:]?\s*$", re.I)
TYPED = re.compile(r"FX\.typewriter\s*\(|\.textContent\s*=\s*[\w.$]+\.(?:slice|substring|substr)\(\s*0\s*,")
FLAT = 0.85         # this share of a still in one colour = a flat ground
EMPTY = 0.985       # ... and nothing drawn at all


def _scene_of(t, scenes):
    for sc in scenes:
        if sc["start"] - 0.01 <= t < sc["end"]:
            return sc["id"]
    return scenes[-1]["id"] if scenes else None


def flat_share(img):
    """The share of the still within a few levels of its most common colour (1.0 = one flat colour)."""
    import numpy as np
    a = np.asarray(img.convert("RGB").resize((54, 96))).reshape(-1, 3).astype(int)
    q = a // 12
    keys, counts = np.unique(q[:, 0] * 10000 + q[:, 1] * 100 + q[:, 2], return_counts=True)
    k = keys[counts.argmax()]
    mode = a[(q[:, 0] * 10000 + q[:, 1] * 100 + q[:, 2]) == k].mean(axis=0)
    return float((np.abs(a - mode).max(axis=1) <= 10).mean())


def slop(bundle, lint, aspect="9:16", motion=()):
    """Slop findings for a bundle (its scenes' html/js and timing), the --lint stills and the motion lint's scene
    entries. Repeated patterns are reported once for the video; per-scene ones once per scene."""
    from PIL import Image
    z = SAFE.get(aspect, SAFE["9:16"])
    W, H = z["size"]
    scenes = [sc for sc in bundle.get("scenes") or [] if sc.get("id") is not None]
    n = len(scenes)
    out = []

    def add(t, scene, kind, detail, text=""):
        out.append({"t": round(float(t), 2), "scene": scene, "kind": kind, "text": text, "detail": detail})

    boxes, shot_of = {}, {}                          # scene -> its text boxes; scene -> its first still
    for t, shot in sorted(lint.items(), key=lambda kv: float(kv[0])):
        sid = _scene_of(float(t), scenes)
        for b in shot.get("boxes") or []:
            boxes.setdefault(b.get("scene") or sid, []).append((float(t), b))
        if sid is not None and sid not in shot_of and shot.get("file") and os.path.exists(shot["file"]):
            shot_of[sid] = (float(t), shot)
    seen = set()
    for sid, bs in boxes.items():
        for t, b in bs:
            tx = (b.get("text") or "").strip()
            if COUNTER.match(tx) and (sid, "counter") not in seen:
                seen.add((sid, "counter"))
                add(t, sid, "counter", "a counter / step number on screen reads as a slide template; say the order "
                                       "with the picture (a path that grows, a stack that builds)", tx)
    corners = {}
    for sid, bs in boxes.items():
        for t, b in bs:
            tx = (b.get("text") or "").strip()
            if not tx or len(tx) > 28 or b.get("size", 99) > 34:
                continue
            side = "left" if b["x"] < 0.25 * W else "right" if b["x"] + b["w"] > 0.75 * W else None
            end = "top" if b["y"] < 0.2 * H else "bottom" if b["y"] + b["h"] > 0.8 * H else None
            if side and end:
                corners.setdefault(f"{end} {side}", {}).setdefault(sid, (t, tx))
    for corner, hit in corners.items():
        if n >= 2 and len(hit) >= 2 and len(hit) >= 0.5 * n:
            t, tx = min(hit.values())
            add(t, sorted(hit)[0], "corner", f"small labels pinned in the {corner} corner in {len(hit)} of {n} scenes "
                                             "(a deck's running header); drop them or make the label part of the picture", tx)
    heads = {}
    for sid, bs in boxes.items():
        t, b = max(bs, key=lambda tb: tb[1].get("size", 0))
        if b["x"] < 0.18 * W:
            heads[sid] = (t, b)
    if n >= 3:
        for sid, (t, b) in heads.items():
            same = [k for k, (_, o) in heads.items() if abs(o["x"] - b["x"]) <= 30 and abs(o["y"] - b["y"]) <= 40]
            if len(same) >= 3 and len(same) >= 0.6 * n:
                add(t, sid, "template", f"the headline sits in the same slot on the left (x {b['x']}, y {b['y']}) in "
                                        f"{len(same)} of {n} scenes, a title + card slide layout; let each scene's "
                                        "picture decide where its words go", b.get("text") or "")
                break
    for sc in scenes:
        if TYPED.search(sc.get("js") or ""):
            add(sc["start"], sc["id"], "typed", "text typed letter by letter is a template move; bring the headline in "
                                                "by word or line, on the voice")
    flats = {}
    for sid, (t, shot) in shot_of.items():
        try:
            f = flat_share(Image.open(shot["file"]))
        except OSError:
            continue
        flats[sid] = f
        if f >= EMPTY and not shot.get("boxes"):
            add(t, sid, "empty", "an empty frame: one flat colour and nothing drawn")
    if len(flats) >= 3 and all(f >= FLAT for f in flats.values()):
        add(scenes[0]["start"], scenes[0]["id"], "flat", f"every scene stands on a flat one-colour ground ({len(flats)} "
            "of them); give the ground depth, texture or a picture in at least some scenes")
    entries = [m for m in motion or [] if m.get("kind") == "entry"]
    if len(entries) >= 2 and all(m.get("detail") == "fade" for m in entries):
        add(entries[0].get("t", 0), entries[0].get("scene"), "fades", f"all {len(entries)} scene changes are fades; cut, "
            "push, match or wipe so the transition says something")
    return out


GENERIC = re.compile(r"^(default|none|linear|power0|power1|sine|quad)(\.|$)", re.I)
INTENT = re.compile(r"^(power[234]|cubic|quart|quint|strong|expo|circ|back|elastic|bounce|custom|steps)(\.|\(|$)", re.I)
LAYOUT = ("safe", "caption", "overlap", "contrast", "tiny")
GRADES = ((80, "maxxed"), (55, "orta"), (0, "slop"))


def easing(motion):
    """The measured easing of the spatial moves: {moves, generic, intent, kinds, quick, long} (shares 0-1)."""
    ms = [m for m in motion or [] if m.get("kind") == "ease"]
    n = len(ms)
    if not n:
        return {"moves": 0, "generic": 0.0, "intent": 0.0, "kinds": 0, "quick": 0.0, "long": 0.0}
    fam = lambda e: re.split(r"[.(]", str(e))[0].lower()
    return {"moves": n, "generic": round(sum(bool(GENERIC.match(m["detail"])) for m in ms) / n, 2),
            "intent": round(sum(bool(INTENT.match(m["detail"])) for m in ms) / n, 2),
            "kinds": len({fam(m["detail"]) for m in ms}),
            "quick": round(sum(m.get("d", 0) < 0.25 for m in ms) / n, 2),
            "long": round(sum(m.get("d", 0) > 1.6 for m in ms) / n, 2)}


def easing_findings(e, scene=None):
    out = []
    if e["moves"] >= 4 and e["generic"] >= 0.6:
        out.append({"t": 0.0, "scene": scene, "kind": "easing", "text": "",
                    "detail": f"{round(e['generic'] * 100)} % of the {e['moves']} moves use a generic soft ease (default /"
                              " power1 / sine / linear); give moves intent: expo.out or power3.out to land, back.out to "
                              "pop, power2.inOut to travel"})
    if e["moves"] >= 6 and e["kinds"] < 2:
        out.append({"t": 0.0, "scene": scene, "kind": "easing", "text": "",
                    "detail": f"one ease for all {e['moves']} moves; vary it with what each move means"})
    return out


def grade(found, motion=(), scenes=1):
    """The video's grade from its findings and measured easing -> {grade, score, parts}."""
    k = [f["kind"] for f in found]
    e = easing(motion)
    parts = {"layout": -min(20, 4 * sum(x in LAYOUT for x in k)),
             "timing": -min(18, 3 * sum(x not in LAYOUT and x not in SLOP and x != "easing" for x in k)),
             "slop": -min(40, 12 * sum(x in ("corner", "template", "flat", "fades") for x in k)
                          + 5 * sum(x in ("counter", "typed", "empty") for x in k)),
             "easing": 0}
    if e["moves"]:
        parts["easing"] = round(10 * e["intent"] - (15 if e["generic"] >= 0.6 else 0) - (5 if e["moves"] >= 6 and
                                e["kinds"] < 2 else 0) - (5 if e["long"] > 0.3 else 0))
    if e["moves"] < max(1, scenes):                  # less than one move a scene: a slideshow
        parts["motion"] = -15
    score = max(0, min(100, 90 + sum(parts.values())))
    g = next(name for bar, name in GRADES if score >= bar)
    if g == "maxxed" and any(x in SLOP for x in k):
        g = "orta"                                     # no slop pattern in a maxxed video
    return {"grade": g, "score": score, "parts": parts, "easing": e}


def run(bundle_path, times, outdir, aspect="9:16", hide_caps=(), timing=True, span=None, report=None):
    """Stills + findings for an HTML design: (paths, page errors, findings). timing=True also runs the readcheck /
    motion lint pass over the whole video, or over span=(a, b) seconds (no screenshots, a few seconds). A `report`
    dict gets the grade (t520) when the timing pass ran."""
    import sys
    from .config import ROOT
    sys.path.insert(0, os.path.join(ROOT, "bin"))
    import htmlmotion
    paths, errs, lint_path = htmlmotion.shots(bundle_path, times, outdir, lint=True)
    try:
        lint = json.load(open(lint_path)) if lint_path and os.path.exists(lint_path) else {}
    except (OSError, ValueError):
        lint = {}
    found, motion = check(lint, aspect, hide_caps), []
    if timing:
        try:
            data = htmlmotion.readcheck(bundle_path, span)
            motion = data.get("motion") or []
            found += readcheck(data)
        except Exception as e:      # the timing pass must never stop a design round
            errs = errs + [f"readcheck failed: {type(e).__name__}"]
    try:
        bundle = json.load(open(bundle_path))
        found += slop(bundle, lint, aspect, motion)
        found += easing_findings(easing(motion))
        if report is not None and timing:
            report.update(grade(found, motion, len(bundle.get("scenes") or [])))
    except Exception as e:          # nor the slop lint
        errs = errs + [f"slop lint failed: {type(e).__name__}"]
    return paths, errs, found


def as_text(findings, limit=14):
    """Short lines for the designer's self-check prompt."""
    kind = lambda k: "layout" if k in LAYOUT else "slop" if k in SLOP else "timing"
    return [f"{kind(f['kind'])} {f['kind']} @ "
            f"{f['t']:.2f}s scene {f['scene']}: " + (f"'{f['text']}' " if f.get("text") else "") + f"{f['detail']}"
            for f in findings[:limit]]
