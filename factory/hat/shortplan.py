"""The short-film scene plan in two passes: one design system, then the scenes in parallel.

One agent drawing a whole 55-second film in one turn spends most of its tokens reading the script again per scene and
deciding the palette over and over; a fix round then rewrites every scene for one finding. This stage splits it:

  design   one call, no drawing: palette (from the approved direction board), global CSS, the kit, and every scene's
           brief — id, lines, `shows`, camera, mechanism
  scenes   one call per part, PARALLEL at a time, each drawing its own scenes against that design system
  merge    the deterministic checks (camera, subject, mechanism, determinism, originality, the board), the layout lint
           on a real render, then the artifact

A re-run with a note that names scenes rebuilds only the parts those scenes live in; every other scene is kept exactly
as the creator saw it. `ask` is injectable so the flow is testable without a model.
"""
import hashlib, json, os, re

from . import project as P
from . import tools as T

PARALLEL = 2          # 4 cores: the stills render contends, so two designers at a time
DESIGN = "design_short"


class ShortError(RuntimeError):
    pass


def _hash(*parts):
    return hashlib.sha1(json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:12]


def _board(pid, d=None):
    return P.read_artifact(pid, "direction", d) or {}


def _ask(prompt):
    from .. import llm
    return llm.ask(prompt, tools=(), timeout=1200, model="sonnet")


def _call(ask, prompt):
    """(data, meta) from an ask function that returns either the data or (data, meta)."""
    out = ask(prompt)
    if isinstance(out, tuple) and len(out) == 2:
        return out[0] or {}, out[1] or {}
    return out or {}, {}


def _script_text(script):
    return "\n".join(f"{i + 1}. {x}" for i, x in enumerate(script.get("lines") or []))


def _design_prompt(pid, s, script, board, research, d):
    from .. import camera_deck
    from . import agent
    p = P.load(pid, d)
    pal = ", ".join(f"{k} {v}" for k, v in (board.get("palette") or {}).items()) or "choose from the brief"
    typ = board.get("type") or {}
    rules = "\n".join(f"- {r.get('what')}: {r.get('says')}" for r in board.get("rules") or [])
    n = max(3, min(12, round(float(p.get("seconds") or 55) / 6)))
    deck = camera_deck.deal(n, "standard", seed=pid)
    return f"""{agent.skill(p['line'], 'scene_plan', p)}

# This run: the design system only (nothing is drawn yet)
Project: {p.get('title')} · {script.get('title') or ''} · {p.get('video_lang', 'tr')} · {p.get('aspect', '9:16')}
Seconds: {p.get('seconds') or (P.read_artifact(pid, 'proposal', d) or {}).get('seconds')}
Research insight: {str((research or {}).get('insight') or '')[:600]}

PROPOSED CAMERA DECK (dealt for this film; give each scene the next card, in order)
{camera_deck.summary(deck, 'en')}
{chr(10).join(f"- {d['move']} · {d['seconds']:g} s · {d['easing']}" + (" · the one big move" if d['big'] else "")
              for d in deck)}

APPROVED DIRECTION BOARD (binding)
Palette: {pal}
Type: {typ.get('display')} display · {typ.get('body')} body
Rules:
{rules or '- (none)'}

Script lines:
{_script_text(script)}

Write the design system and the scene list. Every line of the script must be covered, in order, by exactly one scene.
Reply ONLY JSON:
{{"concept": "one line: the visual idea of the film",
  "palette": {{"bg": "#..", "ink": "#..", "muted": "#..", "accent": "#..", "accent2": "#.."}},
  "global_css": "the shared CSS (fonts, type scale, .w stage, caption-safe area)",
  "kit": "the reusable components every scene uses (title block, figure, label, chart, source line) as one paragraph",
  "scenes": [{{"id": "lower-case-id", "lines": [first, last], "brief": "what this scene must make the viewer see",
              "shows": "the subject and what it does (an action verb)", "mechanism": "one catalogue mechanism",
              "camera": {{"move": "push_in", "seconds": 1.5, "easing": "ease_out", "target": "what it lands on"}}}}]}}
Use the board's palette and type pairing exactly; no other colour, no other font."""


def _scene_prompt(pid, s, design, part, script, d):
    from . import agent
    p = P.load(pid, d)
    briefs = "\n".join(json.dumps({k: sc.get(k) for k in ("id", "lines", "brief", "shows", "mechanism", "camera")},
                                  ensure_ascii=False) for sc in part)
    return f"""{agent.skill(p['line'], 'scene_plan', p)}

# This run: the scenes {[sc['id'] for sc in part]}
The design system is approved and fixed — use its palette, its CSS and its kit, invent nothing else.

Palette: {json.dumps(design.get('palette') or {{}}, ensure_ascii=False)}
Global CSS:
{design.get('global_css') or ''}

Kit: {design.get('kit') or ''}

Script lines:
{_script_text(script)}

Your scenes (draw exactly these, in this order):
{briefs}

Reply ONLY JSON: {{"scenes": [{{"id": "...", "lines": [a, b], "mechanism": "...", "shows": "...",
  "camera": {{"move": "...", "seconds": 1.5, "easing": "...", "target": "..."}},
  "html": "<div class=\\"w\\">…</div>", "css": "scene-only CSS", "js": "timeline code using T.start"}}]}}
`data-e` numbers on every visible element; no Math.random, no Date.now, no network; text stays out of the caption band."""


def design(pid, s, script, board, research, d=None, ask=None):
    """The design system + the scene briefs (cached while the script and the board are unchanged)."""
    sig = _hash([script.get("title"), script.get("lines"), board.get("fingerprint")])
    cur = P.read_artifact(pid, DESIGN, d) or {}
    if cur.get("sig") == sig and cur.get("scenes"):
        return cur
    ask = ask or _ask
    out, _meta = _call(ask, _design_prompt(pid, s, script, board, research, d))
    if not out.get("scenes"):
        raise ShortError("the design pass returned no scene list")
    art = {"sig": sig, "concept": out.get("concept"), "palette": out.get("palette") or board.get("palette") or {},
           "global_css": out.get("global_css") or "", "kit": out.get("kit") or "", "scenes": out["scenes"]}
    P.write_artifact(pid, DESIGN, art, d)
    P.event(pid, "design_system", d=d, stage=s["id"], scenes=len(art["scenes"]),
            palette=len(art["palette"]), model_digest=sig)
    return art


def parts(briefs, n=PARALLEL, lines=None):
    """Split the scene briefs into `n` balanced parts (by the lines each scene covers)."""
    n = max(1, min(n, len(briefs)))
    weight = [(b.get("lines") or [0, 0])[1] - (b.get("lines") or [0, 0])[0] + 1 for b in briefs]
    total, out, cur, acc = sum(weight) or len(briefs), [], [], 0
    for b, w in zip(briefs, weight):
        cur.append(b)
        acc += w
        if len(out) < n - 1 and acc >= total * (len(out) + 1) / n:
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return [p for p in out if p]


def named(note, briefs):
    """Scene ids the creator's note points at (a plain id, or `sahne 3` → the third scene)."""
    if not note:
        return set()
    low = str(note).lower()
    ids = {b["id"] for b in briefs if b.get("id") and re.search(rf"(?<![\w-]){re.escape(str(b['id']).lower())}(?![\w-])", low)}
    for m in re.finditer(r"(?:sahne|scene)\s*(\d+)", low):
        i = int(m.group(1)) - 1
        if 0 <= i < len(briefs):
            ids.add(briefs[i]["id"])
    return ids


def scenes(pid, s, design_art, part, script, note=None, d=None, ask=None, build=None):
    """One designer run for one part -> {ids, scenes, usd}."""
    ask = ask or _ask
    if build is not None:
        got, meta = build(part), {}
    else:
        prompt = _scene_prompt(pid, s, design_art, part, script, d)
        if note:
            prompt += f"\n\nCreator's note: {note}"
        reply, meta = _call(ask, prompt)
        got = reply.get("scenes") or []
    want = [b["id"] for b in part]
    by_id = {g.get("id"): g for g in got if isinstance(g, dict)}
    missing = [x for x in want if x not in by_id]
    if missing:
        raise ShortError(f"the designer left scenes out: {missing}")
    filled = []
    for b in part:
        sc = dict(by_id[b["id"]])
        sc.setdefault("lines", b.get("lines"))
        sc.setdefault("shows", b.get("shows"))
        sc.setdefault("mechanism", b.get("mechanism"))
        sc.setdefault("camera", b.get("camera"))
        filled.append(sc)
    return {"ids": want, "scenes": filled, "usd": (meta or {}).get("cost_usd") or 0}


def validate(plan, script, board, refs=(), sp=None):
    """Everything the gate would refuse, in one list (camera, subject, mechanism, determinism, originality, board)."""
    from .. import camera, determinism, motiongrammar, originality, shotplan, subjectqc
    lines = script.get("lines") or []
    scenes_ = plan.get("scenes") or []
    words = (sp or {}).get("words") or []
    starts = [sc.get("start") for sc in (sp or {}).get("scenes") or []]
    found = (shotplan.problems(scenes_, lines, words=words, starts=starts if all(s is not None for s in starts) else None)
             or T.validate_artifact("scene_plan", plan))
    found += camera.problems(scenes_) or motiongrammar.problems(scenes_) or subjectqc.problems(scenes_, lines) \
        or determinism.problems(plan) or originality.problems(plan, lines, refs) \
        or direction_problems(plan, board)
    return found


def direction_problems(plan, board):
    from . import direction
    return direction.problems(plan, board) if board else []


def build(pid, s, note=None, d=None, ask=None, build=None, parallel=PARALLEL):
    """The stage: design system -> scenes in parallel -> merge, validate, lint, write. Repair only what a note names."""
    from .. import layoutlint, capabilities
    from . import explainer as X
    p, script = P.load(pid, d), P.read_artifact(pid, "script", d) or {}
    if not script.get("lines"):
        raise ShortError("no script yet: approve the script first")
    board, research = _board(pid, d), P.read_artifact(pid, "research", d) or {}
    design_art = design(pid, s, script, board, research, d, ask)
    briefs = design_art["scenes"]
    current = P.read_artifact(pid, "scene_plan", d) or {}
    keep = {sc["id"]: sc for sc in current.get("scenes") or [] if sc.get("id")}
    groups = parts(briefs, parallel)
    asked = named(note, briefs)
    # a note that names scenes repairs those parts only; no note (or a note about the film as a whole) draws everything
    todo = [part for part in groups if asked & {b["id"] for b in part}] if asked else groups
    done, failed = [], []
    if len(todo) > 1:
        import concurrent.futures as cf
        with cf.ThreadPoolExecutor(max_workers=min(parallel, len(todo))) as pool:
            futs = {pool.submit(scenes, pid, s, design_art, part, script, note, d, ask, build): part for part in todo}
            for f in cf.as_completed(futs):
                try:
                    done.append(f.result())
                except Exception as e:
                    failed.append((futs[f], e))
    else:
        for part in todo:
            try:
                done.append(scenes(pid, s, design_art, part, script, note, d, ask, build))
            except Exception as e:
                failed.append((part, e))
    for part, err in list(failed):                 # one more go, one at a time
        try:
            done.append(scenes(pid, s, design_art, part, script, note, d, ask, build))
            failed.remove((part, err))
        except Exception as e:
            P.event(pid, "part_failed", d=d, stage=s["id"], part=[b["id"] for b in part],
                    error=f"{type(e).__name__}: {e}"[:300])
    if failed:
        raise ShortError("these scenes could not be drawn: " + ", ".join(b["id"] for b, _ in failed)
                         + f" ({type(failed[0][1]).__name__}: {str(failed[0][1])[:200]})")
    drawn = {sc["id"]: sc for run in done for sc in run["scenes"]}
    scenes_out = []
    for b in briefs:                                 # the design pass fixes the order; drawn wins over kept
        sid = b["id"]
        if sid in drawn:
            scenes_out.append(drawn[sid])
        elif sid in keep:
            scenes_out.append(keep[sid])
    plan = {"concept": design_art.get("concept") or "", "palette": design_art.get("palette") or {},
            "global_css": design_art.get("global_css") or "", "kit": design_art.get("kit") or "",
            "scenes": scenes_out,
            "parts": {"rebuilt": sorted(drawn), "kept": sorted(set(keep) & {b["id"] for b in briefs} - set(drawn))}}
    if current.get("edits"):
        plan["edits"] = current["edits"]
    try:
        sp = X.spec(pid, plan, d)
    except Exception:
        sp = None
    problems = validate(plan, script, board, sp=sp)
    plan["checked"] = problems[:12]
    try:                                            # the layout lint needs a browser; its absence is not a failure
        rep = {}
        b = X.bundle(pid, plan, d)
        stills, errs, found = layoutlint.run(b, X.scene_times(pid, plan, d), P.path(pid, "stills", "plan-lint", d=d),
                                             p.get("aspect", "9:16"), report=rep)
        plan["lint"] = {"layout": len(found), "js_errors": errs[:6], "grade": rep.get("grade"),
                        "score": rep.get("score"), "text": layoutlint.as_text(found)}
        plan["stills"] = [X._rel(x) for x in stills]
    except Exception as e:
        P.event(pid, "lint_skipped", d=d, stage=s["id"], error=f"{type(e).__name__}: {e}"[:200])
    lang = p.get("ui_lang") if p.get("ui_lang") in ("tr", "en") else "tr"
    plan["summary"] = ({"tr": f"{len(plan['scenes'])} sahne; {len(plan['parts']['rebuilt'])} çizildi, "
                              f"{len(plan['parts']['kept'])} olduğu gibi kaldı. Kontrol: {len(problems)} bulgu.",
                        "en": f"{len(plan['scenes'])} scenes; {len(plan['parts']['rebuilt'])} drawn, "
                              f"{len(plan['parts']['kept'])} kept as they were. Checks: {len(problems)} findings."}[lang])
    P.write_artifact(pid, "scene_plan", plan, d)
    P.decision(pid, "scene_plan", f"rebuilt {plan['parts']['rebuilt']}, kept {plan['parts']['kept']}", d=d)
    return {"artifact": plan, "summary": plan["summary"],
            "cost": {"usd": round(sum(r.get("usd") or 0 for r in done), 4)}}
