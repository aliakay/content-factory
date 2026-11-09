"""People and accounts of a shared Studio.

- Users (data/users.json, mode 600): who is logged in. The owner (Ali) runs everything on their own Claude Code login
  as before; a member connects their own Claude subscription with a long-lived token (`claude setup-token`, scope
  user:inference), so every Claude step they start runs on their subscription.
- ElevenLabs accounts (data/eleven_accounts.json, mode 600): the owner's account works through the claude.ai
  ElevenLabs connector of the owner's Claude login (no API key); other accounts use an ElevenLabs API key. A production
  picks the account it spends from; voices and the balance are read from that account automatically. The owner
  decides whether members may use the owner's account and up to how many credits a month.
- The current user travels with every job (jobs.user + env FACTORY_USER), so their CLI/model preferences and the right
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


def pref_rec(u, uid):
    """Where this user's preferences live: their own entry, or `owner` while login is off.

    Saving a setting on a fresh install must not create a login (a user without a password would lock the panel out):
    with no logins at all, the owner's preferences go to their own `owner` bucket and `enabled()` stays false."""
    if uid in u["users"]:
        return u["users"][uid]
    if not u["users"] and uid == OWNER:
        return u.setdefault("owner", {"name": "Ali", "role": "owner"})
    raise ValueError("Kullanıcı bulunamadı")


def user(uid=None):
    uid = uid or current()
    u = users()
    if uid in u["users"]:
        return u["users"][uid]
    return (u.get("owner") or {}) if uid == OWNER and not u["users"] else None or ({"name": "Ali", "role": "owner"} if uid == OWNER else None)


def name_of(uid):
    """Display name for a user id ('' for none), for "who started / who approved" labels in a shared Studio."""
    return ((user(uid) or {}).get("name") or uid) if uid else ""


def shared():
    """More than one person logs in, so the Studio labels who started and who approved things."""
    return len(users()["users"]) > 1


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


CLI_PROVIDERS = {"claude", "codex", "openrouter"}
EFFORT_LEVELS = ("low", "medium", "high")     # what the settings page offers per agent
REVIEW_ROUNDS = (0, 1, 2)                      # how many review rounds a stage may use (0 = no reviewer)


# ---------- chosen narrator per account ----------
DEFAULTS = os.path.join(ROOT, "data", "eleven_defaults.json")


def voice_defaults():
    """{account id: {lang: voice_id}} — the narrator the creator picked for a language, per ElevenLabs account."""
    try:
        return json.load(open(DEFAULTS))
    except (OSError, ValueError):
        return {}


def default_voice_for(aid, lang):
    return (voice_defaults().get(aid) or {}).get(lang)


def set_default_voice(aid, lang, voice_id):
    if lang not in ("tr", "en"):
        raise ValueError("Bilinmeyen dil")
    d = voice_defaults()
    d.setdefault(aid, {})[lang] = voice_id
    os.makedirs(os.path.dirname(DEFAULTS), exist_ok=True)
    with open(DEFAULTS, "w") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    return d[aid]


# ---------- Google Gemini per user ----------
def set_gemini_key(uid, key):
    """Store this user's Gemini API key ("" removes it)."""
    key = (key or "").strip()
    if key and (len(key) < 20 or len(key) > 200 or any(c.isspace() for c in key)):
        raise ValueError("Gemini anahtarı geçersiz görünüyor")
    u = users()
    rec = pref_rec(u, uid)
    if key:
        rec["gemini"] = {"key": key, "connected_at": time.strftime("%Y-%m-%d %H:%M")}
    else:
        rec.pop("gemini", None)
    _save(USERS, u)
    return gemini_status(uid)


def gemini_key(uid=None):
    uid = uid or current()
    return ((user(uid) or {}).get("gemini") or {}).get("key") or ""


def gemini_status(uid=None):
    """This user's Gemini key: their own when they saved one, else the owner's GEMINI_API_KEY."""
    uid = uid or current()
    own = ((user(uid) or {}).get("gemini") or {})
    env = os.environ.get("GEMINI_API_KEY") or ""
    key = own.get("key") or env
    return {"connected": bool(key), "mine": bool(own.get("key")), "env": not own.get("key") and bool(env),
            "tail": "…" + key[-4:] if own.get("key") else None, "at": own.get("connected_at")}


def review_rounds(uid=None):
    """How many reviewer rounds one stage may use: 0 = no reviewer, 1 = one pass (the default), 2 = a fix round too."""
    uid = uid or current()
    n = (user(uid) or {}).get("review_rounds")
    return n if n in REVIEW_ROUNDS else 1


def set_review_rounds(uid, n):
    if n not in REVIEW_ROUNDS:
        raise ValueError("Denetim turu geçersiz")
    u = users()
    pref_rec(u, uid)["review_rounds"] = n
    _save(USERS, u)
    return n


# ---------- who makes the media ----------
MEDIA_KINDS = ("voice", "music", "image", "video")
MEDIA_PROVIDERS = ("elevenlabs", "gemini")


def media_settings(uid=None):
    """Per capability, who generates it: ElevenLabs or Gemini (Hesaplar → Medya üreticisi)."""
    uid = uid or current()
    saved = (user(uid) or {}).get("media") or {}
    return {k: (saved.get(k) if saved.get(k) in MEDIA_PROVIDERS else "elevenlabs") for k in MEDIA_KINDS}


def set_media_settings(uid, mapping):
    if not isinstance(mapping, dict) or not mapping:
        raise ValueError("Medya üreticisi seçimi geçersiz")
    clean = {}
    for k, v in mapping.items():
        if k not in MEDIA_KINDS or v not in MEDIA_PROVIDERS:
            raise ValueError("Medya üreticisi seçimi geçersiz")
        clean[k] = v
    u = users()
    rec = pref_rec(u, uid)
    rec["media"] = {**media_settings(uid), **clean}
    _save(USERS, u)
    return media_settings(uid)


# ---------- chosen narrator per account ----------
DEFAULTS = os.path.join(ROOT, "data", "eleven_defaults.json")


def voice_defaults():
    """{account id: {lang: voice_id}} — the narrator the creator picked for a language, per ElevenLabs account."""
    try:
        return json.load(open(DEFAULTS))
    except (OSError, ValueError):
        return {}


def default_voice_for(aid, lang):
    return (voice_defaults().get(aid) or {}).get(lang)


def set_default_voice(aid, lang, voice_id):
    if lang not in ("tr", "en"):
        raise ValueError("Bilinmeyen dil")
    d = voice_defaults()
    d.setdefault(aid, {})[lang] = voice_id
    os.makedirs(os.path.dirname(DEFAULTS), exist_ok=True)
    with open(DEFAULTS, "w") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    return d[aid]


# ---------- Google Gemini per user ----------
def set_gemini_key(uid, key):
    """Store this user's Gemini API key ("" removes it)."""
    key = (key or "").strip()
    if key and (len(key) < 20 or len(key) > 200 or any(c.isspace() for c in key)):
        raise ValueError("Gemini anahtarı geçersiz görünüyor")
    u = users()
    rec = pref_rec(u, uid)
    if key:
        rec["gemini"] = {"key": key, "connected_at": time.strftime("%Y-%m-%d %H:%M")}
    else:
        rec.pop("gemini", None)
    _save(USERS, u)
    return gemini_status(uid)


def gemini_key(uid=None):
    uid = uid or current()
    return ((user(uid) or {}).get("gemini") or {}).get("key") or ""


def gemini_status(uid=None):
    """This user's Gemini key: their own when they saved one, else the owner's GEMINI_API_KEY."""
    uid = uid or current()
    own = ((user(uid) or {}).get("gemini") or {})
    env = os.environ.get("GEMINI_API_KEY") or ""
    key = own.get("key") or env
    return {"connected": bool(key), "mine": bool(own.get("key")), "env": not own.get("key") and bool(env),
            "tail": "…" + key[-4:] if own.get("key") else None, "at": own.get("connected_at")}


def review_rounds(uid=None):
    """How many reviewer rounds one stage may use: 0 = no reviewer, 1 = one pass (the default), 2 = a fix round too."""
    uid = uid or current()
    n = (user(uid) or {}).get("review_rounds")
    return n if n in REVIEW_ROUNDS else 1


def set_review_rounds(uid, n):
    if n not in REVIEW_ROUNDS:
        raise ValueError("Denetim turu geçersiz")
    u = users()
    pref_rec(u, uid)["review_rounds"] = n
    _save(USERS, u)
    return n


# ---------- who makes the media ----------
MEDIA_KINDS = ("voice", "music", "image", "video")
MEDIA_PROVIDERS = ("elevenlabs", "gemini")


def media_settings(uid=None):
    """Per capability, who generates it: ElevenLabs or Gemini (Hesaplar → Medya üreticisi)."""
    uid = uid or current()
    saved = (user(uid) or {}).get("media") or {}
    return {k: (saved.get(k) if saved.get(k) in MEDIA_PROVIDERS else "elevenlabs") for k in MEDIA_KINDS}


def set_media_settings(uid, mapping):
    if not isinstance(mapping, dict) or not mapping:
        raise ValueError("Medya üreticisi seçimi geçersiz")
    clean = {}
    for k, v in mapping.items():
        if k not in MEDIA_KINDS or v not in MEDIA_PROVIDERS:
            raise ValueError("Medya üreticisi seçimi geçersiz")
        clean[k] = v
    u = users()
    rec = pref_rec(u, uid)
    rec["media"] = {**media_settings(uid), **clean}
    _save(USERS, u)
    return media_settings(uid)


# ---------- how ElevenLabs is reached ----------
# ---------- OpenRouter per user ----------
def set_openrouter_key(uid, key):
    """Store this user's OpenRouter API key ("" removes it). Returns the new status."""
    key = (key or "").strip()
    if key and (len(key) < 20 or len(key) > 200 or any(c.isspace() for c in key)):
        raise ValueError("OpenRouter anahtarı geçersiz görünüyor")
    u = users()
    rec = pref_rec(u, uid)
    if key:
        rec["openrouter"] = {"key": key, "connected_at": time.strftime("%Y-%m-%d %H:%M")}
    else:
        rec.pop("openrouter", None)
    _save(USERS, u)
    return openrouter_status(uid)


def openrouter_key(uid=None):
    uid = uid or current()
    return ((user(uid) or {}).get("openrouter") or {}).get("key") or ""


def openrouter_status(uid=None):
    """This user's OpenRouter key: their own when they saved one, else the owner's OPENROUTER_API_KEY."""
    uid = uid or current()
    own = ((user(uid) or {}).get("openrouter") or {})
    env = os.environ.get("OPENROUTER_API_KEY") or ""
    key = own.get("key") or env
    return {"connected": bool(key), "mine": bool(own.get("key")), "env": not own.get("key") and bool(env),
            "tail": "…" + key[-6:] if own.get("key") else None, "at": own.get("connected_at")}


def llm_settings(uid=None):
    """Per-user default CLI, per-step model overrides, and per-step providers.

    `provider` is the default. `providers[step]` (or `providers.default`) sends one agent to another CLI, so a user
    can mix: plan and script on Claude, the motion designer on Codex, a cheap checker on OpenRouter. `models[step]`
    is the model for that step, from its own provider's catalogue."""
    uid = uid or current()
    saved = (user(uid) or {}).get("llm_settings") or {}
    provider = saved.get("provider") if saved.get("provider") in CLI_PROVIDERS else "claude"
    models = saved.get("models") if isinstance(saved.get("models"), dict) else {}
    provs = saved.get("providers") if isinstance(saved.get("providers"), dict) else {}
    effs = saved.get("effort") if isinstance(saved.get("effort"), dict) else {}
    return {"provider": provider,
            "models": {str(k): str(v) for k, v in models.items() if isinstance(k, str) and isinstance(v, str)},
            "providers": {str(k): str(v) for k, v in provs.items()
                          if isinstance(k, str) and isinstance(v, str) and v in CLI_PROVIDERS},
            "effort": {str(k): str(v) for k, v in effs.items()
                       if isinstance(k, str) and isinstance(v, str) and v in EFFORT_LEVELS}}


def set_llm_settings(uid, provider, models, providers=None, effort=None):
    if provider not in CLI_PROVIDERS:
        raise ValueError("CLI seçimi geçersiz")
    if not isinstance(models, dict) or len(models) > 80:
        raise ValueError("Agent model seçimleri geçersiz")
    clean = {}
    for step, model in models.items():
        if not isinstance(step, str) or len(step) > 80 or not isinstance(model, str) or len(model) > 100:
            raise ValueError("Agent model seçimi geçersiz")
        if model:
            clean[step] = model
    provs = {}
    for step, p in (providers or {}).items():
        if not isinstance(step, str) or len(step) > 80 or p not in CLI_PROVIDERS:
            raise ValueError("Agent CLI seçimi geçersiz")
        if p:
            provs[step] = p
    effs = {}
    for step, level in (effort or {}).items():
        if not isinstance(step, str) or len(step) > 80 or level not in EFFORT_LEVELS:
            raise ValueError("Agent düşünme seviyesi geçersiz")
        if level:
            effs[step] = level
    u = users()
    rec = pref_rec(u, uid)
    rec["llm_settings"] = {"provider": provider, "models": clean, "providers": provs, "effort": effs}
    _save(USERS, u)
    return llm_settings(uid)


UI_LANGS = ("tr", "en")


def ui_lang(uid=None):
    """The Studio's interface language for this user: everything they see is in it (videos have their own language)."""
    lang = (user(uid or current()) or {}).get("ui_lang")
    return lang if lang in UI_LANGS else "tr"


def set_ui_lang(uid, lang):
    if lang not in UI_LANGS:
        raise ValueError("unknown interface language")
    u = users()
    pref_rec(u, uid)["ui_lang"] = lang
    _save(USERS, u)
    return lang


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
    """ElevenLabs accounts: API keys only (the CLI connector was removed: voices, music, sfx, images, video and
    lip-sync all come from the REST API now)."""
    a = _load(ELEVEN, None)
    if a is None:
        a = {"accounts": {}}
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
        if acc.get("type") != "apikey":
            continue                      # the CLI connector was removed: only API-key accounts can spend
        if acc["owner"] == uid or acc.get("shared"):
            out.append({"id": aid, "name": acc["name"], "type": acc["type"], "owner": acc["owner"],
                        "mine": acc["owner"] == uid, "shared": bool(acc.get("shared")),
                        "member_month_cap": acc.get("member_month_cap"),
                        "key_tail": ("…" + acc["key"][-4:]) if acc.get("key") else None})
    return out


def default_eleven(uid=None):
    """The account a production spends from unless it names its own: the user's saved choice, else their own, else any."""
    uid = uid or current()
    acc = usable_eleven(uid)
    chosen = ((user(uid) or {}).get("default_eleven") or "")
    if chosen and any(a["id"] == chosen for a in acc):
        return chosen
    mine = [a for a in acc if a["mine"]]
    return (mine or acc or [{"id": "ali"}])[0]["id"]


def set_default_eleven(uid, aid):
    """Save the account a production spends from by default (an account id from usable_eleven)."""
    if not any(a["id"] == aid for a in usable_eleven(uid)):
        raise ValueError("ElevenLabs hesabı bulunamadı")
    u = users()
    pref_rec(u, uid)["default_eleven"] = aid
    _save(USERS, u)
    return aid


def can_use(aid, uid=None):
    uid = uid or current()
    acc = eleven(aid)
    return bool(acc) and (acc["owner"] == uid or acc.get("shared"))
