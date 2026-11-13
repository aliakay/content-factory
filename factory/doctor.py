"""Readiness report for the render host: `factory doctor` / `python -m factory.doctor`.

Every check is free and secret-free: it looks at versions, files and the presence of a key (never a value; at most
the last four characters), and it can spend nothing. `--online` adds two authenticated GET calls (ElevenLabs
subscription, Gemini model list) and is off by default, so the report runs on an air-gapped machine too.

A check is `ok`, `warn`, `fail` or `info`; only a `fail` on a `required` check makes the exit code non-zero, and every
check that is not ok carries a fix hint. The checks mirror install.sh and the tool registry (`factory/hat/tools.py`,
`available()`): the same ffmpeg filters, the same Playwright install, the same folders.
"""
import argparse
import glob
import importlib.util
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import urllib.request

from .config import CLAUDE, FFMPEG, FFPROBE, HOST, NODE, ROOT, STUDIO_PORT
from . import accounts

# The filters the render/audit path asks ffmpeg for (same list as the reference doctor, minus the ones we never call
# is not the point: a missing filter fails a render late, so the list is deliberately broad).
FILTERS = ("fps", "scale", "crop", "format", "setpts", "blackdetect", "freezedetect", "loudnorm", "silencedetect",
           "astats", "ametadata", "aresample", "asetnsamples")
REQUIRED_MODULES = {"numpy": "numpy", "pillow": "PIL", "streamlit": "streamlit", "faster-whisper": "faster_whisper",
                    "av": "av", "soundfile": "soundfile", "pytest": "pytest", "rembg": "rembg"}
MIN_PY = (3, 10)
DISK_WARN_GB = 5.0
DISK_FAIL_GB = 0.5
MIN_WHISPER = ("small", "small.en")


def _tr(en, tr):
    return {"tr": tr, "en": en}


def _run(cmd, args=(), timeout=8, cwd=None):
    """Run a tool with an argument array (no shell), bounded time and output; None when it cannot run."""
    try:
        r = subprocess.run([cmd, *args], capture_output=True, text=True, timeout=timeout, cwd=cwd,
                           stdin=subprocess.DEVNULL)
        return ((r.stdout or "") + (r.stderr or "")) if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def _version(text):
    m = re.search(r"\d+\.\d+(?:\.\d+)?", text or "")
    return m.group(0) if m else "?"


def _tail(key):
    key = (key or "").strip()
    return ("…" + key[-4:]) if key else None


def _which(exe):
    return exe if exe and os.path.exists(exe) else (shutil.which(os.path.basename(exe or "")) or None)


# ---------------------------------------------------------------- individual probes

def _python():
    v = ".".join(str(x) for x in sys.version_info[:3])
    ok = sys.version_info[:2] >= MIN_PY
    return {"status": "ok" if ok else "fail", "detail": _tr(f"Python {v}", f"Python {v}"),
            "hint": None if ok else _tr(f"install Python {MIN_PY[0]}.{MIN_PY[1]}+", "Python 3.10+ kur")}


def _venv(root):
    inside = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    local = os.path.join(root, ".venv", "bin", "python")
    if inside:
        return {"status": "ok", "detail": _tr(f"venv {sys.prefix}", f"venv {sys.prefix}"), "hint": None}
    if os.path.exists(local):
        return {"status": "warn", "detail": _tr("not running inside .venv", "venv dışında çalışıyor"),
                "hint": _tr(f"run {local}", f"{local} ile çalıştır")}
    return {"status": "fail", "detail": _tr("no virtual environment", "sanal ortam yok"),
            "hint": _tr("./install.sh creates .venv", ".venv'i ./install.sh kurar")}


def _requirements(root):
    path = os.path.join(root, "requirements.txt")
    try:
        lines = open(path, encoding="utf-8").read().splitlines()
    except OSError:
        return {"status": "warn", "detail": _tr("requirements.txt missing", "requirements.txt yok"),
                "hint": _tr("restore requirements.txt and run ./install.sh", "requirements.txt'i geri koy, ./install.sh çalıştır")}
    wanted = []
    for line in lines:
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        pkg = re.split(r"[<>=!~\[ ]", line, 1)[0].strip().lower()
        if pkg:
            wanted.append(REQUIRED_MODULES.get(pkg, pkg.replace("-", "_")))
    missing = []
    for mod in wanted:
        try:
            if importlib.util.find_spec(mod) is None:
                missing.append(mod)
        except (ImportError, ValueError, AttributeError):
            missing.append(mod)
    if missing:
        return {"status": "fail", "detail": _tr("missing: " + ", ".join(missing), "eksik: " + ", ".join(missing)),
                "hint": _tr(".venv/bin/pip install -r requirements.txt", ".venv/bin/pip install -r requirements.txt")}
    return {"status": "ok", "detail": _tr(f"{len(wanted)} packages importable", f"{len(wanted)} paket içe aktarılabiliyor"),
            "hint": None}


def _tool_version(name, exe, run):
    out = run(exe, ["-version"], timeout=5) if exe else None
    if out is None:
        return {"status": "fail", "detail": _tr(f"{name} not found", f"{name} bulunamadı"),
                "hint": _tr(f"install {name} (apt install ffmpeg) or set CF_{name.upper()}", f"{name} kur (apt install ffmpeg) ya da config.env'de CF_{name.upper()} ayarla")}
    return {"status": "ok", "detail": _tr(f"{name} {_version(out)}", f"{name} {_version(out)}"), "hint": None}


def _filters(ffmpeg, run):
    flt = run(ffmpeg, ["-hide_banner", "-filters"], timeout=8) if ffmpeg else None
    enc = run(ffmpeg, ["-hide_banner", "-encoders"], timeout=8) if ffmpeg else None
    found = set(re.findall(r"^\s*[.A-Z|]{2,3}\s+(\w+)\s+[A-Z|]+->", flt or "", re.M))
    missing = [f for f in FILTERS if f not in found]
    no264 = "libx264" not in (enc or "")
    problems = missing + (["libx264"] if no264 else [])
    if problems:
        return {"status": "fail", "detail": _tr("missing: " + ", ".join(problems), "eksik: " + ", ".join(problems)),
                "hint": _tr("install a full ffmpeg build (apt install ffmpeg)", "tam bir ffmpeg kur (apt install ffmpeg)")}
    return {"status": "ok", "detail": _tr(f"{len(FILTERS)} filters + libx264", f"{len(FILTERS)} filtre + libx264"),
            "hint": None}


def _browser(root, run):
    """Launch the Playwright Chromium bin/htmlmotion.py uses, once, headless; reads nothing and downloads nothing."""
    motion = os.path.join(root, "motion")
    if not os.path.isdir(os.path.join(motion, "node_modules", "playwright")):
        return {"status": "fail", "detail": _tr("Playwright is not installed", "Playwright kurulu değil"),
                "hint": _tr("cd motion && npm ci && npx playwright install chromium",
                            "cd motion && npm ci && npx playwright install chromium")}
    node = _which(NODE)
    if not node:
        return {"status": "fail", "detail": _tr("node not found", "node bulunamadı"),
                "hint": _tr("install Node 18+", "Node 18+ kur")}
    pw = os.path.join(motion, "node_modules", "playwright")
    script = ('const {chromium}=require(' + json.dumps(pw) + ');'
              'chromium.launch({headless:true,args:["--disable-dev-shm-usage"]})'
              '.then(async b=>{console.log(b.version());await b.close()})'
              '.catch(e=>{console.error(e.message);process.exit(1)})')
    out = run(node, ["-e", script], timeout=25, cwd=motion)
    if not out or "HeadlessChrome" not in out and not re.search(r"\d+\.\d+\.\d+\.\d+", out):
        return {"status": "fail", "detail": _tr("Chromium did not start", "Chromium başlamadı"),
                "hint": _tr("cd motion && npx playwright install chromium (and install-deps on Linux)",
                            "cd motion && npx playwright install chromium (Linux'ta install-deps de)")}
    return {"status": "ok", "detail": _tr("Chromium " + _version(out), "Chromium " + _version(out)), "hint": None}


def _fonts(root):
    d = os.path.join(root, "fonts")
    try:
        n = len([f for f in os.listdir(d) if f.lower().endswith((".ttf", ".otf", ".woff", ".woff2"))])
    except OSError:
        n = 0
    if n < 1:
        return {"status": "fail", "detail": _tr("fonts/ is empty", "fonts/ boş"),
                "hint": _tr("restore the project's fonts/ folder", "projenin fonts/ klasörünü geri koy")}
    return {"status": "ok", "detail": _tr(f"{n} font files", f"{n} font dosyası"), "hint": None}


def _claude_cli(run, env=None):
    env = os.environ if env is None else env
    exe = _which(CLAUDE) or shutil.which("claude")
    if not exe:
        return {"status": "fail", "detail": _tr("Claude Code CLI not found", "Claude Code CLI bulunamadı"),
                "hint": _tr("install it (https://code.claude.com) and run `claude` once",
                            "kur (https://code.claude.com) ve bir kez `claude` çalıştır")}
    out = run(exe, ["--version"], timeout=10)
    if out is None:
        return {"status": "fail", "detail": _tr("claude --version failed", "claude --version çalışmadı"),
                "hint": _tr("run `claude` once in a terminal", "bir terminalde bir kez `claude` çalıştır")}
    home = pathlib.Path(env.get("HOME") or os.path.expanduser("~"))
    logged = bool(env.get("CLAUDE_CODE_OAUTH_TOKEN"))
    for f in (home / ".claude" / ".credentials.json", home / ".claude" / "auth.json"):
        try:
            logged = logged or f.stat().st_size > 2
        except OSError:
            pass
    if not logged:
        try:
            data = json.loads((home / ".claude.json").read_text(encoding="utf-8"))
            logged = any(k in data for k in ("claudeAiOauth", "oauthAccount", "accessToken"))
        except (OSError, ValueError):
            pass
    if not logged:
        return {"status": "warn", "detail": _tr(f"Claude Code {_version(out)}, not logged in",
                                                f"Claude Code {_version(out)}, giriş yok"),
                "hint": _tr("run `claude` once to sign in", "giriş için bir kez `claude` çalıştır")}
    return {"status": "ok", "detail": _tr(f"Claude Code {_version(out)}, logged in", f"Claude Code {_version(out)}, giriş yapılmış"),
            "hint": None}


def _eleven_key(uid=None):
    for a in accounts.usable_eleven(uid):
        acc = accounts.eleven(a["id"]) or {}
        if acc.get("key"):
            return acc["key"]
    return ""


def _key_checks(uid=None):
    out = []
    el = _eleven_key(uid)
    out.append({"id": "key.elevenlabs", "required": False, "status": "ok" if el else "warn",
                "detail": _tr("ElevenLabs key " + ("set " + (_tail(el) or "") if el else "missing"),
                              "ElevenLabs anahtarı " + ("ayarlı " + (_tail(el) or "") if el else "yok")),
                "hint": None if el else _tr("Studio > Hesaplar > add an ElevenLabs API key",
                                            "Studio > Hesaplar > ElevenLabs API anahtarı ekle")})
    g = accounts.gemini_status(uid)
    gkey = accounts.gemini_key(uid)
    out.append({"id": "key.gemini", "required": False, "status": "ok" if g["connected"] else "warn",
                "detail": _tr("Gemini key " + ("set " + (_tail(gkey) or "") if g["connected"] else "missing"),
                              "Gemini anahtarı " + ("ayarlı " + (_tail(gkey) or "") if g["connected"] else "yok")),
                "hint": None if g["connected"] else _tr("Studio > Hesaplar > Google Gemini key, or GEMINI_API_KEY in config.env",
                                                        "Studio > Hesaplar > Google Gemini anahtarı ya da config.env'de GEMINI_API_KEY")})
    o = accounts.openrouter_status(uid)
    okey = accounts.openrouter_key(uid)
    out.append({"id": "key.openrouter", "required": False, "status": "ok" if o["connected"] else "warn",
                "detail": _tr("OpenRouter key " + ("set " + (_tail(okey) or "") if o["connected"] else "missing"),
                              "OpenRouter anahtarı " + ("ayarlı " + (_tail(okey) or "") if o["connected"] else "yok")),
                "hint": None if o["connected"] else _tr("Studio > Hesaplar > OpenRouter key, or OPENROUTER_API_KEY",
                                                        "Studio > Hesaplar > OpenRouter anahtarı ya da OPENROUTER_API_KEY")})
    return out


def _online(uid=None):
    """Two free authenticated GETs: the ElevenLabs subscription and the Gemini model list. No generation, no spend."""
    out = []
    key = _eleven_key(uid)
    if not key:
        out.append({"id": "online.elevenlabs", "required": False, "status": "warn",
                    "detail": _tr("skipped: no key", "atlandı: anahtar yok"), "hint": None})
    else:
        try:
            from . import eleven_api
            s = eleven_api.subscription(key)
            out.append({"id": "online.elevenlabs", "required": False, "status": "ok",
                        "detail": _tr(f"subscription {s.get('tier') or '?'}, {s.get('left', 0)} credits left",
                                      f"abonelik {s.get('tier') or '?'}, {s.get('left', 0)} kredi kaldı"), "hint": None})
        except Exception as e:                      # the message may carry a URL; keep it to one short line
            out.append({"id": "online.elevenlabs", "required": False, "status": "warn",
                        "detail": _tr("subscription could not be read: " + str(e)[:120],
                                      "abonelik okunamadı: " + str(e)[:120]),
                        "hint": _tr("check the key in Studio > Hesaplar", "Studio > Hesaplar'daki anahtarı denetle")})
    gkey = accounts.gemini_key(uid)
    if not gkey:
        out.append({"id": "online.gemini", "required": False, "status": "warn",
                    "detail": _tr("skipped: no key", "atlandı: anahtar yok"), "hint": None})
    else:
        try:
            from . import gemini
            n = gemini.check(gkey)["models"]
            out.append({"id": "online.gemini", "required": False, "status": "ok",
                        "detail": _tr(f"key valid, {n} models listed", f"anahtar geçerli, {n} model listelendi"),
                        "hint": None})
        except Exception as e:
            out.append({"id": "online.gemini", "required": False, "status": "warn",
                        "detail": _tr(str(e)[:120], str(e)[:120]),
                        "hint": _tr("check the key in Studio > Hesaplar", "Studio > Hesaplar'daki anahtarı denetle")})
    return out


def _whisper():
    if importlib.util.find_spec("faster_whisper") is None:
        return {"status": "fail", "detail": _tr("faster-whisper is not installed", "faster-whisper kurulu değil"),
                "hint": _tr(".venv/bin/pip install faster-whisper", ".venv/bin/pip install faster-whisper")}
    home = pathlib.Path(os.path.expanduser("~"))
    cached = []
    for base in (home / ".cache" / "huggingface" / "hub", home / ".cache" / "whisper"):
        cached += [os.path.basename(p) for p in glob.glob(str(base / "models--*faster-whisper*"))]
        cached += [os.path.basename(p) for p in glob.glob(str(base / "*.pt"))]
    if not cached:
        return {"status": "warn", "detail": _tr("no cached model (downloads on first use)", "önbellekte model yok (ilk kullanımda indirir)"),
                "hint": _tr("run one voice alignment once with network, or install a model",
                            "bir kez ağ bağlantısıyla ses hizalama çalıştır ya da model kur")}
    names = ", ".join(sorted({n.split("--")[-1] for n in cached if "--" in n}) or ["small"])
    return {"status": "ok", "detail": _tr("cached: " + names, "önbellekte: " + names), "hint": None}


def _disk(root):
    out = []
    for name in ("work", "out"):
        d = os.path.join(root, name)
        try:
            os.makedirs(d, exist_ok=True)
            free = shutil.disk_usage(d).free / 1e9
        except OSError as e:
            out.append({"id": f"disk.{name}", "required": False, "status": "warn",
                        "detail": _tr(f"{name}/ unreadable: {e}", f"{name}/ okunamadı: {e}"), "hint": None})
            continue
        status = "fail" if free < DISK_FAIL_GB else ("warn" if free < DISK_WARN_GB else "ok")
        out.append({"id": f"disk.{name}", "required": True, "status": status,
                    "detail": _tr(f"{name}/ {free:.1f} GB free", f"{name}/ {free:.1f} GB boş"),
                    "hint": None if status == "ok" else _tr("free disk space (renders need several GB)",
                                                            "disk alanı aç (render'lar birkaç GB ister)")})
    return out


def _data_writable(root):
    d = os.path.join(root, "data")
    try:
        os.makedirs(d, exist_ok=True)
        test = os.path.join(d, f".doctor-{os.getpid()}")
        with open(test, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(test)
    except OSError as e:
        return {"status": "fail", "detail": _tr(f"data/ is not writable: {e}", f"data/ yazılamıyor: {e}"),
                "hint": _tr("fix the ownership/permissions of data/", "data/ sahipliğini/izinlerini düzelt")}
    return {"status": "ok", "detail": _tr("data/ writable", "data/ yazılabilir"), "hint": None}


def _studio():
    """Info only: is the panel answering on its port (loopback first, then the configured host)?"""
    hosts = []
    for h in ("127.0.0.1", HOST or ""):
        if h and h not in hosts:
            hosts.append(h)
    ok = False
    for host in hosts:
        try:
            with urllib.request.urlopen(f"http://{host}:{STUDIO_PORT}/", timeout=1.5) as r:
                ok = r.status < 500
            break
        except Exception:
            continue
    return {"status": "ok" if ok else "info",
            "detail": _tr(f"Studio :{STUDIO_PORT} {'reachable' if ok else 'not running'}",
                          f"Studio :{STUDIO_PORT} {'erişilebilir' if ok else 'çalışmıyor'}"),
            "hint": None if ok else _tr("bin/start-factory.sh starts it", "bin/start-factory.sh başlatır")}


def _git(root, run):
    out = run("git", ["rev-parse", "--abbrev-ref", "HEAD"], timeout=5, cwd=root)
    branch = (out or "").strip().splitlines()[-1] if out else "?"
    return {"status": "info", "detail": _tr(f"git branch {branch}", f"git dalı {branch}"), "hint": None}


# ---------------------------------------------------------------- the report

def inspect(root=None, online=False, uid=None, run=_run, browser=_browser, lang="tr"):
    """Every check as {id, required, status, detail, hint}; `detail`/`hint` are strings in `lang`."""
    root = os.path.abspath(root or ROOT)
    run = run or _run
    checks = []

    def add(cid, required, res):
        c = {"id": cid, "required": bool(required), "status": res["status"],
             "detail": (res.get("detail") or {}).get(lang) or (res.get("detail") or {}).get("tr") or "",
             "hint": ((res.get("hint") or {}).get(lang) or (res.get("hint") or {}).get("tr")) if res.get("hint") else None}
        checks.append(c)

    add("python", True, _python())
    add("venv", True, _venv(root))
    add("requirements", True, _requirements(root))
    ffmpeg, ffprobe = _which(FFMPEG), _which(FFPROBE)
    add("ffmpeg", True, _tool_version("ffmpeg", ffmpeg, run))
    add("ffprobe", True, _tool_version("ffprobe", ffprobe, run))
    add("ffmpeg.filters", True, _filters(ffmpeg, run))
    add("browser", True, (browser or _browser)(root, run))
    add("fonts", True, _fonts(root))
    add("claude", False, _claude_cli(run))
    for c in _key_checks(uid):
        add(c["id"], c["required"], c)
    add("whisper", True, _whisper())
    for c in _disk(root):
        add(c["id"], c["required"], c)
    add("data", True, _data_writable(root))
    add("studio", False, _studio())
    add("git", False, _git(root, run))
    if online:
        for c in _online(uid):
            add(c["id"], c["required"], c)
    ok = not any(c["required"] and c["status"] == "fail" for c in checks)
    return {"version": 1, "ok": ok, "checks": checks}


ICON = {"ok": "✓", "warn": "⚠", "fail": "✗", "info": "·"}


def text(report, lang="tr"):
    head = _tr("factory doctor — readiness report", "factory doctor — hazırlık raporu")[lang]
    lines = [head]
    for c in report["checks"]:
        lines.append(f"{ICON.get(c['status'], '?')} {c['id']}: {c['detail']}")
        if c.get("hint"):
            lines.append(f"    → {c['hint']}")
    fails = sum(1 for c in report["checks"] if c["required"] and c["status"] == "fail")
    warns = sum(1 for c in report["checks"] if c["status"] == "warn")
    lines.append(_tr(f"{fails} blocking failure(s), {warns} warning(s)", f"{fails} engelleyici hata, {warns} uyarı")[lang])
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="factory doctor", description="Hazırlık denetimi: araçlar, anahtarlar, disk.")
    ap.add_argument("--json", action="store_true", help="makine okunur rapor")
    ap.add_argument("--online", action="store_true", help="ücretsiz kimlik doğrulamalı GET denetimleri de yap")
    ap.add_argument("--lang", choices=("tr", "en"), default="tr")
    a = ap.parse_args(argv)
    report = inspect(online=a.online, lang=a.lang)
    if a.json:
        print(json.dumps(report, ensure_ascii=False, indent=1))
    else:
        print(text(report, a.lang))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
