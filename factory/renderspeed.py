"""How long a render takes on THIS machine, measured, not guessed: the Studio shows it per technique (catalog) and per
plan / production ("30 sn video: final ~6 dk").

Measurements (data/render_speed.json, runtime state):
  calib     a full-size (1080x1920) capture benchmark: browser start-up + seconds per captured frame
  final     every real final render: captured frames (x motion-blur samples) -> capture wall time, and the
            mix + encode wall time per video second
  preview   the same for previews (half size, 15 fps)
  demo:<id> each catalog demo clip (same size and fps for all), so techniques compare: a 3D set or a weather canvas
            costs more per frame than kinetic type. weight(id) = its seconds per frame / the median demo's.
Until something is measured, rough defaults for a 4-core VM are used and the estimate says so (measured: False).
"""
import json, os, statistics, time

from . import capabilities
from .config import ROOT

PATH = os.path.join(ROOT, "data", "render_speed.json")
KEEP = 20
DEFAULT = {"per_capture": 0.45, "startup": 6.0, "post_per_s": 0.6, "preview_per_capture": 0.16}   # 4 cores, no GPU
FPS = {"final": 30, "preview": 15}


def _load():
    try:
        return json.load(open(PATH))
    except (OSError, ValueError):
        return {}


def _save(d):
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    tmp = PATH + ".tmp"
    json.dump(d, open(tmp, "w"))
    os.replace(tmp, PATH)


def record(kind, captures, seconds, **extra):
    """One measured render: `captures` screenshots took `seconds` of wall time (+ extra numbers, e.g. post_per_s)."""
    if captures <= 0 or seconds <= 0:
        return
    d = _load()
    d[kind] = (d.get(kind) or [])[-(KEEP - 1):] + [{"n": int(captures), "s": round(float(seconds), 2), "at": int(time.time()), **extra}]
    _save(d)


def _median(rows, f):
    vals = [f(r) for r in rows or [] if f(r) is not None]
    return statistics.median(vals) if vals else None


def machine():
    """Seconds per full-size captured frame, browser start-up, mix + encode per video second; measured where possible."""
    d = _load()
    calib, finals = d.get("calib") or [], d.get("final") or []
    startup = _median(calib, lambda r: r.get("startup")) or DEFAULT["startup"]
    pc = _median(finals, lambda r: max(0.01, (r["s"] - startup) / r["n"])) or _median(calib, lambda r: r.get("per_capture"))
    post = _median(finals, lambda r: r.get("post_per_s"))
    prev = _median(d.get("preview") or [], lambda r: max(0.005, (r["s"] - startup) / r["n"]))
    return {"per_capture": pc or DEFAULT["per_capture"], "startup": startup, "post_per_s": post or DEFAULT["post_per_s"],
            "preview_per_capture": prev or (pc * 0.35 if pc else DEFAULT["preview_per_capture"]),
            "measured": bool(pc), "finals": len(finals), "cores": os.cpu_count()}


def weight(cid):
    """How heavy a technique's frames are compared with the median technique (1.0), from the catalog demo timings."""
    d = _load()
    st = machine()["startup"]   # browser start-up is the same for every demo: leave it out of the comparison
    rates = {k[5:]: _median(v, lambda r: max(0.001, r["s"] - st) / r["n"]) for k, v in d.items() if k.startswith("demo:")}
    rates = {k: v for k, v in rates.items() if v}
    if cid not in rates or len(rates) < 3:
        return 1.0
    return round(max(0.7, min(4.0, rates[cid] / statistics.median(rates.values()))), 2)


def blur(ids):
    return max([int((capabilities.CAPS.get(i, {}).get("data") or {}).get("motion_blur") or 1) for i in ids or []] or [1])


def estimate(seconds=30, ids=(), blur_samples=None):
    """-> {preview_s, final_s, blur, weight, measured}: the wall time of a preview and a final render of a `seconds`
    long video made with techniques `ids` on this machine."""
    m = machine()
    b = blur_samples or blur(ids)
    w = max([weight(i) for i in ids] or [1.0])
    final = m["startup"] + seconds * FPS["final"] * b * m["per_capture"] * w + seconds * m["post_per_s"]
    preview = m["startup"] + seconds * FPS["preview"] * m["preview_per_capture"] * w + seconds * m["post_per_s"] * 0.5
    return {"preview_s": round(preview), "final_s": round(final), "blur": b, "weight": w, "measured": m["measured"],
            "seconds": seconds}


def label(sec):
    """'~40 sn' / '~6 dk' / '~1 sa 10 dk' for the Studio."""
    sec = int(sec)
    if sec < 90:
        return f"~{max(5, round(sec / 5) * 5)} sn"
    m = round(sec / 60)
    return f"~{m} dk" if m < 60 else f"~{m // 60} sa {m % 60} dk"


def calibrate():
    """Full-size capture benchmark on this machine (~20-40 s): a short and a longer render of the same scene, so the
    browser start-up and the per-frame cost separate."""
    import sys
    from . import catalog
    sys.path.insert(0, os.path.join(ROOT, "bin"))
    import htmlmotion
    os.makedirs(catalog.DIR, exist_ok=True)
    b, _, _ = catalog._bundle("look.code_characters")
    path = os.path.join(catalog.DIR, "_calib.json")
    json.dump(b, open(path, "w"))
    out = os.path.join(catalog.DIR, "_calib.mp4")
    walls = []
    for dur in (0.2, 2.0):
        t0 = time.time()
        r = htmlmotion._node(path, out, dur, ["--opaque"], FPS["final"])
        if r.returncode:
            raise RuntimeError("calibration render failed: " + (r.stderr or "")[-200:])
        walls.append(time.time() - t0)
    n0, n1 = round(0.2 * FPS["final"]), round(2.0 * FPS["final"])
    pc = max(0.01, (walls[1] - walls[0]) / (n1 - n0))
    record("calib", n1, walls[1], per_capture=round(pc, 4), startup=round(max(0.5, walls[0] - n0 * pc), 2))
    for f in (out, path):
        try:
            os.remove(f)
        except OSError:
            pass
    return machine()
