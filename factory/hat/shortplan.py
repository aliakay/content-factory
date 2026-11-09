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
import hashlib, json, os, re, time

from . import project as P
from . import tools as T

PARALLEL = 2          # 4 cores: the stills render contends, so two designers at a time
DESIGN = "design_short"


class ShortError(RuntimeError):
    pass


# a note about WHERE the film cuts needs the design pass again (the scene line ranges live there); a note about how one
# scene looks does not, so it only redraws that part
DESIGN_WORDS = ("kesim", "cut", "satır", "line", "aralık", "range", "süre", "second", "zaman", "timing", "böl",
                "kaydır", "move the")


def needs_design(note):
    low = str(note or "").lower()
    return bool(low) and any(w in low for w in DESIGN_WORDS)


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
    """The script as the prompts show it: the index in brackets IS the number `lines` must use (0-based).

    A "1. …" list made the design pass answer with 1-based ranges, which the gate refuses
    ("lines 11..12 run past the script", "never shows line(s) [0]"). The index is printed, not the ordinal.
    """
    lines = script.get("lines") or []
    return "\n".join(f"[{i}] {x}" for i, x in enumerate(lines))


def _line_note(found, n_lines):
    """The one correction a design pass needs when it numbered the script from 1 instead of 0."""
    return ("The scene `lines` are 0-based indices into the script below: the first scene starts at line 0 and the last "
            f"ends at line {max(0, n_lines - 1)}; cover every line exactly once, in order. The checks refused the last "
            "answer: " + "; ".join(found[:6]))


def rebase_one_based(scenes, n_lines):
    """Shift the classic 1-based answer (`[1, n]` tiled once, in order) down to 0-based. True if it changed anything.

    This is the unambiguous case: the ranges start at 1, end at the script's line count, and each one begins where the
    previous ended, so the only thing wrong is the origin. Anything less regular is left to the checks to refuse — a
    half-shifted plan must not be guessed at.
    """
    if not n_lines or not scenes:
        return False
    ranges = []
    for sc in scenes:
        r = sc.get("lines") if isinstance(sc, dict) else None
        if not (isinstance(r, list) and len(r) == 2
                and all(isinstance(x, int) and not isinstance(x, bool) for x in r)):
            return False
        ranges.append((r[0], r[1]))
    if ranges[0][0] != 1 or ranges[-1][1] != n_lines:
        return False
    if any(not 1 <= a <= b <= n_lines for a, b in ranges):
        return False
    if any(b + 1 != na for (_, b), (na, _) in zip(ranges, ranges[1:])):
        return False
    for sc in scenes:
        a, b = sc["lines"]
        sc["lines"] = [a - 1, b - 1]
    return True


def _brief_problems(briefs, lines):
    """The structural checks on the design pass's briefs, before any scene is drawn from them."""
    from .. import shotplan
    return shotplan.problems(briefs, lines)


def _design_prompt(pid, s, script, board, research, d, note=None):
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

Write the design system and the scene list. Every line of the script must be covered, in order, by exactly one scene;
the numbers in brackets above are the indices to write (`lines` is 0-based, first line 0, last line {max(0, len(script.get('lines') or []) - 1)}).
Reply ONLY JSON:
{{"concept": "one line: the visual idea of the film",
  "palette": {{"bg": "#..", "ink": "#..", "muted": "#..", "accent": "#..", "accent2": "#.."}},
  "global_css": "the shared CSS (fonts, type scale, .w stage, caption-safe area)",
  "kit": "the reusable components every scene uses (title block, figure, label, chart, source line) as one paragraph",
  "scenes": [{{"id": "lower-case-id", "lines": [first, last] (0-based indices, inclusive), "brief": "what this scene must make the viewer see",
              "shows": "the subject and what it does (an action verb)", "mechanism": "one catalogue mechanism",
              "camera": {{"move": "push_in", "seconds": 1.5, "easing": "ease_out", "target": "what it lands on"}}}}]}}
Use the board's palette and type pairing exactly; no other colour, no other font.
Give the camera moves different lengths (a quick 1.5 s push, a long 5 s pull-back): a film where every move lasts the
same number of seconds reads as a slideshow.
{("The creator's note about this film (it may ask to move where the scenes cut): " + str(note)) if note else ""}"""


def _scene_prompt(pid, s, design, part, script, d):
    from . import agent
    p = P.load(pid, d)
    from .. import words as _w
    def must(sc):
        a, b = (sc.get("lines") or [0, 0])[:2]
        text = " ".join(str(x) for x in (script.get("lines") or [])[a:b + 1])
        import re as _re
        nums = _re.findall(r"\d[\d.,]*", text)
        names = [n for n in _w.proper_nouns(text) if len(n) > 2]
        return [x for x in dict.fromkeys(nums + names)][:6]
    briefs = "\n".join(json.dumps({**{k: sc.get(k) for k in ("id", "lines", "brief", "shows", "mechanism", "camera")},
                                    "shows_must_name": must(sc)}, ensure_ascii=False) for sc in part)
    return f"""{agent.skill(p['line'], 'scene_plan', p)}

# This run: the scenes {[sc['id'] for sc in part]}
The design system is approved and fixed — use its palette, its CSS and its kit, invent nothing else.

Palette: {json.dumps(design.get('palette') or {}, ensure_ascii=False)}
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
Every scene's `shows` is one line: the subject, an action verb (rises, splits, fills, travels, appears, drops, counts
up), and every figure or proper name its lines say — the list in `shows_must_name` is the minimum.
`data-e` numbers on every visible element; no Math.random, no Date.now, no network; text stays out of the caption band."""


def design(pid, s, script, board, research, d=None, ask=None, note=None):
    """The design system + the scene briefs.

    Cached while the script and the board are unchanged — unless a note comes with the repair: the cut laws live in
    the scene `lines` ranges, so a note that names where the cuts land has to re-decide them here, not only inside the
    scenes."""
    sig = _hash([script.get("title"), script.get("lines"), board.get("fingerprint"), note or ""])
    cur = P.read_artifact(pid, DESIGN, d) or {}
    if cur.get("sig") == sig and cur.get("scenes"):
        return cur
    ask = ask or _ask
    out, _meta = _call(ask, _design_prompt(pid, s, script, board, research, d, note))
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
        # the cut plan is the design pass's call: the scene redraws its picture, never re-decides where it starts and
        # ends (a designer echoing 1-based or overlapping ranges would silently break the plan's coverage)
        if b.get("lines"):
            sc["lines"] = list(b["lines"])
        sc.setdefault("shows", b.get("shows"))
        sc.setdefault("mechanism", b.get("mechanism"))
        sc.setdefault("camera", b.get("camera"))
        filled.append(sc)
    return {"ids": want, "scenes": filled, "usd": (meta or {}).get("cost_usd") or 0}


def validate(plan, script, board, refs=(), sp=None, lang="tr"):
    """Everything the gate would refuse, in one list (camera, subject, mechanism, determinism, originality, board)."""
    from .. import camera, determinism, motiongrammar, originality, shotplan, subjectqc
    lines = script.get("lines") or []
    scenes_ = plan.get("scenes") or []
    # the cut laws need the voice: a draft's word positions are an estimate, and cutting against them would refuse
    # every plan before the voice exists (the animatic gate checks them again on real timing)
    voiced = (sp or {}).get("timing") == "voice"
    words = (sp or {}).get("words") or [] if voiced else []
    starts = [sc.get("start") for sc in (sp or {}).get("scenes") or []]
    found = (shotplan.problems(scenes_, lines, words=words, starts=starts if words and all(s is not None for s in starts) else None)
             or T.validate_artifact("scene_plan", plan))
    found += camera.problems(scenes_) or motiongrammar.problems(scenes_) or subjectqc.problems(scenes_, lines, lang) \
        or determinism.problems(plan) or originality.problems(plan, lines, refs) \
        or direction_problems(plan, board)
    return found


def direction_problems(plan, board):
    from . import direction
    return direction.problems(plan, board) if board else []


def _designed(pid, s, script, board, research, d, ask, note):
    """The design pass, with the line ranges held to the script's 0-based indices before a scene is drawn.

    The design prompt shows the script with its indices, but a model can still answer with a 1-based tiling; that is
    shifted deterministically, without a second call. Anything else is sent back once with the exact rule, and a design
    pass that still cannot place the lines fails the stage here — before seven scenes are drawn against it."""
    lines = script.get("lines") or []
    art = design(pid, s, script, board, research, d, ask, note)
    for attempt in range(2):
        if rebase_one_based(art.get("scenes") or [], len(lines)):
            P.event(pid, "lines_rebased", d=d, stage=s["id"], where="design", attempt=attempt + 1)
            P.write_artifact(pid, DESIGN, art, d)          # the cache must hold the corrected ranges too
        found = _brief_problems(art.get("scenes") or [], lines)
        if not found:
            return art
        if attempt:
            raise ShortError("the design pass did not fix the scene `lines`: " + "; ".join(found[:6]))
        art = design(pid, s, script, board, research, d, ask,
                     "\n".join(x for x in (note, _line_note(found, len(lines))) if x))
    raise ShortError("the design pass did not return usable scene lines")


def _assemble(briefs, drawn, keep):
    """The plan's scenes in the design pass's order: a freshly drawn scene wins over the one on disk.

    The line range always comes from the brief: the design pass decides where the cuts land, and a kept scene from an
    older design must not carry a stale range into the merged plan."""
    out = []
    for b in briefs:
        sid = b["id"]
        if sid in drawn:
            out.append(drawn[sid])
        elif sid in keep:
            sc = dict(keep[sid])
            if b.get("lines"):
                sc["lines"] = list(b["lines"])
            out.append(sc)
    return out


def _repair_once(pid, s, script, design_art, briefs, groups, drawn, keep, plan, problems, d, ask, build):
    """Redraw only the scenes the checks named, then check again. Plan-level findings cannot be patched this way."""
    named, per_scene = set(), []
    for f in problems:
        m = re.match(r"scene ([^:\s]+):", str(f))
        if m:
            named.add(m.group(1))
            per_scene.append(str(f))
        else:
            return problems                    # a hole in the coverage or the pace is not a scene's picture: no patch
    todo = [part for part in groups if named & {b["id"] for b in part}]
    if not todo:
        return problems
    for part in todo:
        ids = {b["id"] for b in part}
        mine = [f for f in per_scene if re.match(r"scene ([^:\s]+):", f).group(1) in ids]
        try:
            run = scenes(pid, s, design_art, part, script,
                         "The gate refused these findings; fix exactly them:\n" + "\n".join(mine), d, ask, build)
            for sc in run["scenes"]:
                drawn[sc["id"]] = sc
        except Exception as e:
            P.event(pid, "repair_failed", d=d, stage=s["id"], part=sorted(ids),
                    error=f"{type(e).__name__}: {e}"[:300])
    plan["scenes"] = _assemble(briefs, drawn, keep)
    plan["parts"]["rebuilt"] = sorted(set(plan["parts"]["rebuilt"]) | named)
    return None


def build(pid, s, note=None, d=None, ask=None, build=None, parallel=PARALLEL):
    """The stage: design system -> scenes in parallel -> merge, validate, lint, write. Repair only what a note names."""
    from .. import layoutlint, capabilities
    from . import explainer as X
    p, script = P.load(pid, d), P.read_artifact(pid, "script", d) or {}
    if not script.get("lines"):
        raise ShortError("no script yet: approve the script first")
    lines = script.get("lines") or []
    board, research = _board(pid, d), P.read_artifact(pid, "research", d) or {}
    prev_design = P.read_artifact(pid, DESIGN, d) or {}
    design_art = _designed(pid, s, script, board, research, d, ask, note if needs_design(note) else None)
    # a fresh design pass may rename or re-range the scenes: then every part has to be drawn against it (a rebased
    # design keeps its signature but moves the ranges, so the ranges are compared too)
    fresh = (design_art.get("sig") != prev_design.get("sig")
             or [(b.get("id"), b.get("lines")) for b in design_art["scenes"]]
             != [(b.get("id"), b.get("lines")) for b in prev_design.get("scenes") or []])
    briefs = design_art["scenes"]
    current = P.read_artifact(pid, "scene_plan", d) or {}
    keep = {sc["id"]: sc for sc in current.get("scenes") or [] if sc.get("id")}
    groups = parts(briefs, parallel)
    asked = named(note, briefs)
    # a note that names scenes repairs those parts only — unless the design itself changed (new ids or ranges), in which
    # case keeping an old scene next to a new design would mix two films: draw every part again
    todo = groups if (fresh or not asked) else [part for part in groups if asked & {b["id"] for b in part}]
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
        raise ShortError("these scenes could not be drawn: "
                         + ", ".join(b["id"] for part, _ in failed for b in part)
                         + f" ({type(failed[0][1]).__name__}: {str(failed[0][1])[:200]})")
    drawn = {sc["id"]: sc for run in done for sc in run["scenes"]}
    missing = [b["id"] for b in briefs if b["id"] not in drawn and b["id"] not in keep]
    if missing:
        raise ShortError(f"these scenes would be lost (the design renamed them?): {missing}")
    scenes_out = _assemble(briefs, drawn, keep)
    plan = {"concept": design_art.get("concept") or "", "palette": design_art.get("palette") or {},
            "global_css": design_art.get("global_css") or "", "kit": design_art.get("kit") or "",
            "scenes": scenes_out,
            "parts": {"rebuilt": sorted(drawn), "kept": sorted(set(keep) & {b["id"] for b in briefs} - set(drawn))}}
    if current.get("edits"):
        plan["edits"] = current["edits"]
    plan["summary"] = ""                           # the schema requires it; the real line is written after the checks
    # the same last line of defence as a shifted design pass: a scene echoes its brief's range, but never with an origin
    if rebase_one_based(plan["scenes"], len(lines)):
        P.event(pid, "lines_rebased", d=d, stage=s["id"], where="plan")
    try:
        sp = X.spec(pid, plan, d)
    except Exception:
        sp = None
    video_lang = p.get("video_lang") or "tr"
    try:
        refs = T._refs(T.Ctx(pid, s["id"], d))
    except Exception:
        refs = ()
    problems = validate(plan, script, board, refs=refs, sp=sp, lang=video_lang)
    if problems:                                   # one redraw of the scenes the checks named, then the checks again
        problems = _repair_once(pid, s, script, design_art, briefs, groups, drawn, keep, plan, problems, d, ask, build)
        if problems is None:
            problems = validate(plan, script, board, refs=refs, sp=sp, lang=video_lang)
    plan["checked"] = problems[:12]
    try:                                            # the layout lint needs a browser; its absence is not a failure
        rep = {}
        b = X.bundle(pid, plan, d)
        # the Studio reads the newest `stills/<stage>-*` folder: name it after the stage so the frames show on the card
        stills, errs, found = layoutlint.run(b, X.scene_times(pid, plan, d),
                                             P.path(pid, "stills", f"{s['id']}-{int(time.time())}", d=d),
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
    if problems:                                   # never hand the gate a plan it has already refused
        raise ShortError("the scene plan still fails its checks after a repair round: " + "; ".join(problems[:6]))
    return {"artifact": plan, "summary": plan["summary"],
            "cost": {"usd": round(sum(r.get("usd") or 0 for r in done), 4)}}
