"""The review gauntlet (t516): the builder is never the judge, the judge looks at a fresh render, and every finding
goes into a ledger that later reviews must close.

- Fresh render: before each review of a stage that can be drawn (its tools include render_stills), the studio renders
  the submitted artifact itself into a new folder and tiles a contact sheet. The reviewer is told to judge those
  pictures, not stills the author made (an author's stills can be from an older draft).
- Ledger: artifacts/review_ledger.json keeps every finding of every review of the stage, with an id. The next
  review gets the open entries by id and marks each one fixed, open or dropped (the creator's note made it moot);
  its new findings are added. The author's fix note lists what is still open, so an old problem cannot quietly
  come back. The gate card shows the ledger.
"""

from . import project as P

FILE = "review_ledger"
STATUSES = ("open", "fixed", "dropped")


def load(pid, sid, d=None):
    return ((P.read_artifact(pid, FILE, d) or {}).get(sid)) or {"entries": [], "reviews": 0}


def _save(pid, sid, led, d=None):
    data = P.read_artifact(pid, FILE, d) or {}
    data[sid] = led
    P.write_artifact(pid, FILE, data, d)


def open_entries(led):
    return [e for e in led["entries"] if e["status"] == "open"]


def brief(pid, s, d=None):
    """The reviewer's ledger section: the open entries it must close or keep open."""
    led = load(pid, s["id"], d)
    rows = open_entries(led)
    if not rows:
        return ""
    return ("\n## Ledger: findings of earlier reviews still open (binding)\nFor EACH id below, check the output again "
            'and put it in `ledger` as {"id": ..., "status": "fixed" | "open" | "dropped"} ("dropped" only when the '
            "creator's feedback made it moot). Do not repeat these in `findings`; `findings` is for new problems.\n"
            + "\n".join(f"- {e['id']} [{e['severity']}] {e['item']}: {e['problem']} -> {e['fix']}" for e in rows) + "\n")


def record(pid, s, review, rnd, d=None):
    """Merge one review into the ledger. Returns the ledger summary kept on the review: {open, fixed, dropped, entries}."""
    led = load(pid, s["id"], d)
    led["reviews"] += 1
    n = led["reviews"]
    by_id = {e["id"]: e for e in led["entries"]}
    for x in review.pop("ledger_marks", None) or []:
        e = by_id.get(str(x.get("id")))
        if e and e["status"] == "open" and x.get("status") in STATUSES and x["status"] != "open":
            e.update(status=x["status"], closed_review=n)
    run = P.checkpoint(pid, s["id"], d)["revisions"]
    for f in review["findings"]:
        if f["severity"] == "nitpick":
            continue                                    # taste is not tracked
        led["entries"].append({"id": f"f{len(led['entries']) + 1}", "review": n, "run": run, "round": rnd + 1,
                               "status": "open", **{k: f[k] for k in ("severity", "item", "problem", "fix")}})
    _save(pid, s["id"], led, d)
    count = {k: sum(1 for e in led["entries"] if e["status"] == k) for k in STATUSES}
    return {**count, "entries": led["entries"][-40:]}


def fix_lines(pid, s, d=None):
    """Ledger entries from EARLIER reviews that are still open, for the author's note (the latest review's own
    findings are already in it)."""
    led = load(pid, s["id"], d)
    return [f"- {e['id']} [{e['item']}] {e['problem']} -> {e['fix']}" for e in open_entries(led)
            if e["review"] < led["reviews"]]


def open_critical(pid, s, d=None):
    return sum(1 for e in open_entries(load(pid, s["id"], d)) if e["severity"] == "critical")


def fresh_render(pid, s, rnd, d=None):
    """Render the submitted artifact into a new folder for the reviewer. -> {stills, sheet, js_errors} or None."""
    from . import tools as T
    if "render_stills" not in s["tools"] or not T.available("render_stills")[0]:
        return None
    ctx = T.Ctx(pid, f"review-{s['id']}-r{rnd + 1}", d)
    try:
        r = T.call("render_stills", ctx, {})
        out = {"stills": r["stills"], "js_errors": r.get("js_errors") or [], "times": r.get("times"), "sheet": None}
        if r["stills"]:
            out["sheet"] = T.call("contact_sheet", ctx, {"stills": r["stills"], "title": f"review {rnd + 1}"})["sheet"]
        if "layout_lint" in s["tools"]:                 # the measured grade (t520) and the lint, for the reviewer too
            try:
                lint = T.call("layout_lint", ctx, {})
                out.update(grade=lint.get("grade"), lint=lint.get("text") or [])
            except Exception as e:
                P.event(pid, "review_lint_error", d=d, stage=s["id"], error=str(e)[:300])
        P.event(pid, "review_render", d=d, stage=s["id"], round=rnd + 1, stills=len(r["stills"]))
        return out
    except Exception as e:                              # a failed render never blocks the review; it is logged
        P.event(pid, "review_render_error", d=d, stage=s["id"], error=str(e)[:300])
        return None


def render_brief(r):
    if not r:
        return ""
    return ("\n## Fresh render (made by the studio from the submitted artifact just now)\nJudge THESE pictures with "
            "Read; do not trust stills the author made, they can be from an older draft. "
            f"Contact sheet: {r['sheet'] or '(none)'}\nStills (one settled frame per scene, at {r.get('times')} s):\n"
            + "\n".join(f"- {x}" for x in r["stills"])
            + (f"\nJavaScript errors on the page: {r['js_errors']}\n" if r["js_errors"] else "\n")
            + grade_brief(r))


def grade_brief(r):
    g = r.get("grade")
    if not g and not r.get("lint"):
        return ""
    head = (f"\n## Measured grade: {g['grade'].upper()} {g['score']}/100 (layout, timing, slop lint, measured easing: "
            f"{g['parts']})\nA SLOP grade, or any `slop` line below, is a major finding unless the brief asks for it.\n"
            if g else "\n## Lint\n")
    return head + "\n".join(f"- {x}" for x in (r.get("lint") or [])[:14]) + "\n"
