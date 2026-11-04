"""The line manager: moves a project through its production line. Deterministic, no creative decisions.

It starts the next runnable stage as a background job (`hat_stage`), runs that stage (a code step from the manifest's
`call`, or a stage agent), records the result through factory/hat/project.py, and keeps going until it reaches a
gate or the end. The three human actions are here too: continue (approve), feedback (re-run this stage with a note)
and go back (reopen an earlier stage).

`queue(kind, arg) -> job id` is passed in, so the Studio uses factory/jobs.queue and tests use a list.
"""
import importlib, json, traceback

from . import manifest, project as P

JOB = "hat_stage"


def _job_arg(pid, sid):
    return json.dumps({"project": pid, "stage": sid}, ensure_ascii=False)


def advance(pid, queue, by=None, d=None):
    """Queue the next runnable stage, if any. Returns (state, stage) after the call."""
    state, sid = P.next_stage(pid, d)
    if state != "run":
        return state, sid
    s = manifest.stage(manifest.get(P.load(pid, d)["line"]), sid)
    if s["run"] == "planned":
        return "planned", sid
    P.start(pid, sid, by=by, d=d)
    P.event(pid, "queued", d=d, stage=sid)
    queue(JOB, _job_arg(pid, sid))
    return P.next_stage(pid, d)   # "busy" while the job runs; a fast job may already be at the next gate


def approve(pid, sid, queue, by=None, note=None, d=None):
    from .. import proof
    proof.guard(pid, sid, d)          # proof mode: a number without its source cannot pass the gate
    P.approve(pid, sid, by=by, note=note, d=d)
    p = P.load(pid, d)       # the approved proposal (whatever the stage is called) fixes the budget every
    if manifest.stage(manifest.get(p["line"]), sid)["artifact"] == "proposal":   # credit-spending step stays inside
        lock_budget(pid, by, d)
    return advance(pid, queue, by, d)


def feedback(pid, sid, note, queue, by=None, d=None):
    from .. import filmstyles as styles     # "stil: noir" at a look-choosing proposal gate sets the style; no agent re-run
    style = styles.pick(note)
    if style and styles.picks_style(manifest.stage(manifest.get(P.load(pid, d)["line"]), sid)) \
            and P.checkpoint(pid, sid, d)["status"] == "awaiting_approval":
        styles.apply(pid, sid, style, by=by, d=d)
        return P.next_stage(pid, d)
    P.feedback(pid, sid, note, by=by, d=d)
    return advance(pid, queue, by, d)


def back(pid, sid, by=None, d=None):
    P.reopen(pid, sid, by=by, d=d)
    return P.next_stage(pid, d)


def retry(pid, sid, queue, by=None, d=None):
    """Run a failed stage again without a note."""
    cp = P.checkpoint(pid, sid, d)
    if cp["status"] != "failed":
        raise P.GateError(f"'{sid}' did not fail")
    cp["status"] = "pending"
    P._write_cp(pid, cp, d)
    return advance(pid, queue, by, d)


def lock_budget(pid, by=None, d=None):
    prop = P.read_artifact(pid, "proposal", d, {}) or {}
    cost = prop.get("cost") or {}
    p = P.load(pid, d)
    p["budget"] = {"credits": int(cost.get("credits") or 0), "usd": float(cost.get("usd") or 0),
                   "approved_by": by, "lines": cost.get("lines") or []}
    P.save(p, d)
    P.decision(pid, "budget", f"{p['budget']['credits']} credits", reason="proposal approved", by=by, d=d)


def _code_step(call):
    mod, fn = call.split(":", 1)
    return getattr(importlib.import_module(mod), fn)


def execute(pid, sid, d=None):
    """Run one started stage and record its outcome. Returns the stage's checkpoint."""
    p = P.load(pid, d)
    s = manifest.stage(manifest.get(p["line"]), sid)
    cp = P.checkpoint(pid, sid, d)
    if cp["status"] != "running":
        raise P.GateError(f"'{sid}' was not started (it is {cp['status']})")
    try:
        if s["run"] == "code":
            out = _code_step(s["call"])(pid, s, note=cp.get("note"), d=d) or {}
        elif s["run"] == "agent":
            from . import agent
            out = agent.run_stage(pid, s, note=cp.get("note"), d=d) or {}
            from .. import framenotes
            framenotes.settle(pid, s, d)      # frame comments (t514): only the commented scenes may change
        else:
            raise P.GateError(f"'{sid}' is not built yet on this line")
    except Exception as e:
        traceback.print_exc()
        return P.fail(pid, sid, f"{type(e).__name__}: {e}", d=d)
    return P.finish(pid, sid, artifact=out.get("artifact"), review=out.get("review"), cost=out.get("cost"),
                    summary=out.get("summary"), d=d)


def run_job(arg, queue, d=None):
    """The `hat_stage` job: run the stage, then keep the line moving until a gate, a failure or the end."""
    o = json.loads(arg)
    pid, sid = o["project"], o["stage"]
    cp = execute(pid, sid, d)
    if cp["status"] == "done":
        state, nxt = advance(pid, queue, d=d)
        return f"{sid}: done -> {state} {nxt or ''}".strip()
    return f"{sid}: {cp['status']}"
