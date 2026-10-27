"""Tempo and beat times of a music file, numpy only (no librosa on this VM).

Onset strength = half-wave-rectified spectral flux of a log-magnitude STFT; tempo = the strongest autocorrelation
lag of that envelope between 70 and 180 BPM (preferring ~110 BPM like librosa's prior); beats = the phase of a
pulse train at that tempo that collects the most onset energy, then each beat nudged to the nearest local peak.
Good enough to cut on the beat of steady pop/cinematic tracks; it is not a full dynamic-programming tracker.
"""
import os, subprocess

import numpy as np

from .config import FFMPEG
SR, N_FFT, HOP = 22050, 2048, 512


def load(path, sr=SR):
    raw = subprocess.run([FFMPEG, "-v", "error", "-i", path, "-f", "f32le", "-ac", "1", "-ar", str(sr), "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32)


def onset_envelope(y):
    n = 1 + max(0, (len(y) - N_FFT) // HOP)
    idx = np.arange(N_FFT)[None, :] + HOP * np.arange(n)[:, None]
    frames = y[idx] * np.hanning(N_FFT)[None, :]
    mag = np.log1p(100 * np.abs(np.fft.rfft(frames, axis=1)))
    flux = np.maximum(0, np.diff(mag, axis=0)).sum(axis=1)
    flux = np.r_[0, flux]
    flux -= np.convolve(flux, np.ones(16) / 16, mode="same")  # remove slow loudness drift
    return np.maximum(flux, 0)


def tempo(env, fps):
    ac = np.correlate(env - env.mean(), env - env.mean(), mode="full")[len(env) - 1:]
    lags = np.arange(len(ac))
    bpm = 60 * fps / np.maximum(lags, 1)
    ok = (bpm >= 70) & (bpm <= 180)
    prior = np.exp(-0.5 * (np.log2(bpm / 110) / 0.9) ** 2)
    score = np.where(ok, ac * prior, -np.inf)
    lag = int(np.argmax(score))
    return 60 * fps / lag, lag


def beats(path):
    """-> {"bpm": float, "beats": [seconds], "duration": seconds}. librosa's tracker when installed (uv pip),
    else the numpy fallback below."""
    y = load(path)
    try:
        import librosa
        bpm, bt = librosa.beat.beat_track(y=y, sr=SR, units="time")
        return {"bpm": round(float(bpm[0] if hasattr(bpm, "__len__") else bpm), 1),
                "beats": [round(float(b), 3) for b in bt], "duration": round(len(y) / SR, 2)}
    except ImportError:
        pass
    env = onset_envelope(y)
    fps = SR / HOP
    bpm, lag = tempo(env, fps)
    phase = max(range(lag), key=lambda p: env[p::lag].sum())
    grid = np.arange(phase, len(env), lag)
    out = []
    w = max(1, lag // 6)
    for g in grid:
        lo, hi = max(0, g - w), min(len(env), g + w + 1)
        out.append((lo + int(np.argmax(env[lo:hi]))) / fps)
    return {"bpm": round(float(bpm), 1), "beats": [round(b, 3) for b in out], "duration": round(len(y) / SR, 2)}


def grid(bpm, duration, offset=0.0):
    """A plain beat grid, for cutting to a tempo when the music is added later in the app."""
    step = 60.0 / bpm
    return [round(offset + i * step, 3) for i in range(int((duration - offset) / step) + 1)]


def snap(times, beat_times, max_shift=0.25):
    """Move each time to the nearest beat if one is within max_shift seconds."""
    b = np.asarray(beat_times)
    if not len(b):
        return list(times)
    out = []
    for t in times:
        j = int(np.argmin(np.abs(b - t)))
        out.append(float(b[j]) if abs(b[j] - t) <= max_shift else t)
    return out
