"""One video = one project folder. The folder is the source of truth for a production line run: what was made at
each stage (artifacts), where each stage stands (checkpoints), and what happened (events, decisions). The Studio, the
headless stage agents and an interactive Claude Code session all read and write the same files.

  projects/<NNN-slug>/
    project.json              line, title, languages, aspect, channel, budget, who made it
    artifacts/<name>.json     one canonical output per stage (research, proposal, script, scene_plan, ...)
    checkpoints/<stage>.json  status + review notes + cost + history of that stage
    events.jsonl              tool calls, timings, costs (the board's live feed)
    decisions.jsonl           every choice with its reason (provider, style, fallback, approval policy)

Gate rules (binding, enforced here, never left to an agent):
  - a stage runs only when every earlier stage is complete (approved or done) and none is stale;
  - a gated stage finishes as `awaiting_approval` and only `approve()` completes it;
  - feedback re-runs that stage with the note, at most MAX_REVISIONS times;
  - reopening an earlier stage marks every later stage `stale`, visibly; nothing is deleted.
"""
import json, os, re, tempfile, unicodedata

from ..config import ROOT
from ..store import now
from . import manifest

DIR = os.path.join(ROOT, "projects")
MAX_REVISIONS = 3
STATUSES = ("pending", "running", "awaiting_approval", "approved", "done", "failed", "stale")
COMPLETE = ("approved", "done")


class GateError(RuntimeError):
    """A request the gate rules do not allow (the Studio shows the message as it is)."""


def _atomic(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def _read(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


_TRANSLIT = str.maketrans({"ı": "i", "İ": "I", "ß": "ss", "ø": "o", "Ø": "O", "æ": "ae", "Æ": "AE", "đ": "d", "ł": "l"})


def slug(text, n=40):
    """ASCII slug; letters NFKD cannot split (Turkish dotless ı and the like) are mapped first, not dropped."""
    t = unicodedata.normalize("NFKD", str(text or "").translate(_TRANSLIT)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:n].strip("-") or "video"


def root(d=None):
    return d or DIR


def path(pid, *parts, d=None):
    return os.path.join(root(d), pid, *parts)


def _numbers(d=None):
    out = []
    try:
        out += [int(n[:3]) for n in os.listdir(root(d)) if n[:3].isdigit()]
    except OSError:
        pass
    return out


def next_number(con=None, d=None):
    """One counter for old productions and new projects, so no two videos share a number."""
    used = _numbers(d)
    if con is not None:
        try:
            used += [int(r[0][:3]) for r in con.execute("SELECT name FROM productions WHERE name IS NOT NULL")
                     if str(r[0])[:3].isdigit()]
        except Exception:
            pass
        try:
            from ..jobs import next_number as legacy
            used.append(legacy() - 1)
        except Exception:
            pass
    return max(used + [0]) + 1


def create(line_id, title, brief="", video_lang="tr", aspect="9:16", channel=None, user=None, con=None, d=None,
           num=None, extra=None):
    m = manifest.get(line_id)
    num = num or next_number(con, d)
    pid = f"{num:03d}-{slug(title)}"
    if os.path.exists(path(pid, d=d)):
        raise GateError(f"project {pid} already exists")
    p = {"id": pid, "num": num, "line": line_id, "title": title, "brief": brief, "video_lang": video_lang,
         "aspect": aspect, "channel": channel, "created_at": now(), "created_by": user, "status": "active",
         "budget": None, **(extra or {})}
    for sub in ("artifacts", "checkpoints", "assets", "stills", "renders"):
        os.makedirs(path(pid, sub, d=d), exist_ok=True)
    _atomic(path(pid, "project.json", d=d), p)
    for s in m["stages"]:
        _atomic(path(pid, "checkpoints", s["id"] + ".json", d=d), _blank(s))
    event(pid, "created", d=d, line=line_id, by=user)
    return p


def _blank(s):
    return {"stage": s["id"], "status": "pending", "artifact": s["artifact"], "revisions": 0, "review": None,
            "cost": {"credits": 0, "usd": 0.0}, "note": None, "error": None, "history": []}


def load(pid, d=None):
    p = _read(path(pid, "project.json", d=d))
    if p is None:
        raise GateError(f"no project {pid}")
    return p


def save(p, d=None):
    _atomic(path(p["id"], "project.json", d=d), p)


def list_ids(d=None):
    try:
        return sorted((n for n in os.listdir(root(d)) if os.path.isfile(path(n, "project.json", d=d))), reverse=True)
    except OSError:
        return []


# ---------------------------------------------------------------- checkpoints

def checkpoint(pid, sid, d=None):
    cp = _read(path(pid, "checkpoints", sid + ".json", d=d))
    if cp is None:
        raise GateError(f"{pid}: no stage '{sid}'")
    return cp


def _write_cp(pid, cp, d=None):
    _atomic(path(pid, "checkpoints", cp["stage"] + ".json", d=d), cp)


def _log(cp, event_, by=None, note=None):
    cp["history"].append({"at": now(), "event": event_, **({"by": by} if by else {}), **({"note": note} if note else {})})


def stages(pid, d=None):
    """[(stage manifest entry, checkpoint)] in line order."""
    p = load(pid, d)
    m = manifest.get(p["line"])
    return [(s, checkpoint(pid, s["id"], d)) for s in m["stages"]]


def next_stage(pid, d=None):
    """The first stage that is not complete, and what it waits for:
       ("run", sid)       ready to run (earlier stages complete)
       ("gate", sid)      finished, waiting for the human
       ("busy", sid)      running now
       ("failed", sid)    last run failed (retry or feedback)
       ("done", None)     every stage complete."""
    for s, cp in stages(pid, d):
        st = cp["status"]
        if st in COMPLETE:
            continue
        if st == "awaiting_approval":
            return "gate", s["id"]
        if st == "running":
            return "busy", s["id"]
        if st == "failed":
            return "failed", s["id"]
        return "run", s["id"]          # pending or stale
    return "done", None


def _require_ready(pid, sid, d=None):
    for s, cp in stages(pid, d):
        if s["id"] == sid:
            return s, cp
        if cp["status"] not in COMPLETE:
            raise GateError(f"'{sid}' cannot start: '{s['id']}' is {cp['status']}")
    raise GateError(f"{pid}: no stage '{sid}'")


def start(pid, sid, by=None, d=None):
    s, cp = _require_ready(pid, sid, d)
    if cp["status"] == "running":
        raise GateError(f"'{sid}' is already running")
    if cp["status"] in COMPLETE:
        raise GateError(f"'{sid}' is already complete; reopen it first")
    if s["run"] == "planned":
        raise GateError(f"'{sid}' is not built yet on this line")
    cp.update(status="running", error=None, started_at=now())
    _log(cp, "start", by, cp.get("note"))
    _write_cp(pid, cp, d)
    event(pid, "stage_start", d=d, stage=sid)
    return cp


def finish(pid, sid, artifact=None, review=None, cost=None, summary=None, d=None):
    """The stage's work is written. A gate waits for the human; anything else is done."""
    p = load(pid, d)
    s = manifest.stage(manifest.get(p["line"]), sid)
    cp = checkpoint(pid, sid, d)
    if cp["status"] != "running":
        raise GateError(f"'{sid}' is not running (it is {cp['status']})")
    if artifact is not None:
        write_artifact(pid, s["artifact"], artifact, d)
    if not os.path.exists(path(pid, "artifacts", s["artifact"] + ".json", d=d)):
        raise GateError(f"'{sid}' finished without its artifact '{s['artifact']}'")
    for k, v in (cost or {}).items():
        cp["cost"][k] = round(cp["cost"].get(k, 0) + (v or 0), 4)
    cp.update(status="awaiting_approval" if s["gate"] else "done", review=review, summary=summary,
              finished_at=now(), note=None)
    _log(cp, "finish")
    _write_cp(pid, cp, d)
    event(pid, "stage_finish", d=d, stage=sid, status=cp["status"])
    return cp


def fail(pid, sid, error, d=None):
    cp = checkpoint(pid, sid, d)
    cp.update(status="failed", error=str(error)[:2000], finished_at=now())
    _log(cp, "fail", note=str(error)[:300])
    _write_cp(pid, cp, d)
    event(pid, "stage_fail", d=d, stage=sid, error=str(error)[:300])
    return cp


def approve(pid, sid, by=None, note=None, d=None):
    cp = checkpoint(pid, sid, d)
    if cp["status"] != "awaiting_approval":
        raise GateError(f"'{sid}' is not waiting for approval (it is {cp['status']})")
    cp.update(status="approved", approved_at=now(), approved_by=by)
    _log(cp, "approve", by, note)
    _write_cp(pid, cp, d)
    event(pid, "approve", d=d, stage=sid, by=by)
    decision(pid, "approval", f"{sid} approved", by=by, note=note, d=d)
    return cp


def feedback(pid, sid, note, by=None, d=None):
    """Re-run this stage with the creator's note. Allowed while it waits at its gate or after it failed."""
    note = (note or "").strip()
    if not note:
        raise GateError("feedback needs a note")
    cp = checkpoint(pid, sid, d)
    if cp["status"] not in ("awaiting_approval", "failed"):
        raise GateError(f"'{sid}' takes feedback only at its gate (it is {cp['status']}); reopen it first")
    if cp["revisions"] >= MAX_REVISIONS:
        raise GateError(f"'{sid}' reached {MAX_REVISIONS} revisions; go back to an earlier stage or approve")
    cp.update(status="pending", note=note, revisions=cp["revisions"] + 1)
    _log(cp, "feedback", by, note)
    _write_cp(pid, cp, d)
    event(pid, "feedback", d=d, stage=sid, by=by)
    return cp


def reopen(pid, sid, by=None, d=None):
    """Go back: this stage waits at its gate again (or pending if it has no gate); every later stage turns stale."""
    rows = stages(pid, d)
    ids = [s["id"] for s, _ in rows]
    if sid not in ids:
        raise GateError(f"{pid}: no stage '{sid}'")
    if any(cp["status"] == "running" for _, cp in rows):
        raise GateError("a stage is running; wait for it to finish")
    i = ids.index(sid)
    s, cp = rows[i]
    if cp["status"] not in COMPLETE:
        raise GateError(f"'{sid}' is not complete; nothing to reopen")
    cp.update(status="awaiting_approval" if s["gate"] else "pending", revisions=0)
    _log(cp, "reopen", by)
    _write_cp(pid, cp, d)
    for s2, cp2 in rows[i + 1:]:
        if cp2["status"] != "pending":
            cp2["status"] = "stale"
            _log(cp2, "stale", note=f"'{sid}' was reopened")
            _write_cp(pid, cp2, d)
    event(pid, "reopen", d=d, stage=sid, by=by)
    return cp


# ---------------------------------------------------------------- artifacts, events, decisions

def write_artifact(pid, name, data, d=None):
    _atomic(path(pid, "artifacts", name + ".json", d=d), data)


def read_artifact(pid, name, d=None, default=None):
    return _read(path(pid, "artifacts", name + ".json", d=d), default)


def _append(pid, fname, row, d=None):
    with open(path(pid, fname, d=d), "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def event(pid, kind, d=None, **data):
    _append(pid, "events.jsonl", {"at": now(), "kind": kind, **data}, d)


def decision(pid, category, choice, reason=None, d=None, **data):
    _append(pid, "decisions.jsonl", {"at": now(), "category": category, "choice": choice, "reason": reason, **data}, d)


def tail(pid, fname="events.jsonl", n=50, d=None):
    try:
        with open(path(pid, fname, d=d), encoding="utf-8") as f:
            lines = f.readlines()[-n:]
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except ValueError:
            pass
    return out


# ---------------------------------------------------------------- the board's view

def flow(pid, lang="tr", d=None):
    """Everything the Studio's flow view needs, in one language."""
    p = load(pid, d)
    m = manifest.localize(manifest.get(p["line"]), lang)
    cps = {s["id"]: checkpoint(pid, s["id"], d) for s in m["stages"]}
    state, current = next_stage(pid, d)
    return {"project": p, "line": {k: m[k] for k in ("id", "name", "tagline", "status")}, "state": state,
            "current": current,
            "stages": [{**{k: s[k] for k in ("id", "name", "says", "gate_says", "gate", "run", "artifact")},
                        **{k: cps[s["id"]].get(k) for k in ("status", "revisions", "review", "cost", "summary", "error",
                                                            "note", "history")}} for s in m["stages"]],
            "spent": {"credits": sum(c["cost"].get("credits", 0) for c in cps.values()),
                      "usd": round(sum(c["cost"].get("usd", 0) for c in cps.values()), 4)}}
