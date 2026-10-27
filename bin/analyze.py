#!/usr/bin/env python3
"""Score a raw clip to find its best moments.

Usage: analyze.py raw/clip.MOV [bucket_seconds]

Prints, per time bucket: sharpness (higher = crisper frames) and motion
(mean frame-to-frame change; lower = steadier camera). Good moments are
sharp and steady.
"""
import os, sys
import av
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from factory.config import ROOT  # noqa: E402


def laplacian_var(g):
    lap = (-4 * g[1:-1, 1:-1] + g[:-2, 1:-1] + g[2:, 1:-1] + g[1:-1, :-2] + g[1:-1, 2:])
    return float(lap.var())


def main(path, bucket=0.5):
    c = av.open(os.path.join(ROOT, path))
    stream = c.streams.video[0]
    stream.thread_type = "AUTO"
    rows, prev = [], None
    for frame in c.decode(stream):
        t = float(frame.time)
        g = frame.to_ndarray(format="gray", width=270, height=480).astype(np.float32)
        motion = float(np.abs(g - prev).mean()) if prev is not None else 0.0
        rows.append((t, laplacian_var(g), motion))
        prev = g
    rows = np.array(rows)
    print(f"{'time':>9} {'sharp':>7} {'motion':>7}")
    for b0 in np.arange(0, rows[:, 0].max() + 1e-6, bucket):
        m = (rows[:, 0] >= b0) & (rows[:, 0] < b0 + bucket)
        if m.any():
            print(f"{b0:4.1f}-{b0 + bucket:4.1f} {rows[m, 1].mean():7.0f} {rows[m, 2].mean():7.2f}")


if __name__ == "__main__":
    main(sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else 0.5)
