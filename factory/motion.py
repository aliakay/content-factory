"""Motion-graphics layers: HTML templates rendered to transparent video by motion/render.mjs (headless Chromium).

Templates live in motion/templates/*.html and take parameters through the URL hash. Any browser library works
inside a template (Anime.js, Three.js, PixiJS, p5.js, Matter.js, tsParticles, OGL ...) as long as the page exposes
a deterministic window.render(t). Results are cached by (template, params, duration).
"""
import hashlib, os, subprocess, urllib.parse

from .config import ROOT
MOTION = os.path.join(ROOT, "motion")
CACHE = os.path.join(ROOT, "work", "motion")


def templates():
    d = os.path.join(MOTION, "templates")
    return sorted(f[:-5] for f in os.listdir(d) if f.endswith(".html")) if os.path.isdir(d) else []


def render(template, params, duration, fps=30):
    """Render a template to work/motion/<hash>.mov (ProRes 4444 + alpha) and return its path relative to ROOT."""
    key = hashlib.sha1(f"{template}|{sorted(params.items())}|{duration}|{fps}".encode()).hexdigest()[:16]
    os.makedirs(CACHE, exist_ok=True)
    out = os.path.join(CACHE, f"{template}_{key}.mov")
    if not os.path.exists(out):
        page = os.path.join(MOTION, "templates", f"{template}.html") + "#" + urllib.parse.urlencode(params)
        subprocess.run(["node", os.path.join(MOTION, "render.mjs"), page, out + ".part.mov", str(duration), str(fps)],
                       check=True, cwd=MOTION)
        os.replace(out + ".part.mov", out)
    return os.path.relpath(out, ROOT)
