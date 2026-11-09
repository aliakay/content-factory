"""The line manager: moves a project through its production line. Deterministic, no creative decisions.

It starts the next runnable stage as a background job (`hat_stage`), runs that stage (a code step from the manifest's
`call`, or a stage agent), records the result through factory/hat/project.py, and keeps going until it reaches a
gate or the end. The three human actions are here too: continue (approve), feedback (re-run this stage with a note)
and go back (reopen an earlier stage).

`queue(kind, arg) -> job id` is passed in, so the Studio uses factory/jobs.queue and local callers use a list.
"""
import importlib, json, time, traceback

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
    from .. import coldtest, hookrule, licence, proof
    cp = P.checkpoint(pid, sid, d)
    if cp["status"] != "awaiting_approval":        # the wrong stage: say so before any rule about its content
        raise P.GateError(f"'{sid}' is not waiting for approval (it is {cp['status']})")
    st = manifest.stage(manifest.get(P.load(pid, d)["line"]), sid)
    if st["gate"] and (st["run"] == "code" or st["artifact"] == "scene_plan"):
        # Code stages can write artifacts without going through submit_artifact. Apply the same schema and
        # semantic checks at the approval boundary, especially to long_explainer's merged scene plan.
        from . import tools
        artifact = P.read_artifact(pid, st["artifact"], d) or {}
        found = tools.validate_artifact(st["schema"], artifact) or tools._meaning(
            tools.Ctx(pid, sid, d), st["schema"], artifact)
        if found:
            raise P.GateError("This stage does not pass its artifact checks:\n" + "\n".join("- " + x for x in found))
    if st["gate"] and st["artifact"] == "scene_plan" and st["schema"] == "scene_plan":
        _verify_scene_determinism(pid, sid, d)
    if st["gate"] and st["artifact"] == "animatic":
        found = hookrule.animatic_problems(P.read_artifact(pid, "animatic", d) or {})
        if found:
            raise P.GateError("Opening-motion rule: the animatic does not pass:\n" + "\n".join("- " + x for x in found))
    proof.guard(pid, sid, d)          # proof mode: a number without its source cannot pass the gate
    hookrule.guard(pid, sid, d)       # the hook rule: line 1 must land in 3 s, concrete and on-subject
    coldtest.guard(pid, sid, d)       # an independent reader must understand the exact lines at the script gate
    rows = licence.guard(pid, sid, d) # the attribution ledger: no unlicensed asset, no missing required credit
    if rows is not None:
        art = P.read_artifact(pid, "publish", d) or {}
        art["credits_file"] = licence.write_credits(pid, d, rows)
        P.write_artifact(pid, "publish", art, d)
    P.approve(pid, sid, by=by, note=note, d=d)
    p = P.load(pid, d)       # the approved proposal (whatever the stage is called) fixes the budget every
    art = manifest.stage(manifest.get(p["line"]), sid)["artifact"]
    if art == "proposal":    # credit-spending step stays inside it
        lock_budget(pid, by, d)
    elif art == "script":
        refit_budget(pid, by, d)   # the narrated text now exists: price it, so the voice is not refused later
    return advance(pid, queue, by, d)


def _verify_scene_determinism(pid, sid, d=None):
    """At the human gate, capture the same three moments in two fresh browsers and refuse pixel drift."""
    from .. import determinism
    from . import explainer, tools
    ctx = tools.Ctx(pid, sid, d)
    plan = P.read_artifact(pid, "scene_plan", d) or {}
    times = explainer.scene_times(pid, plan, d)
    all_times = list(times or [])
    probe = sorted(set(round(float(t), 2) for t in all_times[:1]
                       + all_times[len(all_times) // 2:len(all_times) // 2 + 1] + all_times[-1:]))
    if not probe:
        raise P.GateError("Determinism check could not run: the scene plan has no renderable moments.")
    bundle = tools._draft_plan(ctx, plan)
    out = ctx.path("stills", f"gate-determinism-{time.time_ns()}")
    try:
        first, _ = explainer._htmlmotion().shots(bundle, probe, out)
        if len(first or []) != len(probe):
            raise RuntimeError("the first capture did not produce every sampled frame")
        found = tools._render_determinism(ctx, bundle, probe, first, explainer, determinism)
        subject_findings = tools._subject_motion(ctx, plan, bundle, explainer)
    except Exception as e:
        raise P.GateError(f"Determinism check could not complete: {type(e).__name__}: {e}") from None
    if found:
        raise P.GateError("The same scene moments changed between fresh renders:\n"
                          + "\n".join("- " + x.get("detail", "non-deterministic render") for x in found))
    if subject_findings:
        raise P.GateError("Camera / subject action check: the camera move explains the change, but the subject stays still:\n"
                          + "\n".join("- " + x.get("detail", "subject action missing") for x in subject_findings))


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


def _voice_chars(script):
    """Characters the narration request will be charged for: the same pieces `explainer.narrate` sends."""
    from . import explainer as X
    lines = script.get("lines") or []
    starts = [c.get("line") for c in script.get("chapters") or []]
    return sum(len(" ".join(lines[a:b + 1])) for a, b in X.pieces(lines, starts))


def refit_budget(pid, by=None, d=None):
    """Re-price the narration from the written script at its gate: the proposal priced a script that did not exist.

    The proposal estimates the voice from words per second before a line is written, so the real script can land more
    than the guard's +15 % above that estimate — and then the assets stage refuses to spend a single credit. Approving
    the script approves what that script costs: the tts line becomes the measured price and the total moves by the
    difference. Every other line (music, plates, clips) keeps exactly what the creator approved, and the budget never
    drops below what is already spent.
    """
    from .. import credits, formats
    from . import explainer as X
    p = P.load(pid, d)
    b = p.get("budget") or {}
    script = P.read_artifact(pid, "script", d) or {}
    rows = b.get("lines") or []
    # only the lines whose voice is `explainer.assets` narrating inside this budget: other lines price their own steps
    if not b.get("credits") or not script.get("lines") or not X.narrated(script):
        return None
    if not any(st.get("call") == "factory.hat.explainer:assets" for st in manifest.get(p["line"])["stages"]):
        return None
    tts = [i for i, it in enumerate(rows) if it.get("kind") == "tts"]
    if not tts:
        return None
    chars = _voice_chars(script)
    est = credits.estimate([{"kind": "tts", "model": formats.VOICE_MODEL, "units": chars, "unit": "char",
                             "label": rows[tts[0]].get("label") or "Narration"}])
    if est["unknown"] or not est["total"]:
        return None
    before = sum(int(rows[i].get("credits") or 0) for i in tts)
    after = int(est["total"])
    total = max(int(X.spent_credits(pid, d)), int(b["credits"]) - before + after)
    fresh, at = dict(est["lines"][0]), tts[0]
    kept = [fresh if i == at else dict(r) for i, r in enumerate(rows) if i == at or i not in tts]
    p["budget"] = {**b, "credits": total, "lines": kept}
    P.save(p, d)
    P.decision(pid, "budget", f"{total} credits", by=by, d=d,
               reason=f"script approved: narration {before} -> {after} credits ({chars} characters)")
    P.event(pid, "budget_refit", d=d, stage="script", before=before, after=after, chars=chars, total=total)
    return total


def _code_step(call):
    mod, fn = call.split(":", 1)
    return getattr(importlib.import_module(mod), fn)


def execute(pid, sid, d=None):
    """Run one started stage and record its outcome. Returns the stage's checkpoint.

    A stage may also return `{"revise": {"stage": sid, "note": text}}`: it saw the finished work, found the fault in
    an earlier stage, and sends the note back there (factory/hat/project.revise). Nothing new is written; the line
    then goes back to that stage with the note, which is the point of a stage that reviews earlier work."""
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
        cp = P.finish(pid, sid, artifact=out.get("artifact"), review=out.get("review"), cost=out.get("cost"),
                      summary=out.get("summary"), d=d)
        r = out.get("revise")
        if r:                                 # it saw the finished work and found the fault in an earlier stage
            P.revise(pid, r["stage"], r["note"], by=sid, d=d)
            cp = P.checkpoint(pid, sid, d)
    except Exception as e:                    # a stage that cannot record its own result fails with the reason
        traceback.print_exc()
        return P.fail(pid, sid, f"{type(e).__name__}: {e}", d=d)
    return cp


def run_job(arg, queue, d=None):
    """The `hat_stage` job: run the stage, then keep the line moving until a gate, a failure or the end."""
    o = json.loads(arg)
    pid, sid = o["project"], o["stage"]
    execute(pid, sid, d)
    cp = P.checkpoint(pid, sid, d)            # `revise` may have turned this stage stale after it finished
    if cp["status"] in ("done", "stale"):
        state, nxt = advance(pid, queue, d=d)
        return f"{sid}: {cp['status']} -> {state} {nxt or ''}".strip()
    return f"{sid}: {cp['status']}"
