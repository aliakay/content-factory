"""Original music composer (t513): an agent writes a short score in a small ABC subset that lands on the video's scene
cues; it is played here with our own instruments (numpy synths, or note samples dropped into assets/samples/<inst>/),
mixed and written as an m4a. No credits: an alternative to ElevenLabs music. Our own code; the idea of
'score + sampled instruments' only.

Score: {"bpm": 96, "key": "Am", "meter": "4/4", "unit": "1/8",
        "voices": [{"inst": "pad", "abc": "[A,CE]8 | [F,A,C]8 |", "gain": 0.7, "pan": -0.2}, ...]}
ABC subset: notes C D E F G A B (C = middle C), c d e ... one octave up, ' and , shift octaves; ^ sharp, _ flat,
= natural (until the bar line); a length after the note (2, 3, /2, 3/2, /) in units of `unit`; z rest; [CEG] chord;
| bar; (3abc triplet; a-a tie; a>b / a<b broken rhythm; !pp! !p! !mp! !mf! !f! !ff! dynamics; "Am" chord names are
ignored. Drums: C kick, D snare, E clap, F closed hat, G open hat, A tom, B crash (octave ignored).
"""
import glob, json, math, os, re, subprocess

import numpy as np
from scipy.signal import lfilter

from .config import FFMPEG, ROOT

SR = 44100
SAMPLES = os.path.join(ROOT, "assets", "samples")
INSTRUMENTS = {   # name -> (lowest, highest midi it sounds good in, default pan, what it is for)
    "piano": (36, 96, 0.0, "felt piano: chords, arpeggios, a melody"),
    "pad": (36, 84, 0.0, "soft synth pad: held chords under a voice"),
    "strings": (36, 91, 0.15, "string section: swells, long lines"),
    "bass": (28, 55, 0.0, "round bass: roots on the beat"),
    "pluck": (45, 93, -0.25, "plucked string: ostinatos, light rhythm"),
    "bell": (60, 100, 0.3, "soft bell: sparkle, an accent on a cue"),
    "lead": (55, 91, 0.1, "mellow lead: a short hook (never under narration)"),
    "drums": (0, 127, 0.0, "kit: C kick, D snare, E clap, F hat, G open hat, A tom, B crash"),
}
DYN = {"pp": 0.3, "p": 0.45, "mp": 0.6, "mf": 0.75, "f": 0.9, "ff": 1.0}
DRUMS = {"C": "kick", "D": "snare", "E": "clap", "F": "hat", "G": "openhat", "A": "tom", "B": "crash"}
_KEYS = {"C": 0, "G": 1, "D": 2, "A": 3, "E": 4, "B": 5, "F#": 6, "C#": 7, "F": -1, "Bb": -2, "Eb": -3, "Ab": -4,
         "Db": -5, "Gb": -6, "Cb": -7}
_MINOR = {"A": 0, "E": 1, "B": 2, "F#": 3, "C#": 4, "G#": 5, "D#": 6, "A#": 7, "D": -1, "G": -2, "C": -3, "F": -4,
          "Bb": -5, "Eb": -6, "Ab": -7}
_STEP = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


class ScoreError(ValueError):
    pass


# ---------- score ----------
def key_alters(key):
    """{'F': 1, ...}: the key signature as semitone shifts per letter. 'Am', 'Bbm', 'D', 'Ebmaj'."""
    k = str(key or "C").strip().replace("maj", "").replace("min", "m")
    minor = k.endswith("m") and k not in ("m",)
    root = k[:-1] if minor else k
    n = (_MINOR if minor else _KEYS).get(root)
    if n is None:
        raise ScoreError(f"unknown key {key!r}")
    order = "FCGDAEB" if n > 0 else "BEADGCF"
    return {c: (1 if n > 0 else -1) for c in order[:abs(n)]}


def _frac(s, default=1.0):
    s = str(s or "").strip()
    if not s:
        return default
    a, _, b = s.partition("/")
    return float(a) / float(b)


_NOTE = re.compile(r"(\^\^|\^|__|_|=)?([A-Ga-gzx])([',]*)(\d*)(/*)(\d*)")


def parse(abc, key="C", unit=0.125, drums=False):
    """ABC subset -> [(start, length, midi or drum name, velocity)] in whole notes. Raises ScoreError with the place."""
    alters, bar_acc = key_alters(key), {}
    out, t, vel, i, s = [], 0.0, DYN["mf"], 0, str(abc or "")
    tuplet, broken, tie = [0, 1.0], 1.0, False

    def note(m):
        acc, letter, octs, d1, sl, d2 = m.groups()
        ln = (float(d1) if d1 else 1.0) / (float(d2) if d2 else 2 ** len(sl) if sl else 1.0) if (d1 or sl) else 1.0
        if letter in "zx":
            return None, ln
        if drums:
            return DRUMS[letter.upper()], ln
        midi = 60 + _STEP[letter.upper()] + (12 if letter.islower() else 0) + 12 * octs.count("'") - 12 * octs.count(",")
        k = (letter.upper(), midi // 12)
        if acc:
            bar_acc[k] = {"^": 1, "^^": 2, "_": -1, "__": -2, "=": 0}[acc]
        midi += bar_acc.get(k, alters.get(letter.upper(), 0))
        return midi, ln

    def place(pitches, ln):
        nonlocal t, broken, tie, tuplet
        ln *= broken
        broken = 1.0
        if tuplet[0]:
            ln *= tuplet[1]
            tuplet[0] -= 1
        dur = ln * unit
        for p in pitches:
            if tie and out and out[-1][2] == p and abs(out[-1][0] + out[-1][1] - t) < 1e-6:
                out[-1] = (out[-1][0], out[-1][1] + dur, p, out[-1][3])
            elif p is not None:
                out.append((t, dur, p, vel))
        tie = False
        t += dur

    while i < len(s):
        c = s[i]
        if c.isspace() or c in ")`":
            i += 1
        elif c == '"':
            j = s.find('"', i + 1)
            i = len(s) if j < 0 else j + 1
        elif c == "!":
            j = s.find("!", i + 1)
            if j < 0:
                raise ScoreError(f"unclosed !...! at {i}")
            if s[i + 1:j] in DYN:
                vel = DYN[s[i + 1:j]]
            i = j + 1
        elif c in "|:]" or s.startswith("[|", i):
            bar_acc.clear()
            i += 2 if s.startswith("[|", i) else 1
        elif c == "(" and i + 1 < len(s) and s[i + 1].isdigit():
            n = int(s[i + 1])
            tuplet = [n, {2: 1.5, 3: 2 / 3, 4: 0.75, 5: 0.8, 6: 2 / 3}.get(n, 1.0)]
            i += 2
        elif c == "(":
            i += 1
        elif c == "-":
            tie = True
            i += 1
        elif c in "><":
            if not out:
                raise ScoreError(f"'{c}' before any note at {i}")
            k = 1.5 if c == ">" else 0.5
            last = out[-1]
            extra = last[1] * (k - 1)
            for j in range(len(out) - 1, -1, -1):          # every note of the last chord
                if abs(out[j][0] - last[0]) > 1e-9:
                    break
                out[j] = (out[j][0], out[j][1] * k, out[j][2], out[j][3])
            t += extra
            broken = 2 - k
            i += 1
        elif c == "[":
            j = s.find("]", i)
            if j < 0:
                raise ScoreError(f"unclosed chord at {i}")
            inner, pitches, lens, k = s[i + 1:j], [], [], 0
            while k < len(inner):
                if inner[k].isspace():
                    k += 1
                    continue
                m = _NOTE.match(inner, k)
                if not m or m.group(2) in "zx":
                    raise ScoreError(f"bad chord {inner!r} at {i}")
                p, ln = note(m)
                pitches.append(p)
                lens.append(ln)
                k = m.end()
            if not pitches:
                raise ScoreError(f"empty chord at {i}")
            m = re.compile(r"(\d*)(/*)(\d*)").match(s, j + 1)
            d1, sl, d2 = m.groups()
            outer = (float(d1) if d1 else 1.0) / (float(d2) if d2 else 2 ** len(sl) if sl else 1.0) if (d1 or sl) else 1.0
            place(pitches, lens[0] * outer)
            i = m.end()
        else:
            m = _NOTE.match(s, i)
            if not m:
                raise ScoreError(f"cannot read {s[i:i + 8]!r} at {i}")
            p, ln = note(m)
            place([p], ln)
            i = m.end()
    return out, t


def bars(abc, meter="4/4", unit=0.125):
    """Length of each bar (whole notes) as written, to catch a miscounted bar."""
    out = []
    for chunk in re.split(r"\|+|:\||\|:|\[\|", str(abc or "")):
        if chunk.strip():
            out.append(parse(chunk, unit=unit, drums=True)[1])        # lengths only: pitches do not matter
    return out


def whole_seconds(bpm, meter="4/4"):
    """Seconds of one whole note: the beat is the meter's denominator."""
    return 60.0 / float(bpm) * int(str(meter).split("/")[1])


def bar_seconds(bpm, meter="4/4"):
    return whole_seconds(bpm, meter) * _frac(meter)


def events(score):
    """All voices -> [(start s, length s, pitch, vel, voice index)] and the score's length in seconds."""
    unit, key, meter = _frac(score.get("unit") or "1/8"), score.get("key") or "C", score.get("meter") or "4/4"
    ws, out, end = whole_seconds(score["bpm"], meter), [], 0.0
    for vi, v in enumerate(score.get("voices") or []):
        evs, total = parse(v.get("abc", ""), key, unit, drums=v.get("inst") == "drums")
        out += [(a * ws, b * ws, p, vel, vi) for a, b, p, vel in evs]
        end = max(end, total * ws)
    return out, end


def problems(score, seconds=None):
    """What is wrong with a score, in words an agent can act on ([] = it plays)."""
    out = []
    try:
        bpm = float(score.get("bpm") or 0)
    except (TypeError, ValueError):
        bpm = 0
    if not 50 <= bpm <= 180:
        out.append("bpm must be 50-180")
        return out
    try:
        key_alters(score.get("key") or "C")
        unit = _frac(score.get("unit") or "1/8")
        bar = _frac(score.get("meter") or "4/4")
    except (ScoreError, ValueError, ZeroDivisionError) as e:
        return out + [f"header: {e}"]
    vs = score.get("voices") or []
    if not 1 <= len(vs) <= 6:
        out.append("1-6 voices")
    for v in vs:
        name = v.get("inst")
        if name not in INSTRUMENTS:
            out.append(f"unknown instrument {name!r} (use {', '.join(INSTRUMENTS)})")
            continue
        try:
            evs, _ = parse(v.get("abc", ""), score.get("key") or "C", unit, drums=name == "drums")
            lens = bars(v.get("abc", ""), score.get("meter") or "4/4", unit)
        except ScoreError as e:
            out.append(f"{name}: {e}")
            continue
        if not evs:
            out.append(f"{name}: no notes")
        wrong = [k + 1 for k, ln in enumerate(lens[:-1]) if abs(ln - bar) > 1e-6]
        if wrong:
            out.append(f"{name}: bars {wrong[:6]} do not add up to one {score.get('meter') or '4/4'} bar "
                       f"({round(bar / unit)} units of {score.get('unit') or '1/8'})")
        lo, hi = INSTRUMENTS[name][:2]
        off = sorted({p for _, _, p, _ in evs if isinstance(p, int) and not lo <= p <= hi})
        if off:
            out.append(f"{name}: notes outside its range {lo}-{hi} (midi {off[:4]})")
    if seconds and not out:
        _, end = events(score)
        if end < 0.5 * seconds:
            out.append(f"the score lasts {end:.1f} s; write at least {0.5 * seconds:.0f} s (it is looped to {seconds:.0f} s)")
    return out


# ---------- cues ----------
def fit_bpm(cues, lo=80, hi=128, meter="4/4", prefer=None):
    """The whole-number tempo that puts the scene starts closest to a half-bar line (prefer: a mood's tempo)."""
    cues = [c for c in cues if c > 0.5]
    best = None
    for bpm in range(int(lo), int(hi) + 1):
        half = bar_seconds(bpm, meter) / 2
        cost = sum(min(c % half, half - c % half) for c in cues) / max(1, len(cues))
        cost += 0.002 * abs(bpm - prefer) if prefer else 0.0
        if best is None or cost < best[0] - 1e-9:
            best = (cost, bpm)
    return best[1]


def where(t, bpm, meter="4/4"):
    """'bar 5 beat 3' (1-based, nearest beat) for a time in seconds."""
    beat = 60.0 / bpm * 4 / int(str(meter).split("/")[1])
    n = int(str(meter).split("/")[0])
    k = round(t / beat)
    return f"bar {k // n + 1} beat {k % n + 1}"


# ---------- instruments ----------
def _t(n):
    return np.arange(n) / SR


def _lp(x, hz):
    a = math.exp(-2 * math.pi * hz / SR)
    return lfilter([1 - a], [1, -a], x)


def _hp(x, hz):
    return x - _lp(x, hz)


def _release(y, dur, rel):
    n0 = int(dur * SR)
    if n0 < len(y):
        y[n0:] *= np.exp(-np.arange(len(y) - n0) / (rel * SR))
    return y


def _saw(f, t, phase=0.0):
    return 2 * ((f * t + phase) % 1.0) - 1


def _piano(f, dur, vel):
    t = _t(int((dur + 1.0) * SR))
    y = np.zeros_like(t)
    for k in range(1, 9):
        fk = f * k * math.sqrt(1 + 0.0004 * k * k)
        if fk > SR / 2.2:
            break
        y += (vel ** (0.12 * k)) / k ** 1.3 * np.sin(2 * math.pi * fk * t) * np.exp(-t * (1.2 + 0.7 * k) * (f / 440) ** 0.3)
    y *= np.minimum(1, t / 0.003)
    return _release(y, dur, 0.12) * vel


def _pad(f, dur, vel, attack=0.6, cut=1200.0, rel=0.8):
    t = _t(int((dur + rel * 2) * SR))
    y = sum(_saw(f * d, t, ph) for d, ph in ((1.0, 0), (1.004, 0.33), (0.996, 0.66))) / 3
    y = _lp(_lp(y, cut + 1200 * vel), cut + 1200 * vel)
    y *= np.minimum(1, t / attack)
    return _release(y, dur, rel) * vel


def _strings(f, dur, vel):
    t = _t(int((dur + 1.0) * SR))
    vib = 0.003 * np.sin(2 * math.pi * 5.2 * t) * np.minimum(1, t / 0.6)
    ph = np.cumsum(f * (1 + vib)) / SR
    y = sum(2 * ((ph * d + o) % 1.0) - 1 for d, o in ((1.0, 0), (1.006, 0.4), (0.994, 0.7))) / 3
    y = _lp(_lp(y, 1800 + 2000 * vel), 2600)
    y *= np.minimum(1, t / 0.25)
    return _release(y, dur, 0.45) * vel


def _bass(f, dur, vel):
    t = _t(int((dur + 0.3) * SR))
    y = np.sin(2 * math.pi * f * t) + 0.25 * _lp(_saw(f, t), 500)
    y *= np.minimum(1, t / 0.005) * (0.7 + 0.3 * np.exp(-t * 6))
    return np.tanh(1.4 * _release(y, dur, 0.06)) * vel


def _pluck(f, dur, vel):
    n, period = int((dur + 1.2) * SR), max(2, int(round(SR / f)))
    x = np.zeros(n)
    x[:period] = np.random.default_rng(int(f * 10)).uniform(-1, 1, period)
    y = _comb(x, period, 0.4975, 0.4975)            # Karplus-Strong
    return _release(_lp(y, 3000 + 3000 * vel), dur + 0.3, 0.15) * vel


def _bell(f, dur, vel):
    t = _t(int((dur + 2.0) * SR))
    y = np.sin(2 * math.pi * f * t + 2.5 * vel * np.exp(-t * 3) * np.sin(2 * math.pi * 3.5 * f * t))
    return y * np.exp(-t * 2.2) * np.minimum(1, t / 0.002) * vel * 0.7


def _lead(f, dur, vel):
    t = _t(int((dur + 0.3) * SR))
    y = np.tanh(3 * np.sin(2 * math.pi * f * t)) * 0.6 + 0.2 * _saw(f * 1.003, t)
    y = _lp(y, 2500 + 1500 * vel) * np.minimum(1, t / 0.012)
    return _release(y, dur, 0.1) * vel * 0.7


def _noise(n, seed):
    return np.random.default_rng(seed).uniform(-1, 1, n)


def _drum(name, vel):
    if name == "kick":
        t = _t(int(0.45 * SR))
        f = 45 + 75 * np.exp(-t * 28)
        y = np.sin(2 * math.pi * np.cumsum(f) / SR) * np.exp(-t * 7) + 0.3 * _noise(len(t), 1) * np.exp(-t * 300)
    elif name == "snare":
        t = _t(int(0.3 * SR))
        y = 0.55 * _hp(_noise(len(t), 2), 1200) * np.exp(-t * 14) + 0.5 * np.sin(2 * math.pi * 185 * t) * np.exp(-t * 22)
    elif name == "clap":
        t = _t(int(0.3 * SR))
        burst = sum(np.exp(-np.clip(t - o, 0, None) * 90) * (t >= o) for o in (0, 0.011, 0.022))
        y = _hp(_noise(len(t), 3), 900) * (burst + 0.5 * np.exp(-t * 12)) * 0.6
    elif name in ("hat", "openhat"):
        t = _t(int((0.08 if name == "hat" else 0.45) * SR))
        y = _hp(_hp(_noise(len(t), 4), 7000), 7000) * np.exp(-t * (45 if name == "hat" else 7)) * 0.5
    elif name == "tom":
        t = _t(int(0.4 * SR))
        f = 100 + 60 * np.exp(-t * 20)
        y = np.sin(2 * math.pi * np.cumsum(f) / SR) * np.exp(-t * 9)
    else:                                           # crash
        t = _t(int(1.8 * SR))
        y = _hp(_noise(len(t), 5), 4000) * np.exp(-t * 1.8) * 0.45
    return y * vel


SYNTHS = {"piano": _piano, "pad": _pad, "strings": _strings, "bass": _bass, "pluck": _pluck, "bell": _bell, "lead": _lead}


def _note_name(stem):
    m = re.fullmatch(r"([A-Ga-g])([#b]?)(-?\d)", stem)
    if m:
        return 12 * (int(m.group(3)) + 1) + _STEP[m.group(1).upper()] + {"#": 1, "b": -1, "": 0}[m.group(2)]
    return int(stem) if stem.isdigit() else None


_BANKS = {}


def bank(inst):
    """Note samples dropped into assets/samples/<inst>/ ('C4.wav', 'A#3.wav', '60.wav'; drums 'kick.wav', ...)."""
    if inst not in _BANKS:
        import soundfile as sf
        b = {}
        for f in sorted(glob.glob(os.path.join(SAMPLES, inst, "*.wav"))):
            stem = os.path.splitext(os.path.basename(f))[0]
            key = stem if inst == "drums" else _note_name(stem)
            if key is None:
                continue
            y, sr = sf.read(f, dtype="float32", always_2d=True)
            y = y.mean(axis=1)
            if sr != SR:
                y = np.interp(np.arange(int(len(y) * SR / sr)) * sr / SR, np.arange(len(y)), y)
            b[key] = y
        _BANKS[inst] = b
    return _BANKS[inst]


_NOTES = {}


def voice_note(inst, pitch, dur, vel):
    """One note as samples (a sampled instrument when its bank has it, else our synth); a repeated note is reused."""
    key = (inst, pitch, round(dur, 4), round(vel, 3))
    if key not in _NOTES:
        if len(_NOTES) > 4000:
            _NOTES.clear()
        _NOTES[key] = _voice_note(inst, pitch, dur, vel)
    return _NOTES[key]


def _voice_note(inst, pitch, dur, vel):
    b = bank(inst)
    if inst == "drums":
        return b[pitch] * vel if pitch in b else _drum(pitch, vel)
    if b:
        root = min(b, key=lambda k: abs(k - pitch))
        src, ratio = b[root], 2 ** ((pitch - root) / 12)
        n = min(int((dur + 0.6) * SR), int(len(src) / ratio))
        y = np.interp(np.arange(n) * ratio, np.arange(len(src)), src)
        return _release(y, dur, 0.2) * vel
    return SYNTHS[inst](440.0 * 2 ** ((pitch - 69) / 12), dur, vel)


# ---------- mix ----------
def _reverb(x, mix=0.16):
    """A small Schroeder room: four combs, two all-passes."""
    wet = np.zeros_like(x)
    for d, g in ((1557, 0.80), (1617, 0.79), (1491, 0.81), (1422, 0.80)):
        wet += _comb(x, d, g)
    for d, g in ((225, 0.5), (556, 0.5)):
        y = _comb(wet, d, g)                        # all-pass = -g x + (1 - g^2) comb(x)
        wet = -g * wet + (1 - g * g) * np.concatenate([np.zeros(d), y[:-d]])
    return x + mix * wet / 4


def _comb(x, d, g, g2=0.0):
    """y[n] = x[n] + g y[n-d] + g2 y[n-d-1], a block of d samples at a time (a long-delay lfilter is far too slow)."""
    y = np.zeros(len(x) + d + 1)
    y[d + 1:] = x
    for k in range(d + 1, len(y), d):
        e = min(k + d, len(y))
        y[k:e] += g * y[k - d:e - d] + (g2 * y[k - d - 1:e - d - 1] if g2 else 0.0)
    return y[d + 1:]


def render(score, seconds, dst):
    """Play the score for `seconds` (looped in whole bars when it is shorter, faded at the end) -> dst (.m4a/.wav)."""
    probs = problems(score)
    if probs:
        raise ScoreError("; ".join(probs))
    evs, end = events(score)
    bar = bar_seconds(score["bpm"], score.get("meter") or "4/4")
    loop = max(bar, math.ceil(end / bar - 1e-6) * bar)
    n = int((seconds + 2.5) * SR)
    voices = score["voices"]
    bufs = [np.zeros(n) for _ in voices]
    k = 0
    while k * loop < seconds:
        for a, ln, p, vel, vi in evs:
            st = int((a + k * loop) * SR)
            if st >= n or a + k * loop >= seconds:
                continue
            y = voice_note(voices[vi]["inst"], p, ln, vel)
            m = min(len(y), n - st)
            bufs[vi][st:st + m] += y[:m]
        k += 1
    left, right = np.zeros(n), np.zeros(n)
    for v, b in zip(voices, bufs):
        pan = float(v.get("pan", INSTRUMENTS[v["inst"]][2]))
        g = float(v.get("gain", 0.7))
        left += b * g * math.cos((pan + 1) * math.pi / 4)
        right += b * g * math.sin((pan + 1) * math.pi / 4)
    st = np.stack([_reverb(_hp(left, 30)), _reverb(_hp(right, 30))], axis=1)[:int(seconds * SR)]
    st = np.tanh(st / max(1e-6, np.abs(st).max()) * 1.2) / math.tanh(1.2) * 0.89
    fade = min(2.0, seconds / 4)
    st[-int(fade * SR):] *= np.linspace(1, 0, int(fade * SR))[:, None]
    st[:int(0.01 * SR)] *= np.linspace(0, 1, int(0.01 * SR))[:, None]
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    wav = os.path.splitext(dst)[0] + ".wav"
    import soundfile as sf
    sf.write(wav, st.astype(np.float32), SR, subtype="PCM_16")
    if not dst.endswith(".wav"):
        subprocess.run([FFMPEG, "-v", "error", "-y", "-i", wav, "-c:a", "aac", "-b:a", "160k", dst], check=True)
        os.remove(wav)
    return dst


# ---------- a score without an agent ----------
MOODS = {   # chord loop (roman numerals in the key), tempo, instruments
    "calm": (["i", "VI", "III", "VII"], 84, ["pad", "piano", "bass"]),
    "bright": (["I", "V", "vi", "IV"], 104, ["piano", "pluck", "bass", "drums"]),
    "tense": (["i", "i", "VI", "V"], 96, ["strings", "pad", "bass", "drums"]),
    "drive": (["i", "VII", "VI", "VII"], 118, ["pluck", "pad", "bass", "drums"]),
}
_ROMAN = {"i": 0, "ii": 2, "iii": 4, "iv": 5, "v": 7, "vi": 9, "vii": 11}
_MINOR_ROMAN = {"i": 0, "ii": 2, "iii": 3, "iv": 5, "v": 7, "vi": 8, "vii": 10}


def mood_of(prompt):
    p = str(prompt or "").lower()
    for m, words in (("tense", ("tense", "dark", "suspense", "gerilim", "karanlık", "ominous")),
                     ("drive", ("drive", "energetic", "upbeat", "hype", "enerjik", "hızlı", "punchy")),
                     ("bright", ("bright", "happy", "warm", "uplifting", "neşeli", "sıcak", "positive"))):
        if any(w in p for w in words):
            return m
    return "calm"


def _abc_note(midi):
    names = ["C", "^C", "D", "^D", "E", "F", "^F", "G", "^G", "A", "^A", "B"]
    o, pc = divmod(midi, 12)
    nm = names[pc]
    acc, letter = nm[:-1], nm[-1]
    if o >= 6:                                      # midi 72 = c
        return acc + letter.lower() + "'" * (o - 6)
    return acc + letter + "," * (5 - o)             # midi 60 = C


def auto_score(prompt="", seconds=30, cues=(), bpm=None):
    """A plain, valid score from the mood words (the fallback when no agent score plays): a 4-chord loop, key A minor
    or C major, an accent (crash/bell) on the bar each scene cue falls in."""
    mood = mood_of(prompt)
    prog, tempo, insts = MOODS[mood]
    bpm = bpm or fit_bpm(cues, tempo - 12, tempo + 12, prefer=tempo)
    minor = prog[0].islower() and prog[0] == "i"
    tonic = 57 if minor else 60                     # A3 / C4
    nbars = max(4, math.ceil(seconds / bar_seconds(bpm)))
    accents = {int(c // bar_seconds(bpm)) for c in cues if c > 0.5}
    vs = {i: [] for i in insts}
    for b in range(nbars):
        r = prog[b % len(prog)]
        deg = (_MINOR_ROMAN if minor else _ROMAN)[r.lower()]
        root = tonic + deg
        third = 3 if r.islower() else 4
        tri = [root, root + third, root + 7]
        tri = [x - 12 if x > 72 else x for x in tri]
        ch = "[" + "".join(_abc_note(x) for x in sorted(tri)) + "]"
        for inst in insts:
            if inst in ("pad", "strings"):
                vs[inst].append(("!mf!" if b in accents else "!p!") + ch + "8")
            elif inst == "piano":
                a, c3, e = sorted(tri)
                vs[inst].append(" ".join(_abc_note(x) for x in (a, e, c3 + 12, e, a + 12, e, c3 + 12, e)))
            elif inst == "pluck":
                a, c3, e = sorted(tri)
                vs[inst].append("".join(_abc_note(x + 12) for x in (a, c3, e, c3, a, c3, e, c3)))
            elif inst == "bass":
                lo = root - 24 if root - 24 >= 28 else root - 12
                vs[inst].append(_abc_note(lo) + "3" + _abc_note(lo) + " z2" + _abc_note(lo) + "2")
            elif inst == "drums":
                head = "[BC]" if b in accents else "C"
                vs[inst].append(f"{head}F DF CF DF" if mood != "calm" else f"{head}2 z2 D2 z2")
    gains = {"pad": 0.55, "strings": 0.5, "piano": 0.6, "pluck": 0.45, "bass": 0.7, "drums": 0.55}
    return {"bpm": bpm, "key": "Am" if minor else "C", "meter": "4/4", "unit": "1/8", "mood": mood, "auto": True,
            "voices": [{"inst": i, "abc": " | ".join(vs[i]) + " |", "gain": gains.get(i, 0.6)} for i in insts]}


# ---------- the agent ----------
GUIDE = """You compose original instrumental music for a short video. Write a score in this ABC subset and return JSON
only: {"bpm": <the given tempo>, "key": "Am", "meter": "4/4", "unit": "1/8", "voices": [{"inst": "...", "abc": "...",
"gain": 0.3-1.0, "pan": -1..1}], "notes": "one line: the idea"}.

ABC subset: C D E F G A B is the octave from middle C, c d e f g a b the one above, ' and , move an octave
(C, = one below, c' = two above). ^ sharp, _ flat, = natural (until the bar line); the key signature applies.
A length follows the note in units of 1/8: C (an eighth), C2 (a quarter), C4 (a half), C8 (a whole bar), C/2, C3/2.
z rest. [CEG]4 chord. | bar line: EVERY 4/4 bar must add up to exactly 8 units. (3CDE triplet. C-C tie.
!p! !mp! !mf! !f! dynamics until changed. Drums voice letters: C kick, D snare, E clap, F closed hat, G open hat,
A tom, B crash; chords like [CF] hit together.
Instruments (midi range): {instruments}.

Rules: 1-5 voices. Keep the given tempo so the cues land. Mark every cue: change the texture, add a crash or a bell, or
start a new chord there. {voice_rule} Write {bars} bars (it may be shorter; it is looped in whole bars and faded).
Original material only: never quote an existing melody."""


def write_score(prompt, seconds, cues, narrated=True, ask=None):
    """-> (score, meta). The agent writes the score (one retry with its problems); a plain mood score if it cannot."""
    from . import llm
    ask = ask or llm.ask
    mood = mood_of(prompt)
    bpm = fit_bpm([c["t"] for c in cues], MOODS[mood][1] - 14, MOODS[mood][1] + 14, prefer=MOODS[mood][1])
    nbars = math.ceil(seconds / bar_seconds(bpm))
    cue_txt = "\n".join(f"- {c['label']} at {c['t']:.2f} s = {where(c['t'], bpm)}" for c in cues if c["t"] > 0.5) or "- none"
    task = GUIDE.replace("{instruments}", "; ".join(f"{k} {v[0]}-{v[1]} ({v[3]})" for k, v in INSTRUMENTS.items())) \
        .replace("{voice_rule}", "A voice talks over it: stay soft (p/mp), sparse, low-mid; no lead melody." if narrated
                 else "No voice: the music leads; a clear hook and hits on the cues.") \
        .replace("{bars}", str(nbars))
    task += f"\n\nBrief: {prompt or 'a calm bed'}\nTempo: {bpm} bpm, {seconds:.1f} s, {nbars} bars\nCues:\n{cue_txt}\n"
    note, tries = "", []
    for _ in range(2):
        try:
            data, meta = ask(task + note, tools=(), timeout=600)
        except Exception as e:                          # no agent now: the plain score keeps the stage free and moving
            tries.append(f"agent failed: {e}"[:200])
            break
        sc = data if isinstance(data, dict) else {}
        sc["bpm"] = bpm
        probs = problems(sc, seconds)
        if not probs:
            return sc, {"agent": True, "tries": len(tries) + 1, "bpm": bpm}
        tries.append("; ".join(probs)[:400])
        note = "\n\nYour last score had these problems; fix them and return the whole JSON again:\n- " + "\n- ".join(probs)
    return auto_score(prompt, seconds, [c["t"] for c in cues], bpm), {"agent": False, "tries": len(tries), "bpm": bpm,
                                                                     "why": tries[-1] if tries else ""}


def compose(prompt, seconds, cues, dst, narrated=True, ask=None):
    """Score + play it. -> {"file", "score", "agent", "bpm", "credits": 0}"""
    score, meta = write_score(prompt, seconds, cues, narrated, ask)
    try:
        render(score, seconds, dst)
    except ScoreError as e:                             # a score that validated but does not play: the plain one
        score, meta = auto_score(prompt, seconds, [c["t"] for c in cues], meta["bpm"]), {**meta, "agent": False, "why": str(e)}
        render(score, seconds, dst)
    with open(os.path.splitext(dst)[0] + ".score.json", "w", encoding="utf-8") as f:
        json.dump(score, f, ensure_ascii=False, indent=1)
    return {"file": dst, "score": score, "credits": 0, **meta}


if __name__ == "__main__":       # python -m factory.compose "<mood words>" 20 out.m4a: the plain score, no agent
    import sys
    pr, secs, out = (sys.argv[1:] + ["calm", "20", os.path.join(ROOT, "work", "compose_demo.m4a")])[:3]
    sc = auto_score(pr, float(secs), [5.0, 10.0])
    print(render(sc, float(secs), out), json.dumps(sc)[:300])
