"""People and accounts of a shared Studio.

- Users (data/users.json, mode 600): who is logged in. The owner (Ali) runs everything on their own Claude Code login
  as before; a member connects their own Claude subscription with a long-lived token (`claude setup-token`, scope
  user:inference), so every Claude step they start runs on their subscription.
- ElevenLabs accounts (data/eleven_accounts.json, mode 600): the owner's account works through the claude.ai
  ElevenLabs connector of the owner's Claude login (no API key); other accounts use an ElevenLabs API key. A production
  picks the account it spends from; voices and the balance are read from that account automatically. The owner
  decides whether members may use the owner's account and up to how many credits a month.
- The current user travels with every job (jobs.user + env FACTORY_USER), so the right Claude login and the right
  ElevenLabs account are used inside the job processes too.
"""
import contextvars, hashlib, hmac, json, os, secrets, time

from .config import ROOT
USERS = os.path.join(ROOT, "data", "users.json")
ELEVEN = os.path.join(ROOT, "data", "eleven_accounts.json")
PROFILES = os.path.expanduser("~/.claude-profiles")   # per-member Claude config dirs (sessions, settings)
OWNER = "ali"
COOKIE = "studio_session"
_current = contextvars.ContextVar("factory_user", default=None)


# ---------- storage ----------
def _load(path, default):
    try:
        return json.load(open(path))
    except (OSError, ValueError):
        return default


def _save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def users():
    u = _load(USERS, None)
    if u is None:
        u = {"secret": secrets.token_hex(32), "users": {}}
    return u


def enabled():
    """Login is required as soon as one user exists (before that the Studio behaves as the single-owner panel)."""
    return bool(users()["users"])


# ---------- current user ----------
def current():
    return _current.get() or os.environ.get("FACTORY_USER") or OWNER


def set_current(uid):
    return _current.set(uid)


class as_user:
    """with accounts.as_user("ali"): ... runs Claude calls on that user's login (e.g. the owner's connector)."""
    def __init__(self, uid):
        self.uid = uid

    def __enter__(self):
        self.tok = _current.set(self.uid)

    def __exit__(self, *a):
        _current.reset(self.tok)


def user(uid=None):
    uid = uid or current()
    return users()["users"].get(uid) or ({"name": "Ali", "role": "owner"} if uid == OWNER else None)


def is_owner(uid=None):
    return (user(uid) or {}).get("role") == "owner"


# ---------- passwords + sessions ----------
def _hash(pw, salt):
    return hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt), n=2 ** 14, r=8, p=1).hex()


def add_user(uid, name, password, role="member"):
    u = users()
    salt = secrets.token_hex(16)
    old = u["users"].get(uid, {})
    u["users"][uid] = {**old, "name": name, "role": role, "salt": salt, "hash": _hash(password, salt)}
    _save(USERS, u)


def check_password(uid, password):
    rec = users()["users"].get(uid)
    return bool(rec) and hmac.compare_digest(rec["hash"], _hash(password or "", rec["salt"]))


def make_session(uid, days=30):
    exp = int(time.time()) + days * 86400
    msg = f"{uid}.{exp}"
    sig = hmac.new(bytes.fromhex(users()["secret"]), msg.encode(), "sha256").hexdigest()
    return f"{msg}.{sig}"


def read_session(value):
    try:
        uid, exp, sig = (value or "").rsplit(".", 2)
        good = hmac.new(bytes.fromhex(users()["secret"]), f"{uid}.{exp}".encode(), "sha256").hexdigest()
        if hmac.compare_digest(sig, good) and int(exp) > time.time() and uid in users()["users"]:
            return uid
    except (ValueError, KeyError):
        pass
    return None


# ---------- Claude per user ----------
def set_claude_token(uid, token):
    u = users()
    u["users"][uid]["claude"] = {"token": token, "connected_at": time.strftime("%Y-%m-%d %H:%M")}
    _save(USERS, u)


def set_claude_login(uid):
    """Full Claude login stored in the member's own config dir (connectors included)."""
    u = users()
    u["users"][uid]["claude"] = {"mode": "login", "connected_at": time.strftime("%Y-%m-%d %H:%M")}
    _save(USERS, u)


def claude_status(uid=None):
    uid = uid or current()
    if is_owner(uid) or uid == OWNER:
        return {"connected": True, "mode": "login", "how": "VM'deki Claude Code girişi (sahip)", "connectors": True}
    c = (user(uid) or {}).get("claude") or {}
    login = c.get("mode") == "login"
    return {"connected": login or bool(c.get("token")), "mode": "login" if login else ("token" if c.get("token") else None),
            "how": "kendi Claude hesabı, tam giriş (connector'lar dahil)" if login else "kendi Claude aboneliği (sadece model)",
            "connectors": login, "at": c.get("connected_at")}


class NoClaude(RuntimeError):
    pass


def claude_env(uid=None):
    """Extra environment for the `claude` CLI so the step runs on this user's subscription."""
    uid = uid or current()
    if uid == OWNER or is_owner(uid):
        return {}
    c = (user(uid) or {}).get("claude") or {}
    cfg = os.path.join(PROFILES, uid)
    os.makedirs(cfg, mode=0o700, exist_ok=True)
    if c.get("mode") == "login":            # full login in their config dir: their connectors work too
        return {"CLAUDE_CONFIG_DIR": cfg}
    if not c.get("token"):
        raise NoClaude(f"{(user(uid) or {}).get('name', uid)} henüz Claude hesabını bağlamadı (Hesaplar sayfası)")
    return {"CLAUDE_CODE_OAUTH_TOKEN": c["token"], "CLAUDE_CONFIG_DIR": cfg}


# ---------- ElevenLabs accounts ----------
def eleven_accounts():
    a = _load(ELEVEN, None)
    if a is None:  # the owner's existing connector account
        a = {"accounts": {"ali": {"name": "Ali'nin ElevenLabs'ı", "type": "connector", "owner": OWNER,
                                  "shared": True, "member_month_cap": None}}}
        _save(ELEVEN, a)
    return a


def add_eleven(uid, name, key):
    a = eleven_accounts()
    aid = f"{uid}-{secrets.token_hex(3)}"
    a["accounts"][aid] = {"name": name, "type": "apikey", "owner": uid, "key": key, "shared": False,
                          "member_month_cap": None, "added_at": time.strftime("%Y-%m-%d %H:%M")}
    _save(ELEVEN, a)
    return aid


def add_eleven_connector(uid, name):
    """The member's own claude.ai ElevenLabs connector (needs their full Claude login); voices are read by a job."""
    a = eleven_accounts()
    aid = f"{uid}-conn"
    a["accounts"][aid] = {"name": name, "type": "connector", "owner": uid, "shared": False, "member_month_cap": None,
                          "month_cap": None, "voices": [], "added_at": time.strftime("%Y-%m-%d %H:%M")}
    _save(ELEVEN, a)
    return aid


def set_voices(aid, voices):
    a = eleven_accounts()
    a["accounts"][aid]["voices"] = voices
    a["accounts"][aid]["voices_at"] = time.strftime("%Y-%m-%d %H:%M")
    _save(ELEVEN, a)


def update_eleven(aid, **kw):
    a = eleven_accounts()
    acc = a["accounts"][aid]
    for k in ("name", "shared", "member_month_cap", "key", "month_cap"):
        if k in kw:
            acc[k] = kw[k]
    _save(ELEVEN, a)


def remove_eleven(aid):
    a = eleven_accounts()
    a["accounts"].pop(aid, None)
    _save(ELEVEN, a)


def eleven(aid):
    return eleven_accounts()["accounts"].get(aid)


def usable_eleven(uid=None):
    """Accounts this user may spend from: their own + the ones their owners share."""
    uid = uid or current()
    out = []
    for aid, acc in eleven_accounts()["accounts"].items():
        if acc["owner"] == uid or acc.get("shared"):
            out.append({"id": aid, "name": acc["name"], "type": acc["type"], "owner": acc["owner"],
                        "mine": acc["owner"] == uid, "shared": bool(acc.get("shared")),
                        "member_month_cap": acc.get("member_month_cap"),
                        "key_tail": ("…" + acc["key"][-4:]) if acc.get("key") else None})
    return out


def default_eleven(uid=None):
    uid = uid or current()
    acc = usable_eleven(uid)
    mine = [a for a in acc if a["mine"]]
    return (mine or acc or [{"id": "ali"}])[0]["id"]


def can_use(aid, uid=None):
    uid = uid or current()
    acc = eleven(aid)
    return bool(acc) and (acc["owner"] == uid or acc.get("shared"))
