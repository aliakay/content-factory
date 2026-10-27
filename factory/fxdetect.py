"""What a clip offers the art director for effects, measured instead of guessed (numpy on small grey frames).

  horizon     strongest horizontal edge per second (y as 0..1 of the frame, None when there is no clear line):
              two shots whose horizons sit at the same height are match-cut material
  flow        dominant motion per second (dx, dy in % of the frame per second, phase correlation): pans or walks in
              the same direction cut together as one movement
  occlusions  moments when something dark and big passes close to the lens (a person, a pole, a tree): the cut can
              hide inside it ("object wipe", stylecut enter "object" with the previous shot ending at `t`)

`analyze(path)` -> dict (stored per clip in clips.fx). `match_pairs(fx_by_clip)` lists candidate match cuts.
"""
import json, subprocess

import numpy as np

from .config import FFMPEG

FPS = 8
WIDTH = 96


def frames(path, fps=FPS, width=WIDTH, max_s=60):
    """Grey frames as float32 [n, h, w] in 0..1 (at most max_s seconds)."""
    r = subprocess.run([FFMPEG, "-v", "error", "-t", str(max_s), "-i", path, "-vf",
                        f"fps={fps},scale={width}:-2,format=gray", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                       capture_output=True)
    raw = r.stdout
    probe = subprocess.run([FFMPEG, "-v", "error", "-i", path, "-frames:v", "1", "-vf", f"scale={width}:-2,format=gray",
                            "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True).stdout
    if not probe or len(probe) % width:
        return np.zeros((0, 1, width), dtype=np.float32)
    h = len(probe) // width
    n = len(raw) // (width * h)
    return np.frombuffer(raw[:n * width * h], dtype=np.uint8).reshape(n, h, width).astype(np.float32) / 255


def horizon_y(f):
    """Row (0..1) of the strongest straight horizontal edge, or None."""
    g = np.abs(np.diff(f, axis=0)).mean(axis=1)            # mean vertical gradient per row
    if len(g) < 8:
        return None
    k = np.convolve(g, np.ones(3) / 3, mode="same")
    lo, hi = int(len(k) * 0.08), int(len(k) * 0.92)
    i = lo + int(np.argmax(k[lo:hi]))
    return round(i / len(k), 3) if k[i] > 3 * (np.median(k) + 1e-4) else None


def shift(a, b):
    """(dx, dy) in pixels that best maps frame a onto frame b (phase correlation)."""
    F = np.fft.fft2(a - a.mean()) * np.conj(np.fft.fft2(b - b.mean()))
    r = np.fft.ifft2(F / (np.abs(F) + 1e-6)).real
    y, x = np.unravel_index(int(np.argmax(r)), r.shape)
    h, w = r.shape
    return (x - w if x > w // 2 else x), (y - h if y > h // 2 else y)


def occlusions(fr, fps=FPS):
    """Short stretches where a big dark area appears that was not there half a second before."""
    if len(fr) < fps:
        return []
    ref = np.median(fr)
    lag = max(1, fps // 2)
    cover = []
    for i in range(len(fr)):
        dark = fr[i] < min(0.18, ref * 0.5)
        new = np.abs(fr[i] - fr[max(0, i - lag)]) > 0.2
        cover.append(float((dark & new).mean()))
    out, i = [], 0
    while i < len(cover):
        if cover[i] >= 0.35:
            j = i
            while j < len(cover) and cover[j] >= 0.2:
                j += 1
            seg = cover[i:j]
            if (j - i) / fps <= 1.5:
                p = i + int(np.argmax(seg))
                out.append({"t": round(p / fps, 2), "start": round(i / fps, 2), "end": round(j / fps, 2),
                            "cover": round(max(seg), 2)})
            i = j
        else:
            i += 1
    return out


def analyze(path, fps=FPS):
    fr = frames(path, fps)
    if not len(fr):
        return {"horizon": [], "flow": [], "occlusions": []}
    h, w = fr.shape[1:]
    horizon, flow = [], []
    for sec in range(int(len(fr) / fps)):
        a = fr[sec * fps]
        horizon.append(horizon_y(a))
        b = fr[min(len(fr) - 1, sec * fps + fps // 2)]
        dx, dy = shift(b, a)
        k = 2 * 100.0                                           # half a second apart, in % of the frame per second
        flow.append([round(dx / w * k, 1), round(dy / h * k, 1)])
    return {"horizon": horizon, "flow": flow, "occlusions": occlusions(fr, fps)}


def summary(fx):
    """Compact form for the art director's prompt."""
    if not fx:
        return None
    hz = [y for y in fx.get("horizon") or [] if y is not None]
    fl = fx.get("flow") or []
    mean = [round(float(np.mean([f[0] for f in fl])), 1), round(float(np.mean([f[1] for f in fl])), 1)] if fl else None
    return {"horizon_y": round(float(np.median(hz)), 2) if len(hz) >= max(2, len(fx.get("horizon") or []) // 2) else None,
            "motion_pct_per_s": mean, "occlusions": fx.get("occlusions") or []}


def match_pairs(fx_by_clip, tol=0.05):
    """Clip pairs whose horizons line up or whose dominant motion points the same way (both moving)."""
    s = {c: summary(fx) for c, fx in fx_by_clip.items() if fx}
    out = []
    ids = sorted(s)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            A, B = s[a], s[b]
            why = []
            if A["horizon_y"] is not None and B["horizon_y"] is not None and abs(A["horizon_y"] - B["horizon_y"]) <= tol:
                why.append(f"horizon at {A['horizon_y']:.2f}/{B['horizon_y']:.2f}")
            ma, mb = A["motion_pct_per_s"], B["motion_pct_per_s"]
            if ma and mb and abs(ma[0]) >= 4 and abs(mb[0]) >= 4 and (ma[0] > 0) == (mb[0] > 0):
                why.append(f"both pan {'right' if ma[0] > 0 else 'left'}")
            if why:
                out.append({"a": a, "b": b, "why": ", ".join(why)})
    return out[:30]


def ensure_column(con):
    if "fx" not in {r[1] for r in con.execute("PRAGMA table_info(clips)")}:
        con.execute("ALTER TABLE clips ADD COLUMN fx TEXT")


def for_clips(con, clip_ids=None, compute=True):
    """{clip_id: fx} for video clips, measuring (and storing) the ones not analysed yet."""
    ensure_column(con)
    q = "SELECT clip_id, path, fx FROM clips WHERE kind='video' AND usable=1"
    rows = con.execute(q).fetchall()
    out = {}
    for r in rows:
        if clip_ids and r["clip_id"] not in clip_ids:
            continue
        fx = json.loads(r["fx"]) if r["fx"] else None
        if fx is None and compute:
            try:
                fx = analyze(r["path"])
            except Exception as e:   # unreadable file: no effects data, never a failed direction
                print("fx:", r["clip_id"], type(e).__name__, flush=True)
                continue
            con.execute("UPDATE clips SET fx=? WHERE clip_id=?", (json.dumps(fx), r["clip_id"]))
            con.commit()
        out[r["clip_id"]] = fx
    return out
