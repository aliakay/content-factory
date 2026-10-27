"""Faceless explainer renderer: code-drawn motion graphics + kinetic captions over the creator's voiceover.

Python + Pillow frames are piped as raw RGB into ffmpeg (no Chromium, no AI video: text and numbers stay sharp).
Spec (compiled by factory/explainer.py, all times absolute seconds):
  {name, aspect "9:16" | "16:9", duration, voice {file, start}, music {file, db}, header "AI UPDATE · OCT 2026",
   words [[word, start, end], ...], scenes [{id, start, end, hide_captions, elements [{type, at, ...}]}], post {...}}
Usage: python bin/explainer.py specs/explainer/<name>.json [--preview] [--still T [T ...]]
"""
import functools, json, math, os, random, subprocess, sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from factory.config import ROOT, FFMPEG  # noqa: E402
FONT = os.path.join(ROOT, "fonts", "InterTight[wght].ttf")
W, H = 1080, 1920
FPS = 30
# Canvas. The graphics are always laid out on a 1080-wide "stage" (VIS_TOP..VIS_BOT, centre x 540). On 9:16 the stage is
# the canvas itself; on 16:9 it is drawn on its own layer and placed, scaled by STAGE_K, in the middle of the wide frame,
# while background, header, source line and captions use the real canvas (CX, *_Y below).
SW = 1080
CX, HEADER_Y, CAP_SIZE = 540, 205, 66
LANDSCAPE = False
STAGE_K, STAGE_TOP = 1.0, 0

# design tokens
BG_TOP, BG_BOT = (6, 9, 20), (10, 22, 46)
TEAL, ORANGE = (46, 230, 197), (255, 138, 61)
TEXT, MUTED = (245, 247, 250), (138, 148, 168)
HERO = COUNTER = PRICE2 = ORANGE
SRC, TRACK, OLD, STROKE, DARK, PAPER = (176, 186, 204), (255, 255, 255, 22), (90, 105, 130), (0, 0, 0), 0.62, False
# per-look roles: ACCENT (new / key), HOT (old world, negation), HERO colour, COUNTER colour, PRICE2, source line, bar
# track + old bar, stroke round captions, paper-look flag. set_theme() swaps them; "tech" is the original look.
TECH = dict(name="tech", BG_TOP=(6, 9, 20), BG_BOT=(10, 22, 46), TEAL=(46, 230, 197), ORANGE=(255, 138, 61),
            TEXT=(245, 247, 250), MUTED=(138, 148, 168), HERO=(255, 138, 61), COUNTER=(255, 138, 61),
            PRICE2=(255, 138, 61), SRC=(176, 186, 204), TRACK=(255, 255, 255, 22), OLD=(90, 105, 130),
            STROKE=(0, 0, 0), DARK=0.62, PAPER=False)
# "paper" = the Vox register (printed, not lit): cream paper, ink type, one yellow highlighter per scene, red = old
# world / negation, cobalt = new capability; hard offset shadows, grain, halftone dots stepping at 12 fps, sheet-wipe cut.
PAPER = dict(name="paper", BG_TOP=(242, 236, 223), BG_BOT=(242, 236, 223), TEAL=(47, 95, 232), ORANGE=(229, 72, 63),
             TEXT=(22, 21, 19), MUTED=(112, 104, 90), HERO=(22, 21, 19), COUNTER=(47, 95, 232),
             PRICE2=(22, 21, 19), SRC=(96, 89, 76), TRACK=(22, 21, 19, 30), OLD=(229, 72, 63),
             STROKE=(242, 236, 223), DARK=0.72, PAPER=True)
YELLOW, INK, CREAM, CARD = (255, 210, 0), (22, 21, 19), (242, 236, 223), (251, 247, 238)
THEMES = {"tech": TECH, "paper": PAPER}
# Deeper style tokens (factory/styles.py, Level 2). Missing keys fall back to what the look did before, so "tech" and
# "paper" render exactly as they always did:
#   HIGHLIGHT  highlighter / active-caption block colour (paper: yellow)
#   FONT_DISPLAY, FONT_BODY, WGHT_DISPLAY  font files in fonts/ for big type and for body/labels, display weight
#   UPPER      big type and captions in capitals (True) or as written
#   TRACKING   extra letter spacing of labels/header in px
#   RADIUS, SHADOW  card corner radius and "hard" / "soft" / "none" shadow; GRID "lines" / "dots" / "none"
#   ENTRANCE   "pop" (scale with overshoot + rise), "slap" (1.15 -> 1, no overshoot), "rise" (slide up), "fade"
#   POP_DUR    entrance length in s; TRANSITION between scenes "fade" / "sheet" (paper wipe) / "cut"
STYLE_DEFAULTS = {
    "tech": dict(HIGHLIGHT=YELLOW, FONT_DISPLAY="InterTight[wght].ttf", FONT_BODY="InterTight[wght].ttf", WGHT_DISPLAY=900,
                 UPPER=True, TRACKING=7, RADIUS=36, SHADOW="none", GRID="lines", ENTRANCE="pop", POP_DUR=0.22,
                 TRANSITION="fade"),
    "paper": dict(HIGHLIGHT=YELLOW, FONT_DISPLAY="InterTight[wght].ttf", FONT_BODY="InterTight[wght].ttf", WGHT_DISPLAY=900,
                  UPPER=True, TRACKING=7, RADIUS=10, SHADOW="hard", GRID="dots", ENTRANCE="slap", POP_DUR=0.5,
                  TRANSITION="sheet"),
}
HIGHLIGHT, FONT_DISPLAY, FONT_BODY, WGHT_DISPLAY, UPPER, TRACKING = YELLOW, FONT, FONT, 900, True, 7
RADIUS, SHADOW, GRID, ENTRANCE, POP_DUR, TRANSITION = 36, "none", "lines", "pop", 0.22, "fade"


def set_theme(name):
    g = globals()
    th = THEMES.get(name, TECH)
    base = STYLE_DEFAULTS["paper" if th.get("PAPER") else "tech"]
    for k, v in {**base, **th}.items():
        if k == "name":
            continue
        if k in ("FONT_DISPLAY", "FONT_BODY"):
            v = os.path.join(ROOT, "fonts", os.path.basename(str(v)))
            v = v if os.path.exists(v) else FONT
        if k == "HIGHLIGHT" or (isinstance(v, list) and k not in ("name",)):
            v = tuple(v) if isinstance(v, (list, tuple)) else v
        g[k] = v
    g["YELLOW"] = g["HIGHLIGHT"]
    g["LOOK"] = th["name"]
    for fn in (_text_img, _card_img, background, glow, bg_photo, grain, dots, font):
        fn.cache_clear()


LOOK = "tech"
VIS_TOP, VIS_BOT = 300, 1250      # visual area of the stage; header ~200, source ~1260, captions ~1600 (on 9:16)
SOURCE_Y, CAPTION_Y = 1262, 1600
STAGE_CROP = (VIS_TOP - 60, VIS_BOT + 60)   # the part of the stage shown on a 16:9 canvas


def set_canvas(aspect):
    """Switch every canvas-dependent position for "9:16" (1080x1920) or "16:9" (1920x1080)."""
    g = globals()
    if aspect == "16:9":
        g.update(W=1920, H=1080, CX=960, HEADER_Y=62, SOURCE_Y=902, CAPTION_Y=984, CAP_SIZE=56, LANDSCAPE=True,
                 STAGE_K=0.78, STAGE_TOP=104, STAGE_CROP=(VIS_TOP - 20, VIS_BOT + 20))
    else:
        g.update(W=1080, H=1920, CX=540, HEADER_Y=205, SOURCE_Y=1262, CAPTION_Y=1600, CAP_SIZE=66, LANDSCAPE=False,
                 STAGE_K=1.0, STAGE_TOP=0, STAGE_CROP=(VIS_TOP - 60, VIS_BOT + 60))
    g["PARTS"] = particles()
    for fn in (background, glow, bg_photo, grain, dots):
        fn.cache_clear()
HEIGHTS = {"label": 64, "title": 150, "hero": 210, "text": 110, "stat_card": 400, "counter": 250, "bars": 120,
           "checks": 100, "strike": 270, "price": 230, "cta": 560}
GAP = 34


# ---------- easing ----------
LANG = "en"


def up(text):
    """Upper-case with Turkish rules (i -> İ, ı -> I) when the video is Turkish."""
    if not UPPER:
        return text
    if LANG == "tr":
        text = text.replace("i", "İ").replace("ı", "I")
    return text.upper()


def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def out_cubic(p):
    return 1 - (1 - clamp(p)) ** 3


def out_back(p, s=1.70158):
    p = clamp(p) - 1
    return 1 + (s + 1) * p ** 3 + s * p ** 2


# ---------- text sprites ----------
@functools.lru_cache(maxsize=None)
def font(size, wght=800, path=None):
    f = ImageFont.truetype(path or FONT, size)
    try:
        f.set_variation_by_axes([wght])
    except (OSError, AttributeError):   # a static font (Anton, DM Serif ...) has one weight
        pass
    return f


def face(wght):
    """Big type (weight >= 850) uses the style's display font, everything else its body font."""
    return FONT_DISPLAY if wght >= 850 else FONT_BODY


def text_img(text, size, wght=800, fill=None, stroke=0, track=0):
    return _text_img(text, size, wght, fill or TEXT, stroke, track, STROKE, face(wght))


@functools.lru_cache(maxsize=4096)
def _text_img(text, size, wght, fill, stroke, track, stroke_fill, path=None):
    """Tight RGBA sprite of one line of text; `track` = extra letter spacing in px."""
    f = font(size, WGHT_DISPLAY if wght >= 850 else wght, path)
    pad = stroke + 6
    if track:
        widths = [f.getlength(ch) + track for ch in text]
        w = int(sum(widths)) + 2 * pad
    else:
        w = int(f.getlength(text)) + 2 * pad
    h = int(size * 1.35) + 2 * pad
    img = Image.new("RGBA", (max(w, 2), h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if track:
        x = pad
        for ch, cw in zip(text, widths):
            d.text((x, pad), ch, font=f, fill=fill, stroke_width=stroke, stroke_fill=stroke_fill + (255,))
            x += cw
    else:
        d.text((pad, pad), text, font=f, fill=fill, stroke_width=stroke, stroke_fill=stroke_fill + (255,))
    bbox = img.getbbox()
    return img.crop(bbox) if bbox else img


def fit_text(text, size, maxw, wght=800, **kw):
    """Largest size <= `size` whose sprite fits `maxw`."""
    while size > 24:
        spr = text_img(text, size, wght, **kw)
        if spr.width <= maxw:
            return spr
        size -= 4
    return text_img(text, 24, wght, **kw)


def blit(img, spr, cx, cy, alpha=1.0, scale=1.0, dy=0.0, rot=0.0):
    if alpha <= 0.01:
        return
    if rot:
        spr = spr.rotate(rot, resample=Image.BICUBIC, expand=True)
    if abs(scale - 1) > 1e-3:
        spr = spr.resize((max(1, int(spr.width * scale)), max(1, int(spr.height * scale))), Image.BILINEAR)
    a = spr.getchannel("A")
    if alpha < 1:
        a = a.point(lambda v: int(v * alpha))
    x, y = int(cx - spr.width / 2), int(cy + dy - spr.height / 2)
    if img.mode == "RGBA":   # the 16:9 stage layer: composite so soft edges keep their alpha
        layer = spr.copy()
        layer.putalpha(a)
        sx, sy = max(0, -x), max(0, -y)
        if sx < layer.width and sy < layer.height and x + layer.width > 0 and y + layer.height > 0:
            img.alpha_composite(layer, (max(0, x), max(0, y)), (sx, sy))
        return
    img.paste(spr, (x, y), a)


def pop(t, t0, dur=None):
    """(alpha, scale, dy) of the shared entrance (style token ENTRANCE): pop = fade in, scale 0.85->1 with ease-out-back,
    rise 40 px; slap = scale 1.15 -> 1 on power3.out (no overshoot), fast fade, no rise; rise = slide up; fade = fade."""
    d = POP_DUR if dur is None else max(dur, POP_DUR if ENTRANCE == "slap" else 0)
    p = (t - t0) / max(d, 0.05)
    if p <= 0:
        return 0.0, 1.0, 0.0
    if ENTRANCE == "slap":
        return clamp(p * 3), 1.15 - 0.15 * out_cubic(p), 0.0
    if ENTRANCE == "rise":
        return clamp(p * 1.5), 1.0, (1 - out_cubic(p)) * 70
    if ENTRANCE == "fade":
        return clamp(p), 1.0, 0.0
    return clamp(p), 0.85 + 0.15 * out_back(p), (1 - out_cubic(p)) * 40


def card_img(w, h, border=None, bw=3, r=36):
    return _card_img(w, h, border or TEAL, bw, min(r, RADIUS) if not PAPER else RADIUS, LOOK)


@functools.lru_cache(maxsize=256)
def _card_img(w, h, border, bw, r, look):
    if PAPER:  # ink-outlined paper card with a hard offset shadow (no blur)
        img = Image.new("RGBA", (w + 12, h + 14), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        if SHADOW != "none":
            d.rounded_rectangle((10, 12, w + 9, h + 11), r, fill=TEXT + (44,))
        d.rounded_rectangle((0, 0, w - 1, h - 1), r, fill=CARD + (255,), outline=TEXT + (255,), width=4)
        return img
    pad = 14 if SHADOW != "none" else 0
    img = Image.new("RGBA", (w + pad, h + pad), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if SHADOW == "hard":
        d.rounded_rectangle((pad, pad, w + pad - 1, h + pad - 1), r, fill=(0, 0, 0, 90))
    elif SHADOW == "soft":
        sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle((pad // 2, pad, w + pad // 2 - 1, h + pad - 1), r, fill=(0, 0, 0, 110))
        img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(10)))
    d.rounded_rectangle((0, 0, w - 1, h - 1), r, fill=(255, 255, 255, 15), outline=border + (255,), width=bw)
    return img


def tilt(k):
    """Editorial imperfection: paper cards settle crooked by +-0.4-0.8 degrees (deterministic, never straight)."""
    return (0.5 + 0.1 * (k % 3)) * (1 if k % 2 else -1) if PAPER else 0.0


def swipe(img, cx, cy, w, h, t, t0, color=None):
    """Highlighter swipe: a yellow block behind a key word grows left to right (0.45 s power2.out)."""
    p = clamp((t - t0) / 0.45)
    p = 1 - (1 - p) ** 2
    if p > 0:
        ImageDraw.Draw(img).rectangle((cx - w / 2, cy - h / 2, cx - w / 2 + w * p, cy + h / 2), fill=color or YELLOW)


def compose(base, parts):
    """Stack sprites centred inside `base` (list of (sprite, cy_offset))."""
    for spr, cy in parts:
        base.alpha_composite(spr, (int((base.width - spr.width) / 2), int(cy - spr.height / 2)))
    return base


# ---------- background ----------
@functools.lru_cache(maxsize=1)
def grain():
    """Paper grain: deterministic noise, drawn once."""
    import numpy as np
    n = np.random.default_rng(11).integers(0, 255, (H, W), dtype=np.uint8)
    img = Image.merge("RGBA", [Image.fromarray(n)] * 3 + [Image.fromarray((n // 14).astype("uint8"))])
    return img


@functools.lru_cache(maxsize=1)
def dots():
    """Halftone dot field (two sizes), a little larger than the frame so it can pan."""
    img = Image.new("RGBA", (W + 60, H + 60), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for y in range(0, H + 60, 30):
        for x in range(0, W + 60, 30):
            r = 2 if (x // 30 + y // 30) % 2 else 3
            d.ellipse((x - r, y - r, x + r, y + r), fill=TEXT + (26,))
    return img


@functools.lru_cache(maxsize=1)
def background():
    if PAPER:
        img = Image.new("RGB", (W, H), BG_TOP)
        if GRID == "lines":   # e.g. a cream page with thin coloured grid lines
            g = ImageDraw.Draw(img)
            for x in range(0, W, 90):
                g.line((x, 0, x, H), fill=tuple((a * 5 + b) // 6 for a, b in zip(BG_TOP, TEAL)))
            for y in range(0, H, 90):
                g.line((0, y, W, y), fill=tuple((a * 5 + b) // 6 for a, b in zip(BG_TOP, TEAL)))
        return img
    img = Image.new("RGB", (W, H))
    px = img.load()
    rows = [tuple(int(BG_TOP[i] + (BG_BOT[i] - BG_TOP[i]) * y / (H - 1)) for i in range(3)) for y in range(H)]
    d = ImageDraw.Draw(img)
    for y, c in enumerate(rows):
        d.line((0, y, W, y), fill=c)
    if GRID == "lines":
        grid = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        g = ImageDraw.Draw(grid)
        for x in range(0, W, 90):
            g.line((x, 0, x, H), fill=(120, 160, 220, 14))
        for y in range(0, H, 90):
            g.line((0, y, W, y), fill=(120, 160, 220, 14))
        img.paste(grid, (0, 0), grid)
    return img


@functools.lru_cache(maxsize=1)
def glow():
    if PAPER:
        return Image.new("RGBA", (2, 2), (0, 0, 0, 0))
    s = 900
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse((250, 250, 650, 650), fill=TEAL + (70,))
    return img.filter(ImageFilter.GaussianBlur(120))


def particles():
    return [(random.Random(i + 300).random() * W, random.Random(i).random() * H, random.Random(i + 99).uniform(8, 26),
             random.Random(i + 5).choice([2, 2, 3, 4])) for i in range(40)]


PARTS = particles()


def draw_background(t):
    img = background().copy()
    if PAPER:  # nothing glows: dot field pans in 12 fps steps, then the paper grain
        if GRID == "dots":
            o = int(t * 12) * 0.75 % 30
            d = dots()
            img.paste(d, (-int(o) - 15, -int(o) - 15), d)
        g = grain()
        img.paste(g, (0, 0), g)
        return img
    blit(img, glow(), W / 2 + 140 * math.sin(t * 0.35), H * 0.365 + 90 * math.cos(t * 0.27), 0.9)
    d = ImageDraw.Draw(img)
    for x0, y0, v, r in PARTS:
        x, y = (x0 + 6 * math.sin(t * 0.4 + y0)) % W, (y0 - v * t) % H
        d.ellipse((x - r, y - r, x + r, y + r), fill=(70, 120, 150))
    return img


# ---------- elements ----------
def el_height(el):
    t = el["type"]
    if t == "checks":
        return HEIGHTS["checks"] * len(el["items"])
    if t == "bars":
        return 60 + HEIGHTS["bars"] * len(el["items"])
    return HEIGHTS.get(t, 100)


def layout(scene):
    """Stack the scene's elements vertically, centred in the visual area; the layout never changes as they appear."""
    stack = [e for e in scene["elements"] if e["type"] not in ("source", "orb")]
    total = sum(el_height(e) for e in stack) + GAP * max(0, len(stack) - 1)
    y = max(VIS_TOP, (VIS_TOP + VIS_BOT) / 2 - total / 2)
    for e in stack:
        h = el_height(e)
        e["_cy"], e["_h"] = y + h / 2, h
        y += h + GAP


def fmt_num(v, el):
    dec = int(el.get("decimals", 0))
    s = f"{v:,.{dec}f}" if dec else f"{round(v):,}"
    return f"{el.get('prefix', '')}{s}{el.get('suffix', '')}"


def draw_element(img, el, t, fade):
    t0 = el["at"]
    if t < t0:
        return
    a, sc, dy = pop(t, t0)
    a *= fade
    cy, ty = el.get("_cy", 0), el["type"]
    if ty == "label":
        lab = text_img(up(el["text"]), 40, 800, TEXT if PAPER else TEAL, track=TRACKING)
        if PAPER:
            swipe(img, 540, cy, lab.width + 36, 58, t, t0)
        blit(img, lab, 540, cy, a, sc, dy)
    elif ty == "title":
        blit(img, fit_text(el["text"], 150, 940, 900), 540, cy, a, sc, dy)
    elif ty == "text":
        lines = el["text"].split("\n")
        for i, ln in enumerate(lines):
            blit(img, fit_text(ln, 52, 900, 600, fill=MUTED), 540, cy + (i - (len(lines) - 1) / 2) * 62, a, sc, dy)
    elif ty == "hero":
        txt = up(el["text"])
        size = 210
        while font(size, 900).getlength(txt) > 960 and size > 60:
            size -= 6
        gap, st = 4, float(el.get("stagger", 0.07))
        widths = [font(size, 900).getlength(ch) for ch in txt]
        x = 540 - (sum(widths) + gap * (len(txt) - 1)) / 2
        if PAPER:  # ink type on a yellow highlighter block (the one emphasis of the scene)
            swipe(img, 540, cy + size * 0.04, sum(widths) + gap * len(txt) + 40, size * 0.78, t, t0)
        for i, (ch, cw) in enumerate(zip(txt, widths)):
            if ch != " ":
                la, ls, ld = pop(t, t0 + st * i)
                blit(img, text_img(ch, size, 900, HERO), x + cw / 2, cy, la * fade, ls, ld)
            x += cw + gap
    elif ty == "stat_card":
        big = fit_text(el["big"], 190, 700, 900, fill=TEXT if PAPER else TEAL)
        cap = el.get("caption") or []
        cap = [cap] if isinstance(cap, str) else cap
        card = card_img(860, 400).copy()
        parts = [(big, 150)] + [(text_img(c, 44, 600, TEXT), 285 + i * 52) for i, c in enumerate(cap[:2])]
        if PAPER:
            hl = Image.new("RGBA", (big.width + 40, int(big.height * 0.7)), YELLOW + (255,))
            parts.insert(0, (hl, 160))
        blit(img, compose(card, parts), 540, cy, a, sc, dy, tilt(0))
    elif ty == "counter":
        p = out_cubic((t - t0) / 0.6)
        v = el.get("from", 0) + (el["to"] - el.get("from", 0)) * p
        spr = fit_text(fmt_num(v, el), 200, 860, 900, fill=COUNTER)
        blit(img, spr, 540, cy - (20 if el.get("caption") else 0), a, sc, dy)
        if el.get("caption"):
            blit(img, text_img(el["caption"], 42, 600, MUTED), 540, cy + 95, a, sc, dy)
    elif ty == "bars":
        items = el["items"]
        top = cy - el["_h"] / 2 + 30
        for i, it in enumerate(items):
            ia, isc, idy = pop(t, t0 + 0.12 * i)
            y = top + 60 + i * HEIGHTS["bars"]
            lab = text_img(it["label"], 40, 700, TEXT if i == len(items) - 1 else MUTED)
            blit(img, lab, 100 + lab.width / 2, y, ia * fade, 1, idy * 0.3)
            frac = clamp(float(it["value"]) / 100.0)
            grow = out_cubic((t - t0 - 0.12 * i) / 0.9)
            bar = Image.new("RGBA", (880, 36), (0, 0, 0, 0))
            bd = ImageDraw.Draw(bar)
            bd.rounded_rectangle((0, 0, 879, 35), 18, fill=TRACK)
            wbar = max(36, int(880 * frac * grow))
            bd.rounded_rectangle((0, 0, wbar - 1, 35), 18, fill=(TEAL if i == len(items) - 1 else OLD) + (255,))
            blit(img, bar, 540, y + 50, ia * fade)
            if it.get("display"):
                v = text_img(str(it["display"]), 38, 800, TEXT)
                blit(img, v, 980 - v.width / 2, y, ia * fade)
    elif ty == "checks":
        for i, it in enumerate(el["items"]):
            ia, isc, idy = pop(t, t0 + 0.35 * i)
            y = cy - el["_h"] / 2 + HEIGHTS["checks"] * (i + 0.5)
            row = card_img(900, 84, TEAL, 2, 28).copy()
            ImageDraw.Draw(row).ellipse((22, 20, 66, 64), fill=TEAL + (255,))
            dd = ImageDraw.Draw(row)
            prog = clamp((t - t0 - 0.35 * i - 0.15) / 0.25)
            if prog > 0:  # two-segment stroke draw
                k1 = min(prog * 2, 1.0)
                dd.line(((33, 43), (33 + 9 * k1, 43 + 9 * k1)), fill=BG_TOP + (255,), width=5)
                if prog > 0.5:
                    k2 = (prog - 0.5) * 2
                    dd.line(((42, 52), (42 + 14 * k2, 52 - 20 * k2)), fill=BG_TOP + (255,), width=5)
            lab = fit_text(it, 38, 760, 700)
            row.alpha_composite(lab, (90, int(42 - lab.height / 2)))
            blit(img, row, 540, y, ia * fade, isc, idy, tilt(i + 1))
    elif ty == "strike":
        old = text_img(el["old"], 96, 800, MUTED)
        new = text_img(el["new"], 120, 900, TEAL)
        blit(img, old, 540, cy - 85, a, sc, dy)
        d = ImageDraw.Draw(img)
        k = out_cubic((t - t0 - 0.3) / 0.3)
        if k > 0:
            half = old.width / 2 * k
            y = int(cy - 85 + dy)
            d.line((540 - old.width / 2 - 10, y, 540 - old.width / 2 - 10 + (old.width + 20) * k, y), fill=ORANGE, width=9)
        na, ns, nd = pop(t, t0 + 0.7)
        blit(img, text_img("↓", 70, 800, MUTED), 540, cy - 5, na * fade, ns, nd)
        blit(img, new, 540, cy + 85, na * fade, ns, nd)
    elif ty == "price":
        items = el["items"][:2]
        for i, it in enumerate(items):
            ia, isc, idy = pop(t, t0 + 0.15 * i)
            x = 540 + (i - (len(items) - 1) / 2) * 460
            card = card_img(420, 230, PRICE2 if i else TEAL)
            c = card.copy()
            val = fit_text(it["value"], 100, 360, 900, fill=PRICE2 if i else TEAL)
            compose(c, [(val, 95), (text_img(it["label"], 38, 600, TEXT), 180)])
            blit(img, c, x, cy, ia * fade, isc, idy, tilt(i + 2))
    elif ty == "cta":
        q = up(el["question"]).split("\n")
        card = card_img(940, 360, TEAL, 3, 44).copy()
        parts = [(fit_text(ln, 96, 860, 900), 110 + i * 120) for i, ln in enumerate(q[:2])]
        blit(img, compose(card, parts), 540, cy - 80, a, sc, dy, tilt(5))
        sub = text_img(el.get("sub", "Follow for more"), 54, 800, TEXT if PAPER else TEAL)
        # pulse ring: outline grows and fades on a 1.1 s loop
        phase = 0.0 if PAPER else ((t - t0) % 1.1) / 1.1
        pad = 14 + 60 * phase
        ring = Image.new("RGBA", (int(sub.width + 140 + 2 * pad), int(120 + 2 * pad)), (0, 0, 0, 0))
        ImageDraw.Draw(ring).rounded_rectangle((0, 0, ring.width - 1, ring.height - 1), 60,
                                               outline=TEAL + (int(255 * (1 - phase)),), width=4)
        pa, ps, pd = pop(t, t0 + 0.5)
        pill = Image.new("RGBA", (sub.width + 140, 120), (0, 0, 0, 0))
        ImageDraw.Draw(pill).rounded_rectangle((0, 0, pill.width - 1, 119), 60, fill=(YELLOW + (255,)) if PAPER else TEAL + (40,),
                                               outline=(TEXT if PAPER else TEAL) + (255,), width=4 if PAPER else 3)
        pill.alpha_composite(sub, (70, int(60 - sub.height / 2)))
        blit(img, pill, 540, cy + 200, pa * fade, ps, pd)
        if not PAPER:
            blit(img, ring, 540, cy + 200, pa * fade * (1 - phase))


def draw_source(img, el, t, fade):
    if t >= el["at"]:
        a, _, _ = pop(t, el["at"], 0.3)
        blit(img, fit_text(el["text"], 36, 900 if not LANDSCAPE else 1300, 600, fill=SRC), CX, SOURCE_Y, a * fade)


def draw_header(img, text, t):
    a, sc, dy = pop(t, -0.3, 0.3)
    spr = text_img(up(text), 30, 800, TEXT, track=max(0, TRACKING - 2))
    pill = Image.new("RGBA", (spr.width + 100, 66), (0, 0, 0, 0))
    d = ImageDraw.Draw(pill)
    if PAPER:
        d.rounded_rectangle((0, 0, pill.width - 1, 65), 8, fill=CARD + (255,), outline=TEXT + (255,), width=3)
        d.rectangle((24, 23, 42, 41), fill=YELLOW + (255,), outline=TEXT + (255,), width=2)
    else:
        d.rounded_rectangle((0, 0, pill.width - 1, 65), 33, fill=(255, 255, 255, 18), outline=TEAL + (200,), width=2)
        d.ellipse((26, 25, 42, 41), fill=TEAL + (255,))
    pill.alpha_composite(spr, (60, int(33 - spr.height / 2)))
    blit(img, pill, CX, HEADER_Y, a, sc, dy)


# ---------- captions ----------
def chunk_words(words):
    """Chunks of <= 3 words / <= 16 chars, also broken after , . : ? !"""
    chunks, cur = [], []
    for w in words:
        txt = w[0]
        if cur and (len(cur) >= 3 or len(" ".join(x[0] for x in cur + [w])) > 16):
            chunks.append(cur)
            cur = []
        cur.append(w)
        if txt[-1:] in ",.:?!":
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    return chunks


def draw_captions(img, chunks, t):
    ci = None
    for i, ch in enumerate(chunks):
        if ch[0][1] <= t:
            ci = i
    if ci is None:
        return
    ch = chunks[ci]
    end = chunks[ci + 1][0][1] if ci + 1 < len(chunks) else ch[-1][2] + 0.5
    if t >= end:
        return
    active = max((i for i, w in enumerate(ch) if w[1] <= t), default=0)
    sprs = []
    for i, w in enumerate(ch):
        on = i == active
        s = text_img(up(w[0]), CAP_SIZE, 900, TEXT if PAPER else (TEAL if on else TEXT), stroke=6)
        sprs.append(s.resize((int(s.width * 1.04), int(s.height * 1.04)), Image.BILINEAR) if on else s)
    total = sum(s.width for s in sprs) + 12 * (len(sprs) - 1)
    x = CX - total / 2
    hh = CAP_SIZE * 2 / 3
    for i, s in enumerate(sprs):
        if PAPER and i == active:  # the active word sits on a yellow highlighter block
            ImageDraw.Draw(img).rectangle((x - 8, CAPTION_Y - hh, x + s.width + 8, CAPTION_Y + hh), fill=YELLOW)
        blit(img, s, x + s.width / 2, CAPTION_Y)
        x += s.width + 12


# ---------- scene backgrounds (photo / clip behind the graphics, darkened) ----------
DARK = 0.62          # share of navy mixed over the picture so text and cards stay readable
READERS = {}         # scene id -> ClipReader (frames are requested in order while rendering a video)
FRAME_FPS = FPS


@functools.lru_cache(maxsize=6)
def bg_photo(path):
    im = Image.open(os.path.join(ROOT, path)).convert("RGB")
    k = max(W * 1.25 / im.width, H * 1.25 / im.height)
    im = im.resize((int(im.width * k) + 1, int(im.height * k) + 1), Image.BILINEAR)
    return Image.blend(im, Image.new("RGB", im.size, BG_TOP), DARK)


def photo_frame(path, p):
    """Slow push-in: the crop window shrinks from 1.25x to ~1.07x of the canvas as the scene progresses."""
    im = bg_photo(path)
    z = 1.25 - 0.18 * clamp(p)
    cw, ch = W * z, H * z
    x, y = (im.width - cw) / 2, (im.height - ch) / 2
    return im.crop((int(x), int(y), int(x + cw), int(y + ch))).resize((W, H), Image.BILINEAR)


class ClipReader:
    """Sequential RGB frames of a library clip (muted, looped if shorter than the scene), cover-cropped to the canvas."""

    def __init__(self, path, start):
        vf = f"fps={FRAME_FPS},scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}"
        self.proc = subprocess.Popen([FFMPEG, "-v", "error", "-stream_loop", "-1", "-ss", str(start), "-i",
                                      os.path.join(ROOT, path), "-an", "-vf", vf, "-f", "rawvideo", "-pix_fmt", "rgb24",
                                      "-"], stdout=subprocess.PIPE, stdin=subprocess.DEVNULL)
        self.last = Image.new("RGB", (W, H), BG_TOP)

    def next(self):
        raw = self.proc.stdout.read(W * H * 3)
        if len(raw) == W * H * 3:
            self.last = Image.blend(Image.frombytes("RGB", (W, H), raw), Image.new("RGB", (W, H), BG_TOP), DARK)
        return self.last

    def close(self):
        self.proc.kill()
        self.proc.wait()


def clip_still(path, t):
    raw = subprocess.run([FFMPEG, "-v", "error", "-ss", f"{t:.2f}", "-i", os.path.join(ROOT, path), "-frames:v", "1",
                          "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}", "-f", "rawvideo",
                          "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    if len(raw) != W * H * 3:
        return None
    return Image.blend(Image.frombytes("RGB", (W, H), raw), Image.new("RGB", (W, H), BG_TOP), DARK)


def with_background(img, sc, t, last, still):
    bg = sc.get("bg")
    if not bg:
        return img
    a = clamp((t - sc["start"]) / 0.3) * (1.0 if last else clamp((sc["end"] - t) / 0.3))
    if a <= 0:
        return img
    if bg["type"] == "image":
        fr = photo_frame(bg["file"], (t - sc["start"]) / max(sc["end"] - sc["start"], 0.1))
    elif still:
        fr = clip_still(bg["file"], bg.get("in", 0) + max(0.0, t - sc["start"]))
    else:
        if sc["id"] not in READERS:
            READERS[sc["id"]] = ClipReader(bg["file"], bg.get("in", 0))
        fr = READERS[sc["id"]].next()
    return Image.blend(img, fr, a) if fr is not None else img


# ---------- frame + video ----------
def scene_at(scenes, t):
    for i, s in enumerate(scenes):
        if s["start"] <= t < s["end"]:
            return i, s
    return len(scenes) - 1, scenes[-1]


def make_frame(spec, chunks, t, still=False):
    img = draw_background(t)
    i, sc = scene_at(spec["scenes"], t)
    last = i == len(spec["scenes"]) - 1
    img = with_background(img, sc, t, last, still)
    draw_header(img, spec.get("header", ""), t)
    fade = 1.0 if (last or TRANSITION != "fade") else clamp((sc["end"] - t) / 0.3)
    stage = Image.new("RGBA", (SW, STAGE_CROP[1]), (0, 0, 0, 0)) if LANDSCAPE else img
    for el in sc["elements"]:
        if el["type"] == "source":
            draw_source(img, el, t, fade)
        elif el["type"] != "orb":
            draw_element(stage, el, t, fade)
    if LANDSCAPE:
        place_stage(img, stage)
    if not sc.get("hide_captions"):
        draw_captions(img, chunks, t)
    if TRANSITION == "sheet":
        sheet_wipe(img, spec["scenes"], t)
    return img


def place_stage(img, stage):
    """16:9: the stage's visual band, scaled by STAGE_K, centred on the wide canvas."""
    band = stage.crop((0, STAGE_CROP[0], SW, STAGE_CROP[1]))
    k = STAGE_K
    band = band.resize((int(band.width * k), int(band.height * k)), Image.BILINEAR)
    img.paste(band, (int(CX - band.width / 2), STAGE_TOP), band)


def sheet_wipe(img, scenes, t):
    """The only transition of the paper look: a full-width sheet sweeps across (0.4 s) and covers the cut on both
    sides. Ease in-out so the seam is fully covered at its midpoint."""
    for sc in scenes[:-1]:
        p = (t - (sc["end"] - 0.2)) / 0.4
        if 0 < p < 1:
            q = p * p * (3 - 2 * p)
            x = -1.15 * W + q * 2.3 * W
            d = ImageDraw.Draw(img)
            d.rectangle((x, 0, x + W, H), fill=BG_TOP)
            d.rectangle((x - 8, 0, x, H), fill=TEXT)
            d.rectangle((x + W, 0, x + W + 8, H), fill=TEXT)
            return


def prepare(spec):
    for sc in spec["scenes"]:
        layout(sc)
    shift = spec.get("voice_start", (spec.get("voice") or {}).get("start", 0))
    words = [[w, s + shift, e + shift] for w, s, e in spec["words"]]
    return chunk_words(words)


def main(path, preview=False, stills=None):
    spec = json.load(open(path))
    global LANG
    LANG = spec.get("lang", "en")
    set_canvas(spec.get("aspect", "9:16"))
    if spec.get("theme"):  # custom look extracted from the creator's references (factory/styles.py)
        t = {k: tuple(v) if isinstance(v, list) else v for k, v in spec["theme"].items()}
        THEMES[spec["look"]] = {"name": spec["look"], **t}
    set_theme(spec.get("look", "tech"))
    name = spec["name"]
    chunks = prepare(spec)
    total = spec["duration"]
    if stills:
        out = os.path.join(ROOT, "work", "explainer", name)
        os.makedirs(out, exist_ok=True)
        paths = []
        for s in stills:
            p = os.path.join(out, f"still_{s:05.2f}.png")
            make_frame(spec, chunks, s, still=True).save(p)
            paths.append(p)
        return paths
    out_dir = os.path.join(ROOT, "work", "preview") if preview else os.path.join(ROOT, "out", name)
    os.makedirs(out_dir, exist_ok=True)
    dst = os.path.join(out_dir, f"{name}.mp4")
    global FRAME_FPS
    fps = FRAME_FPS = 15 if preview else FPS
    size = (W // 2, H // 2) if preview else (W, H)
    cmd = [FFMPEG, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{size[0]}x{size[1]}",
           "-r", str(fps), "-i", "-"]
    inputs, chain, mix = 1, [], None
    vo = spec.get("voice")
    if vo:
        ms = int(vo.get("start", 0) * 1000)
        cmd += ["-i", os.path.join(ROOT, vo["file"])]
        chain.append(f"[{inputs}:a]aformat=sample_rates=48000:channel_layouts=stereo,adelay={ms}|{ms},apad,"
                     f"atrim=0:{total:.3f}[vo]")
        mix, inputs = "[vo]", inputs + 1
    if spec.get("music"):
        mu = spec["music"]
        cmd += ["-i", os.path.join(ROOT, mu["file"])]
        chain.append(f"[{inputs}:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={mu.get('db', -20)}dB,apad,"
                     f"atrim=0:{total:.3f},afade=t=in:d=0.5,afade=t=out:st={max(0, total - 1.5):.3f}:d=1.5[mus]")
        chain.append((f"{mix}[mus]amix=inputs=2:normalize=0[mx]" if mix else "[mus]anull[mx]"))
        mix = "[mx]"
    if mix:
        chain.append(f"{mix}loudnorm=I=-14:TP=-1.5:LRA=11,atrim=0:{total:.3f}[a]")
        cmd += ["-filter_complex", ";".join(chain), "-map", "0:v", "-map", "[a]", "-c:a", "aac", "-b:a", "192k",
                "-ar", "48000"]
    cmd += ["-c:v", "libx264", "-preset", "ultrafast" if preview else "medium", "-crf", "28" if preview else "17",
            "-pix_fmt", "yuv420p", "-t", f"{total:.3f}", "-movflags", "+faststart", dst]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    n = int(round(total * fps))
    for k in range(n):
        img = make_frame(spec, chunks, k / fps)
        if preview:
            img = img.resize(size, Image.BILINEAR)
        proc.stdin.write(img.tobytes())
        if k % (fps * 5) == 0:
            print(f"frame {k}/{n}", flush=True)
    proc.stdin.close()
    for r in READERS.values():
        r.close()
    READERS.clear()
    if proc.wait():
        raise RuntimeError("ffmpeg failed")
    if spec.get("post") and not preview:
        sys.path.insert(0, os.path.join(ROOT, "bin"))
        import cinecut
        cinecut.write_caption(os.path.join(out_dir, "caption.txt"), spec["post"])
    print(f"{dst}  ({total:.2f}s)")
    return dst, total


if __name__ == "__main__":
    args = sys.argv[1:]
    stills = None
    if "--still" in args:
        i = args.index("--still")
        stills = [float(x) for x in args[i + 1:]]
        args = args[:i]
    main(args[0], preview="--preview" in args, stills=stills)
