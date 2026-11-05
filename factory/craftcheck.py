"""Craft checks distilled from sarpstar/cinecode (MIT): the measurable rules of its writing, rhythm, sound and QC
chapters, as small model-free functions. Each returns findings [{kind, severity, detail, ...}] like soundqa and qa.

  words_check   narration copy: dashes, generated-sounding stock phrasing, greeting / filler openers
  rhythm        scene lengths: too even (spread < 0.30), five or more of about the same length in a row
  sound_budget  designed sounds: whooshes per 30 s, risers per 30 s, the same transition sound twice in a row,
                the share of cuts that carry a designed sound
  scene_loudness  loudness and 2-5 kHz share per scene; flags scenes > 3 LU / > 3 dB from the median
  loop_seam     does the last frame of a looping video flow into the first
  frame_bpms    tempos whose beat is a whole number of frames (every cue on the grid lands on a frame)
"""
import re
import subprocess

import numpy as np

from .config import FFMPEG

DASHES = "—–"          # em and en dash; a spoken line has no use for them
# Stock phrasing that reads as generated, per language. Matched case-insensitively on word boundaries.
STOCK = {
    "en": ["in today's fast-paced world", "in this video", "did you know", "let's dive in", "dive into", "delve",
           "game-changer", "game changer", "unlock the power", "unleash", "revolutionize", "tapestry", "navigate the "
           "landscape", "it's important to note", "it is important to note", "at the end of the day", "in conclusion",
           "look no further", "buckle up", "stay tuned", "without further ado", "a testament to", "ever-evolving",
           "ever-changing", "cutting-edge", "seamless", "not just .{1,40}, but"],
    "tr": ["bu videoda", "biliyor muydunuz", "biliyor muydun", "hadi başlayalım", "derinlemesine", "oyunun kurallarını "
           "değiştir", "devrim niteliğinde", "sonuç olarak", "unutmayın ki", "şunu belirtmek gerekir", "günümüzün hızla",
           "gelin birlikte", "kemerlerinizi bağlayın", "takipte kalın", "sadece .{1,40} değil, aynı zamanda"],
}
GREETING = {"en": r"^(hi|hey|hello|welcome|what's up|so,?)\b", "tr": r"^(merhaba|selam|hoş geldin|arkadaşlar|herkese)\b"}


def words_check(lines, lang="en"):
    """Findings for narration lines (a list of strings). Never edits; the writer decides."""
    lang = lang if lang in STOCK else "en"
    out = []
    for i, line in enumerate(lines or []):
        text = line if isinstance(line, str) else str(line.get("text", ""))
        if any(c in text for c in DASHES) or re.search(r"\s-\s", text):
            out.append({"kind": "dash", "severity": "warn", "line": i, "detail": "dash in spoken copy: use a full stop, "
                        "a comma or two sentences"})
        low = text.lower()
        for pat in STOCK[lang]:
            if re.search(rf"(?<!\w){pat}(?!\w)", low):
                out.append({"kind": "stock_phrase", "severity": "warn", "line": i,
                            "detail": f"generated-sounding phrasing ({pat.split('.')[0].strip()}): say the concrete thing"})
                break
        if i == 0 and re.search(GREETING[lang], low.strip()):
            out.append({"kind": "greeting", "severity": "warn", "line": 0, "detail": "the hook starts with a greeting: "
                        "open on the surprise"})
    return out


def rhythm(durations, run=5, spread_min=0.30, tol=0.15):
    """Findings for scene or shot lengths in seconds. Spread = stdev / mean; a run is `run` or more neighbours within
    `tol` of each other's length."""
    d = [float(x) for x in durations if x and float(x) > 0]
    out = []
    if len(d) < 4:
        return out
    spread = float(np.std(d) / np.mean(d))
    if spread < spread_min:
        out.append({"kind": "even_rhythm", "severity": "warn", "spread": round(spread, 2),
                    "detail": f"scene lengths too even (spread {spread:.2f}, want >= {spread_min}): let the idea set "
                              "the length, short for a beat, long for a reveal"})
    start = 0
    for i in range(1, len(d) + 1):
        if i == len(d) or abs(d[i] - d[start]) > tol * d[start]:
            if i - start >= run:
                out.append({"kind": "flat_run", "severity": "warn", "from": start, "to": i - 1,
                            "detail": f"scenes {start + 1}-{i} all run about {d[start]:.1f} s: break the pattern"})
            start = i
    return out


def sound_budget(cues, total, cuts=()):
    """Findings for placed cues [{t, kind}] over `total` s. `cuts` = scene change times, to measure how many carry a
    designed sound. Whoosh / swish count together; a riser is its own kind."""
    out, cues = [], sorted(cues or [], key=lambda c: c["t"])
    swoosh = [c for c in cues if c["kind"] in ("whoosh", "swish")]
    risers = [c for c in cues if c["kind"] == "riser"]
    for name, items, cap in (("whooshes", swoosh, 2), ("risers", risers, 1)):
        for a in np.arange(0, max(total - 30, 0) + 1e-6, 10.0):
            n = sum(a <= c["t"] < a + 30 for c in items)
            if n > cap:
                out.append({"kind": f"too_many_{name}", "severity": "warn", "t": round(float(a), 1),
                            "detail": f"{n} {name} in {a:.0f}-{a + 30:.0f} s (at most {cap} per 30 s): score the cuts with "
                                      "the picture's own sound or nothing"})
                break
    trans = [c for c in cues if c["kind"] in ("whoosh", "swish", "riser", "flip")]
    for a, b in zip(trans, trans[1:]):
        if a["kind"] == b["kind"] and a.get("take", 0) == b.get("take", 0) and b["t"] - a["t"] < 6:
            out.append({"kind": "same_transition_sound", "severity": "info", "t": b["t"],
                        "detail": f"'{b['kind']}' twice in a row within {b['t'] - a['t']:.1f} s with the same take"})
            break
    cuts = [float(c) for c in cuts]
    if len(cuts) >= 4:
        hit = sum(any(abs(c["t"] - t) < 0.35 for c in cues) for t in cuts)
        share = hit / len(cuts)
        if share > 0.7:
            out.append({"kind": "sound_on_every_cut", "severity": "warn", "share": round(share, 2),
                        "detail": f"{round(100 * share)} % of the cuts carry a designed sound (keep it under 70 %): "
                                  "most cuts should ride on the music"})
    return out


def scene_loudness(path, boundaries):
    """Per-scene loudness (RMS dBFS) and 2-5 kHz share. `boundaries` = scene start times in s (first is 0).
    Returns {"scenes": [...], "findings": [...]}; flags scenes > 3 dB from the median and presence outliers."""
    from .soundqa import SR, band_energy, db, decode
    y = decode(path)
    edges = sorted({0.0, *[float(b) for b in boundaries]}) + [len(y) / SR]
    rows = []
    for a, b in zip(edges, edges[1:]):
        seg = y[int(a * SR):int(b * SR)]
        if len(seg) < SR // 4:
            continue
        lvl = float(db(np.sqrt(np.mean(seg ** 2))))
        pres, tot = band_energy(seg, SR, 2000, 5000)
        rows.append({"from": round(a, 2), "to": round(b, 2), "db": round(lvl, 1),
                     "presence_db": round(float(db(pres / max(tot, 1e-12))), 1)})
    out = []
    if len(rows) >= 3:
        med = float(np.median([r["db"] for r in rows]))
        pmed = float(np.median([r["presence_db"] for r in rows]))
        for r in rows:
            if r["db"] > -60 and abs(r["db"] - med) > 3:
                out.append({"kind": "scene_level", "severity": "warn", "t": r["from"],
                            "detail": f"scene at {r['from']:.1f} s is {r['db'] - med:+.1f} dB from the median scene"})
            if r["presence_db"] - pmed > 3:
                out.append({"kind": "scene_harsh", "severity": "info", "t": r["from"],
                            "detail": f"scene at {r['from']:.1f} s has {r['presence_db'] - pmed:+.1f} dB more 2-5 kHz "
                                      "than the median scene"})
    return {"scenes": rows, "findings": out}


def loop_seam(path, fps=10, width=96):
    """Compare the jump from the last frame to the first with the video's typical frame-to-frame change."""
    r = subprocess.run([FFMPEG, "-v", "error", "-i", path, "-vf", f"fps={fps},scale={width}:-2,format=gray",
                        "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True)
    p = subprocess.run([FFMPEG, "-v", "error", "-i", path, "-frames:v", "1", "-vf", f"scale={width}:-2,format=gray",
                        "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True).stdout
    if not p or len(p) % width or not r.stdout:
        return {"findings": [], "jump": None, "typical": None}
    h = len(p) // width
    n = len(r.stdout) // (width * h)
    f = np.frombuffer(r.stdout[:n * width * h], dtype=np.uint8).reshape(n, h, width).astype(np.float32)
    if n < 6:
        return {"findings": [], "jump": None, "typical": None}
    steps = np.abs(np.diff(f, axis=0)).mean(axis=(1, 2))
    jump = float(np.abs(f[-1] - f[0]).mean())
    typical = float(np.percentile(steps, 90))
    out = []
    if jump > max(3 * typical, 4.0):
        out.append({"kind": "loop_seam", "severity": "warn", "detail": f"last frame to first jumps {jump:.1f} (typical "
                    f"step {typical:.1f}): the loop will visibly pop; end on the opening picture or cross-dissolve"})
    return {"findings": out, "jump": round(jump, 2), "typical": round(typical, 2)}


def frame_bpms(fps=30, lo=70, hi=150):
    """Tempos in [lo, hi] whose beat is a whole number of frames: fps * 60 / bpm is an integer."""
    return [{"bpm": b, "frames_per_beat": int(fps * 60 // b)} for b in range(int(lo), int(hi) + 1)
            if (fps * 60) % b == 0]
