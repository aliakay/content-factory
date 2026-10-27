"""Synthesised, royalty-free sound effects and their automatic placement.

Placement rules distilled from the sound-design training shared by the user (whooshes for movement with the peak on
the fastest frame, textures for pops/clicks, one riser + hit into the main segment, levels whoosh -12 / textures -6..-7 /
riser -5 dB) and the WeAreNoCode style guide (silence is the default; no whoosh under text in subtle mode).
"""
import os, wave

import numpy as np

from .config import ROOT
LIB = os.path.join(ROOT, "assets", "sfx")
SR = 48000
PEAKS = {"whoosh": 0.62, "pop": 0.0, "tick": 0.0, "riser": 1.6, "hit": 0.0}  # where the audible peak sits (s)
LEVELS = {"subtle": {"whoosh": -16, "pop": -11, "tick": -13, "riser": -9, "hit": -10},
          "full": {"whoosh": -12, "pop": -7, "tick": -9, "riser": -5, "hit": -6}}
MOVING = ("slideleft", "slideup", "smoothleft", "wipeleft", "zoomin", "circleopen")


def _write(name, x):
    x = x / (np.abs(x).max() + 1e-9) * 10 ** (-3 / 20)  # peak-normalise to -3 dBFS
    os.makedirs(LIB, exist_ok=True)
    with wave.open(os.path.join(LIB, f"{name}.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((x * 32767).astype(np.int16).tobytes())


def _lowpass_sweep(x, cutoffs):
    y, prev = np.empty_like(x), 0.0
    for i, (v, fc) in enumerate(zip(x, cutoffs)):
        a = 1 - np.exp(-2 * np.pi * fc / SR)
        prev += a * (v - prev)
        y[i] = prev
    return y


def build_library(force=False):
    if os.path.isdir(LIB) and not force and all(os.path.exists(os.path.join(LIB, f"{k}.wav")) for k in PEAKS):
        return LIB
    rng = np.random.default_rng(7)
    # whoosh: pink-ish noise through a low-pass that opens then closes; peak at 62 % of 1 s
    d = 1.0
    t = np.arange(int(SR * d)) / SR
    tp = PEAKS["whoosh"]
    env = np.where(t < tp, (t / tp) ** 2.2, np.exp(-(t - tp) * 9))
    fc = 300 + 3200 * np.where(t < tp, (t / tp) ** 1.5, np.exp(-(t - tp) * 6))
    _write("whoosh", _lowpass_sweep(rng.standard_normal(len(t)), fc) * env)
    # pop: fast downward pitch blip
    t = np.arange(int(SR * 0.16)) / SR
    f = 380 + 1500 * np.exp(-38 * t)
    _write("pop", np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-28 * t))
    # tick: short bright click
    t = np.arange(int(SR * 0.035)) / SR
    n = np.diff(rng.standard_normal(len(t) + 1))
    _write("tick", (n * 0.6 + np.sin(2 * np.pi * 2400 * t)) * np.exp(-260 * t))
    # riser: rising sweep + noise, crescendo to the end
    d = PEAKS["riser"]
    t = np.arange(int(SR * d)) / SR
    f = 150 * (900 / 150) ** (t / d)
    tone = np.sin(2 * np.pi * np.cumsum(f) / SR)
    noise = _lowpass_sweep(rng.standard_normal(len(t)), 500 + 5000 * (t / d) ** 2)
    _write("riser", (0.6 * tone + 0.8 * noise) * (t / d) ** 3)
    # hit: sub thump with a transient
    t = np.arange(int(SR * 0.9)) / SR
    f = 50 + 90 * np.exp(-22 * t)
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-5 * t)
    click = rng.standard_normal(len(t)) * np.exp(-120 * t) * 0.5
    _write("hit", body + click)
    return LIB


def plan(idea, montage, timing, level="subtle"):
    """List of {t, kind, gain_db} in output seconds. `montage` is the montage spec, `timing` its starts/total."""
    if level not in LEVELS:
        return []
    L, starts, total = LEVELS[level], timing["starts"], timing["total"]
    beats = idea.get("beats", [])
    beat_starts = [float(b.get("t0", 0)) for b in beats]
    events = []

    def add(t, kind):
        t = round(t, 3)
        if 0 <= t <= total:
            events.append({"t": t, "kind": kind, "gain_db": L[kind]})

    for i, sh in enumerate(montage["shots"][1:], start=1):
        trans, xd = sh.get("trans", "fade"), sh.get("xd", 0.3)
        mid = starts[i] + xd / 2
        near_text = any(abs(bs - mid) < 0.25 for bs in beat_starts)
        if trans in MOVING and (level == "full" or not near_text):
            add(mid, "whoosh")
        elif trans == "fadewhite":
            add(starts[i], "tick")
    for b in beats:
        t0 = float(b.get("t0", 0))
        if b.get("animation") in ("pop", "highlight"):
            add(t0 + 0.08, "pop")
        elif b.get("type") == "card":
            add(t0 + 0.05, "tick")
        elif b.get("animation") == "counter":
            add(t0 + 0.8, "pop")
    # one riser + hit into the main segment: the first beat boundary after ~3 s (end of the hook)
    if total >= 8:
        cand = [bs for bs in beat_starts if 2.5 <= bs <= min(8.0, total - 2)]
        if cand:
            hit_t = cand[0]
            add(hit_t - 0.001, "riser")
            add(hit_t, "hit")
    # silence is the default: thin out anything closer than 0.6 s (subtle) / 0.3 s (full) to the previous sound
    gap = 0.6 if level == "subtle" else 0.3
    events.sort(key=lambda e: e["t"])
    kept = []
    for e in events:
        if e["kind"] in ("riser", "hit") or not kept or e["t"] - kept[-1]["t"] >= gap:
            kept.append(e)
    return kept


def to_render(events):
    """Render-spec entries: file + the time the FILE should start so its peak lands on t."""
    build_library()
    return [{"file": os.path.join(LIB, f"{e['kind']}.wav"), "start": max(0.0, e["t"] - PEAKS[e["kind"]]),
             "gain_db": e["gain_db"], "kind": e["kind"], "t": e["t"]} for e in events]
