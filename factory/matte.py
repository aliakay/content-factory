"""Subject mattes for text-behind-subject (stylecut layers with "behind": true), frame break and vertigo.

Backend: rembg with the small u2netp model (ONNX, ~5 MB, CPU) when installed:
    ~/.local/bin/uv pip install --python .venv/bin/python "rembg[cpu]"
Only frames inside the layers' time windows are segmented (at 320 px, then scaled up and softened); the rest of the
matte is black. Without a backend `matte_video` raises NoBackend and the renderer draws the text on top instead.
"""
import os, subprocess

import numpy as np
from PIL import Image, ImageFilter

from .config import FFMPEG, FFPROBE

SEG_PX = 320
_session = None


class NoBackend(RuntimeError):
    pass


def backend():
    global _session
    if _session is None:
        try:
            from rembg import new_session
            _session = new_session("u2netp")
        except Exception as e:
            raise NoBackend(f"rembg not available ({type(e).__name__})")
    return _session


def segment(img):
    """PIL RGB -> PIL L mask (white = subject) at the image size."""
    from rembg import remove
    small = img.copy()
    small.thumbnail((SEG_PX, SEG_PX))
    m = remove(small, session=backend(), only_mask=True)
    return m.resize(img.size, Image.BILINEAR).filter(ImageFilter.GaussianBlur(2))


def _size(path):
    r = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                        "-of", "csv=p=0", path], capture_output=True, text=True).stdout.strip().split(",")
    return int(r[0]), int(r[1])


def matte_video(src, dst, windows, fps=30, seg=None):
    """Grey matte video for `src`: subject masks inside `windows` [(start, end) s], black elsewhere.
    `seg` replaces the segmenter (tests)."""
    seg = seg or segment
    if seg is segment:
        backend()                      # fail before decoding anything
    w, h = _size(src)
    dec = subprocess.Popen([FFMPEG, "-v", "error", "-i", src, "-vf", f"fps={fps}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                           stdout=subprocess.PIPE, stdin=subprocess.DEVNULL)
    enc = subprocess.Popen([FFMPEG, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{w}x{h}", "-r", str(fps),
                            "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "10", "-pix_fmt", "yuv420p", dst],
                           stdin=subprocess.PIPE)
    black = np.zeros((h, w), dtype=np.uint8).tobytes()
    k, size = 0, w * h * 3
    last = None
    try:
        while True:
            raw = dec.stdout.read(size)
            if len(raw) < size:
                break
            t = k / fps
            if any(a - 0.1 <= t <= b + 0.1 for a, b in windows):
                if k % 2 == 0 or last is None:    # segment every other frame; the subject moves little in 1/15 s
                    last = seg(Image.frombytes("RGB", (w, h), raw)).convert("L").tobytes()
                enc.stdin.write(last)
            else:
                last = None
                enc.stdin.write(black)
            k += 1
    finally:
        enc.stdin.close()
        dec.kill()
        dec.wait()
    if enc.wait() or not os.path.exists(dst):
        raise RuntimeError("matte encode failed")
    return dst
