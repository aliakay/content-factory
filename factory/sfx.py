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
# The story / ad kit: one sound for every visible action (a knock, a light clunking off, a sign flipping, a tap on a
# phone, glass shattering, the logo landing). Each line: peak (s), default gain (dB under a 0 dB voice), what it is for.
# Effects sit 6-12 dB under the voice; factory/audiofx.no_mask keeps them off the words.
EXTRA = {
    "knock":     (0.0, -8,  "three knuckle knocks on glass or a door"),
    "buzz":      (0.0, -14, "fluorescent light hum / flicker (lights on, a sign buzzing)"),
    "clunk":     (0.0, -7,  "a big switch: lights or power going off"),
    "swish":     (0.18, -12, "a fast short whoosh: a card or object sliding in, a slash"),
    "glass":     (0.0, -9,  "glass shattering: something breaks, a fake card is smashed"),
    "impact":    (0.0, -7,  "a heavy hit with a long sub tail: the reveal, the twist"),
    "logo_hit":  (0.0, -8,  "a bright shimmer chord over a thump: the logo / product lands"),
    "typing":    (0.0, -14, "a burst of keyboard clicks: text being typed, a search bar"),
    "notify":    (0.0, -11, "a two-tone phone notification: a message, an alert arrives"),
    "click":     (0.0, -13, "a small UI tap: a button press, a toggle"),
    "heartbeat": (0.0, -10, "one lub-dub heartbeat: tension, fear"),
    "drone":     (0.0, -16, "a 4 s ominous low drone swelling: dread before something appears"),
    "alarm":     (0.0, -12, "a pulsing alert beep: a warning on a phone or radio (not a broadcast tone)"),
    "flip":      (0.05, -11, "a card / sign flipping over (OPEN -> CLOSED, NIGHT 1 -> NIGHT 2)"),
}
for _k, (_pk, _db, _) in EXTRA.items():
    PEAKS[_k] = _pk
    LEVELS["subtle"][_k] = _db - 3
    LEVELS["full"][_k] = _db
KINDS = {**{"whoosh": "movement", "pop": "something pops in", "tick": "a card / number appears",
            "riser": "build into the main segment", "hit": "lands on the end of the build"},
         **{k: v[2] for k, v in EXTRA.items()}}
BASE = ("whoosh", "pop", "tick", "riser", "hit")
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
    if force or not all(os.path.exists(os.path.join(LIB, f"{k}.wav")) for k in BASE):
        _build_base()
    for k in EXTRA:
        if force or not os.path.exists(os.path.join(LIB, f"{k}.wav")):
            _write(k, SYNTH[k](np.random.default_rng(sum(map(ord, k)))))
    return LIB


def _build_base():
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


def _t(d):
    return np.arange(int(SR * d)) / SR


def _sweep(f0, f1, d):
    t = _t(d)
    f = f0 * (f1 / f0) ** (t / d)
    return np.sin(2 * np.pi * np.cumsum(f) / SR)


def _knock(rng):
    out = np.zeros(int(SR * 0.62))
    for k, at in enumerate((0.0, 0.2, 0.36)):
        t = _t(0.16)
        body = np.sin(2 * np.pi * (190 - 25 * k) * t) * np.exp(-34 * t)
        tap = _lowpass_sweep(rng.standard_normal(len(t)), np.full(len(t), 2400.0)) * np.exp(-90 * t)
        i = int(at * SR)
        out[i:i + len(t)] += (body + 0.8 * tap) * (1 - 0.12 * k)
    return out


def _buzz(rng):
    t = _t(0.9)
    hum = sum(np.sin(2 * np.pi * 120 * h * t) / h for h in (1, 2, 3, 5, 7))
    flicker = 0.65 + 0.35 * (np.sin(2 * np.pi * 9 * t + rng.random() * 6) > -0.4)
    return hum * flicker * np.minimum(1, t / 0.02) * np.minimum(1, (0.9 - t) / 0.1)


def _clunk(rng):
    t = _t(0.7)
    click = rng.standard_normal(len(t)) * np.exp(-160 * t)
    thunk = np.sin(2 * np.pi * np.cumsum(70 + 60 * np.exp(-30 * t)) / SR) * np.exp(-9 * t)
    room = _lowpass_sweep(rng.standard_normal(len(t)), np.full(len(t), 600.0)) * np.exp(-6 * t) * 0.25
    return 0.6 * click + thunk + room


def _swish(rng):
    t = _t(0.34)
    tp = PEAKS["swish"]
    env = np.where(t < tp, (t / tp) ** 1.6, np.exp(-(t - tp) * 22))
    fc = 900 + 5200 * np.where(t < tp, t / tp, np.exp(-(t - tp) * 14))
    return _lowpass_sweep(rng.standard_normal(len(t)), fc) * env


def _glass(rng):
    t = _t(1.1)
    out = rng.standard_normal(len(t)) * np.exp(-14 * t) * 0.5
    out = out - _lowpass_sweep(out, np.full(len(t), 2500.0))      # keep the bright part only
    for _ in range(26):
        at, f = rng.random() * 0.5, 2500 + rng.random() * 5000
        i, tt = int(at * SR), _t(0.12)
        seg = np.sin(2 * np.pi * f * tt) * np.exp(-45 * tt) * (0.4 + 0.6 * rng.random())
        out[i:i + len(tt)] += seg[:len(out) - i]
    return out


def _impact(rng):
    t = _t(1.6)
    sub = np.sin(2 * np.pi * np.cumsum(38 + 80 * np.exp(-14 * t)) / SR) * np.exp(-2.6 * t)
    crack = _lowpass_sweep(rng.standard_normal(len(t)), 300 + 6000 * np.exp(-25 * t)) * np.exp(-12 * t)
    return sub + 0.7 * crack


def _logo_hit(rng):
    t = _t(1.8)
    chord = sum(np.sin(2 * np.pi * f * t + rng.random()) * np.exp(-(2.2 + i * 0.4) * t)
                for i, f in enumerate((880, 1318.5, 1760, 2637)))
    shimmer = np.sin(2 * np.pi * 6.5 * t) * 0.15 + 0.85
    thump = np.sin(2 * np.pi * np.cumsum(55 + 70 * np.exp(-20 * t)) / SR) * np.exp(-7 * t)
    return 0.45 * chord * shimmer + thump


def _typing(rng):
    out = np.zeros(int(SR * 0.62))
    at = 0.0
    while at < 0.55:
        t = _t(0.03)
        k = rng.standard_normal(len(t)) * np.exp(-220 * t) + 0.5 * np.sin(2 * np.pi * (1800 + 900 * rng.random()) * t) * np.exp(-260 * t)
        i = int(at * SR)
        out[i:i + len(t)] += k[:len(out) - i] * (0.6 + 0.4 * rng.random())
        at += 0.055 + 0.05 * rng.random()
    return out


def _notify(rng):
    a, b = _t(0.16), _t(0.42)
    tone = lambda f, t, dec: (np.sin(2 * np.pi * f * t) + 0.3 * np.sin(2 * np.pi * 2 * f * t)) * np.exp(-dec * t)  # noqa: E731
    return np.concatenate([tone(1318.5, a, 18), tone(1760, b, 7)])


def _click(rng):
    t = _t(0.03)
    return (rng.standard_normal(len(t)) * 0.4 + np.sin(2 * np.pi * 3200 * t)) * np.exp(-300 * t)


def _heartbeat(rng):
    out = np.zeros(int(SR * 0.9))
    for at, g in ((0.0, 1.0), (0.24, 0.7)):
        t = _t(0.22)
        beat = np.sin(2 * np.pi * np.cumsum(45 + 40 * np.exp(-25 * t)) / SR) * np.exp(-16 * t) * g
        i = int(at * SR)
        out[i:i + len(t)] += beat
    return out


def _drone(rng):
    t = _t(4.0)
    pad = sum(np.sin(2 * np.pi * f * t + rng.random() * 6) * g for f, g in ((55, 1), (55.4, 0.8), (82.4, 0.5), (110.3, 0.3)))
    air = _lowpass_sweep(rng.standard_normal(len(t)), np.full(len(t), 400.0)) * 0.3
    swell = np.minimum(1, t / 2.6) ** 2 * np.minimum(1, (4.0 - t) / 0.6)
    return (pad + air) * swell


def _alarm(rng):
    out = np.zeros(int(SR * 1.2))
    for k in range(4):
        t = _t(0.16)
        beep = np.sign(np.sin(2 * np.pi * 1046.5 * t)) * 0.5 + np.sin(2 * np.pi * 2093 * t) * 0.3
        i = int(k * 0.3 * SR)
        out[i:i + len(t)] += beep * np.minimum(1, t / 0.005) * np.minimum(1, (0.16 - t) / 0.01)
    return out


def _flip(rng):
    w = _swish(rng)[: int(SR * 0.12)] * 0.6
    c = np.zeros(int(SR * 0.25))
    c[: len(w)] += w
    k = _click(rng)
    i = int(PEAKS["flip"] * SR)
    c[i:i + len(k)] += k
    return c


SYNTH = {"knock": _knock, "buzz": _buzz, "clunk": _clunk, "swish": _swish, "glass": _glass, "impact": _impact,
         "logo_hit": _logo_hit, "typing": _typing, "notify": _notify, "click": _click, "heartbeat": _heartbeat,
         "drone": _drone, "alarm": _alarm, "flip": _flip}


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


def cue(kind, t, gain_db=None, level="full"):
    """One sound-effect cue at t seconds (peak on t). Unknown kinds -> None."""
    if kind not in PEAKS:
        return None
    return {"t": round(float(t), 3), "kind": kind,
            "gain_db": float(gain_db) if gain_db is not None else LEVELS[level][kind]}


# Where a sound sits against its picture (measured norms of professional films): clicks / taps land a hair BEFORE the
# visible press, impacts and contacts one frame AFTER it (light arrives first), whooshes peak on the move itself.
SYNC = {"click": -0.015, "typing": -0.01, "hit": 0.033, "impact": 0.033, "knock": 0.02, "clunk": 0.02, "glass": 0.02,
        "logo_hit": 0.033, "pop": 0.01, "tick": 0.0, "flip": 0.0}
# importance when a busy window has to be thinned: the big story sounds stay, small UI sounds go first
RANK = {"impact": 9, "logo_hit": 9, "clunk": 8, "glass": 8, "knock": 8, "hit": 7, "riser": 7, "alarm": 7, "notify": 6,
        "drone": 6, "heartbeat": 6, "flip": 5, "whoosh": 4, "swish": 4, "buzz": 4, "pop": 3, "click": 3, "tick": 2,
        "typing": 2}
TAKES = 3   # a repeated sound rotates through 3 takes (slight pitch / level), never the same take twice in a row


def clean_cues(raw, total, level="full", gap=0.12, cap=80, per10=9):
    """Cues from a designer (scene JS or an edit plan): known kinds inside the video, the same kind never twice within
    `gap` s, at most `per10` in any 10 s window (the least important go first; restraint is the norm, ~5 per 10 s) and
    `cap` in all. Repeats get rotating takes and a run of pops climbs in pitch."""
    out = []
    for c in raw or []:
        if not isinstance(c, dict):
            continue
        try:
            x = cue(c.get("kind"), float(c.get("t")), c.get("gain_db", c.get("db")), level)
        except (TypeError, ValueError):
            x = None
        if x and 0 <= x["t"] <= total and not any(o["kind"] == x["kind"] and abs(o["t"] - x["t"]) < gap for o in out):
            x["gain_db"] = max(-30.0, min(x["gain_db"], -3.0))
            out.append(x)
    out.sort(key=lambda e: e["t"])
    while True:   # thin the busiest 10 s window until every window is within budget
        busy = None
        for c in out:
            win = [o for o in out if c["t"] <= o["t"] < c["t"] + 10]
            if len(win) > per10:
                busy = win
                break
        if not busy:
            break
        out.remove(min(busy, key=lambda o: (RANK.get(o["kind"], 3), -o["t"])))
    seen, last_pop = {}, None
    for c in out:
        n = seen.get(c["kind"], 0)
        seen[c["kind"]] = n + 1
        if n:
            c["take"] = n % TAKES
        if c["kind"] in ("pop", "tick", "click") and last_pop and last_pop["kind"] == c["kind"] and c["t"] - last_pop["t"] < 0.7:
            c["semitones"] = min(4, last_pop.get("semitones", 0) + 1)    # a run climbs (+1 st per step)
        last_pop = c if c["kind"] in ("pop", "tick", "click") else last_pop
    return out[:cap]


def take_file(kind, take=0, semitones=0.0):
    """The library file for a kind, or a cached variant: takes differ by a few cents of pitch and ~1 dB (deterministic),
    semitones shifts a run. Variants are resampled from the same synthesis, so a material stays one material."""
    base = os.path.join(LIB, f"{kind}.wav")
    if not take and not semitones:
        return base
    cents = {0: 0, 1: -35, 2: 30}.get(take, 0) + 100 * semitones
    gain = {0: 0.0, 1: -1.2, 2: 0.8}.get(take, 0.0)
    out = os.path.join(LIB, "takes", f"{kind}_t{take}_{int(cents)}.wav")
    if os.path.exists(out):
        return out
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with wave.open(base) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float64) / 32768
    r = 2 ** (cents / 1200)
    idx = np.arange(0, len(x) - 1, r)
    y = np.interp(idx, np.arange(len(x)), x) * 10 ** (gain / 20)
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(y, -1, 1) * 32767).astype(np.int16).tobytes())
    return out


def to_render(events):
    """Render-spec entries: file + the time the FILE should start so its peak lands on t."""
    build_library()
    return [{"file": take_file(e["kind"], e.get("take", 0), e.get("semitones", 0)),
             "start": max(0.0, e["t"] + SYNC.get(e["kind"], 0.0) - PEAKS[e["kind"]] / 2 ** (e.get("semitones", 0) / 12)),
             "gain_db": e["gain_db"], "kind": e["kind"], "t": e["t"]} for e in events if e["kind"] in PEAKS]
