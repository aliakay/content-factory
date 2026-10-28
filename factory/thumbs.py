"""Cover / thumbnail candidates for a finished video, drawn in code (Pillow), free and instant.

Frames are sampled from the final mp4 and scored (sharpness, colourfulness, brightness, not a transition); the best
three distinct moments become three designs in the channel's colours:
  A  big title on the left third over a darkened edge (YouTube classic)
  B  a bold bar with the title at the bottom
  C  one huge word in the middle, the rest of the title small
16:9 videos get 1280x720 YouTube thumbnails, 9:16 videos 1080x1920 covers (title kept inside the app's safe zone).
Files: out/<name>/thumb_1.jpg ... thumb_3.jpg (+ thumbs.json with the chosen times).
"""
import json, os, re, subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from .config import FFMPEG, ROOT

FONT = os.path.join(ROOT, "fonts", "InterTight[wght].ttf")
ANTON = os.path.join(ROOT, "fonts", "Anton-Regular.ttf")


def _font(path, size, wght=900):
    f = ImageFont.truetype(path, size)
    try:
        f.set_variation_by_axes([wght])
    except (OSError, AttributeError):
        pass
    return f


def frames(path, n=24):
    """[(t, PIL image)] sampled evenly (skipping the first and last 4 %)."""
    r = subprocess.run([FFMPEG.replace("ffmpeg", "ffprobe"), "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                        path], capture_output=True, text=True)
    try:
        dur = float(r.stdout.strip())
    except ValueError:
        return []
    out = []
    for k in range(n):
        t = dur * (0.04 + 0.92 * k / max(1, n - 1))
        raw = subprocess.run([FFMPEG, "-v", "error", "-ss", f"{t:.2f}", "-i", path, "-frames:v", "1", "-f", "image2pipe",
                              "-vcodec", "png", "-"], capture_output=True).stdout
        if raw:
            from io import BytesIO
            out.append((round(t, 2), Image.open(BytesIO(raw)).convert("RGB")))
    return out


def score(im):
    a = np.asarray(im.resize((160, int(160 * im.height / im.width))), dtype=np.float32) / 255
    g = a.mean(axis=2)
    sharp = float(np.abs(np.diff(g, axis=0)).mean() + np.abs(np.diff(g, axis=1)).mean())
    rg, yb = a[..., 0] - a[..., 1], (a[..., 0] + a[..., 1]) / 2 - a[..., 2]
    colour = float(np.sqrt(rg.std() ** 2 + yb.std() ** 2) + 0.3 * np.sqrt(rg.mean() ** 2 + yb.mean() ** 2))
    bright = float(g.mean())
    return sharp * 4 + colour * 2 - abs(bright - 0.5) * 1.2


def pick(cands, k=3, gap=1.5):
    ranked = sorted(cands, key=lambda c: -score(c[1]))
    out = []
    for t, im in ranked:
        if all(abs(t - u) >= gap for u, _ in out):
            out.append((t, im))
        if len(out) == k:
            break
    return out


def cover(im, size):
    w, h = size
    k = max(w / im.width, h / im.height)
    im = im.resize((int(im.width * k) + 1, int(im.height * k) + 1), Image.LANCZOS)
    x, y = (im.width - w) // 2, (im.height - h) // 2
    return im.crop((x, y, x + w, y + h))


def _hex(c):
    c = (c or "#FFD93D").lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def words_of(title, lang="en"):
    t = re.sub(r"\s+", " ", (title or "").strip())
    t = t.replace("i", "İ").replace("ı", "I") if lang == "tr" else t
    return t.upper().split(" ")


def wrap_lines(draw, words, font, maxw, maxlines=3):
    lines, cur = [], ""
    for w in words:
        nxt = (cur + " " + w).strip()
        if draw.textlength(nxt, font=font) <= maxw or not cur:
            cur = nxt
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines[:maxlines]


def design(im, title, variant, size, accent, logo=None, lang="en"):
    w, h = size
    base = cover(im, size)
    base = ImageEnhance.Contrast(ImageEnhance.Color(base).enhance(1.25)).enhance(1.08)
    img = base.convert("RGBA")
    d = ImageDraw.Draw(img)
    words = words_of(title, lang)[:7]
    tall = h > w
    if variant == "A":   # left third, darkened edge, accent on the longest word
        grad = Image.new("L", (w, 1))
        for x in range(w):
            grad.putpixel((x, 0), int(210 * max(0.0, 1 - x / (w * 0.62))))
        shade = Image.new("RGBA", size, (0, 0, 0, 255))
        shade.putalpha(grad.resize(size))
        img.alpha_composite(shade)
        size_px = int(h * (0.075 if tall else 0.15))
        f = _font(ANTON, size_px)
        lines = wrap_lines(d, words, f, w * (0.86 if tall else 0.52), 4)
        y = int(h * (0.16 if tall else 0.14))
        key = max(words, key=len)
        for ln in lines:
            x = int(w * 0.06)
            for wd in ln.split(" "):
                col = accent if wd == key else (255, 255, 255)
                d.text((x, y), wd, font=f, fill=col, stroke_width=max(4, size_px // 14), stroke_fill=(0, 0, 0))
                x += int(d.textlength(wd + " ", font=f))
            y += int(size_px * 1.05)
    elif variant == "B":   # bottom bar
        size_px = int(h * (0.05 if tall else 0.095))
        f = _font(FONT, size_px, 900)
        lines = wrap_lines(d, words, f, w * 0.88, 2)
        bar_h = int(size_px * 1.25 * len(lines) + size_px * 0.9)
        top = int(h * 0.62) if tall else h - bar_h - int(h * 0.06)
        d.rectangle((0, top, w, top + bar_h), fill=accent + (240,))
        y = top + int(size_px * 0.45)
        for ln in lines:
            d.text((int(w * 0.06), y), ln, font=f, fill=(15, 15, 18))
            y += int(size_px * 1.25)
    else:   # C: one huge word in the middle
        key = max(words, key=len)
        rest = " ".join(x for x in words if x != key)
        img.alpha_composite(Image.new("RGBA", size, (0, 0, 0, 90)))
        size_px = int(h * (0.13 if tall else 0.26))
        f = _font(ANTON, size_px)
        while d.textlength(key, font=f) > w * 0.9 and size_px > 40:
            size_px -= 8
            f = _font(ANTON, size_px)
        tw = d.textlength(key, font=f)
        cy = int(h * (0.36 if tall else 0.42))
        d.text(((w - tw) / 2, cy), key, font=f, fill=accent, stroke_width=max(5, size_px // 16), stroke_fill=(0, 0, 0))
        if rest:
            f2 = _font(FONT, int(size_px * 0.32), 850)
            tw2 = d.textlength(rest, font=f2)
            d.text(((w - tw2) / 2, cy - int(size_px * 0.45)), rest, font=f2, fill=(255, 255, 255), stroke_width=4, stroke_fill=(0, 0, 0))
    if logo and os.path.isfile(logo):
        lg = Image.open(logo).convert("RGBA")
        lw = int(min(w, h) * 0.12)
        lg = lg.resize((lw, max(1, int(lg.height * lw / lg.width))), Image.LANCZOS)
        img.alpha_composite(lg, (w - lw - int(w * 0.04), int(h * (0.1 if tall else 0.05))))
    return img.convert("RGB")


def make(video, out_dir, title, aspect="9:16", accent="#FFD93D", logo=None, lang="en"):
    """Three cover candidates next to the video. Returns the list of file paths."""
    size = (1280, 720) if aspect == "16:9" else (1080, 1920)
    best = pick(frames(video))
    if not best:
        return []
    acc = _hex(accent)
    paths, meta = [], []
    for i, (v, (t, im)) in enumerate(zip("ABC", best)):
        p = os.path.join(out_dir, f"thumb_{i + 1}.jpg")
        design(im, title, v, size, acc, logo, lang).save(p, quality=90)
        paths.append(p)
        meta.append({"file": os.path.basename(p), "t": t, "variant": v})
    json.dump(meta, open(os.path.join(out_dir, "thumbs.json"), "w"))
    return paths
