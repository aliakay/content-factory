"""Machine-specific settings in one place, so a fresh clone runs anywhere.

Values come from the environment, else from `<ROOT>/config.env` (KEY=VALUE lines, see config.env.example), else from
defaults that work in any clone. Resolved values are exported back to the environment (CF_*) so child processes
(bin/*.py, motion/*.mjs) see the same paths.
"""
import os, shutil

ROOT = os.path.realpath(os.environ.get("CF_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load_env_file(path):
    try:
        lines = open(path).read().splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), os.path.expandvars(os.path.expanduser(v.strip().strip('"').strip("'"))))


_load_env_file(os.path.join(ROOT, "config.env"))
_load_env_file(os.path.join(ROOT, ".env"))   # API keys (YOUTUBE_API_KEY ...)


def _tool(env, name, *candidates):
    """Explicit env value, else the first existing candidate path, else `name` from PATH."""
    if os.environ.get(env):
        return os.environ[env]
    for c in candidates:
        c = os.path.expanduser(c)
        if os.path.exists(c):
            return c
    return shutil.which(name) or name


FFMPEG = _tool("CF_FFMPEG", "ffmpeg", "~/opt/bin/ffmpeg")
FFPROBE = _tool("CF_FFPROBE", "ffprobe", "~/opt/bin/ffprobe")
CLAUDE = _tool("CF_CLAUDE", "claude", "~/.local/bin/claude")
NODE = _tool("CF_NODE", "node")
# Chromium runtime libraries unpacked without root (only needed on machines without system Chromium deps)
CHROME_LIBS = os.environ.get("CF_CHROME_LIBS") or ":".join(
    p for p in (os.path.expanduser("~/opt/chromelibs/root/usr/lib/x86_64-linux-gnu"),
                os.path.expanduser("~/opt/chromelibs/root/usr/lib/x86_64-linux-gnu/gbm")) if os.path.isdir(p))
# Studio / panels bind to this address; empty = the machine's Tailscale IP, else 127.0.0.1
HOST = os.environ.get("CF_HOST", "")
STUDIO_PORT = int(os.environ.get("CF_STUDIO_PORT", "8501"))
SHORTS_PORT = int(os.environ.get("CF_SHORTS_PORT", "8095"))
STREAMLIT_PORT = int(os.environ.get("CF_STREAMLIT_PORT", "8503"))

WORK = os.path.join(ROOT, "work")
# headless Claude runs with cwd=WORK, so the CLI keeps its transcripts here (read by factory/usage.py)
CLAUDE_TRANSCRIPTS = os.path.join(os.path.expanduser("~/.claude/projects"), WORK.replace("/", "-").replace(".", "-"))

for _k, _v in (("CF_ROOT", ROOT), ("CF_FFMPEG", FFMPEG), ("CF_FFPROBE", FFPROBE), ("CF_CLAUDE", CLAUDE),
               ("CF_CHROME_LIBS", CHROME_LIBS)):
    os.environ.setdefault(_k, _v)
