"""Long explainer (t507): a 2-8 minute, 16:9 explainer for YouTube, told in chapters.

The script names its chapters; each chapter opens on a short title line the narrator reads, and that line becomes a
chapter card drawn here (same design for every chapter: number, title, the list of chapters with this one lit). The
outline stage (an agent, gated) fixes the shared design system (palette, global CSS, a written component kit) and a
brief per scene. The scene plan stage then draws the scenes with several designer agents at once, one per part (the
intro before the first chapter, then each chapter's body), each with the render/lint tools on the whole plan as it
stands; their parts are merged with the chapter cards into the ordinary `scene_plan`, so the explainer's assets, edit
and compose stages, the scene editor and the exporters work unchanged. A thin progress bar in chapter segments runs
along the bottom edge (the shell's `chrome.progress`).

A re-run of the scene plan rebuilds only what needs it: parts whose outline changed, parts never built, and the parts
the creator's note names (a scene id, "chapter 3" / "bölüm 3", "intro" / "giriş"); every other part keeps its scenes
from the current plan, hand edits included.
"""
import concurrent.futures as cf, hashlib, html as H, json, os, re, time

from .. import llm, recipes
from ..config import ROOT
from . import explainer as X, manifest, mcp_server, project as P, tools as T

PARALLEL = 3                   # designer agents at once
CARD = "chapter-"              # scene id prefix of the chapter cards
LABEL = {"tr": "BÖLÜM", "en": "CHAPTER", "de": "KAPITEL"}
INTRO = {"tr": "Giriş", "en": "Intro", "de": "Einleitung"}
TITLE_WORDS = 10               # a chapter title line is short: it is read over the card
BUDGET_USD = 6.0               # per designer run
TIMEOUT = 2400


class LongError(P.GateError):
    pass


# ---------------------------------------------------------------- chapters and parts

def chapters(script):
    """[{n, title, line, end}]: chapter n spans script lines line..end, its title line first."""
    lines = script.get("lines") or []
    seen, chs = set(), []
    for c in sorted(script.get("chapters") or [], key=lambda c: c.get("line", 0)):
        if 0 < int(c.get("line", 0)) < len(lines) and c["line"] not in seen:
            seen.add(c["line"])
            chs.append(c)
    return [{"n": i + 1, "title": c["title"], "line": c["line"],
             "end": (chs[i + 1]["line"] - 1) if i + 1 < len(chs) else len(lines) - 1} for i, c in enumerate(chs)]


def script_problems(script):
    """Readable problems of a long script's chapters ([] = fine)."""
    lines, out = script.get("lines") or [], []
    raw = [c.get("line") for c in script.get("chapters") or []]
    if raw != sorted(set(raw)):
        out.append("chapters: lines must rise strictly (one chapter per title line, in order)")
    for c in script.get("chapters") or []:
        i = c.get("line", 0)
        if not 0 < i < len(lines):
            out.append(f"chapter '{c.get('title')}': line {i} is not a script line after the intro")
        elif len(lines[i].split()) > TITLE_WORDS:
            out.append(f"chapter '{c.get('title')}': its title line {i} has more than {TITLE_WORDS} words; the chapter "
                       f"opens on a short title line the narrator reads over the chapter card")
    for c in chapters(script):
        if c["end"] <= c["line"]:
            out.append(f"chapter {c['n']} '{c['title']}' has only its title line; give it at least one more line")
    return out


def parts(script):
    """What the designers draw, in order: the intro (lines before chapter 1) and each chapter's body (its lines
    after the title line). -> [{k, key, name, lines: [a, b], chapter}]"""
    chs = chapters(script)
    first = chs[0]["line"] if chs else len(script.get("lines") or [])
    out = [{"k": 0, "key": "intro", "name": "intro", "lines": [0, first - 1], "chapter": None}] if first > 0 else []
    for c in chs:
        out.append({"k": c["n"], "key": f"chapter{c['n']}", "name": c["title"], "lines": [c["line"] + 1, c["end"]],
                    "chapter": c["n"]})
    return out


def _in(sc, part):
    a, b = sc["lines"]
    return part["lines"][0] <= a and b <= part["lines"][1]


def outline_problems(script, outline):
    """The outline's scenes must cover every line but the chapter title lines, once, in order, inside one part."""
    out, ps = [], parts(script)
    titles = {c["line"] for c in chapters(script)}
    ids, want = set(), 0
    n = len(script.get("lines") or [])
    for sc in outline.get("scenes") or []:
        a, b = (sc.get("lines") or [0, -1])[:2]
        if sc["id"] in ids or sc["id"].startswith(CARD):
            out.append(f"scene '{sc['id']}': ids must be unique and must not start with '{CARD}' (chapter cards are drawn for you)")
        ids.add(sc["id"])
        while want in titles:
            want += 1
        if a != want:
            out.append(f"scene '{sc['id']}' starts at line {a}; the next uncovered line is {want}")
        if b < a or b >= n:
            out.append(f"scene '{sc['id']}': lines [{a}, {b}] are not a range of script lines")
        if any(a <= t <= b for t in titles):
            out.append(f"scene '{sc['id']}' covers a chapter title line; the chapter card shows it")
        elif not any(_in(sc, p) for p in ps):
            out.append(f"scene '{sc['id']}' crosses from one chapter into the next")
        bad = recipes.unknown(sc.get("recipes"))
        if bad:
            out.append(f"scene '{sc['id']}': unknown recipes {bad} (the recipes tool lists them)")
        want = max(want, b + 1)
    while want in titles:
        want += 1
    if want < n and not out:
        out.append(f"lines {want}..{n - 1} are not covered by any scene")
    return out


def part_problems(outline_scenes, data):
    """A designer's part must keep the outline's scene ids and line ranges exactly."""
    want = [(s["id"], list(s["lines"])) for s in outline_scenes]
    got = [(s.get("id"), list(s.get("lines") or [])) for s in data.get("scenes") or []]
    if got != want:
        return [f"scenes must be exactly these ids and lines, in order: {json.dumps(want)} (got {json.dumps(got)})"]
    return [f"scene '{s['id']}': empty html" for s in data["scenes"] if not str(s.get("html", "")).strip()]


# ---------------------------------------------------------------- chapter cards

def card_scene(ch, chs, lang="en"):
    """The chapter card: big number, label + title, and the chapter list with this one lit. Drawn from the palette
    tokens, inside the 16:9 safe area (x 80-1840, y 60-850), captions off (the narrator reads the title)."""
    n = ch["n"]
    items = "".join(f'<li class="{"on" if c["n"] == n else "done" if c["n"] < n else ""}"><span>{c["n"]:02d}</span>'
                    f'{H.escape(c["title"])}</li>' for c in chs)
    html = (f'<div class="cc-num">{n:02d}</div><div class="cc-label">{LABEL.get(lang, LABEL["en"])} {n}</div>'
            f'<h1 class="cc-title">{H.escape(ch["title"])}</h1><div class="cc-rule"></div><ol class="cc-list">{items}</ol>')
    css = ("background:var(--bg,#0b0d12);"
           ".cc-num{position:absolute;left:120px;top:110px;font:900 300px/1 'Inter Tight',sans-serif;color:var(--accent,#2ee6c5);letter-spacing:-.04em}"
           ".cc-label{position:absolute;left:128px;top:452px;font:700 30px/1 'Inter Tight',sans-serif;letter-spacing:.22em;color:var(--muted,#9aa3b2)}"
           ".cc-title{position:absolute;left:120px;top:506px;width:960px;margin:0;font:800 80px/1.06 'Inter Tight',sans-serif;color:var(--ink,#fff);letter-spacing:-.015em}"
           ".cc-rule{position:absolute;left:1180px;top:150px;width:4px;height:600px;background:var(--accent,#2ee6c5);transform-origin:50% 0}"
           ".cc-list{position:absolute;left:1240px;top:150px;width:580px;margin:0;padding:0;list-style:none}"
           ".cc-list li{display:flex;gap:18px;align-items:baseline;font:600 30px/1.2 'Inter Tight',sans-serif;color:var(--muted,#9aa3b2);margin:0 0 26px}"
           ".cc-list li span{font-weight:800;font-size:24px;min-width:40px}"
           ".cc-list li.on{color:var(--ink,#fff)}.cc-list li.on span{color:var(--accent,#2ee6c5)}")
    js = ("const s = T.start;"
          "tl.from($('.cc-num')[0], {xPercent: -18, opacity: 0, duration: 0.7}, s);"
          "tl.from($('.cc-rule')[0], {scaleY: 0, duration: 0.6, ease: 'power2.inOut'}, s + 0.05);"
          "tl.from($('.cc-label')[0], {y: 18, opacity: 0, duration: 0.45}, s + 0.15);"
          "tl.from($('.cc-title')[0], {y: 36, opacity: 0, duration: 0.65}, s + 0.25);"
          "tl.from($('.cc-list li'), {x: 28, opacity: 0, duration: 0.4, stagger: 0.06}, s + 0.3);"
          "FX.sfx('whoosh', s + 0.05);")
    return {"id": f"{CARD}{n}", "lines": [ch["line"], ch["line"]], "html": html, "css": css, "js": js,
            "hide_captions": True, "card": True}


# ---------------------------------------------------------------- the plan

def _placeholder(sc):
    return {"id": sc["id"], "lines": list(sc["lines"]), "trigger": sc.get("trigger", ""),
            "html": f'<div style="position:absolute;inset:0;display:grid;place-items:center;font:600 40px \'Inter Tight\',sans-serif;'
                    f'color:var(--muted,#888)">{H.escape(sc["id"])} …</div>', "css": "", "js": "", "placeholder": True}


def part_art(k):
    return f"scene_part_{k}"


def sig(outline, part, script):
    """What a part's scenes depend on: the design system, its scenes' briefs and its lines' words."""
    lines = script.get("lines") or []
    mine = [s for s in outline.get("scenes") or [] if _in(s, part)]
    blob = json.dumps([outline.get("palette"), outline.get("global_css"), outline.get("kit"), mine,
                       lines[part["lines"][0]:part["lines"][1] + 1]], sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(blob.encode()).hexdigest()[:12]


def plan(pid, d=None, override=None, keep=None):
    """The whole scene plan as it stands: outline design + chapter cards + each part's scenes, from `override`
    ({k: part data}) first, then `keep` ({k: scenes} from the current plan), then the built part artifacts, else
    placeholders from the outline. Ordered by line."""
    script = P.read_artifact(pid, "script", d) or {}
    outline = P.read_artifact(pid, "outline", d)
    if not outline:
        raise LongError("no outline yet")
    lang = P.load(pid, d).get("video_lang", "en")
    chs, scenes = chapters(script), []
    for c in chs:
        scenes.append(card_scene(c, chs, lang))
    for part in parts(script):
        k, mine = part["k"], [s for s in outline.get("scenes") or [] if _in(s, part)]
        got = (override or {}).get(k)
        got = got["scenes"] if got else (keep or {}).get(k)
        if not got:
            art = P.read_artifact(pid, part_art(k), d) or {}
            got = art.get("scenes") if art.get("sig") == sig(outline, part, script) else None
        scenes += [dict(s) for s in got] if got else [_placeholder(s) for s in mine]
    scenes.sort(key=lambda s: (s["lines"][0], 0 if s["id"].startswith(CARD) else 1))
    return {"concept": outline.get("concept", ""), "palette": outline.get("palette") or {},
            "global_css": outline.get("global_css", ""), "kit": outline.get("kit", ""), "scenes": scenes,
            "chapters": [{"title": c["title"], "line": c["line"]} for c in chs], "chrome": {"progress": True},
            "captions": X.CAPTIONS, "summary": ""}


def part_times(pid, k, d=None, draft=None):
    """Settled moments of part k's scenes, and the span (s) the part covers."""
    script = P.read_artifact(pid, "script", d) or {}
    part = next((p for p in parts(script) if p["k"] == k), None)
    if part is None:
        raise LongError(f"no part {k}")
    pl = plan(pid, d, override={k: draft} if draft else None)
    sp = X.spec(pid, pl, d)
    mine = [s for s in sp["scenes"] if part["lines"][0] <= s["lines"][0] <= part["lines"][1] and not s["id"].startswith(CARD)]
    times = [round(s["start"] + (s["end"] - s["start"]) * 0.7, 2) for s in mine]
    span = (mine[0]["start"], mine[-1]["end"]) if mine else (0.0, 0.0)
    return pl, times, span, {s["id"] for s in mine}


# ---------------------------------------------------------------- the designers (one agent run per part)

def _recipe_cards(scenes):
    ids = [r for x in scenes for r in x.get("recipes") or []]
    return f"\n## Recipe cards the outline names for your scenes (proven FX calls; adapt them to 1920x1080)\n{recipes.card_text(ids)}\n" if ids else ""


def _task(pid, s, part, outline, script, note=None, d=None):
    from .. import proof, sceneedit
    from . import agent
    p = P.load(pid, d)
    lines = script.get("lines") or []
    mine = [x for x in outline.get("scenes") or [] if _in(x, part)]
    rows = "\n".join(f'- "{x["id"]}" lines [{x["lines"][0]}, {x["lines"][1]}]'
                     f'{" · device: " + x["device"] if x.get("device") else ""}'
                     f'{" · recipes: " + ", ".join(x["recipes"]) if x.get("recipes") else ""}\n  brief: {x["brief"]}\n  says: '
                     + " ".join(lines[x["lines"][0]:x["lines"][1] + 1]) for x in mine)
    where = "the intro (before chapter 1)" if part["chapter"] is None else f"chapter {part['chapter']}: {part['name']}"
    ui = p.get("ui_lang", "tr")
    fb = f"\n## The creator's feedback on the scene plan\n{note}\n" if note else ""
    return f"""{agent.contract()}

# This run
Line: Long explainer (long_explainer) · Stage: Scene plan (scene_plan) · You draw ONE part: {where}
Output: submit_artifact with {{scenes, summary}} (artifact `{part_art(part['k'])}`); other designers draw the other
parts at the same time from the same outline, so keep to the shared design system exactly.
Video language: {agent.LANG_NAME.get(p.get('video_lang'), p.get('video_lang'))} · Interface language for `summary`: {agent.LANG_NAME.get(ui, ui)}
Aspect: 16:9 (1920x1080)
{fb}
## Your scenes (keep these ids and line ranges exactly)
{rows}

## The shared design system (from the approved outline)
Concept: {outline.get('concept', '')}
Palette tokens: {json.dumps(outline.get('palette') or {}, ensure_ascii=False)}
Global CSS (already loaded for every scene):
{outline.get('global_css', '') or '(none)'}
Component kit (binding: reuse these looks for titles, figures, labels, charts):
{outline.get('kit', '')}
{_recipe_cards(mine)}
## Stage brief
{agent.skill('long_explainer', 'scene_build', p)}{proof.brief(pid, s, d)}{sceneedit.brief(pid, s, d)}
"""


def _build(pid, s, part, outline, script, note=None, d=None, user=None):
    """One designer run for one part. -> {k, usd, summary} (raises AgentError when nothing was accepted)."""
    from .agent import AgentError, SERVER
    p = P.load(pid, d)
    ours, builtins = T.agent_tools(s["tools"])
    servers = {SERVER: mcp_server.config(pid, s["id"], ours, d=d, user=user or p.get("created_by"), part=part["k"])}
    model = s.get("model") or "opus"
    art = P.path(pid, "artifacts", part_art(part["k"]) + ".json", d=d)
    before = os.path.getmtime(art) if os.path.exists(art) else 0
    started = time.time()
    P.event(pid, "agent_start", d=d, stage=s["id"], part=part["k"], model=model)
    try:
        reply, meta = llm.ask_text(_task(pid, s, part, outline, script, note, d),
                                   tools=tuple([f"mcp__{SERVER}__{n}" for n in ours] + builtins + ["Read"]),
                                   timeout=TIMEOUT, model=model, retries=1, servers=servers, budget_usd=BUDGET_USD)
    except llm.LLMError as e:
        raise AgentError(str(e)) from None
    written = os.path.exists(art) and os.path.getmtime(art) > before and os.path.getmtime(art) >= started - 1
    P.event(pid, "agent_end", d=d, stage=s["id"], part=part["k"], seconds=round(time.time() - started),
            cost_usd=meta.get("cost_usd"), submitted=written)
    if not written:
        raise AgentError(f"part {part['k']}: the designer ended without accepted scenes ({reply.strip()[-200:]})")
    data = P.read_artifact(pid, part_art(part["k"]), d) or {}
    P.write_artifact(pid, part_art(part["k"]), {**data, "sig": sig(outline, part, script)}, d)
    return {"k": part["k"], "usd": meta.get("cost_usd") or 0, "summary": data.get("summary", "")}


def named(note, script, outline):
    """Part numbers the creator's note points at: a scene id, chapter N / bölüm N, intro / giriş."""
    if not note:
        return set()
    low, out = note.lower(), set()
    ps = parts(script)
    for sc in outline.get("scenes") or []:
        if re.search(r"(?<![\w-])" + re.escape(sc["id"].lower()) + r"(?![\w-])", low):
            out |= {p["k"] for p in ps if _in(sc, p)}
    for m in re.finditer(r"(?:chapter|bölüm|bolum|kapitel)\s*(\d+)", low):
        out.add(int(m.group(1)))
    if re.search(r"\b(intro|giriş|giris|einleitung)\b", low):
        out.add(0)
    return out & {p["k"] for p in ps}


def build_scenes(pid, s, note=None, d=None, build=None):
    """The scene plan stage: draw the parts that need it, several at once, then merge and lint the whole plan.
    `build` replaces the agent run (tests)."""
    from .. import layoutlint
    script = P.read_artifact(pid, "script", d) or {}
    outline = P.read_artifact(pid, "outline", d)
    if not outline:
        raise LongError("no outline yet: approve the scene outline first")
    probs = outline_problems(script, outline)
    if probs:
        raise LongError("the outline does not fit the script: " + "; ".join(probs[:3]))
    ps, current = parts(script), P.read_artifact(pid, "scene_plan", d) or {}
    by_id = {sc["id"]: sc for sc in current.get("scenes") or [] if not sc.get("placeholder")}
    keep, todo = {}, []
    asked = named(note, script, outline)
    for part in ps:
        mine = [x for x in outline.get("scenes") or [] if _in(x, part)]
        art = P.read_artifact(pid, part_art(part["k"]), d) or {}
        fresh = art.get("sig") == sig(outline, part, script)
        have = [by_id.get(x["id"]) for x in mine]
        if fresh and part["k"] not in asked and (not note or asked):
            if all(have) and [h["id"] for h in have] == [x["id"] for x in mine]:
                keep[part["k"]] = have            # the current plan's scenes, hand edits included
            continue
        todo.append(part)
    run = build or (lambda part: _build(pid, s, part, outline, script, note, d))
    done, failed = [], []
    if todo:
        with cf.ThreadPoolExecutor(max_workers=min(PARALLEL, len(todo))) as pool:
            futs = {pool.submit(run, part): part for part in todo}
            for f in cf.as_completed(futs):
                try:
                    done.append(f.result())
                except Exception as e:
                    failed.append((futs[f], e))
    for part, _ in list(failed):                   # one more go, one at a time
        try:
            done.append(run(part))
            failed.remove((part, _))
        except Exception as e:
            P.event(pid, "part_failed", d=d, stage=s["id"], part=part["k"], error=f"{type(e).__name__}: {e}"[:300])
    if failed:
        raise LongError("these parts could not be drawn: " + ", ".join(str(p["name"]) for p, _ in failed)
                        + f" ({type(failed[0][1]).__name__}: {str(failed[0][1])[:200]})")
    pl = plan(pid, d, keep=keep)
    if current.get("edits"):
        pl["edits"] = current["edits"]
    b = X.bundle(pid, pl, d)
    p = P.load(pid, d)
    rep = {}
    stills, errs, found = layoutlint.run(b, X.scene_times(pid, pl, d), P.path(pid, "stills", "long-lint", d=d), "16:9",
                                         report=rep)
    errors = [f for f in found if f["kind"] in ("safe", "caption", "overlap", "contrast", "tiny")]
    ui = p.get("ui_lang") if p.get("ui_lang") in ("tr", "en") else "tr"
    n = len([x for x in pl["scenes"] if not x["id"].startswith(CARD)])
    slop = sum(1 for f in found if f["kind"] in layoutlint.SLOP)
    pl["lint"] = {"layout": len(errors), "slop": slop, "timing": len(found) - len(errors) - slop, "js_errors": errs[:6],
                  "grade": rep.get("grade"), "score": rep.get("score"),
                  "text": layoutlint.as_text(found)}
    pl["stills"] = [X._rel(x) for x in stills]
    pl["parts"] = {"built": sorted(r["k"] for r in done), "kept": sorted(keep)}
    pl["summary"] = {"tr": f"{n} sahne, {len(chapters(script))} bölüm kartı; {len(done)} parça çizildi"
                           f"{', ' + str(len(keep)) + ' parça olduğu gibi kaldı' if keep else ''}. "
                           f"Yerleşim kontrolü: {len(errors)} bulgu.",
                     "en": f"{n} scenes, {len(chapters(script))} chapter cards; {len(done)} parts drawn"
                           f"{', ' + str(len(keep)) + ' kept as they were' if keep else ''}. "
                           f"Layout check: {len(errors)} findings."}[ui]
    P.decision(pid, "scene_plan", f"parts drawn {pl['parts']['built']}, kept {pl['parts']['kept']}", d=d)
    return {"artifact": pl, "summary": pl["summary"], "cost": {"usd": round(sum(r["usd"] for r in done), 4)}}


# ---------------------------------------------------------------- after the render

def marks(pid, d=None):
    """YouTube chapter marks from the real timing: [{t, title}], the intro at 0:00 when there is one."""
    script = P.read_artifact(pid, "script", d) or {}
    pl = P.read_artifact(pid, "scene_plan", d) or {}
    sp = X.spec(pid, pl, d)
    lang = P.load(pid, d).get("video_lang", "en")
    out = [{"t": c["start"], "title": c["title"]} for c in sp.get("chapters") or []]
    if out and out[0]["t"] > 0.5:
        out.insert(0, {"t": 0.0, "title": INTRO.get(lang, INTRO["en"])})
    if out:
        out[0]["t"] = 0.0
    return out


def stamp(t):
    t = int(round(t))
    return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60}:{t % 60:02d}"


def marks_text(pid, d=None):
    return "\n".join(f"{stamp(m['t'])} {m['title']}" for m in marks(pid, d))


def compose(pid, s, note=None, d=None):
    """The explainer's final render + QA + covers, plus the chapter marks for the YouTube description."""
    out = X.compose(pid, s, note, d)
    out["artifact"]["chapters"] = marks(pid, d)
    out["artifact"]["chapters_text"] = marks_text(pid, d)
    return out
