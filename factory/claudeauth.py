"""Connect a member's Claude subscription from the Studio, two ways:
- mode "login": `claude auth login --claudeai` into the member's own config dir (~/.claude-profiles/<id>): a full
  login, so their claude.ai connectors (e.g. their ElevenLabs) work in the Studio too;
- mode "token": `claude setup-token`: a long-lived token with scope user:inference only (no connectors).
Runs in a pseudo-terminal on the VM, hands the sign-in URL to the browser and takes the code the member pastes back.
One pending sign-in per user, 10 minutes max."""
import fcntl, os, pty, shutil, re, select, signal, struct, tempfile, termios, threading, time

from . import accounts

from .config import CLAUDE
ANSI = re.compile(r"\x1b\][^\x07\x1b]*(\x07|\x1b\\)|\x1b\[[0-9;?<>=]*[ -/]*[@-~]|\x1b[=>78]")
TOKEN = re.compile(r"sk-ant-oat\d+-[A-Za-z0-9_\-]{20,}")
URL = re.compile(r"https://claude\.(?:com|ai)/[^\s\x07\x1b\"']*oauth/authorize\?[^\s\x07\x1b\"']+")
_pending, _lock = {}, threading.Lock()


def _read(fd, until, timeout):
    buf, end = b"", time.time() + timeout
    while time.time() < end:
        r, _, _ = select.select([fd], [], [], 0.5)
        if r:
            try:
                chunk = os.read(fd, 65536)
            except OSError:
                break
            if not chunk:
                break
            buf += chunk
            if until(buf.decode(errors="replace")):
                break
    return buf.decode(errors="replace")


def _kill(uid):
    old = _pending.pop(uid, None)
    if old:
        try:
            os.kill(old["pid"], signal.SIGKILL)
            os.waitpid(old["pid"], 0)
        except OSError:
            pass
        try:
            os.close(old["fd"])
        except OSError:
            pass
        if old.get("temp"):
            shutil.rmtree(old["cfg"], ignore_errors=True)


def start(uid, mode="login"):
    """Begin a sign-in for `uid`; returns the URL the member opens in their own browser."""
    with _lock:
        _kill(uid)
        temp = mode != "login"
        cfg = tempfile.mkdtemp(prefix="claude-setup-") if temp else os.path.join(accounts.PROFILES, uid)
        os.makedirs(cfg, mode=0o700, exist_ok=True)
        args = [CLAUDE, "setup-token"] if temp else [CLAUDE, "auth", "login", "--claudeai"]
        pid, fd = pty.fork()
        if pid == 0:
            os.environ.update({"CLAUDE_CONFIG_DIR": cfg, "BROWSER": "/bin/true", "TERM": "xterm-256color"})
            os.environ.pop("CLAUDE_CODE_OAUTH_TOKEN", None)
            os.execv(CLAUDE, args)
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", 50, 1000, 0, 0))  # wide: URL and token on one line
        out = _read(fd, lambda t: URL.search(ANSI.sub("", t)) or URL.search(t), 40)
        m = URL.search(ANSI.sub("", out)) or URL.search(out)
        if not m:
            os.kill(pid, signal.SIGKILL)
            raise RuntimeError("Claude giriş linki alınamadı")
        _pending[uid] = {"pid": pid, "fd": fd, "at": time.time(), "cfg": cfg, "temp": temp, "mode": mode}
        return m.group(0)


def finish(uid, code):
    """Send the pasted code, capture the token, store it. Returns True on success."""
    with _lock:
        p = _pending.get(uid)
        if not p or time.time() - p["at"] > 600:
            _kill(uid)
            raise RuntimeError("Giriş süresi doldu, baştan başlat")
        os.write(p["fd"], (code.strip() + "\r").encode())
        if p["mode"] == "login":
            out = _read(p["fd"], lambda t: "rror" in t or "uccess" in t or "ogged in" in t, 60)
            time.sleep(1.5)
            _kill(uid)
            if not logged_in(p["cfg"]):
                raise RuntimeError("Giriş tamamlanmadı: " + ANSI.sub("", out).strip()[-160:])
            accounts.set_claude_login(uid)
            return True
        out = _read(p["fd"], lambda t: TOKEN.search(ANSI.sub("", t)) or "rror" in t, 60)
        m = TOKEN.search(ANSI.sub("", out))
        _kill(uid)
        if not m:
            raise RuntimeError("Kod kabul edilmedi: " + ANSI.sub("", out).strip()[-160:])
        accounts.set_claude_token(uid, m.group(0))
        return True


def logged_in(cfg):
    import json, subprocess
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_CODE_OAUTH_TOKEN"}
    env["CLAUDE_CONFIG_DIR"] = cfg
    r = subprocess.run([CLAUDE, "auth", "status", "--json"], capture_output=True, text=True, env=env, timeout=60)
    try:
        return bool(json.loads(r.stdout).get("loggedIn"))
    except ValueError:
        return r.returncode == 0 and "not" not in r.stdout.lower()
