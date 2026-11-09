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
    def __init__(self, pid, stage=None, d=None, user=None, part=None):
        self.pid, self.stage, self.d, self.user, self.part = pid, stage, d, user, part

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
    st = manifest.stage(manifest.get(p["line"]), ctx.stage)
    name, schema = st["artifact"], st["schema"]
    if ctx.part is not None:                 # a long explainer's designer hands in its own part of the scene plan
        from . import longform
        name, schema = longform.part_art(ctx.part), "scene_part"
    problems = validate_artifact(schema, data) or _meaning(ctx, schema, data)
    if problems:
        P.event(ctx.pid, "submit_rejected", d=ctx.d, stage=ctx.stage, artifact=name, problems=problems[:6])
        return {"accepted": False, "problems": problems}
    P.write_artifact(ctx.pid, name, data, ctx.d)
    return {"accepted": True, "artifact": name}


def _meaning(ctx, schema, data):
    """Checks a schema cannot say: a long script's chapters, an outline against its script, a part against its outline,
    a scene plan against the camera vocabulary, the picture's subject, determinism, originality and the direction
    board, and a script against the cold test."""
    from . import longform
    from .. import camera, coldtest, determinism, hookrule, motiongrammar, originality, subjectqc
    p = P.load(ctx.pid, ctx.d)
    script = P.read_artifact(ctx.pid, "script", ctx.d) or {}
    lines = script.get("lines") or []
    if schema in ("scene_plan", "scene_part"):
        # Long-form chapter cards are editorial chrome generated by the factory, not designed story scenes.
        # Keep them in determinism checks, but don't require a narrative subject, mechanism or camera brief.
        scenes = [sc for sc in data.get("scenes") or [] if not sc.get("card")]
        from .. import shotplan
        structural = shotplan.problems(data.get("scenes") or [], lines)
        if structural:
            return structural
        story = data | {"scenes": scenes}
        found = motiongrammar.problems(scenes) if p["line"] in motiongrammar.LINES else []
        if not found and p["line"] in camera.LINES:
            found = (camera.problems(scenes)
                     or subjectqc.problems(scenes, lines, p.get("video_lang") or "tr")
                     or determinism.problems(data)
                     or originality.problems(story, lines, _refs(ctx))
                     or direction_problems(ctx, story))
        if found:
            return found
    if schema in ("script", "long_script") and hookrule.authored(p["line"], ctx.stage):
        lang = p.get("video_lang") or "tr"
        found = hookrule.problems(data, lang) + coldtest.problems(data, lang)
        evidence = P.read_artifact(ctx.pid, "cold_read", ctx.d) or {}
        if evidence.get("fingerprint") != coldtest.fingerprint(data):
            found.append("run `cold_test` on this exact title and these lines before submitting")
        elif (evidence.get("result") or {}).get("ok") is not True:
            found.extend((evidence.get("result") or {}).get("problems") or
                         ["the cold reader did not understand the film's subject; revise the script and run `cold_test` again"])
        if schema == "long_script":
            found += longform.script_problems(data)
        if found:
            return found
    if schema == "proposal":
        return proposal_problems(data)
    if schema == "outline":
        found = longform.outline_problems(script, data)
        if not found and p["line"] in camera.LINES:
            found = camera.problems(data.get("scenes")) or subjectqc.problems(
                data.get("scenes"), lines, p.get("video_lang") or "tr")
        return found or direction_problems(ctx, data)
    if schema == "scene_part":
        part = next((x for x in longform.parts(script) if x["k"] == ctx.part), None)
        outline = P.read_artifact(ctx.pid, "outline", ctx.d) or {}
        return longform.part_problems([s for s in outline.get("scenes") or [] if part and longform._in(s, part)], data)
    return []


def _refs(ctx):
    """Declared reference signatures and recent completed films, for a measured visual-overlap check."""
    from .. import originality
    r = P.read_artifact(ctx.pid, "research", ctx.d) or {}
    refs = [x for x in (r.get("visual_signatures") or r.get("visual_refs") or [])
            if isinstance(x, dict) and any(k in x for k in ("palette", "cameras", "mechanisms", "seconds"))]
    past = []
    for old in P.list_ids(ctx.d):
        if old == ctx.pid:
            continue
        try:
            if P.checkpoint(old, "publish", ctx.d).get("status") not in ("approved", "done"):
                continue
            title = P.load(old, ctx.d).get("title") or old
            render = P.read_artifact(old, "render", ctx.d) or {}
            sig = render.get("originality_signature")
            if not sig:
                plan = P.read_artifact(old, "scene_plan", ctx.d) or {}
                old_script = P.read_artifact(old, "script", ctx.d) or {}
                if not plan.get("scenes"):
                    continue
                sig = originality.signature(plan, old_script.get("lines") or [])
            if sig:
                past.append({**sig, "kind": "past_film", "title": title})
            if len(past) >= 20:
                break
        except Exception:
            continue
    return refs + past


def proposal_problems(data):
    """An agent-built proposal: three distinct treatments and a chosen one (a code step builds `proposal_code`)."""
    concepts = [c for c in (data or {}).get("concepts") or [] if isinstance(c, dict)]
    shapes = {str(c.get("structure") or c.get("title") or c.get("id") or "").strip().lower() for c in concepts}
    out = []
    if len(shapes) < 3:
        out.append("a proposal needs three distinct treatments: three different structures, not one film under three titles")
    chosen = str((data or {}).get("chosen") or "")
    if chosen and not any(str(c.get("id")) == chosen for c in concepts):
        out.append(f"`chosen` names '{chosen}', which is not one of the concept ids")
    return out


def direction_problems(ctx, plan):
    """The scene plan must be drawn in the approved board's palette and type pairing."""
    from . import direction
    board = P.read_artifact(ctx.pid, "direction", ctx.d)
    return direction.problems(plan, board) if board else []


# ---------------------------------------------------------------- planning

@tool("catalog", "planning", "The studio's technique catalogue (story shapes, film styles, looks, sound, captions, edit) "
      "for a kind of video, so a proposal only uses what the factory can render.",
      schema={"type": "object", "properties": {"kind": {"type": "string", "enum": ["topic", "footage", "talk", "series"]}}})
def catalog(ctx, kind="topic"):
    from .. import capabilities
    return capabilities.catalogue(kind)


@tool("recipes", "planning", "The motion recipe cards (text, annotation, data, camera, transition, set piece, "
      "character, living world, rhythm). No ids: one line per card. With ids: the full cards (the FX call, timing, "
      "pitfalls and a working example), to name in a scene's `recipes` or to copy into a scene's js.",
      schema={"type": "object", "properties": {
          "ids": {"type": "array", "items": {"type": "string"}},
          "family": {"type": "string", "enum": ["text", "annotate", "data", "camera", "transition", "setpiece",
                                                 "character", "living", "rhythm"]}}})
def recipes(ctx, ids=None, family=None):
    from .. import recipes as R
    if ids:
        return {"cards": R.card_text(ids), "unknown": R.unknown(ids)}
    return {"index": R.index("en", family)}


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


def _part_plan(ctx, draft):
    """A long explainer's designer: the whole plan with its part as drafted (or as last submitted) -> (bundle,
    its scenes' times, its span, its scene ids)."""
    from . import explainer, longform
    draft = draft or P.read_artifact(ctx.pid, longform.part_art(ctx.part), ctx.d)
    pl, times, span, ids = longform.part_times(ctx.pid, ctx.part, ctx.d, draft)
    return explainer.bundle(ctx.pid, pl, ctx.d), times, span, ids


_PLAN = {"type": "object", "description": "a scene_plan draft; omit to use the last submitted one"}


@tool("render_stills", "design", "Render the scene plan to PNG stills at the given seconds (default: one settled frame "
      "per scene) with the current timing, and report the page's JavaScript errors. Read the PNGs to look at them.",
      needs=("node", "chromium"),
      schema={"type": "object", "properties": {"times": {"type": "array", "items": {"type": "number", "minimum": 0}},
                                               "plan": _PLAN}})
def render_stills(ctx, times=None, plan=None):
    from . import explainer
    if ctx.part is not None:
        b, mine, _, _ = _part_plan(ctx, plan)
        times = times or mine
    else:
        b = _draft_plan(ctx, plan)
        times = times or explainer.scene_times(ctx.pid, plan, ctx.d)
    out = ctx.path("stills", f"{ctx.stage or 'x'}{'' if ctx.part is None else '-p' + str(ctx.part)}-{int(time.time())}")
    paths, errs = explainer._htmlmotion().shots(b, times, out)
    return {"stills": paths, "js_errors": errs, "times": times}


@tool("layout_lint", "qa", "Check layout, typography, readability and motion, then render up to three of the same "
      "frames in a fresh browser process to prove they are pixel-identical.",
      needs=("node", "chromium"),
      schema={"type": "object", "properties": {"times": {"type": "array", "items": {"type": "number", "minimum": 0}},
                                               "plan": _PLAN}})
def layout_lint(ctx, times=None, plan=None):
    from .. import layoutlint
    from .. import determinism
    from . import explainer
    p = P.load(ctx.pid, ctx.d)
    if ctx.part is not None:                 # only this designer's part: its stills, its span of the timing pass
        b, mine, span, ids = _part_plan(ctx, plan)
        sample_times = times or mine
        paths, errs, found = layoutlint.run(b, sample_times, ctx.path("stills", f"lint-p{ctx.part}"), "16:9", span=span)
        found += _render_determinism(ctx, b, sample_times, paths, explainer, determinism)
        found += _subject_motion(ctx, P.read_artifact(ctx.pid, "scene_plan", ctx.d) or plan or {}, b,
                                 explainer, scene_ids=ids)
        found = [f for f in found if f.get("scene") in ids or
                 (f["kind"] in ("easing", "non_deterministic") and f.get("scene") is None)]
        return {"findings": found, "text": layoutlint.as_text(found), "js_errors": errs, "stills": paths}
    b = _draft_plan(ctx, plan)
    times = times or explainer.scene_times(ctx.pid, plan, ctx.d)
    rep = {}
    paths, errs, found = layoutlint.run(b, times, ctx.path("stills", "lint"), p.get("aspect", "9:16"), report=rep)
    deterministic = _render_determinism(ctx, b, times, paths, explainer, determinism)
    found += deterministic
    subject_motion = _subject_motion(ctx, plan or P.read_artifact(ctx.pid, "scene_plan", ctx.d) or {}, b, explainer)
    found += subject_motion
    if deterministic:
        rep = layoutlint.grade(found, scenes=len(b.get("scenes") or []))
    text = layoutlint.as_text(found)
    if rep:
        P.event(ctx.pid, "lint_grade", d=ctx.d, stage=ctx.stage, grade=rep["grade"], score=rep["score"])
        text = [f"grade {rep['grade']} {rep['score']}/100 {rep['parts']}"] + text
    return {"findings": found, "text": text, "js_errors": errs, "stills": paths, "grade": rep or None}


def _render_determinism(ctx, bundle, times, paths, explainer, determinism):
    """Render up to three of the same moments in a fresh Chromium process and compare their PNG bytes."""
    probe = sorted(set(round(float(t), 2) for t in (times or [])[:1] + (times or [])[len(times or []) // 2:len(times or []) // 2 + 1]
                       + (times or [])[-1:]))
    if not probe or not paths:
        return []
    out = ctx.path("stills", f"determinism-{time.time_ns()}")
    try:
        second, errors = explainer._htmlmotion().shots(bundle, probe, out)
        by_time = lambda ps: {os.path.basename(x)[5:-4]: x for x in ps if os.path.basename(x).startswith("shot_")}
        first_map = by_time(paths)
        first = [first_map.get(f"{t:06.2f}") for t in probe]
        result = determinism.compare_frames(first, second)
        if result["identical"]:
            return []
        return [{"t": probe[0], "scene": None, "kind": "non_deterministic", "text": "",
                 "detail": "the same scene still changed between fresh renders: " + result["reason"]
                           + (f" ({', '.join(result['different'][:3])})" if result.get("different") else "")
                           + (f"; renderer: {errors[0]}" if errors else "")}]
    except Exception as e:
        return [{"t": probe[0], "scene": None, "kind": "non_deterministic", "text": "",
                 "detail": f"the repeat-render check could not complete: {type(e).__name__}: {e}"[:240]}]


def _subject_motion(ctx, plan, bundle, explainer, scene_ids=None):
    """Compare two settled frames in each moving-camera scene after removing one global camera transform."""
    from .. import camera, subjectqc
    sp = explainer.spec(ctx.pid, plan, ctx.d)
    spans = {s["id"]: s for s in sp.get("scenes") or []}
    chosen, times = [], []
    wanted = set(str(x) for x in scene_ids) if scene_ids is not None else None
    for sc in (plan or {}).get("scenes") or []:
        if sc.get("card") or (wanted is not None and str(sc.get("id")) not in wanted):
            continue
        span = spans.get(sc.get("id"))
        if not span or float(span["end"]) - float(span["start"]) < 0.8:
            continue
        cam = camera.parse(sc.get("camera"))
        if not cam.get("move") or cam["move"] == "hold":
            continue
        start, end = float(span["start"]), float(span["end"])
        a, b = round(start + (end - start) * 0.25, 2), round(start + (end - start) * 0.75, 2)
        if b - a < 0.25:
            continue
        chosen.append(sc)
        times.extend((a, b))
    if not times:
        return []
    out = ctx.path("stills", f"subject-motion-{time.time_ns()}")
    try:
        paths, _ = explainer._htmlmotion().shots(bundle, times, out)
    except Exception:
        return []
    by_t = {}
    for path in paths or []:
        name = os.path.basename(path)
        if name.startswith("shot_") and name.endswith(".png"):
            try:
                by_t[round(float(name[5:-4]), 2)] = path
            except ValueError:
                continue
    findings = []
    for i, sc in enumerate(chosen):
        first = by_t.get(times[2 * i])
        second = by_t.get(times[2 * i + 1])
        if not first or not second:
            continue
        measured = subjectqc.motion_pair(first, second)
        detail = subjectqc.motion_problem(sc, measured)
        if detail:
            findings.append({"t": times[2 * i], "scene": sc.get("id"), "kind": "camera_only", "text": "",
                             "detail": detail})
    return findings


@tool("chapter_marks", "publish", "The video's chapter marks from its real timing, as YouTube wants them in the "
      "description (\"0:00 Intro\" first, one line per chapter).")
def chapter_marks(ctx):
    from . import longform
    return {"marks": longform.marks(ctx.pid, ctx.d), "text": longform.marks_text(ctx.pid, ctx.d)}


@tool("proof_check", "qa", "Proof mode: find every number in this stage's output (or in a draft `data`) and say which "
      "match a sourced figure, and for scenes whether the script says it and the scene names and shows its source.",
      schema={"type": "object", "properties": {"data": {"type": "object"}}})
def proof_check(ctx, data=None):
    from .. import proof
    r = proof.check(ctx.pid, ctx.stage, ctx.d, data=data)
    if r is None:
        return {"proof_mode": False, "note": "proof mode is off for this project; nothing to check"}
    return r | {"problems": proof.problems(r, "en")}


@tool("words_check", "qa", "Check narration lines for dashes, generated-sounding stock phrasing and a greeting opener. "
      "Findings only; you decide the rewrite. Pass `lines` or leave empty to check the project's script.",
      schema={"type": "object", "properties": {"lines": {"type": "array", "items": {"type": "string"}}}})
def words_check_tool(ctx, lines=None):
    from .. import craftcheck
    p = P.load(ctx.pid, ctx.d)
    if lines is None:
        lines = [l if isinstance(l, str) else l.get("text", "") for l in (P.read_artifact(ctx.pid, "script", ctx.d) or {}).get("lines") or []]
    return {"findings": craftcheck.words_check(lines, p.get("video_lang", "en"))}


@tool("rhythm_check", "qa", "Check the scene plan's pacing before any render: scene lengths (estimated from the words "
      "each scene covers) that are too even or run five or more alike. Findings only.",
      schema={"type": "object", "properties": {"plan": {"type": "object"}}})
def rhythm_check(ctx, plan=None):
    from .. import craftcheck
    plan = plan or P.read_artifact(ctx.pid, "scene_plan", ctx.d) or {}
    lines = (P.read_artifact(ctx.pid, "script", ctx.d) or {}).get("lines") or []
    words = [len((l if isinstance(l, str) else l.get("text", "")).split()) for l in lines]
    sizes = [sum(words[a:b + 1]) for a, b in (sc["lines"] for sc in plan.get("scenes") or [])]
    return {"scene_words": sizes, "findings": craftcheck.rhythm(sizes)}


@tool("beat_frames", "qa", "Tempos whose beat is a whole number of frames at the video's fps, so every cue on the beat "
      "grid lands exactly on a frame (pick one of these for music-led pieces).",
      schema={"type": "object", "properties": {"fps": {"type": "integer"}}})
def beat_frames_tool(ctx, fps=30):
    from .. import craftcheck
    return {"fps": fps, "tempos": craftcheck.frame_bpms(fps)}


@tool("cold_test", "qa", "The cold test: a model that has not seen the film reads only the script lines and says in one "
      "sentence what it is about. Run it before submitting; it costs one small call and catches a film about nothing.",
      needs=("network",), schema={"type": "object", "properties": {"data": {"type": "object"}}})
def cold_test(ctx, data=None):
    from .. import coldtest
    p = P.load(ctx.pid, ctx.d)
    script = data or P.read_artifact(ctx.pid, "script", ctx.d) or {}
    r = coldtest.cold_read(script, p.get("video_lang") or "tr")
    evidence = {"fingerprint": coldtest.fingerprint(script), "result": r,
                "findings": coldtest.findings(script, p.get("video_lang") or "tr")}
    P.write_artifact(ctx.pid, "cold_read", evidence, ctx.d)
    return r | {"findings": evidence["findings"]}


@tool("subject_check", "design", "Look at the stills of the scene plan and say, per scene, whether the frame shows the "
      "subject doing what the line says. Needs render_stills first; one vision call per scene.",
      needs=("network",), schema={"type": "object", "properties": {"plan": {"type": "object"},
                                                                  "stills": {"type": "object"}}})
def subject_check(ctx, plan=None, stills=None):
    from .. import subjectqc
    if plan is None and ctx.part is not None:
        from . import longform
        plan = P.read_artifact(ctx.pid, longform.part_art(ctx.part), ctx.d) or {}
    plan = plan or P.read_artifact(ctx.pid, "scene_plan", ctx.d) or {}
    lines = (P.read_artifact(ctx.pid, "script", ctx.d) or {}).get("lines") or []
    if isinstance(stills, dict) and isinstance(stills.get("stills"), list):
        stills = stills["stills"]
    if isinstance(stills, list):
        stills = {str(sc.get("id")): path for sc, path in zip(plan.get("scenes") or [], stills)}
    if not isinstance(stills, dict):
        stills = _stills_map(ctx, plan)
    checks = []
    for sc in plan.get("scenes") or []:
        if sc.get("card"):
            continue
        f = stills.get(str(sc.get("id")))
        a, b = (sc.get("lines") or [0, 0])[:2]
        line = " ".join(str(lines[i]) for i in range(a, min(b, len(lines) - 1) + 1) if 0 <= i < len(lines))
        if f and os.path.exists(f):
            checks.append(subjectqc.vision(f, line, sc.get("shows"), sc.get("id")) | {"scene": sc.get("id")})
    story = [sc for sc in plan.get("scenes") or [] if not sc.get("card")]
    return {"checks": checks, "problems": [x for c in checks for x in c.get("problems") or []],
            "unchecked": [sc.get("id") for sc in story if str(sc.get("id")) not in stills]}


def _stills_map(ctx, plan):
    """The latest render_stills folder paired with the plan's scenes, in the order the stills were rendered."""
    root = ctx.path("stills")
    if not os.path.isdir(root):
        return {}
    prefix = f"{ctx.stage or 'x'}{'' if ctx.part is None else '-p' + str(ctx.part)}-"
    dirs = sorted((os.path.join(root, n) for n in os.listdir(root)
                   if n.startswith(prefix) and os.path.isdir(os.path.join(root, n))),
                  key=lambda p: os.path.getmtime(p), reverse=True)
    for d in dirs:
        shots = sorted(os.path.join(d, f) for f in os.listdir(d) if f.startswith("shot_") and f.endswith(".png"))
        if shots:
            scenes = (plan or {}).get("scenes") or []
            if ctx.part is not None:
                scenes = [sc for sc in scenes if not sc.get("card")]
            return {str(sc.get("id")): shots[i] for i, sc in enumerate(scenes)
                    if i < len(shots)}
    return {}


@tool("originality_check", "design", "Score the scene plan for originality: stock metaphors, one mechanism or one "
      "camera move for the whole film, duplicate pictures, and (when the research declares one) a copied reference "
      "signature. Returns the 0-100 score, the verdict and the findings.",
      schema={"type": "object", "properties": {"plan": {"type": "object"},
                                              "references": {"type": "array", "items": {"type": "object"}}}})
def originality_check(ctx, plan=None, references=None):
    from .. import originality
    plan = plan or P.read_artifact(ctx.pid, "scene_plan", ctx.d) or {}
    lines = (P.read_artifact(ctx.pid, "script", ctx.d) or {}).get("lines") or []
    refs = references if references is not None else _refs(ctx)
    r = originality.check(plan, lines, refs)
    p = P.load(ctx.pid, ctx.d)
    return r | {"problems": originality.problems(plan, lines, refs),
                "summary": originality.summary(r, p.get("video_lang") or "tr")}


@tool("attribution", "publish", "The licence ledger for this project: every image, voice, music track and font the film "
      "uses, with its author, licence and the credit line it owes. Put the `block` in `publish.credits`.",
      schema={"type": "object", "properties": {}})
def attribution(ctx):
    from .. import licence
    p = P.load(ctx.pid, ctx.d)
    lang = p.get("video_lang") or "tr"
    rows = licence.entries(ctx.pid, ctx.d)
    return {"entries": rows, "block": licence.block(rows, lang), "summary": licence.summary(rows, lang),
            "missing": [r["file"] for r in licence.missing(rows)],
            "needs_credit": [r["file"] for r in licence.required(rows)]}


@tool("retake_flags", "edit", "Retakes, stutters and false starts in the source footage, from its own transcript: the "
      "flags to show the creator before anything is cut. Nothing is cut here; the creator approves which ids go.",
      needs=("ffmpeg",), schema={"type": "object", "properties": {"file": {"type": "string"},
                                                               "threshold": {"type": "number", "minimum": 0.15, "maximum": 0.6}}})
def retake_flags(ctx, file=None, threshold=None):
    from .. import footagecut
    tr = _transcript(ctx, file)
    flags = footagecut.find_flags(tr["words"], tr["duration"])
    if threshold is not None:
        flags = [f for f in flags if (f.get("ratio") or 0) >= float(threshold)]
    return {"flags": flags, "count": len(flags),
            "summary": f"{len(flags)} bayrak: " + ", ".join(f"{f['id']} {f['kind']} ({f['confidence']})"
                                                            for f in flags[:6]) if flags else "bayrak yok"}


@tool("pause_trim", "edit", "How much a take shrinks when its long silences are cut to a natural breath: the kept "
      "intervals, the seconds saved, and an ffmpeg filter for the cut. The creator approves before it is used.",
      needs=("ffmpeg",), schema={"type": "object", "properties": {"file": {"type": "string"},
                                                               "fps": {"type": "integer", "minimum": 1, "maximum": 120}}})
def pause_trim(ctx, file=None, fps=30):
    from .. import footagecut
    tr = _transcript(ctx, file)
    keep = footagecut.keep_intervals(tr["words"], tr["duration"])
    saved = round(float(tr["duration"]) - sum(b - a for a, b in keep), 3)
    return {"intervals": keep, "saved_s": saved, "duration": tr["duration"],
            "filter": footagecut.filter_args(keep, fps),
            "summary": f"{saved:g} s kısalıyor ({tr['duration']:g} s -> {round(tr['duration'] - saved, 2):g} s)"}


def _transcript(ctx, file=None):
    """The project's own transcript (`transcript` artifact, then assets/transcript.json), or one made from `file`."""
    from .. import talk

    def _norm(tr):
        words = [w if isinstance(w, (list, tuple)) else [w.get("word"), w.get("start"), w.get("end")]
                 for w in (tr or {}).get("words") or []]
        return {"words": [tuple(w[:3]) for w in words], "duration": (tr or {}).get("duration")}

    tr = P.read_artifact(ctx.pid, "transcript", ctx.d)
    if tr and tr.get("words"):
        return _norm(tr)
    path = os.path.join(ctx.path(), "assets", "transcript.json")
    if os.path.exists(path):
        return _norm(json.load(open(path)))
    if not file:
        raise ToolError("no transcript yet: run the clip/transcript step, or pass `file`")
    src = _project_file(ctx, file)
    p = P.load(ctx.pid, ctx.d)
    words, dur = talk.transcribe(src, p.get("video_lang", "tr"))
    return {"words": [tuple(w[:3]) for w in words], "duration": dur}


@tool("contact_sheet", "qa", "Tile several stills into one labelled picture, to see the whole piece at a glance.",      schema={"type": "object", "required": ["stills"], "properties": {
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


# ---------------------------------------------------------------- code-stage tools (listed in the catalogue; run by the
# explainer's code stages, not by agents)

@tool("tts", "voice", "Narration from ElevenLabs (cloned or stock voice), cached by text, voice and model. Spends credits "
      "and refuses to run beyond the project's approved budget.", provider="elevenlabs", runtime="cloud",
      spends="credits per character", needs=("network",), agent=False,
      schema={"type": "object", "required": ["text"], "properties": {"text": {"type": "string"}, "voice_id": {"type": "string"}}})
def tts_tool(ctx, text, voice_id=None):
    from .. import eleven, formats
    from . import explainer as E
    p = P.load(ctx.pid, ctx.d)
    path, cost = eleven.tts(E._con(), text, voice_id or formats.default_voice(p.get("video_lang")), formats.VOICE_MODEL,
                            approved=E.remaining_budget(ctx.pid, ctx.d))
    return {"file": E._rel(path), "credits": cost}


@tool("align_words", "voice", "Word-level timings of a voice file against its script lines (faster-whisper, local).",
      needs=("ffmpeg",), agent=False,
      schema={"type": "object", "required": ["file", "lines"], "properties": {"file": {"type": "string"},
                                                                            "lines": {"type": "array", "items": {"type": "string"}}}})
def align_tool(ctx, file, lines):
    from .. import productions
    times, dur, words = productions.align(os.path.join(ROOT, file), lines, P.load(ctx.pid, ctx.d).get("video_lang", "tr"))
    return {"line_times": times, "duration": dur, "words": words}


@tool("music", "music", "An instrumental track from ElevenLabs Music for a given length and mood. Spends credits inside "
      "the approved budget.", provider="elevenlabs", runtime="cloud", spends="credits per second", needs=("network",),
      agent=False, schema={"type": "object", "required": ["prompt", "seconds"],
                           "properties": {"prompt": {"type": "string"}, "seconds": {"type": "number"}}})
def music_tool(ctx, prompt, seconds):
    from .. import eleven, productions
    from . import explainer as E
    path, cost = eleven.generate(E._con(), "music", productions.MUSIC_MODEL, prompt, {"duration_seconds": seconds,
                                 "instrumental": True}, seconds, "s", ext="mp3", approved=E.remaining_budget(ctx.pid, ctx.d))
    return {"file": E._rel(path), "credits": cost}


@tool("preview_render", "compose", "Half-size 15 fps preview of the whole video with its sound.", needs=("node", "chromium",
      "ffmpeg"), agent=False)
def preview_render(ctx):
    from . import explainer as E
    return E._render(ctx.pid, final=False, d=ctx.d)[0]


@tool("final_render", "compose", "Full-size 30 fps final render with mixed sound and the look's film post.",
      needs=("node", "chromium", "ffmpeg"), agent=False)
def final_render(ctx):
    from . import explainer as E
    return E._render(ctx.pid, final=True, d=ctx.d)[0]


@tool("compile_bundle", "edit", "Scene plan + timing -> the renderer's bundle.", agent=False)
def compile_bundle(ctx):
    from . import explainer as E
    return {"bundle": E.bundle(ctx.pid, d=ctx.d)}


@tool("qa_technical", "qa", "Black frames, frozen time, flashes, broken frames, duration and loudness of a video.",
      needs=("ffmpeg",), agent=False, schema={"type": "object", "required": ["file"], "properties": {"file": {"type": "string"}}})
def qa_technical(ctx, file):
    from .. import qa
    return qa.technical(os.path.join(ROOT, file))


@tool("qa_sound", "qa", "Measure a finished mix like a sound supervisor: loudness, peaks, clicks, voice clarity.",
      needs=("ffmpeg",), agent=False, schema={"type": "object", "required": ["file"], "properties": {"file": {"type": "string"}}})
def qa_sound(ctx, file):
    from .. import soundqa
    return soundqa.review(os.path.join(ROOT, file))


@tool("thumbnails", "publish", "Three cover candidates drawn from the best frames of the final video.", agent=False)
def thumbnails(ctx):
    from .. import thumbs
    fin = P.read_artifact(ctx.pid, "render", ctx.d) or {}
    if not fin.get("final"):
        raise ToolError("no final render yet")
    p = P.load(ctx.pid, ctx.d)
    return {"covers": thumbs.make(os.path.join(ROOT, fin["final"]), ctx.path("renders"), p["title"], p.get("aspect", "9:16"))}


# ---------------------------------------------------------------- images, video, avatars (factory/hat/media.py)

@tool("media_models", "planning", "Which image / video / avatar / lip-sync model fits a shot: give the family, what you "
      "have (prompt, images, start_frame, image, audio, video), the tags you need (e.g. talking_head, illustration, "
      "refs, sound, cinematic, cheap), the clip seconds and aspect. Returns the models ranked with reasons.",
      schema={"type": "object", "required": ["family"], "properties": {
          "family": {"type": "string", "enum": ["image", "video", "avatar", "lipsync", "performance"]},
          "have": {"type": "array", "items": {"type": "string"}}, "need": {"type": "array", "items": {"type": "string"}},
          "seconds": {"type": "number"}, "aspect": {"type": "string"}, "cheap": {"type": "boolean"}}})
def media_models_tool(ctx, family, have=(), need=(), seconds=None, aspect=None, cheap=False):
    from . import media
    return {"models": media.pick(family, have, need, seconds, aspect or P.load(ctx.pid, ctx.d).get("aspect"), cheap)}


@tool("image_gen", "image", "One image through the ElevenLabs connector (optionally from reference image nodes on a flow, "
      "for the same character or place). Spends credits inside the approved budget.", provider="elevenlabs",
      runtime="cloud", spends="credits per image", needs=("network",), agent=False,
      schema={"type": "object", "required": ["prompt"], "properties": {"prompt": {"type": "string"},
              "model": {"type": "string"}, "flow_id": {"type": "string"}, "refs": {"type": "array", "items": {"type": "string"}}}})
def image_gen_tool(ctx, prompt, model=None, flow_id=None, refs=()):
    from .. import eleven
    from . import explainer as E
    p = P.load(ctx.pid, ctx.d)
    path, cost, flow, node = eleven.image(E._con(), prompt, E.remaining_budget(ctx.pid, ctx.d), p.get("eleven_account"),
                                          p.get("aspect", "9:16"), flow_id, tuple(refs), model=model)
    return {"file": E._rel(path), "credits": cost, "flow_id": flow, "node_id": node}


@tool("video_gen", "video", "One generated video clip (Seedance 2.5 by default, Veo 3.1 for short cinematic shots) through "
      "the ElevenLabs connector. Spends credits inside the approved budget.", provider="elevenlabs", runtime="cloud",
      spends="credits per second", needs=("network",), agent=False,
      schema={"type": "object", "required": ["prompt", "seconds"], "properties": {"prompt": {"type": "string"},
              "seconds": {"type": "number", "minimum": 4, "maximum": 30}, "model": {"type": "string"},
              "audio": {"type": "boolean"}}})
def video_gen_tool(ctx, prompt, seconds, model=None, audio=False):
    from .. import eleven
    from . import explainer as E, media
    p = P.load(ctx.pid, ctx.d)
    m = media.get(model or "bytedance-seedance-v2.5")
    if not m or m["family"] != "video":
        raise ValueError(f"unknown video model {model}")
    lo, hi = m.get("seconds") or (4, 30)
    secs = max(lo, min(hi, seconds))
    if m.get("steps"):
        secs = min(m["steps"], key=lambda s: abs(s - secs))
    params = {"duration_secs": secs, "aspect_ratio": p.get("aspect", "9:16"), "generate_audio": bool(audio)}
    path, cost = eleven.generate(E._con(), "video", m["id"], prompt, params, secs, "s", ext="mp4",
                                 approved=E.remaining_budget(ctx.pid, ctx.d), account=p.get("eleven_account"))
    return {"file": E._rel(path), "credits": cost, "seconds": secs, "model": m["id"]}


@tool("minimax_draft", "video", "A MiniMax H3 clip (5-15 s, prompt with an optional start frame or up to 4 reference "
      "images from the project folder) as a cheap 480p draft through the ElevenLabs connector. The final is made only "
      "after the creator approves the draft (minimax_final).", provider="elevenlabs", runtime="cloud",
      spends="credits per second (480p)", needs=("network",), agent=False,
      best_for=["illustrations and characters that move", "a shot from a still", "trying an idea cheaply"],
      schema={"type": "object", "required": ["prompt", "seconds"], "properties": {
          "prompt": {"type": "string"}, "seconds": {"type": "number", "minimum": 5, "maximum": 15},
          "quality": {"type": "string", "enum": ["768p", "2K", "4K"]}, "start": {"type": "string"},
          "refs": {"type": "array", "items": {"type": "string"}, "maxItems": 4}}})
def minimax_draft_tool(ctx, prompt, seconds, quality="768p", start=None, refs=()):
    from . import minimax
    c = minimax.new(ctx.pid, prompt, seconds, quality, start, tuple(refs or ()), ctx.d, ctx.user)
    c = minimax.draft(ctx.pid, c["id"], ctx.d)
    return {"clip": c["id"], "file": c["draft"]["file"], "credits": c["draft"]["credits"], "status": c["status"]}


@tool("minimax_final", "video", "The final of a MiniMax clip whose draft the creator approved, at the clip's quality "
      "(768p, 2K or 4K). Refused for a draft nobody approved.", provider="elevenlabs", runtime="cloud",
      spends="credits per second", needs=("network",), agent=False,
      schema={"type": "object", "required": ["clip"], "properties": {"clip": {"type": "string"}}})
def minimax_final_tool(ctx, clip):
    from . import minimax
    c = minimax.final(ctx.pid, clip, ctx.d)
    return {"clip": c["id"], "file": c["final"]["file"], "credits": c["final"]["credits"], "status": c["status"]}


# ---------------------------------------------------------------- the FFmpeg tool family + platform delivery (t506)

def _project_file(ctx, rel):
    """A project-relative path, refused outside the project folder."""
    base = os.path.realpath(ctx.path())
    p = os.path.realpath(os.path.join(base, rel))
    if not p.startswith(base + os.sep):
        raise ToolError(f"{rel}: only files inside the project folder")
    return p


@tool("ffmpeg_ops", "edit", "The FFmpeg operations (cut, join, fit, crop, stabilize, colour, denoise, silence cut, speed "
      "ramp, loop, reverse, freeze, watermark, censor, multicam, sync, loudness ...) with their argument schemas.")
def ffmpeg_ops(ctx):
    from .. import fftools
    return {"ops": [{k: o[k] for k in ("name", "group", "summary", "schema", "inputs")} for o in fftools.describe()]}


@tool("ffmpeg", "edit", "Run one FFmpeg operation on project files: it measures the inputs, processes, then checks the "
      "output (duration, size, frame rate, streams, loudness) and reports every check. Paths are relative to the "
      "project folder; the output goes to work/ff/. Free, local.", needs=("ffmpeg",),
      schema={"type": "object", "required": ["op", "inputs"], "properties": {
          "op": {"type": "string"}, "inputs": {"type": "array", "minItems": 1, "maxItems": 20, "items": {"type": "string"}},
          "args": {"type": "object"}}})
def ffmpeg_tool(ctx, op, inputs, args=None):
    from .. import fftools
    ins = [_project_file(ctx, i) for i in inputs]
    for k in ("file",):         # lut / subtitles name a file argument: keep it inside the project too
        if args and isinstance(args.get(k), str):
            args = dict(args, **{k: _project_file(ctx, args[k])})
    try:
        r = fftools.run(op, ins, args=args or {}, outdir=ctx.path("work", "ff"))
    except fftools.FFError as e:
        raise ToolError(str(e)) from None
    base = ctx.path()
    rel = lambda m: dict(m, path=os.path.relpath(m["path"], base))
    r["inputs"] = [rel(m) for m in r["inputs"]]
    if "output" in r:
        r["output"] = rel(r["output"])
        r["problems"] = fftools.failed(r)
    return r


@tool("safe_area", "qa", "What sits under a platform's own interface (tabs, buttons, caption, player controls) in a "
      "project video: measured scene texts for HTML scenes, otherwise an estimate from picture detail; plus a preview "
      "picture with the zones drawn on.", needs=("ffmpeg",),
      schema={"type": "object", "required": ["file", "platform"], "properties": {
          "file": {"type": "string"}, "platform": {"type": "string", "enum": ["tiktok", "reels", "shorts", "youtube", "x", "linkedin"]}}})
def safe_area_tool(ctx, file, platform):
    from .. import delivery, export
    path = _project_file(ctx, file)
    lint = size = None
    if export.html_engine(ctx.pid, ctx.d):
        lint, size = delivery._lint_boxes(ctx.pid, ctx.d)
    found = delivery.text_findings(lint, platform, size) if lint else delivery.busy_findings(path, platform)
    prev = delivery.preview(path, platform, ctx.path("work", "ff", f"safe-{platform}.png"), lang="en")
    return {"findings": found, "measured": "text" if lint else "estimate", "preview": os.path.relpath(prev, ctx.path()),
            "zones": delivery.PLATFORMS[platform]["zones"]}


@tool("deliver", "publish", "One file per platform (TikTok, Reels, Shorts, YouTube, X, LinkedIn) from the final: fitted, "
      "loudness-normalised, verified, with the safe-area check.", needs=("ffmpeg",), agent=False,
      schema={"type": "object", "required": ["platforms"], "properties": {"platforms": {"type": "array", "items": {"type": "string"}}}})
def deliver_tool(ctx, platforms):
    from .. import delivery
    return delivery.build(ctx.pid, platforms, ctx.d, log=lambda *_: None)
