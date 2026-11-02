"""The tool registry: every capability a production line can use, behind one contract.

A tool declares what it is (name, capability, provider, where it runs), what it is good and bad for, the JSON schema
of its arguments, whether it spends ElevenLabs credits, and how to tell if it can run on this machine right now.
Stages ask for tools by name in their manifest; the stage agent sees only those (through factory/hat/mcp_server.py),
and the Studio's catalogue lists them all with their availability.

Every call gets a Ctx: the project and stage it runs for. Calls are logged to the project's events.jsonl with their
time, so the board can show what the agent is doing.
"""
import functools, json, os, shutil, time

import jsonschema
import yaml

from ..config import FFMPEG, NODE, ROOT
from . import manifest, project as P

TOOLS = {}
CAPABILITIES = ("project", "research", "planning", "design", "voice", "music", "sound", "image", "video", "edit",
                "compose", "qa", "publish")
# CLI built-ins a manifest may list: the stage agent gets them as the CLI's own tools, not through our MCP server
BUILTIN = {"web_search": "WebSearch", "web_fetch": "WebFetch"}


class ToolError(RuntimeError):
    pass


class Ctx:
    def __init__(self, pid, stage=None, d=None, user=None):
        self.pid, self.stage, self.d, self.user = pid, stage, d, user

    def path(self, *parts):
        return P.path(self.pid, *parts, d=self.d)


def tool(name, capability, summary, provider="local", runtime="local", schema=None, best_for=(), not_for=(),
         spends=None, needs=(), agent=True):
    """Register fn(ctx, **args) as a tool. `needs`: executables or checks that must pass for it to be available."""
    assert capability in CAPABILITIES, capability

    def wrap(fn):
        TOOLS[name] = {"name": name, "capability": capability, "summary": summary, "provider": provider,
                       "runtime": runtime, "schema": schema or {"type": "object", "properties": {}},
                       "best_for": list(best_for), "not_for": list(not_for), "spends": spends, "needs": list(needs),
                       "agent": agent, "fn": fn}
        return fn
    return wrap


def _has(need):
    if need == "ffmpeg":
        return bool(FFMPEG and (os.path.exists(FFMPEG) or shutil.which(FFMPEG)))
    if need == "node":
        return bool(shutil.which(NODE) or os.path.exists(NODE))
    if need == "chromium":
        return os.path.isdir(os.path.join(ROOT, "motion", "node_modules", "playwright"))
    if need == "network":
        return True
    return bool(shutil.which(need))


def available(name):
    """(ok, reason) for one tool on this machine."""
    t = TOOLS[name]
    missing = [n for n in t["needs"] if not _has(n)]
    return (not missing, f"missing: {', '.join(missing)}" if missing else "")


def describe(names=None, agent_only=False):
    """The public contract (no function), for the MCP tools/list and the Studio catalogue."""
    out = []
    for n, t in TOOLS.items():
        if names is not None and n not in names:
            continue
        if agent_only and not t["agent"]:
            continue
        ok, why = available(n)
        out.append({k: v for k, v in t.items() if k != "fn"} | {"available": ok, "why": why})
    return out


def call(name, ctx, args=None):
    if name not in TOOLS:
        raise ToolError(f"unknown tool '{name}'")
    t = TOOLS[name]
    ok, why = available(name)
    if not ok:
        raise ToolError(f"{name} is not available on this machine ({why})")
    args = args or {}
    try:
        jsonschema.validate(args, t["schema"])
    except jsonschema.ValidationError as e:
        raise ToolError(f"{name}: bad arguments: {e.message}") from None
    t0 = time.time()
    try:
        out = t["fn"](ctx, **args)
    except ToolError:
        raise
    except Exception as e:
        P.event(ctx.pid, "tool_error", d=ctx.d, tool=name, stage=ctx.stage, error=f"{type(e).__name__}: {e}"[:300])
        raise ToolError(f"{name} failed: {type(e).__name__}: {e}") from None
    P.event(ctx.pid, "tool", d=ctx.d, tool=name, stage=ctx.stage, seconds=round(time.time() - t0, 2))
    return out


# ---------------------------------------------------------------- artifact schemas

@functools.lru_cache(maxsize=1)
def schemas():
    with open(os.path.join(manifest.DIR, "_artifacts.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def validate_artifact(name, data):
    """[] when `data` fits the artifact's schema, else readable problems."""
    sch = schemas().get(name)
    if sch is None:
        return []
    v = jsonschema.Draft7Validator(sch)
    return [f"{'/'.join(str(x) for x in e.path) or '(top)'}: {e.message}" for e in sorted(v.iter_errors(data), key=str)][:20]


# ---------------------------------------------------------------- project tools (every stage)

@tool("project_info", "project", "The project's brief, line, video language, aspect, channel and budget, plus this "
      "stage's name and the creator's feedback note if the stage is being redone.")
def project_info(ctx):
    p = P.load(ctx.pid, ctx.d)
    cp = P.checkpoint(ctx.pid, ctx.stage, ctx.d) if ctx.stage else {}
    return {k: p.get(k) for k in ("id", "line", "title", "brief", "video_lang", "aspect", "channel", "budget")} | \
        {"stage": ctx.stage, "feedback": cp.get("note"), "revision": cp.get("revisions", 0),
         "today": time.strftime("%Y-%m-%d")}


@tool("read_artifact", "project", "Read an earlier stage's output (research, proposal, script, scene_plan, assets, ...).",
      schema={"type": "object", "required": ["name"], "properties": {"name": {"type": "string"}}})
def read_artifact(ctx, name):
    data = P.read_artifact(ctx.pid, name, ctx.d)
    if data is None:
        raise ToolError(f"no artifact '{name}' yet")
    return data


@tool("submit_artifact", "project", "Hand in this stage's output. It is checked against the stage's schema; fix the "
      "listed problems and submit again until it is accepted. The last accepted submission is the stage's result.",
      schema={"type": "object", "required": ["data"], "properties": {"data": {"type": "object"}}})
def submit_artifact(ctx, data):
    if not ctx.stage:
        raise ToolError("submit_artifact needs a stage")
    p = P.load(ctx.pid, ctx.d)
    name = manifest.stage(manifest.get(p["line"]), ctx.stage)["artifact"]
    problems = validate_artifact(name, data)
    if problems:
        return {"accepted": False, "problems": problems}
    P.write_artifact(ctx.pid, name, data, ctx.d)
    return {"accepted": True, "artifact": name}


# ---------------------------------------------------------------- planning

@tool("catalog", "planning", "The studio's technique catalogue (story shapes, film styles, looks, sound, captions, edit) "
      "for a kind of video, so a proposal only uses what the factory can render.",
      schema={"type": "object", "properties": {"kind": {"type": "string", "enum": ["topic", "footage", "talk", "series"]}}})
def catalog(ctx, kind="topic"):
    from .. import capabilities
    return capabilities.catalogue(kind)


@tool("memory", "planning", "What the studio made lately, how it performed, what is overused and what is unexplored, "
      "so a new proposal does not repeat itself.")
def memory(ctx):
    from .. import memory as M
    from ..store import connect
    return M.brief(connect())


@tool("estimate_cost", "planning", "ElevenLabs credits for planned generations, from rates learned on real runs. "
      "items: [{kind: tts|music|sfx|image|video, model, units, unit: char|s|img, label}].",
      schema={"type": "object", "required": ["items"], "properties": {"items": {"type": "array", "items": {
          "type": "object", "required": ["kind", "model", "units", "unit"],
          "properties": {"kind": {"type": "string"}, "model": {"type": "string"}, "units": {"type": "number"},
                         "unit": {"type": "string"}, "label": {"type": "string"}}}}}})
def estimate_cost(ctx, items):
    from .. import credits
    return credits.estimate(items)


@tool("render_time", "planning", "Wall time of a preview and a final render on this machine for a video of `seconds`.",
      schema={"type": "object", "properties": {"seconds": {"type": "number", "minimum": 1}}})
def render_time(ctx, seconds=30):
    from .. import renderspeed
    return renderspeed.estimate(seconds)


# ---------------------------------------------------------------- research / design

@tool("stock_search", "image", "Find one open-licence photo on Wikimedia Commons (public domain, CC0, CC BY, CC BY-SA). "
      "Returns its file (use it in HTML as /<file>), title, author and licence for the credit line.",
      provider="wikimedia", runtime="cloud", needs=("network",),
      schema={"type": "object", "required": ["query"], "properties": {"query": {"type": "string", "minLength": 2}}})
def stock_search(ctx, query):
    from .. import stock
    hit = stock.find(query)
    if not hit:
        return {"found": False}
    return {"found": True, **hit}


def _draft_plan(ctx, plan):
    from . import explainer
    return explainer.bundle(ctx.pid, plan, ctx.d)


_PLAN = {"type": "object", "description": "a scene_plan draft; omit to use the last submitted one"}


@tool("render_stills", "design", "Render the scene plan to PNG stills at the given seconds (default: one settled frame "
      "per scene) with the current timing, and report the page's JavaScript errors. Read the PNGs to look at them.",
      needs=("node", "chromium"),
      schema={"type": "object", "properties": {"times": {"type": "array", "items": {"type": "number", "minimum": 0}},
                                               "plan": _PLAN}})
def render_stills(ctx, times=None, plan=None):
    from . import explainer
    b = _draft_plan(ctx, plan)
    times = times or explainer.scene_times(ctx.pid, plan, ctx.d)
    out = ctx.path("stills", f"{ctx.stage or 'x'}-{int(time.time())}")
    paths, errs = explainer._htmlmotion().shots(b, times, out)
    return {"stills": paths, "js_errors": errs, "times": times}


@tool("layout_lint", "qa", "Check the scene plan's layout at the given seconds: safe zone, caption band overlap, text "
      "overlap, contrast, tiny text, plus the readcheck (every text visible long enough) and motion lint.",
      needs=("node", "chromium"),
      schema={"type": "object", "properties": {"times": {"type": "array", "items": {"type": "number", "minimum": 0}},
                                               "plan": _PLAN}})
def layout_lint(ctx, times=None, plan=None):
    from .. import layoutlint
    from . import explainer
    b = _draft_plan(ctx, plan)
    times = times or explainer.scene_times(ctx.pid, plan, ctx.d)
    p = P.load(ctx.pid, ctx.d)
    paths, errs, found = layoutlint.run(b, times, ctx.path("stills", "lint"), p.get("aspect", "9:16"))
    return {"findings": found, "text": layoutlint.as_text(found), "js_errors": errs, "stills": paths}


@tool("contact_sheet", "qa", "Tile several stills into one labelled picture, to see the whole piece at a glance.",
      schema={"type": "object", "required": ["stills"], "properties": {
          "stills": {"type": "array", "minItems": 1, "items": {"type": "string"}},
          "labels": {"type": "array", "items": {"type": "string"}}, "title": {"type": "string"}}})
def contact_sheet(ctx, stills, labels=None, title=""):
    from .. import sheets
    for s in stills:
        if not os.path.realpath(s).startswith(os.path.realpath(ctx.path())):
            raise ToolError("stills must be inside the project folder")
    out = ctx.path("stills", f"sheet-{int(time.time())}.jpg")
    sheets.tile(stills, out, labels=labels, title=title)
    return {"sheet": out}


def agent_tools(stage_tools):
    """Split a stage's manifest tool list into (our MCP tools, CLI built-ins). Project tools are always included."""
    ours = ["project_info", "read_artifact", "submit_artifact"]
    builtins = []
    for n in stage_tools:
        if n in BUILTIN:
            builtins.append(BUILTIN[n])
        elif n in TOOLS and TOOLS[n]["agent"] and n not in ours:
            ours.append(n)
    return ours, builtins
