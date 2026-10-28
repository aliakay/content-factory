"""Automatic layout check for HTML scenes (the "check before you render" step of the shared workflows): the renderer
reports every visible text run with its tight box, colour and size at each still (motion/render.mjs --lint, via
window.lintBoxes in the shell); this module turns that into findings the motion designer must fix:

  safe      text outside the platform-safe area (TikTok / Shorts / Reels buttons and tabs) or clipped by the frame
  caption   scene text inside the caption band while the shell's captions are showing
  overlap   two text runs drawn over each other
  contrast  text vs what is really behind it (measured on the still: a ring of pixels around the text box)
  tiny      text too small to read on a phone

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
        out.append({"t": m.get("t", 0), "scene": m.get("scene"), "kind": m.get("kind"), "text": "", "detail": m.get("detail")})
    return sorted(out, key=lambda f: f["t"])


def run(bundle_path, times, outdir, aspect="9:16", hide_caps=(), timing=True):
    """Stills + findings for an HTML design: (paths, page errors, findings). timing=True also runs the readcheck /
    motion lint pass over the whole video (no screenshots, a few seconds)."""
    import sys
    from .config import ROOT
    sys.path.insert(0, os.path.join(ROOT, "bin"))
    import htmlmotion
    paths, errs, lint_path = htmlmotion.shots(bundle_path, times, outdir, lint=True)
    try:
        lint = json.load(open(lint_path)) if lint_path and os.path.exists(lint_path) else {}
    except (OSError, ValueError):
        lint = {}
    found = check(lint, aspect, hide_caps)
    if timing:
        try:
            found += readcheck(htmlmotion.readcheck(bundle_path))
        except Exception as e:      # the timing pass must never stop a design round
            errs = errs + [f"readcheck failed: {type(e).__name__}"]
    return paths, errs, found


def as_text(findings, limit=14):
    """Short lines for the designer's self-check prompt."""
    return [f"{'layout' if f['kind'] in ('safe', 'caption', 'overlap', 'contrast', 'tiny') else 'timing'} {f['kind']} @ "
            f"{f['t']:.2f}s scene {f['scene']}: " + (f"'{f['text']}' " if f.get("text") else "") + f"{f['detail']}"
            for f in findings[:limit]]
