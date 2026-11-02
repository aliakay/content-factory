"""The stage agent: one headless CLI session (Claude Code or Codex) that does one stage with our tools.

It gets the shared contract (skills/meta/stage-agent.md), the stage brief (skills/pipelines/<line>/<stage>.md), the
manifest's review focus, the project facts and the creator's feedback note; it sees only the tools the manifest
allows (factory-tools MCP server + CLI built-ins such as WebSearch) and hands its output in with submit_artifact.
The stage counts as done only if an accepted artifact was written during this run.
"""
import json, os, time

from .. import llm
from ..config import ROOT
from . import manifest, mcp_server, project as P, tools as T

SKILLS = os.path.join(ROOT, "skills")
SERVER = "factory"
TIMEOUT = 2400                                   # seconds per stage run
BUDGET = {"haiku": 0.5, "sonnet": 2.0, "opus": 5.0}   # USD cap per stage run (Claude), by model
LANG_NAME = {"tr": "Turkish", "en": "English", "de": "German"}


class AgentError(RuntimeError):
    pass


def skill(line_id, sid):
    path = os.path.join(SKILLS, "pipelines", line_id, sid + ".md")
    if not os.path.exists(path):
        raise AgentError(f"no stage brief {os.path.relpath(path, ROOT)}")
    return open(path, encoding="utf-8").read()


def contract():
    return open(os.path.join(SKILLS, "meta", "stage-agent.md"), encoding="utf-8").read()


def task(pid, s, note=None, d=None):
    """The full instruction text for one stage run."""
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
{skill(p['line'], s['id'])}
"""


REVIEW_ROUNDS = 2
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
        review = review_stage(pid, s, d, user)
        cost += review.pop("cost_usd", 0) or 0
        rounds.append({k: review[k] for k in ("verdict", "findings")})
        critical = [f for f in review["findings"] if f["severity"] == "critical"]
        if not critical or rnd == REVIEW_ROUNDS:
            break
        P.event(pid, "review_fix", d=d, stage=s["id"], round=rnd + 1, critical=len(critical))
        author_note = ((note + "\n\n") if note else "") + "A reviewer found these critical problems in your submission; " \
            "fix every one and submit again:\n" + "\n".join(f"- [{f['item']}] {f['problem']} -> {f['fix']}" for f in critical)
    if review is not None:
        review["rounds"] = len(rounds)
        review["open_critical"] = sum(1 for f in review["findings"] if f["severity"] == "critical")
    return {"artifact": None, "summary": out["summary"], "review": review, "cost": {"usd": round(cost, 4)}}


def review_task(pid, s, d=None):
    p = P.load(pid, d)
    ui = p.get("ui_lang", "tr")
    focus = "\n".join(f"- {r}" for r in s["review"])
    return f"""{open(os.path.join(SKILLS, "meta", "reviewer.md"), encoding="utf-8").read()}

# This review
Stage: {s['name']['en']} ({s['id']}) · Artifact to review: `{s['artifact']}`
Video language: {LANG_NAME.get(p.get('video_lang'), p.get('video_lang'))} · Interface language for `summary`: {LANG_NAME.get(ui, ui)}

## Review focus
{focus}
"""


def review_stage(pid, s, d=None, user=None):
    """A fresh reviewer (another model, read-only tools) judges the submitted artifact."""
    p = P.load(pid, d)
    ours, builtins = T.agent_tools([t for t in s["tools"] if t != "submit_artifact"])
    ours = [t for t in ours if t != "submit_artifact"]
    servers = {SERVER: mcp_server.config(pid, s["id"], ours, d=d, user=user or p.get("created_by"))}
    model = OTHER_MODEL.get(s.get("model") or "sonnet", "sonnet")
    try:
        text, meta = llm.ask_text(review_task(pid, s, d), tools=tuple([f"mcp__{SERVER}__{n}" for n in ours] + builtins
                                                                         + ["Read"]),
                                  timeout=1200, model=model, retries=1, servers=servers, budget_usd=BUDGET.get(model, 2.0))
        r = llm.extract_json(text)
    except (llm.LLMError, ValueError) as e:   # a broken review never blocks the stage: the gate shows it as missing
        P.event(pid, "review_error", d=d, stage=s["id"], error=str(e)[:300])
        return {"verdict": "unknown", "findings": [], "summary": "", "error": str(e)[:300], "cost_usd": 0}
    findings = [{"severity": f.get("severity") if f.get("severity") in SEVERITIES else "suggestion",
                 **{k: str(f.get(k, ""))[:600] for k in ("item", "problem", "fix")}}
                for f in (r.get("findings") or []) if isinstance(f, dict)]
    verdict = "fix" if any(f["severity"] == "critical" for f in findings) else "pass"
    P.event(pid, "review", d=d, stage=s["id"], model=model, verdict=verdict, findings=len(findings))
    return {"verdict": verdict, "findings": findings, "summary": str(r.get("summary", ""))[:800], "model": model,
            "cost_usd": meta.get("cost_usd") or 0}


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
