"""A mouth that follows the voice: one open value and one shape per frame, from the audio itself.

A drawn character that talks needs its mouth to move with the sound, not with a random loop. This measures the
voice-over and hands the renderer a curve: per frame, how far the mouth is open (0..1) and which shape it makes.
No model, no ML — four measurements and a smoothing rule, so the same wav always gives the same curve (which the
determinism check depends on).

How it reads a voice (ported from a reviewed reference implementation, motionforge `tools/mouth_curve.py`):
  - mono 16 kHz; per frame the RMS in dB plus three band energies (150–800, 800–1800, 1800–4500 Hz);
  - the floor is the 10th percentile of the dB track; a noise gate sits 8 dB above it so a room tone never opens
    the mouth;
  - the curve is normalised to the 20th percentile of voiced frames at 0 and the 95th at 1 (syllables close between
    hits instead of hanging open), then shaped by a 1.2 exponent;
  - smoothing is asymmetric: attack is a third of the release, so the mouth opens fast and closes slowly (no
    chatter); first-order per frame with `y += (v - y) * (1 - exp(-1 / (tau * fps)))`;
  - a 40 ms lead, because a mouth that arrives with the sound reads as a dub;
  - the shape comes from the band balance: high band up = wide, mid down with no high = round, nearly shut = closed,
    with a five-frame majority so a single frame cannot flicker.

`curve(path)` returns {"fps", "open": [...], "shape": [...]} — the bundle's `mouth` block; `factory/hat/explainer.py`
puts it next to the word timings and `motion/templates/fxlib.js` draws it (`FX.mouth`).
"""
import json, math, subprocess, wave

import numpy as np

from .config import FFMPEG

FPS = 30
SR = 16000
GATE_DB = 8.0
LEAD_MS = 40
RELEASE_MS = 60
BANDS = ((150.0, 800.0), (800.0, 1800.0), (1800.0, 4500.0))


def _pcm(path):
    """Mono 16 kHz float samples from any audio file (ffmpeg), so the maths never depends on the container."""
    p = subprocess.run([FFMPEG, "-v", "error", "-i", path, "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"],
                       capture_output=True)
    if p.returncode or not p.stdout:
        raise RuntimeError(f"could not decode {path}: {(p.stderr or b'')[:200]!r}")
    return np.frombuffer(p.stdout, dtype="<i2").astype(np.float32) / 32768.0


def curve(path, fps=FPS, release_ms=RELEASE_MS, lead_ms=LEAD_MS, gate_db=GATE_DB, data=None):
    """-> {"fps", "open": [0..1 per frame], "shape": ["closed"|"open"|"wide"|"round" per frame]}."""
    x = _pcm(path) if data is None else np.asarray(data, dtype=np.float32)
    hop = max(1, int(round(SR / fps)))
    n = max(1, len(x) // hop)
    db = np.empty(n, dtype=np.float32)
    bands = np.zeros((n, len(BANDS)), dtype=np.float32)
    win = np.hanning(hop * 2)
    for i in range(n):
        seg = x[i * hop:(i + 1) * hop]
        if not len(seg):
            db[i], bands[i] = -120.0, 0.0
            continue
        rms = float(np.sqrt(np.mean(seg ** 2)) or 0.0)
        db[i] = 20 * math.log10(max(rms, 1e-6))
        spec = np.abs(np.fft.rfft(seg * win[:len(seg)], n=hop * 2))
        freqs = np.fft.rfftfreq(hop * 2, 1.0 / SR)
        for b, (lo, hi) in enumerate(BANDS):
            bands[i, b] = float(np.sum(spec[(freqs >= lo) & (freqs < hi)]))
    floor = float(np.percentile(db, 10))
    gate = floor + gate_db
    voiced = db > gate
    if not voiced.any():
        return {"fps": fps, "open": [0.0] * n, "shape": ["closed"] * n}
    top = float(np.percentile(db[voiced], 95))
    low = max(gate, float(np.percentile(db[voiced], 20)) - 2.0)
    raw = np.clip((db - low) / max(top - low, 1e-6), 0.0, 1.0) ** 1.2
    raw[~voiced] = 0.0
    tau = max(0.008, release_ms / 1000.0)
    attack = tau / 3.0
    y = 0.0
    out = np.zeros(n, dtype=np.float32)
    for i, v in enumerate(raw):                       # fast open, slow close: no chatter between syllables
        t = attack if v > y else tau
        y += (float(v) - y) * (1.0 - math.exp(-1.0 / (t * fps)))
        out[i] = min(1.0, max(0.0, y))
    lead = int(round(lead_ms / 1000.0 * fps))
    if lead:
        out = np.concatenate([out[lead:], np.zeros(lead, dtype=np.float32)])
    med_band = np.median(bands[voiced], axis=0) + 1e-9
    z = (bands[voiced] - med_band) / med_band
    shapes = ["closed"] * n
    vi = np.where(voiced)[0]
    for k, i in enumerate(vi):
        if out[i] < 0.08:
            shapes[i] = "closed"
        elif z[k, 2] > 0.6:
            shapes[i] = "wide"
        elif z[k, 1] < -0.6 and z[k, 2] < 0.3:
            shapes[i] = "round"
        else:
            shapes[i] = "open"
    out_shapes = []
    for i in range(n):                                 # five-frame majority: a single frame cannot flicker
        near = shapes[max(0, i - 2):i + 3]
        out_shapes.append(max(set(near), key=near.count))
    return {"fps": fps, "open": [round(float(v), 3) for v in out], "shape": out_shapes}


def save(path, out_json):
    """Measure once, keep the curve beside the take (the renderer reads it from the bundle)."""
    data = curve(path)
    with open(out_json, "w") as f:
        json.dump(data, f)
    return data


def write_wav(path, seconds=2.0, fps=FPS, bursts=((0.2, 0.6), (1.0, 1.4)), sr=SR):
    """A test voice: silence with short bursts (used by the tests, and handy when a take is silent and must be checked)."""
    n = int(seconds * sr)
    x = np.zeros(n, dtype=np.int16)
    for a, b in bursts:
        i, j = int(a * sr), int(min(seconds, b) * sr)
        t = np.arange(j - i) / sr
        x[i:j] = (0.3 * np.sin(2 * math.pi * 1000 * t) * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(x.tobytes())
    return path
