"""Ears for the factory: measure a finished mix the way a sound supervisor would listen to it, and draw it as one
picture an agent can read (the "sheet"). Model-free (numpy + ffmpeg), so it runs on every final render.

Reverse-engineered from the listening workflows the creator shared (earshot's QA sections, HyperFrames' audio check,
the launch-film norms) and turned into checks for OUR mixes:
  silent      a video over ~15 s that tells something has no sound
  loudness    integrated LUFS / true peak off target (-14 LUFS, <= -1 dBTP)
  peak_place  the loudest moment sits in the last 15 % (it belongs on the drop / reveal, ~30-60 % in), not on the logo
  head        the first frame is dead silent for too long, or starts with a click
  tail        the film stops mid-sound instead of a tail into silence
  low_end     most of the energy sits under 150 Hz: plays as nothing on a phone speaker
  harsh       2-6 kHz spikes far above the mix's own presence: the band that hurts first on phones
  clicks      >12 kHz bursts concentrated in ~1 ms (a splice or an effect cut without a fade)
  density     more than ~8 designed effects in a 10 s window (good sound design mostly disappears)
  machinegun  the same effect 4+ times at a regular interval with no variation
  masked      effects that land on words (the mix pulls them down; listed so the designer can move them)
  ratio       the voice is not clearly above the music (~10 dB by RMS is the target)
"""
import os, subprocess

import numpy as np

from .config import FFMPEG

SR = 24000


def decode(path, sr=SR):
    r = subprocess.run([FFMPEG, "-v", "error", "-i", path, "-vn", "-f", "f32le", "-ac", "1", "-ar", str(sr), "-"],
                       capture_output=True)
    return np.frombuffer(r.stdout, dtype=np.float32) if r.returncode == 0 else np.zeros(0, np.float32)


def db(x):
    return 20 * np.log10(np.maximum(x, 1e-9))


def frames_rms(y, sr, win=0.4, hop=0.1):
    n, h = int(win * sr), int(hop * sr)
    if len(y) < n:
        return np.array([]), np.array([])
    idx = np.arange(0, len(y) - n, h)
    r = np.array([np.sqrt(np.mean(y[i:i + n].astype(np.float64) ** 2)) for i in idx])
    return (idx + n / 2) / sr, db(r)


def band_energy(y, sr, lo, hi):
    spec = np.abs(np.fft.rfft(y.astype(np.float64))) ** 2
    f = np.fft.rfftfreq(len(y), 1 / sr)
    return float(spec[(f >= lo) & (f < hi)].sum()), float(spec.sum() + 1e-12)


def click_times(y, sr, max_n=12):
    """Very short high-frequency bursts: a first difference far above its local level, isolated in time."""
    if len(y) < sr:
        return []
    d = np.abs(np.diff(y.astype(np.float64)))
    win = int(0.05 * sr)
    local = np.convolve(d, np.ones(win) / win, mode="same") + 1e-6
    ratio = d / local
    hits = np.where((ratio > 14) & (d > 0.03))[0]
    out, last = [], -1.0
    for i in hits:
        t = i / sr
        if t - last > 0.2:
            out.append(round(t, 3))
            last = t
    return out[:max_n]


def review(path, cues=None, words=None, voice_offset=0.0, total=None, voice_file=None, music=None, lufs=None):
    """Findings + metrics for a finished file. cues = [{t, kind, gain_db}] as placed; words = [[w, s, e]] of the voice
    file starting at voice_offset; music = {"file", "db"} to estimate the voice / music ratio."""
    y = decode(path)
    findings, m = [], {}
    dur = total or (len(y) / SR)
    m["duration"] = round(dur, 2)

    def add(kind, sev, detail, t=None):
        findings.append({"kind": kind, "severity": sev, "detail": detail, **({"t": round(float(t), 2)} if t is not None else {})})

    if len(y) == 0 or float(np.max(np.abs(y))) < 1e-4:
        if dur > 15:
            add("silent", "fail", "no sound at all in a film over 15 s")
        return {"findings": findings, "metrics": m}
    ts, lv = frames_rms(y, SR)
    if lufs is None:
        try:
            from .engines import loudness
            lufs = loudness(path)
        except Exception:
            lufs = (None, None)
    m["lufs"], m["true_peak"] = lufs
    if lufs[0] is not None and abs(lufs[0] + 14) > 1.5:
        add("loudness", "warn", f"{lufs[0]:.1f} LUFS (target -14)")
    if lufs[1] is not None and lufs[1] > -1.0:
        add("loudness", "warn", f"true peak {lufs[1]:.1f} dBTP (keep <= -1)")
    if len(lv):
        i = int(np.argmax(lv))
        m["loudest_at"], m["loudest_share"] = round(float(ts[i]), 2), round(float(ts[i] / max(dur, 0.1)), 2)
        if dur > 12 and ts[i] / dur > 0.85:
            add("peak_place", "warn", f"the loudest moment is at {ts[i]:.1f} s ({round(100 * ts[i] / dur)} % in): it "
                                      "belongs on the drop / reveal, not the ending", ts[i])
        m["lra_db"] = round(float(np.percentile(lv, 95) - np.percentile(lv, 10)), 1)
    head = y[:int(0.5 * SR)]
    if len(head) and float(np.max(np.abs(head))) < 10 ** (-50 / 20) and dur > 8:
        add("head", "info", "the first 0.5 s is silent: the first frame should enter with sound (or be deliberately quiet)")
    tail, before = y[-int(0.12 * SR):], y[-int(1.2 * SR):-int(0.6 * SR)]
    if len(tail) and len(before):
        t_db, b_db = db(np.sqrt(np.mean(tail ** 2))), db(np.sqrt(np.mean(before ** 2)))
        m["tail_db"] = round(float(t_db), 1)
        if t_db > -32 and t_db > b_db - 4:
            add("tail", "warn", f"ends mid-sound ({t_db:.0f} dBFS in the last 0.1 s): fade into a tail of silence", dur - 0.1)
    lo, tot = band_energy(y, SR, 20, 150)
    pres, _ = band_energy(y, SR, 2000, 6000)
    m["low_share"], m["presence_share"] = round(lo / tot, 3), round(pres / tot, 3)
    if lo / tot > 0.55:
        add("low_end", "warn", f"{round(100 * lo / tot)} % of the energy is under 150 Hz: on a phone speaker it plays as "
                               "almost nothing; lift the mids or thin the bass")
    clicks = [c for c in click_times(y, SR) if not any(abs(c - float(q["t"])) < 0.12 for q in cues or [])]  # our own taps
    if clicks:
        add("clicks", "warn", f"{len(clicks)} click(s) at {', '.join(f'{c:.2f}s' for c in clicks[:6])}: a cut without a fade",
            clicks[0])
    # 2-6 kHz harshness: 5 ms spikes in the presence band vs the band's own typical level
    try:
        from numpy.fft import irfft, rfft, rfftfreq
        Y = rfft(y.astype(np.float64))
        f = rfftfreq(len(y), 1 / SR)
        band = irfft(Y * ((f >= 2000) & (f <= 6000)), n=len(y))
        _, blv = frames_rms(band, SR, 0.005, 0.0025)
        if len(blv):
            spike = float(np.percentile(blv, 99.9) - np.median(blv[blv > np.percentile(blv, 30)]))
            m["harsh_spike_db"] = round(spike, 1)
            if spike > 30:
                add("harsh", "info", f"2-6 kHz spikes {spike:.0f} dB over the band's typical level: soften the brightest effects")
    except MemoryError:
        pass
    cues = sorted(cues or [], key=lambda c: c["t"])
    m["effects"] = len(cues)
    for a in np.arange(0, max(0.0, dur - 5), 5.0):
        n = sum(a <= c["t"] < a + 10 for c in cues)
        if n > 8:
            add("density", "warn", f"{n} effects between {a:.0f}-{a + 10:.0f} s (aim for ~5 per 10 s; thin the small ones)", a)
            break
    by = {}
    for c in cues:
        by.setdefault(c["kind"], []).append(c)
    for kind, cs in by.items():
        if len(cs) >= 4:
            gaps = np.diff([c["t"] for c in cs])
            if len(gaps) >= 3 and np.std(gaps) < 0.15 * np.mean(gaps) and not any(c.get("take") for c in cs):
                add("machinegun", "warn", f"'{kind}' {len(cs)} times at a regular {np.mean(gaps):.2f} s with no variation", cs[0]["t"])
    if words:
        spans = [(s + voice_offset, e + voice_offset) for _, s, e in words]
        masked = [c for c in cues if any(a - 0.02 <= c["t"] <= b for a, b in spans) and
                  c["kind"] not in ("riser", "drone")]
        m["on_words"] = len(masked)
        if len(masked) > max(3, len(cues) // 3):
            add("masked", "info", f"{len(masked)} of {len(cues)} effects land on words (pulled under the voice); big ones "
                                  "read better in the gaps between lines", masked[0]["t"])
    if voice_file and music and os.path.exists(voice_file) and os.path.exists(music.get("file", "")):
        v, mu = decode(voice_file), decode(music["file"])
        if len(v) and len(mu):
            rv = db(np.sqrt(np.mean(v[np.abs(v) > 0.01] ** 2))) if np.any(np.abs(v) > 0.01) else -60
            rm = db(np.sqrt(np.mean(mu ** 2))) + float(music.get("db", -18))
            m["voice_over_music_db"] = round(float(rv - rm), 1)
            if rv - rm < 7:
                add("ratio", "warn", f"the voice is only {rv - rm:.0f} dB over the music (target ~10 dB)")
    return {"findings": findings, "metrics": m}


def sheet(path, out_png, cues=None, words=None, voice_offset=0.0, title=""):
    """One picture of the mix for an agent that reads images: waveform, spectrogram, loudness curve, word spans and
    effect cues on one time axis."""
    from PIL import Image, ImageDraw, ImageFont
    y = decode(path, 16000)
    sr = 16000
    W, H = 1600, 560
    im = Image.new("RGB", (W, H), (14, 16, 22))
    d = ImageDraw.Draw(im)
    dur = max(len(y) / sr, 0.1)
    X = lambda t: int(60 + (W - 80) * t / dur)  # noqa: E731
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None
    d.text((10, 6), f"{title}  {dur:.1f} s", fill=(230, 230, 230), font=font)
    # spectrogram (log magnitude, 64 bands up to 8 kHz)
    n, hop = 512, 160
    if len(y) > n:
        idx = np.arange(0, len(y) - n, hop)
        frames = y[idx[:, None] + np.arange(n)[None, :]] * np.hanning(n)
        S = np.log1p(30 * np.abs(np.fft.rfft(frames, axis=1)))[:, :256]
        S = (S / (S.max() + 1e-9) * 255).astype(np.uint8)
        spec = Image.fromarray(np.flipud(S.T)).resize((W - 80, 200))
        spec = Image.merge("RGB", (spec, spec.point(lambda v: v * 0.55), spec.point(lambda v: 60 + v * 0.6)))
        im.paste(spec, (60, 30))
    d.text((8, 120), "spec", fill=(150, 150, 150), font=font)
    # waveform
    if len(y):
        cols = W - 80
        step = max(1, len(y) // cols)
        env = np.abs(y[:cols * step]).reshape(-1, step).max(axis=1)
        for i, v in enumerate(env):
            h = int(min(1, v) * 70)
            d.line([(60 + i, 320 - h), (60 + i, 320 + h)], fill=(110, 200, 255))
    d.text((8, 315), "wave", fill=(150, 150, 150), font=font)
    # loudness curve
    ts, lv = frames_rms(y, sr)
    if len(lv):
        pts = [(X(t), int(470 - (max(-60, v) + 60) / 60 * 70)) for t, v in zip(ts, lv)]
        d.line(pts, fill=(255, 210, 90), width=2)
        i = int(np.argmax(lv))
        d.text((X(ts[i]) - 10, 392), "max", fill=(255, 210, 90), font=font)
    d.text((8, 440), "loud", fill=(150, 150, 150), font=font)
    for _, s, e in words or []:
        d.rectangle([X(s + voice_offset), 500, max(X(s + voice_offset) + 1, X(e + voice_offset)), 508], fill=(90, 220, 140))
    for c in cues or []:
        x = X(c["t"])
        d.line([(x, 30), (x, 515)], fill=(255, 90, 90), width=1)
        d.text((x + 2, 518 + (hash(c["kind"]) % 3) * 12), c["kind"][:8], fill=(255, 140, 140), font=font)
    for t in range(0, int(dur) + 1, 5 if dur > 30 else 2):
        d.text((X(t), H - 14), f"{t}s", fill=(120, 120, 120), font=font)
    im.save(out_png)
    return out_png


def as_text(report, limit=10):
    return [f"sound {f['kind']} ({f['severity']})" + (f" @ {f['t']:.2f}s" if "t" in f else "") + f": {f['detail']}"
            for f in (report or {}).get("findings", [])[:limit]]
