"""ElevenLabs credit estimates, ledger and monthly cap.

Rates are learned from real runs: every generation records its `credit_cost`, and the per-unit rate for that
model is updated from the measurements. Unmeasured models are reported as unknown (never guessed silently).
"""
import json, os
from datetime import datetime, timezone

from .store import now

from .config import ROOT
RATES_PATH = os.path.join(ROOT, "data", "eleven_rates.json")
MONTHLY_CAP = 100_000  # the user's budget (ElevenLabs Pro)

SCHEMA = """CREATE TABLE IF NOT EXISTS eleven_ledger (
  id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT, kind TEXT, model TEXT, units REAL, unit TEXT,
  credits REAL, idea_id INTEGER, note TEXT
)"""

# measured seed: one eleven_v4 sentence, 64 chars -> 73.67 credits (2026-10-26)
SEED = {"tts:eleven_v4": {"unit": "char", "rate": 73.67 / 64, "samples": 1}}


def ensure(con):
    con.execute(SCHEMA)
    cols = {r[1] for r in con.execute("PRAGMA table_info(eleven_ledger)")}
    for c in ("user", "account"):
        if c not in cols:
            con.execute(f"ALTER TABLE eleven_ledger ADD COLUMN {c} TEXT")


def rates():
    try:
        return json.load(open(RATES_PATH))
    except (OSError, ValueError):
        return dict(SEED)


def _save_rates(r):
    os.makedirs(os.path.dirname(RATES_PATH), exist_ok=True)
    json.dump(r, open(RATES_PATH, "w"), indent=1)


def record(con, kind, model, units, unit, credits, idea_id=None, note="", account="ali"):
    """Log a real spend (who started it, which ElevenLabs account paid) and refresh the learned rate."""
    from . import accounts
    ensure(con)
    con.execute("INSERT INTO eleven_ledger (at, kind, model, units, unit, credits, idea_id, note, user, account) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)", (now(), kind, model, units, unit, credits, idea_id, note,
                                                 accounts.current(), account))
    con.commit()
    if units and credits is not None:
        r = rates()
        key = f"{kind}:{model}"
        cur = r.get(key, {"unit": unit, "rate": 0.0, "samples": 0})
        n = cur["samples"]
        cur["rate"] = (cur["rate"] * n + credits / units) / (n + 1)
        cur["samples"], cur["unit"] = n + 1, unit
        r[key] = cur
        _save_rates(r)


def month_spent(con, account="ali", user=None):
    """This month's spend on one ElevenLabs account (old rows without an account are the owner's), optionally by one user."""
    ensure(con)
    start = datetime.now(timezone.utc).strftime("%Y-%m-01")
    q = "SELECT COALESCE(SUM(credits),0) s FROM eleven_ledger WHERE at >= ? AND COALESCE(account,'ali') = ?"
    args = [start, account]
    if user:
        q += " AND COALESCE(user,'ali') = ?"
        args.append(user)
    row = con.execute(q, args).fetchone()
    return float(row[0])


def estimate(items):
    """items: [{kind, model, units, unit, label}] -> {total, known, unknown:[...], lines:[...]}"""
    r, lines, total, unknown = rates(), [], 0.0, []
    for it in items:
        key = f"{it['kind']}:{it['model']}"
        rate = r.get(key, {}).get("rate")
        if rate is None:
            unknown.append(it.get("label") or key)
            lines.append({**it, "credits": None})
        else:
            c = round(rate * it["units"])
            total += c
            lines.append({**it, "credits": c, "rate": round(rate, 3)})
    return {"total": round(total), "lines": lines, "unknown": unknown}


class BudgetError(RuntimeError):
    pass


def guard(con, kind, model, units, approved, account="ali"):
    """Hard stop before any generation: the user must have approved a credit amount for exactly this step, the
    learned estimate must fit inside it (+15 %), and the month must stay under the cap. Unknown rates only pass
    when the approved amount itself fits the remaining budget (the price is then capped by the approval)."""
    if approved is None:
        raise BudgetError("no approved credit amount for this generation")
    est = estimate([{"kind": kind, "model": model, "units": units, "unit": ""}])
    need = est["total"] if not est["unknown"] else approved
    if need > approved * 1.15:
        raise BudgetError(f"estimate {need} credits is above the approved {approved}")
    b = check_budget(con, need, account)
    if not b["ok"]:
        raise BudgetError(b["why"])
    return need


def check_budget(con, needed, account="ali"):
    """Owner's connector account: the monthly cap. API-key accounts: the live balance. A member spending from
    someone else's account: also the owner's per-member monthly limit."""
    from . import accounts
    acc = accounts.eleven(account) or {"type": "connector", "owner": accounts.OWNER}
    if not accounts.can_use(account):
        return {"ok": False, "why": "bu ElevenLabs hesabını kullanma iznin yok", "spent": 0, "cap": 0, "after": 0}
    if acc["type"] == "apikey":
        from . import eleven_api
        left = eleven_api.info(acc["key"])["subscription"]["left"]
        spent, cap = 0, left
        ok, why = needed <= left, f"hesapta {left} kredi kaldı, {needed} gerekiyor"
    else:   # connector accounts: the owner's Pro cap for "ali", an optional monthly cap for a member's own connector
        cap = MONTHLY_CAP if account == "ali" else (acc.get("month_cap") or 10 ** 9)
        spent = month_spent(con, account)
        ok, why = spent + needed <= cap, f"aylık sınır: {round(spent)} harcandı + {needed} > {cap}"
    me = accounts.current()
    mcap = acc.get("member_month_cap")
    if ok and me != acc["owner"] and mcap is not None:
        mine = month_spent(con, account, me)
        if mine + needed > mcap:
            ok, why = False, f"{acc['name']} için bu ay sana ayrılan sınır: {round(mine)} + {needed} > {mcap}"
    return {"spent": round(spent), "cap": cap, "after": round(spent + needed), "ok": ok, "why": why}
