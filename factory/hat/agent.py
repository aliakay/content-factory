"""The stage agent: one headless CLI session (Claude Code or Codex) that does one stage with our tools.

It gets the shared contract (skills/meta/stage-agent.md), the stage brief (skills/pipelines/<line>/<stage>.md), the
manifest's review focus, the project facts and the creator's feedback note; it sees only the tools the manifest
allows (factory-tools MCP server + CLI built-ins such as WebSearch) and hands its output in with submit_artifact.
The stage counts as done only if an accepted artifact was written during this run.
"""
import importlib, json, os, re, time

from .. import llm
from ..config import ROOT
from . import gauntlet, manifest, mcp_server, project as P, tools as T

SKILLS = os.path.join(ROOT, "skills")
SERVER = "factory"
TIMEOUT = 2400                                   # seconds per stage run
BUDGET = {"haiku": 0.5, "sonnet": 2.0, "opus": 5.0}   # USD cap per stage run (Claude), by model
LANG_NAME = {"tr": "Turkish", "en": "English", "de": "German"}


class AgentError(RuntimeError):
    pass


INCLUDE = re.compile(r"\{\{include:([\w.]+):(\w+)\}\}")


def expand(text, p):
    """{{include:module:name}} -> that module's text constant, or name(project) for a function: the craft rules keep
    one source in code and the briefs stay short."""
    def sub(m):
        obj = getattr(importlib.import_module(m.group(1)), m.group(2))
        return str(obj(p) if callable(obj) else obj)
    return INCLUDE.sub(sub, text)


def skill(line_id, sid, p=None):
    path = os.path.join(SKILLS, "pipelines", line_id, sid + ".md")
    if not os.path.exists(path):
        raise AgentError(f"no stage brief {os.path.relpath(path, ROOT)}")
    return expand(open(path, encoding="utf-8").read(), p or {})


def contract():
    return open(os.path.join(SKILLS, "meta", "stage-agent.md"), encoding="utf-8").read()


def task(pid, s, note=None, d=None):
    """The full instruction text for one stage run."""
    from .. import proof, sceneedit
    p = P.load(pid, d)
    m = manifest.get(p["line"])
    earlier = [x["artifact"] for x in m["stages"][:[y["id"] for y in m["stages"]].index(s["id"])]
               if P.read_artifact(pid, x["artifact"], d) is not None]
    ui = p.get("ui_lang", "tr")
    review = "\n".join(f"- {r}" for r in s["review"]) or "- (none listed)"
    feedback = (f"\n## Creator feedback on your previous attempt (revision {P.checkpoint(pid, s['id'], d)['revisions']})"
                f"\n{note}\n") if note else ""
    return f"""{contract()}

# This run
Line: {m['name']['en']} ({m['id']}) · Stage: {s['name']['en']} ({s['id']}) · Output artifact: `{s['artifact']}`
Video language: {LANG_NAME.get(p.get('video_lang'), p.get('video_lang'))} · Interface language for `summary`: {LANG_NAME.get(ui, ui)}
Aspect: {p.get('aspect')} · Earlier artifacts you can read: {', '.join(earlier) or 'none'}
{feedback}
## Review focus (a separate reviewer checks these; meet them before you submit)
{review}

## Stage brief
{skill(p['line'], s['id'], p)}{proof.brief(pid, s, d)}{sceneedit.brief(pid, s, d)}
"""


REVIEW_ROUNDS = 2
PASS_SCORE = 90                                  # rubric points (of 100) a stage output needs from the reviewer (t515)
OTHER_MODEL = {"opus": "sonnet", "sonnet": "opus", "haiku": "sonnet"}
SEVERITIES = ("critical", "suggestion", "nitpick")


def run_stage(pid, s, note=None, d=None, user=None):
    """Author -> reviewer, at most REVIEW_ROUNDS times while the reviewer finds critical problems.
    Returns {artifact: None (already written), summary, review, cost}."""
    cost, rounds, review = 0.0, [], None
    author_note = note
    for rnd in range(REVIEW_ROUNDS + 1):
        try:
            out = _author(pid, s, author_note, d, user)
        except AgentError as e:
            if rnd == 0:
                raise
            P.event(pid, "review_fix_failed", d=d, stage=s["id"], error=str(e)[:300])   # keep the accepted output
            break
        cost += out["cost"]["usd"]
        if not s["review"]:
            break
        review = review_stage(pid, s, d, user, rnd)
        cost += review.pop("cost_usd", 0) or 0
        rounds.append({k: review[k] for k in ("verdict", "findings")})
        if review["verdict"] != "unknown":
            review["ledger"] = gauntlet.record(pid, s, review, rnd, d)
        critical = [f for f in review["findings"] if f["severity"] == "critical"]
        held = gauntlet.open_critical(pid, s, d) if "ledger" in review else 0
        if held and review["verdict"] == "pass":
            review["verdict"] = "fix"                   # an earlier critical the reviewer did not close blocks a pass
        low = review.get("score") is not None and review["score"] < review["pass_score"]
        if not (critical or held or low) or rnd == REVIEW_ROUNDS:
            break
        P.event(pid, "review_fix", d=d, stage=s["id"], round=rnd + 1, critical=len(critical), score=review.get("score"))
        author_note = ((note + "\n\n") if note else "") + _fix_note(review, critical, gauntlet.fix_lines(pid, s, d))
    if review is not None:
        review["rounds"] = len(rounds)
        review["open_critical"] = max(sum(1 for f in review["findings"] if f["severity"] == "critical"),
                                      gauntlet.open_critical(pid, s, d) if "ledger" in review else 0)
    return {"artifact": None, "summary": out["summary"], "review": review, "cost": {"usd": round(cost, 4)}}


def _fix_note(review, critical, ledger=()):
    """What the author is told after a review that did not pass: the critical findings, the rubric items that
    scored below full marks with the findings on them, and every ledger entry still open."""
    out = []
    if critical:
        out.append("A reviewer found these critical problems in your submission; fix every one and submit again:\n"
                   + "\n".join(f"- [{f['item']}] {f['problem']} -> {f['fix']}" for f in critical))
    if review.get("score") is not None and review["score"] < review["pass_score"]:
        weak = [r for r in review["rubric"] if r["score"] < 10]
        rest = [f for f in review["findings"] if f["severity"] != "critical"]
        out.append(f"The reviewer's rubric score is {review['score']}/100; {review['pass_score']} is needed. Raise these "
                   "items (score of 10 each):\n" + "\n".join(f"- {r['item']}: {r['score']}/10" for r in weak)
                   + ("\nTheir other findings:\n" + "\n".join(f"- [{f['item']}] {f['problem']} -> {f['fix']}"
                                                              for f in rest) if rest else ""))
    if ledger:
        out.append("Still open in the review ledger (earlier rounds included); each must be fixed:\n" + "\n".join(ledger))
    return "\n\n".join(out)


def rubric(focus, raw):
    """The reviewer's per-item marks (one 0-10 integer per review-focus item, in order) -> ([{item, score}], 0-100).
    The total is computed here, never taken from the reviewer; a list that does not match the focus gives (None, None)."""
    if not focus or not isinstance(raw, list) or len(raw) != len(focus):
        return None, None
    try:
        marks = [max(0, min(10, int(round(float(x))))) for x in raw]
    except (TypeError, ValueError):
        return None, None
    return [{"item": i, "score": m} for i, m in zip(focus, marks)], round(10 * sum(marks) / len(marks))


def review_task(pid, s, d=None, render=None):
    p = P.load(pid, d)
    ui = p.get("ui_lang", "tr")
    focus = "\n".join(f"{k}. {r}" for k, r in enumerate(s["review"], 1))
    return f"""{open(os.path.join(SKILLS, "meta", "reviewer.md"), encoding="utf-8").read()}

# This review
Stage: {s['name']['en']} ({s['id']}) · Artifact to review: `{s['artifact']}`
Video language: {LANG_NAME.get(p.get('video_lang'), p.get('video_lang'))} · Interface language for `summary`: {LANG_NAME.get(ui, ui)}

## Review focus (the rubric: give one mark per item, in this order, {len(s['review'])} marks in `scores`)
{focus}
Pass mark: {s.get('pass_score') or PASS_SCORE}/100 (the mean of your marks x 10).
{gauntlet.render_brief(render)}{gauntlet.brief(pid, s, d)}"""


def review_stage(pid, s, d=None, user=None, rnd=0):
    """A fresh reviewer (another model, read-only tools, a new session) judges the submitted artifact, on a render
    the studio just made of it when the stage can be drawn."""
    p = P.load(pid, d)
    render = gauntlet.fresh_render(pid, s, rnd, d)
    ours, builtins = T.agent_tools([t for t in s["tools"] if t != "submit_artifact"])
    ours = [t for t in ours if t != "submit_artifact"]
    servers = {SERVER: mcp_server.config(pid, s["id"], ours, d=d, user=user or p.get("created_by"))}
    model = OTHER_MODEL.get(s.get("model") or "sonnet", "sonnet")
    try:
        text, meta = llm.ask_text(review_task(pid, s, d, render), tools=tuple([f"mcp__{SERVER}__{n}" for n in ours] + builtins
                                                                         + ["Read"]),
                                  timeout=1200, model=model, retries=1, servers=servers, budget_usd=BUDGET.get(model, 2.0))
        r = llm.extract_json(text)
    except (llm.LLMError, ValueError) as e:   # a broken review never blocks the stage: the gate shows it as missing
        P.event(pid, "review_error", d=d, stage=s["id"], error=str(e)[:300])
        return {"verdict": "unknown", "findings": [], "summary": "", "error": str(e)[:300], "cost_usd": 0}
    findings = [{"severity": f.get("severity") if f.get("severity") in SEVERITIES else "suggestion",
                 **{k: str(f.get(k, ""))[:600] for k in ("item", "problem", "fix")}}
                for f in (r.get("findings") or []) if isinstance(f, dict)]
    marks, score = rubric(s["review"], r.get("scores"))
    need = s.get("pass_score") or PASS_SCORE
    if marks is None and s["review"]:
        P.event(pid, "review_unscored", d=d, stage=s["id"], got=str(r.get("scores"))[:200])
    verdict = "fix" if any(f["severity"] == "critical" for f in findings) or (score is not None and score < need) \
        else "pass"
    P.event(pid, "review", d=d, stage=s["id"], model=model, verdict=verdict, findings=len(findings), score=score)
    return {"verdict": verdict, "findings": findings, "summary": str(r.get("summary", ""))[:800], "model": model,
            "rubric": marks, "score": score, "pass_score": need, "cost_usd": meta.get("cost_usd") or 0,
            "ledger_marks": [x for x in (r.get("ledger") or []) if isinstance(x, dict)],
            "render": {"sheet": render["sheet"], "stills": len(render["stills"]), "grade": render.get("grade")}
            if render else None}


def _author(pid, s, note=None, d=None, user=None):
    """One authoring run. Returns {summary, cost}."""
    p = P.load(pid, d)
    ours, builtins = T.agent_tools(s["tools"])
    allowed_cli = [f"mcp__{SERVER}__{n}" for n in ours] + builtins + ["Read"]
    servers = {SERVER: mcp_server.config(pid, s["id"], ours, d=d, user=user or p.get("created_by"))}
    model = s.get("model") or "sonnet"
    art = P.path(pid, "artifacts", s["artifact"] + ".json", d=d)
    before = os.path.getmtime(art) if os.path.exists(art) else 0
    started = time.time()
    P.event(pid, "agent_start", d=d, stage=s["id"], model=model, tools=ours + builtins)
    try:
        reply, meta = llm.ask_text(task(pid, s, note, d), tools=tuple(allowed_cli), timeout=s.get("timeout") or TIMEOUT,
                                   model=model, retries=1, servers=servers,
                                   budget_usd=s.get("budget_usd") or BUDGET.get(model, 3.0))
    except llm.LLMError as e:
        raise AgentError(str(e)) from None
    written = os.path.exists(art) and os.path.getmtime(art) > before and os.path.getmtime(art) >= started - 1
    P.event(pid, "agent_end", d=d, stage=s["id"], seconds=round(time.time() - started), cost_usd=meta.get("cost_usd"),
            submitted=written)
    if not written:
        raise AgentError(f"the agent ended without an accepted '{s['artifact']}' (last words: {reply.strip()[-300:]})")
    data = P.read_artifact(pid, s["artifact"], d) or {}
    return {"summary": data.get("summary"), "cost": {"usd": meta.get("cost_usd") or 0}}
