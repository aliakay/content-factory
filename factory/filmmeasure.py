"""Measuring a reference picture, so the direction board can copy a look instead of guessing one.

The board's palette and light come from a style card or from a fixed scheme, so a reference picture the creator
liked is never read: the film ends up near the board's idea of the look rather than the picture's. This module
measures a still - the colours in it, how bright it is, how much of it is in shadow, where the light comes from -
and turns the measurement into the board's own knobs: a five-colour palette with one accent, a key light azimuth and
elevation, and a grade patch that a scene can be drawn against.

Everything here is deterministic. The picture is decoded small (96 px wide), the colours are clustered with a
seeded k-means (no random init), and the same file always gives the same numbers: a board that changes when the
same picture is measured twice is a board nobody trusts.
"""
import json

import numpy as np
from PIL import Image

SAMPLE_W = 96      # the picture is read at this width: cheap, and small enough to cluster in one pass
K = 5              # palette colours
ITER = 16          # k-means iterations
D65 = (0.95047, 1.0, 1.08883)     # the white point of the sRGB / CIELAB standard formula


# ---------------------------------------------------------------- colour

def _to_lab(rgb):
    """sRGB in 0..1 (..., 3) -> CIELAB (..., 3): the standard D65 formula, written out so no extra package is needed."""
    c = np.asarray(rgb, dtype=np.float64)
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = lin[..., 0], lin[..., 1], lin[..., 2]
    x = (0.4124564 * r + 0.3575761 * g + 0.1804375 * b) / D65[0]
    y = (0.2126729 * r + 0.7151522 * g + 0.0721750 * b) / D65[1]
    z = (0.0193339 * r + 0.1191920 * g + 0.9503041 * b) / D65[2]
    f = lambda t: np.where(t > 216 / 24389, np.cbrt(t), (841 / 108) * t + 4 / 29)
    fx, fy, fz = f(x), f(y), f(z)
    return np.stack([116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)], axis=-1)


def _to_rgb(lab):
    """CIELAB (..., 3) -> sRGB in 0..1 (..., 3); out-of-gamut colours are clipped."""
    L, a, b = lab[..., 0], lab[..., 1], lab[..., 2]
    fy = (L + 16) / 116
    fx = fy + a / 500
    fz = fy - b / 200
    back = lambda t: np.where(t ** 3 > 216 / 24389, t ** 3, (108 / 841) * (t - 4 / 29))
    x = D65[0] * back(fx)
    y = D65[1] * back(fy)
    z = D65[2] * back(fz)
    r = 3.2404542 * x - 1.5371385 * y - 0.4985314 * z
    g = -0.9692660 * x + 1.8760108 * y + 0.0415560 * z
    bb = 0.0556434 * x - 0.2040259 * y + 1.0572252 * z
    out = np.stack([r, g, bb], axis=-1)
    out = np.where(out <= 0.0031308, 12.92 * out, 1.055 * np.abs(out) ** (1 / 2.4) - 0.055)
    return np.clip(out, 0, 1)


def _hex(rgb):
    """One sRGB colour (0..1, three channels) -> '#rrggbb'."""
    return "#%02x%02x%02x" % tuple(int(round(float(c) * 255)) for c in rgb)


def _decode(path):
    """The picture as an RGB array (0..1), read small: at most 96 px wide, height in proportion."""
    with Image.open(path) as im:
        im = im.convert("RGB")
        if im.width > SAMPLE_W:
            h = max(1, int(round(im.height * SAMPLE_W / im.width)))
            im = im.resize((SAMPLE_W, h), Image.LANCZOS)
        return np.asarray(im, dtype=np.float64) / 255.0


# ---------------------------------------------------------------- clustering

def _seeds(lab, k):
    """The k-means seeds, in lightness order: the median-lightness pixel first, then the pixels that are furthest
    (in Lab) from the seeds already chosen. No random init, so the same picture always clusters the same way."""
    n = len(lab)
    order = np.argsort(lab[:, 0], kind="stable")
    seeds = [int(order[n // 2])]
    while len(seeds) < k:
        d = np.linalg.norm(lab[seeds][:, None, :] - lab[None, :, :], axis=2).min(axis=0)
        seeds.append(int(np.argmax(d)))          # ties go to the lowest index, which argmax does
    return seeds


def _split_empty(labels, lab, k):
    """Give an empty cluster half of the heaviest one (by lightness), so every slot of the palette means something."""
    counts = np.bincount(labels, minlength=k)
    for j in range(k):
        if counts[j]:
            continue
        big = int(np.argmax(counts))
        idx = np.where(labels == big)[0]
        if len(idx) < 2:
            break
        order = idx[np.argsort(lab[idx, 0], kind="stable")]
        labels[order[len(order) // 2:]] = j
        counts = np.bincount(labels, minlength=k)
    return labels


def _kmeans(lab, k=K, iters=ITER):
    """Lloyd's k-means in Lab with the deterministic seeds above. -> (labels, centroids, shares)."""
    labels = np.zeros(len(lab), dtype=int)
    cent = lab[_seeds(lab, k)].copy()
    for _ in range(iters):
        d = ((lab[:, None, :] - cent[None, :, :]) ** 2).sum(axis=2)
        labels = _split_empty(d.argmin(axis=1), lab, k)
        for j in range(k):
            m = labels == j
            if m.any():
                cent[j] = lab[m].mean(axis=0)
    shares = np.array([(labels == j).mean() for j in range(k)])
    return labels, cent, shares


# ---------------------------------------------------------------- the measurement

def _corner_centre(L):
    """(corner mean, centre mean) of the lightness: the corners are the four corners, the centre the middle."""
    h, w = L.shape
    cw, ch = max(1, int(round(w * 0.15))), max(1, int(round(h * 0.15)))
    corners = np.concatenate([L[:ch, :cw].ravel(), L[:ch, -cw:].ravel(),
                              L[-ch:, :cw].ravel(), L[-ch:, -cw:].ravel()])
    mw, mh = max(1, int(round(w * 0.30))), max(1, int(round(h * 0.30)))
    centre = L[(h - mh) // 2:(h - mh) // 2 + mh, (w - mw) // 2:(w - mw) // 2 + mw]
    return float(corners.mean()), float(centre.mean())


def _key_light(L):
    """Where the key light sits, from the brightest 2 % of the picture: 180 is frontal, 90 the frame right,
    270 the frame left; the height of that patch sets the elevation of the light."""
    h, w = L.shape
    k = max(1, int(round(L.size * 0.02)))
    cut = float(np.sort(L, axis=None)[-k])                # the value of the 98th percentile of the lightness
    ys, xs = np.nonzero(L >= cut)                         # every pixel tied with it counts too, or a flat frame
    x = (float(xs.mean()) / max(1, w - 1)) * 2 - 1        # -1 at the left edge, +1 at the right
    y = (float(ys.mean()) / max(1, h - 1)) * 2 - 1        # -1 at the top, +1 at the bottom
    azimuth = int(round(180 - 90 * x))
    elevation = int(round(45 - 30 * y))                    # a bright patch high in the frame is a high light
    return {"azimuth_deg": azimuth, "elevation_deg": max(10, min(70, elevation))}


def measure(path):
    """Measure a picture: its palette, its accent, its light and how it is graded.

    -> {"palette": five hex colours dark to light, "accent", "shares", "l_p5", "l_p50", "l_p95", "contrast",
        "dark_share", "bright_share", "chroma", "warmth", "vignette", "key"}"""
    rgb = _decode(path)
    lab = _to_lab(rgb)
    flat = lab.reshape(-1, 3)
    L = lab[..., 0]
    labels, cent, shares = _kmeans(flat)

    # The palette is listed dark to light, so a board can read it as ground -> ink -> accent.
    order = np.argsort(cent[:, 0], kind="stable")
    cent, shares = cent[order], shares[order]
    remap = np.empty(K, dtype=int)
    remap[order] = np.arange(K)
    labels = remap[labels]
    palette = [_hex(c) for c in _to_rgb(cent)]

    # The accent is the most colourful cluster; a small one is boosted, because a colour that only shows up in a
    # corner of the frame is usually the point of the picture.
    a_flat, b_flat = flat[:, 1], flat[:, 2]
    chroma_px = np.sqrt(a_flat * a_flat + b_flat * b_flat)
    best, best_score = 0, -1.0
    for j in range(len(shares)):
        m = labels == j
        c = float(chroma_px[m].mean()) if m.any() else 0.0
        score = c * (1.4 if shares[j] < 0.2 else 1.0)
        if score > best_score:
            best, best_score = j, score

    lp5, lp50, lp95 = (int(round(v)) for v in np.percentile(L, [5, 50, 95]))
    mid = (L >= 30) & (L <= 75)
    warmth = float(lab[..., 2][mid].mean()) if mid.any() else 0.0
    corner, centre = _corner_centre(L)
    return {
        "palette": palette,
        "accent": palette[best],
        "shares": [round(float(s), 4) for s in shares],
        "l_p5": lp5,
        "l_p50": lp50,
        "l_p95": lp95,
        "contrast": lp95 - lp5,
        "dark_share": round(float((L < 25).mean()), 4),
        "bright_share": round(float((L > 75).mean()), 4),
        "chroma": round(float(chroma_px.mean()), 3),
        "warmth": round(warmth, 3),
        "vignette": round(corner / centre if centre > 1e-6 else 1.0, 3),
        "key": _key_light(L),
    }


# ---------------------------------------------------------------- the board's knobs

def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def look_patch(measured):
    """The board's knobs, read off a measurement: where the key light sits and how the film is graded.

    -> {"azimuthDeg", "elevationDeg", "ambient", "exposure", "post": {"contrast", "saturation"},
        "vignette": {"darkness"}}"""
    m = measured or {}
    key = m.get("key") or {}
    l50 = float(m["l_p50"]) if m.get("l_p50") is not None else 50.0
    dark = float(m["dark_share"]) if m.get("dark_share") is not None else 0.0
    contrast = float(m["contrast"]) if m.get("contrast") is not None else 0.0
    chroma = float(m["chroma"]) if m.get("chroma") is not None else 0.0
    vignette = float(m["vignette"]) if m.get("vignette") is not None else 1.0
    return {
        "azimuthDeg": int(key.get("azimuth_deg") if key.get("azimuth_deg") is not None else 180),
        "elevationDeg": max(10, min(70, int(key.get("elevation_deg") if key.get("elevation_deg") is not None else 45))),
        "ambient": round(_clamp(0.15 + 0.6 * dark, 0.05, 0.9), 3),        # a frame full of shadow needs a fill
        "exposure": round(_clamp(1 + (50 - l50) / 100, 0.6, 1.6), 3),      # a dark frame is shot brighter
        "post": {"contrast": round(_clamp(1 + contrast / 220, 0.85, 1.35), 3),
                 "saturation": round(_clamp(1 + chroma / 90, 0.85, 1.4), 3)},
        "vignette": {"darkness": round(_clamp((1 - vignette) * 1.4, 0.0, 0.9), 3)},
    }


# ---------------------------------------------------------------- comparing two boards

TOLERANCES = (("l_p50", 8), ("contrast", 12), ("saturation", 6), ("warmth", 5), ("dark_share", 0.12))


def _value(measured, metric):
    """One comparable number of a measurement (saturation is the mean chroma of the frame)."""
    m = measured or {}
    if metric == "saturation":
        v = m.get("saturation")
        v = m.get("chroma") if v is None else v
        return round(float(v or 0.0), 3)
    v = m.get(metric)
    if metric in ("l_p50", "contrast"):
        return int(round(float(v or 0)))
    return round(float(v or 0.0), 4)


def compare(a, b):
    """How far two measurements sit from each other, row by row, with the tolerance the board allows.

    -> [{"metric", "a", "b", "tolerance", "ok"}, ...]"""
    rows = []
    for metric, tol in TOLERANCES:
        va, vb = _value(a, metric), _value(b, metric)
        rows.append({"metric": metric, "a": va, "b": vb, "tolerance": tol,
                     "ok": bool(abs(va - vb) <= tol)})
    return rows


if __name__ == "__main__":
    import sys
    for p in sys.argv[1:]:
        m = measure(p)
        m["patch"] = look_patch(m)
        print(json.dumps(m, indent=2))
