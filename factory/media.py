"""Clip analysis: metadata, contact sheets, motion/sharpness profile, best segments, place grouping."""
import json, math, os, re, subprocess

import numpy as np

from .config import ROOT, FFMPEG, FFPROBE
SHEETS = os.path.join(ROOT, "work", "sheets")
VIDEO_EXT = (".mov", ".mp4", ".m4v")
PHOTO_EXT = (".jpg", ".jpeg", ".png")


def kind_of(path):
    e = os.path.splitext(path)[1].lower()
    return "video" if e in VIDEO_EXT else "photo" if e in PHOTO_EXT else None


def probe_video(path):
    d = json.loads(subprocess.check_output(
        [FFPROBE, "-v", "error", "-show_entries",
         "format=duration:format_tags=com.apple.quicktime.location.ISO6709,com.apple.quicktime.creationdate,"
         "creation_time:stream=codec_type,width,height,r_frame_rate:stream_side_data=rotation",
         "-of", "json", path]))
    tags = d["format"].get("tags", {})
    v = next(s for s in d["streams"] if s.get("codec_type") == "video")
    rot = next((sd.get("rotation") for sd in v.get("side_data_list", []) if "rotation" in sd), 0)
    w, h = v["width"], v["height"]
    if rot in (90, -90, 270, -270):
        w, h = h, w
    lat = lon = None
    m = re.match(r"([+-][\d.]+)([+-][\d.]+)", tags.get("com.apple.quicktime.location.ISO6709", ""))
    if m:
        lat, lon = float(m.group(1)), float(m.group(2))
    num, den = (v.get("r_frame_rate") or "30/1").split("/")
    return {"duration": float(d["format"].get("duration", 0)), "fps": float(num) / float(den or 1),
            "width": w, "height": h, "lat": lat, "lon": lon,
            "captured_at": tags.get("com.apple.quicktime.creationdate") or tags.get("creation_time")}


def probe_photo(path):
    from PIL import Image, ImageOps
    im = Image.open(path)
    ex = im.getexif()
    dt = ex.get(306) or ex.get_ifd(0x8769).get(36867)
    g = ex.get_ifd(0x8825)
    lat = lon = None
    if g and 2 in g and 4 in g:
        dms = lambda v, ref: (-1 if ref in ("S", "W") else 1) * (float(v[0]) + float(v[1]) / 60 + float(v[2]) / 3600)
        lat, lon = dms(g[2], g[1]), dms(g[4], g[3])
    w, h = ImageOps.exif_transpose(im).size
    captured = None
    if dt:
        captured = re.sub(r"^(\d{4}):(\d{2}):(\d{2}) ", r"\1-\2-\3T", str(dt))
    return {"duration": None, "fps": None, "width": w, "height": h, "lat": lat, "lon": lon, "captured_at": captured}


def contact_sheet(path, clip_id, kind, frames=12):
    """Strip of evenly spaced frames (video) or a thumbnail (photo) for the UI and for Claude."""
    os.makedirs(SHEETS, exist_ok=True)
    out = os.path.join(SHEETS, f"{clip_id}.jpg")
    if kind == "video":
        dur = probe_video(path)["duration"] or 1
        subprocess.run([FFMPEG, "-v", "error", "-y", "-i", path, "-vf",
                        f"fps={frames / dur},scale=160:-2,tile={frames}x1:padding=2", "-frames:v", "1", out], check=True)
    else:
        from PIL import Image, ImageOps
        im = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
        im.thumbnail((360, 640))
        im.save(out, quality=85)
    return out


def motion_profile(path, fps=10):
    """Per-sample (t, motion, sharpness) at `fps` from a small grayscale decode."""
    w, h = 108, 192
    p = subprocess.run([FFMPEG, "-v", "error", "-i", path, "-vf", f"fps={fps},scale={w}:{h},format=gray",
                        "-f", "rawvideo", "-"], capture_output=True, check=True)
    frames = np.frombuffer(p.stdout, np.uint8)
    n = len(frames) // (w * h)
    frames = frames[: n * w * h].reshape(n, h, w).astype(np.float32)
    rows, prev = [], None
    for i, g in enumerate(frames):
        lap = (-4 * g[1:-1, 1:-1] + g[:-2, 1:-1] + g[2:, 1:-1] + g[1:-1, :-2] + g[1:-1, 2:]).var()
        mot = float(np.abs(g - prev).mean()) if prev is not None else None
        rows.append((round(i / fps, 2), mot, float(lap)))
        prev = g
    if len(rows) > 1:
        rows[0] = (rows[0][0], rows[1][1], rows[0][2])
    return rows


def best_segments(rows, min_len=1.5, max_len=8.0, k=4):
    """Steadiest stretches: samples below the clip's motion median (or all, if the clip is steady)."""
    if not rows:
        return []
    mot = np.array([r[1] or 0 for r in rows])
    t = np.array([r[0] for r in rows])
    step = t[1] - t[0] if len(t) > 1 else 0.1
    smooth = np.convolve(mot, np.ones(5) / 5, mode="same")
    steady_clip = np.percentile(mot, 90) < 2.0
    calm = np.ones_like(smooth, bool) if steady_clip else smooth <= np.median(smooth)
    segs, i = [], 0
    while i < len(calm):
        if calm[i]:
            j = i
            while j + 1 < len(calm) and calm[j + 1]:
                j += 1
            s, e = t[i], t[j] + step
            while e - s >= min_len:  # split long calm stretches into usable chunks
                ce = min(e, s + max_len)
                sl = (t >= s) & (t < ce)
                segs.append({"start": round(float(s), 2), "end": round(float(ce), 2),
                             "motion": round(float(mot[sl].mean()), 2), "sharp": round(float(np.array(
                                 [r[2] for r in rows])[sl].mean()), 1)})
                s = ce
            i = j + 1
        else:
            i += 1
    segs.sort(key=lambda g: (-(g["end"] - g["start"]), g["motion"]))
    return sorted(segs[:k], key=lambda g: g["start"])


def haversine_km(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def assign_place(con, lat, lon, day, radius_km=4.0):
    """Join an existing place on the same day within radius_km, or create a new one."""
    if lat is None:
        return None
    for p in con.execute("SELECT * FROM places WHERE day=?", (day,)):
        if haversine_km((lat, lon), (p["lat"], p["lon"])) <= radius_km:
            return p["place_id"]
    cur = con.execute("INSERT INTO places (name, day, lat, lon) VALUES (?,?,?,?)",
                      (f"{day} · {lat:.3f},{lon:.3f}", day, lat, lon))
    return cur.lastrowid
