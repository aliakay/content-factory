"""Motion study of a reference video: what makes it feel alive, measured instead of eyeballed.

A 2-frames-a-second grid shows the poses; only the full frame rate shows the timing, the follow-through and the moving
holds, and motion of 1-5 % (a breath, a float, a jiggle, a sway) does not show on any sheet at all. So, inside one
shot of the reference: a contact sheet at the source's frame rate, and the subject's edges tracked frame by frame
(top, left, right, bottom against the backdrop colour at the frame's edges) -> bob / sway / squash / widen as a % of the
subject's size and the period of the motion. Plus exact colours sampled from pixels.

Method after rossark-motion-skill's reference tools (MIT): tools/sheet.sh, track_edges.py, sample_colors.py. Here the
subject is found automatically (pixels far from the backdrop's colour), so no crop or colours are needed.
Works on flat / gradient grounds (animation, illustration, product on a sweep); busy footage is reported as not
measurable, and then the sheet + colours are the way.

CLI: python -m factory.motionref VIDEO [--start S --dur D] [--sheet out.png] [--at T X,Y X,Y ...]
"""
import json, os, subprocess, sys

import numpy as np

from .config import FFMPEG, FFPROBE

WIDTH = 160          # analysis width (px); amplitudes are relative, so a small decode is enough
MAX_FPS = 60


def fps_of(path):
    out = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate",
                          "-of", "csv=p=0", path], capture_output=True, text=True).stdout.strip()
    try:
        a, b = (out.split("/") + ["1"])[:2]
        return float(a) / float(b or 1)
    except (ValueError, ZeroDivisionError):
        return 30.0


def sheet(path, start, dur, out, crop="iw:ih:0:0", per_row=10, fps=None):
    """Every frame (at the source's rate unless `fps`) of a window, 10 per row: the timing, not just the poses."""
    fps = fps or fps_of(path)
    n = max(1, int(np.ceil(dur * fps)))
    rows = (n + per_row - 1) // per_row
    subprocess.run([FFMPEG, "-v", "error", "-y", "-ss", str(start), "-t", str(dur), "-i", path, "-vf",
                    f"fps={fps:g},crop={crop},scale=200:-2,tile={per_row}x{rows}:padding=2", "-frames:v", "1", out],
                   check=True)
    return out, n


def colors(path, at, points):
    """Exact hex colours at points (video pixels) of the frame at `at` s. For a lit state sample that moment too and
    blend between the two colours (never swap them)."""
    probe = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                            "-of", "csv=p=0", path], capture_output=True, text=True, check=True).stdout.strip()
    w, h = map(int, probe.split(",")[:2])
    raw = subprocess.run([FFMPEG, "-v", "error", "-ss", str(at), "-i", path, "-frames:v", "1", "-f", "rawvideo",
                          "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    out = []
    for x, y in points:
        if 0 <= x < w and 0 <= y < h:
            i = (y * w + x) * 3
            out.append((x, y, f"#{raw[i]:02X}{raw[i + 1]:02X}{raw[i + 2]:02X}"))
        else:
            out.append((x, y, None))
    return out


def frames(path, start, dur, fps, width=WIDTH):
    """RGB frames (n, h, w, 3) of a window at `fps`, `width` px wide."""
    raw = subprocess.run([FFMPEG, "-v", "error", "-ss", str(start), "-t", str(dur), "-i", path, "-vf",
                          f"fps={fps:g},scale={width}:-2", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True, check=True).stdout
    probe = subprocess.run([FFMPEG, "-v", "error", "-ss", str(start), "-i", path, "-frames:v", "1", "-vf",
                            f"scale={width}:-2", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                           capture_output=True, check=True).stdout
    h = len(probe) // (width * 3)
    n = len(raw) // (width * h * 3) if h else 0
    return np.frombuffer(raw[: n * width * h * 3], np.uint8).reshape(n, h, width, 3) if n else np.zeros((0, 1, width, 3))


def window(duration, cuts=None, span=3.0):
    """The middle `span` s of the longest shot (a cut inside the window would ruin the background)."""
    edges = [0.0] + sorted(c for c in (cuts or []) if 0 < c < duration) + [duration]
    a, b = max(zip(edges, edges[1:]), key=lambda s: s[1] - s[0])
    mid, half = (a + b) / 2, min(span, b - a - 0.2) / 2
    return round(max(a, mid - half), 2), round(max(0.2, 2 * half), 2)


def _p2p(v):
    v = np.asarray([x for x in v if x is not None], float)
    return float(np.percentile(v, 95) - np.percentile(v, 5)) if len(v) > 2 else 0.0


def _period(v, fps):
    """Dominant period (s) of a signal: the first clear autocorrelation peak, or None."""
    v = np.asarray([x for x in v if x is not None], float)
    if len(v) < 12 or v.std() < 1e-6:
        return None
    v = v - np.polyval(np.polyfit(np.arange(len(v)), v, 1), np.arange(len(v)))   # drop a slow drift
    ac = np.correlate(v, v, "full")[len(v) - 1:]
    ac = ac / (ac[0] or 1)
    for lag in range(2, len(ac) - 1):
        if ac[lag] > 0.3 and ac[lag] >= ac[lag - 1] and ac[lag] >= ac[lag + 1]:
            return round(lag / fps, 2)
    return None


def track(fr, tol=40, run=3):
    """Per frame: (top, bottom, left, right) of the subject, or None, + the share of the frame it covers. The backdrop
    is each row's colour at the frame's left and right edges (median over the window): flat and gradient grounds."""
    edge = np.concatenate([fr[:, :, :4], fr[:, :, -4:]], axis=2).astype(np.int16)        # (n, h, 8, 3)
    ref = np.median(edge.reshape(-1, fr.shape[1], 8, 3).transpose(1, 0, 2, 3).reshape(fr.shape[1], -1, 3), axis=1)
    mask = np.abs(fr.astype(np.int16) - ref[None, :, None, :].astype(np.int16)).max(axis=3) > tol
    out = []
    for m in mask:
        rows, cols = np.where(m.sum(axis=1) >= run)[0], np.where(m.sum(axis=0) >= run)[0]
        out.append((int(rows[0]), int(rows[-1]), int(cols[0]), int(cols[-1])) if len(rows) and len(cols) else None)
    return out, float(mask.mean())


def study(path, start=None, dur=None, cuts=None):
    """Measured motion of one shot of a reference: amplitudes as % of the subject's size, the period, a verdict."""
    fps = min(MAX_FPS, fps_of(path))
    if start is None or dur is None:
        total = float(subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                                     capture_output=True, text=True).stdout.strip() or 0)
        start, dur = window(total, cuts)
    fr = frames(path, start, dur, fps)
    res = {"window": [start, round(start + dur, 2)], "fps": round(fps, 2)}
    if len(fr) < 6:
        return {**res, "verdict": "too short"}
    boxes, area = track(fr)
    seen = [b for b in boxes if b]
    if area > 0.5 or len(seen) < len(boxes) * 0.6:
        return {**res, "verdict": "busy frame" if area > 0.5 else "no steady subject",
                "note": "measure by hand on a locked-off moment (sheet + colours)"}
    top = [b[0] if b else None for b in boxes]
    hgt = [b[1] - b[0] if b else None for b in boxes]
    wid = [b[3] - b[2] if b else None for b in boxes]
    cx = [(b[2] + b[3]) / 2 if b else None for b in boxes]
    H, Wd = float(np.median([h for h in hgt if h is not None]) or 1), float(np.median([w for w in wid if w is not None]) or 1)
    pct = lambda v, size: round(100 * _p2p(v) / max(1.0, size), 1)
    res.update({"subject_frame": [round(Wd / fr.shape[2], 2), round(H / fr.shape[1], 2)],   # share of the frame (w, h)
                "bob_pct": pct(top, H), "sway_pct": pct(cx, Wd), "squash_pct": pct(hgt, H), "widen_pct": pct(wid, Wd)})
    big = max(res["bob_pct"], res["sway_pct"], res["squash_pct"], res["widen_pct"])
    res["period_s"] = _period(top if res["bob_pct"] >= res["sway_pct"] else cx, fps)
    res["verdict"] = "still" if big < 0.8 else "subtle idle life" if big < 8 else "big action"
    if res["verdict"] == "subtle idle life":
        res["note"] = "small motion that never stops: reproduce these amplitudes and period (FX.alive / FX.breathe / FX.jiggle / FX.float)"
    return res


def summary(m):
    """One line for prompts."""
    if not m:
        return ""
    if "bob_pct" not in m:
        return m.get("verdict", "")
    per = f", period {m['period_s']} s" if m.get("period_s") else ""
    return (f"{m['verdict']}: bob {m['bob_pct']} %, sway {m['sway_pct']} %, squash {m['squash_pct']} %, widen "
            f"{m['widen_pct']} % of the subject{per} (measured at {m['fps']} fps, {m['window'][0]}-{m['window'][1]} s)")


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Measure how something moves in a reference video.")
    ap.add_argument("video")
    ap.add_argument("--start", type=float)
    ap.add_argument("--dur", type=float)
    ap.add_argument("--sheet", help="also write a contact sheet of every frame of the window here")
    ap.add_argument("--at", type=float, help="sample colours of this frame (s) at the given X,Y points")
    ap.add_argument("points", nargs="*")
    a = ap.parse_args(argv)
    if a.at is not None:
        for x, y, c in colors(a.video, a.at, [tuple(map(int, p.split(","))) for p in a.points]):
            print(f"{x},{y}  {c or 'outside the frame'}")
        return
    m = study(a.video, a.start, a.dur)
    print(json.dumps(m, indent=1))
    if a.sheet:
        s, e = m["window"]
        print(sheet(a.video, s, e - s, a.sheet)[0])


if __name__ == "__main__":
    main(sys.argv[1:])
