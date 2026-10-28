"""Review sheets: many stills tiled into one labelled picture, so a reviewer (Claude reading images, or the creator)
sees the shape of the whole piece at once: scene starts and middles, strips across every cut (-0.2 / 0 / +0.2 s) and
a phone-width copy (360 px) to judge what can really be read on a phone."""
import os

from PIL import Image, ImageDraw, ImageFont


def tile(paths, out, cols=6, width=300, labels=None, title=""):
    """Tile stills (any size, same aspect) into one sheet with a label under each. Returns out (or None)."""
    ims = []
    for p in paths:
        try:
            ims.append(Image.open(p).convert("RGB"))
        except OSError:
            continue
    if not ims:
        return None
    w = width
    h = int(ims[0].height * w / ims[0].width)
    rows = (len(ims) + cols - 1) // cols
    pad, lab = 8, 22
    top = 26 if title else 0
    sheet = Image.new("RGB", (cols * (w + pad) + pad, top + rows * (h + lab + pad) + pad), (16, 18, 24))
    d = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    if title:
        d.text((pad, 6), title, fill=(235, 235, 235), font=font)
    for i, im in enumerate(ims):
        x, y = pad + (i % cols) * (w + pad), top + pad + (i // cols) * (h + lab + pad)
        sheet.paste(im.resize((w, h)), (x, y))
        if labels and i < len(labels):
            d.text((x + 2, y + h + 4), str(labels[i])[:48], fill=(200, 200, 200), font=font)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    sheet.save(out, quality=88)
    return out


def review_times(scenes, step_cut=0.2):
    """(times, labels) for a review pass: each scene just after it starts and at its middle, plus a strip across every
    cut. scenes = [{id, start, end}]"""
    times, labels = [], []
    for i, sc in enumerate(scenes):
        dur = sc["end"] - sc["start"]
        for t, lab in ((sc["start"] + min(0.6, dur * 0.3), "start"), (sc["start"] + dur * 0.5, "mid")):
            times.append(round(t, 2))
            labels.append(f"{sc['id']} {lab} {t:.1f}s")
        if i:
            for dt in (-step_cut, 0.0, step_cut):
                t = max(0.0, sc["start"] + dt)
                times.append(round(t, 2))
                labels.append(f"cut {sc['id']} {dt:+.1f}")
    return times, labels


def by_time(paths):
    """{time: path} for shot_<t>.png files."""
    out = {}
    for p in paths:
        base = os.path.basename(p)
        try:
            out[round(float(base[5:-4]), 2)] = p
        except ValueError:
            pass
    return out
