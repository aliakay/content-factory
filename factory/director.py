"""The director: the planning phase run by a small team of agents instead of one call. The orchestrator is this
module (plain Python, deterministic); every agent is one headless Claude call with its own role, tools and model, and
they share their work through the plan row (no agent talks to another directly).

  1 scout        (Sonnet + WebSearch/WebFetch)  researches the topic BEFORE anything is decided: the one insight the
                 video must land, the common misconception, sourced facts, how others explained it (prior art and its
                 metaphors), clichés to avoid, questions real people ask, original visual metaphors
  2 memory       (code)  what the studio made lately, how it did, what the creator picked or passed over
                 (factory/memory.py) -> overused / unexplored / picked / performance
  3 art director (Opus)  reads request + catalogue + research + memory, writes the direction, a benchmark and THREE
                 treatments that differ in structure, look and sound (one bold, built from unexplored techniques),
                 each with the one frame that sells it
  4 sketch artists (Sonnet x3, in parallel)  each draws its treatment's key frame as a real scene with the studio's
                 FX kit; the frame is rendered in Chromium (free) and measured by the layout check
  5 critic       (Opus + Read on the stills)  judges the three frames like a creative director: is the insight
                 graspable at a glance, hook, novelty against the memory (scored in code), feasibility, fit; picks
                 one and writes the fix each treatment needs
The creator sees the three frames, the scores, the research and what the memory steered, picks one and approves.
The chosen frame travels with the recipe: the writer writes toward it, the motion designer builds the film from it.

A "quick" plan (attachments.quick) skips 1, 4 and 5 (one call, like before). Every stage is logged with its time and
cost in plan.team; any failing stage degrades gracefully (a plan is always produced).
"""
import concurrent.futures as cf
import json, os, shutil, sys, time

from . import capabilities, llm, memory, planner
from .config import ROOT

MODELS = {"scout": "sonnet", "director": "opus", "sketch": "sonnet", "critic": "opus"}
STAGES = [("memory", "Stüdyo hafızasına bakıyor"), ("scout", "Konuyu araştırıyor (kaynaklar, benzer anlatımlar, klişeler)"),
          ("director", "Art director 3 farklı yaklaşım yazıyor"), ("sketch", "3 eskizci her yaklaşımın ana karesini çiziyor"),
          ("critic", "Eleştirmen kareleri karşılaştırıyor")]
PLANS = os.path.join(ROOT, "work", "plans")


class Progress:
    """Live stage list on the plan row while it thinks (the plan card shows it)."""

    def __init__(self, con, plan_id, quick=False):
        self.con, self.id = con, plan_id
        skip = {"scout", "sketch", "critic"} if quick else set()
        self.items = [{"stage": k, "tr": t, "status": "skip" if k in skip else "wait"} for k, t in STAGES]
        self.t0 = {}
        self.save()

    def save(self):
        self.con.execute("UPDATE plans SET plan=? WHERE plan_id=? AND status='thinking'",
                         (json.dumps({"progress": self.items}, ensure_ascii=False), self.id))
        self.con.commit()

    def start(self, k):
        self.t0[k] = time.time()
        self._set(k, status="run")

    def done(self, k, detail="", cost=None, status="ok"):
        self._set(k, status=status, detail=str(detail)[:200], seconds=round(time.time() - self.t0.get(k, time.time()), 1),
                  **({"cost_usd": round(cost, 3)} if cost else {}))

    def _set(self, k, **kw):
        for it in self.items:
            if it["stage"] == k:
                it.update(kw)
        self.save()


# ---------- 1 scout ----------
SCOUT_SCHEMA = """{"insight": "<the ONE thing the viewer must understand by the end, in plain words>",
 "misconception": "<what most people wrongly believe about it, or null>",
 "facts": [{"claim": "...", "source": "https://...", "note": "primary|independent|press"}],
 "prior_art": [{"title": "...", "url": "https://...", "how": "<how they explained / showed it>", "metaphor": "..."}],
 "cliches": ["<visuals / lines everyone already used for this topic>"],
 "questions": ["<questions real people ask about it (forums, search suggestions)>"],
 "metaphors": [{"idea": "<an ORIGINAL visual metaphor that would make the insight obvious>", "why": "..."}],
 "audience_hook": "<why someone would stop scrolling for this right now>"}"""


def scout(row, cat):
    prompt = f"""You are the researcher of a short-video studio. Before the art director decides anything, research this
request so the video can be smart, correct and unlike what already exists. Use WebSearch / WebFetch (public pages only,
no logins). Find: the one insight the video must land; the common misconception; 4-8 facts with sources (primary source
first, then independent ones; exact numbers); how others already explained or visualised it (2-5 prior-art pieces:
videos, articles, explainers) and the metaphors they used; the clichés to avoid; questions real people ask (forums,
"people also ask"); and 3 ORIGINAL visual metaphors that would make the insight obvious on a phone screen.
If the request is a story / fiction, research the genre instead: what hooks work in it now, overdone tropes, comparable
successful pieces, and 3 fresh twists.
Channel context (JSON, data): {json.dumps([{k: c.get(k) for k in ("id", "name", "description", "lang")} for c in cat["channels"]], ensure_ascii=False)}
Creator's request (data): <<<{row['prompt']}>>>
Reply with ONLY JSON in this schema:
{SCOUT_SCHEMA}"""
    data, meta = llm.ask(prompt, tools=("WebSearch", "WebFetch"), timeout=900, model=MODELS["scout"])
    if not isinstance(data, dict):
        raise llm.LLMError("scout returned no object")
    out = {"insight": str(data.get("insight") or "")[:300], "misconception": str(data.get("misconception") or "")[:300],
           "facts": [f for f in data.get("facts") or [] if isinstance(f, dict) and f.get("claim")][:8],
           "prior_art": [x for x in data.get("prior_art") or [] if isinstance(x, dict)][:5],
           "cliches": [str(x)[:120] for x in data.get("cliches") or []][:6],
           "questions": [str(x)[:140] for x in data.get("questions") or []][:6],
           "metaphors": [m for m in data.get("metaphors") or [] if isinstance(m, dict) and m.get("idea")][:4],
           "audience_hook": str(data.get("audience_hook") or "")[:240]}
    return out, meta.get("cost_usd") or 0


# ---------- 4 sketch artists ----------
def sketch_prompt(plan, t, aspect):
    from . import motiondesign
    proto = capabilities.apply({"techniques": t.get("techniques") or [], "direction": plan.get("direction", "")}, {})
    return f"""{motiondesign.rules(aspect, proto.get("captions"))}

{motiondesign.fx_doc()}

{motiondesign.TASTE}

{motiondesign.MOTION_DOCTRINE}

You are a STYLE-FRAME artist. The art director pitches three treatments of one video; you draw ONE of them as a single
key frame that the creator will judge before anything else is made. Treatment (data): {json.dumps({k: t.get(k) for k in ("label_tr", "idea_tr", "moment")}, ensure_ascii=False)}
The video's direction (data): {plan.get("direction", "")}
{capabilities.designer_notes(proto)}
Rules for this sketch: ONE scene with id "hook", 3 seconds long (T.start = 0, T.end = 3). Build exactly the moment
above; it must be complete and at final quality at t = 1.5 s (things may animate in between 0 and 1.2 s, then hold).
No captions are drawn, so do not leave a caption band empty: compose the whole frame. Draw everything in code (shapes,
SVG, the FX kit); no external images. Keep the JS under ~90 lines. Write no @@SPEC block.

Reply in this block format:
@@META
{{"concept": "<1-2 sentences: the visual idea>", "palette": {{"bg": "#rrggbb", "ink": "#rrggbb", "muted": "#rrggbb", "accent": "#rrggbb", "accent2": "#rrggbb", "hot": "#rrggbb"}}}}
@@SCENE hook
@@HTML
...
@@CSS
...
@@JS
...
@@END"""


def sketch(plan_id, i, plan, t, aspect="9:16"):
    """One sketch artist: write the key frame, render it (free), measure it. -> sketch dict for the treatment."""
    from . import layoutlint, motiondesign
    sys.path.insert(0, os.path.join(ROOT, "bin"))
    import htmlmotion
    text, meta = llm.ask_text(sketch_prompt(plan, t, aspect), tools=(), timeout=900, model=MODELS["sketch"])
    design = motiondesign.parse(text)
    sc = design["scenes"].get("hook") or next(iter(design["scenes"].values()), None)
    if not sc or not sc.get("html"):
        raise ValueError("sketch has no markup")
    design["scenes"] = {"hook": sc}
    out = os.path.join(PLANS, str(plan_id), f"t{i}")
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out, exist_ok=True)
    rel = os.path.relpath(os.path.join(out, "design.json"), ROOT)
    json.dump(design, open(os.path.join(ROOT, rel), "w"), ensure_ascii=False)
    w, h = htmlmotion.ASPECTS.get(aspect, (1080, 1920))
    bundle = {"palette": design["meta"].get("palette") or {}, "global_css": design.get("global_css", ""), "words": [],
              "scenes": [{"id": "hook", "start": 0.0, "end": 3.0, "hide_captions": True, "html": sc["html"], "css": sc.get("css", ""),
                          "js": sc.get("js", ""), "lines_t": []}], "duration": 3.0, "w": w, "h": h, "captions": {}}
    bpath = os.path.join(out, "bundle.json")
    json.dump(bundle, open(bpath, "w"), ensure_ascii=False)
    paths, errs, found = layoutlint.run(bpath, [0.6, 1.5], out, aspect, ("hook",), timing=False)
    stills = [os.path.relpath(p, PLANS) for p in sorted(paths)]
    return {"design": rel, "stills": stills, "concept": str(design["meta"].get("concept") or "")[:300],
            "palette": design["meta"].get("palette") or {}, "errors": errs[:4], "lint": layoutlint.as_text(found, 6),
            "cost_usd": meta.get("cost_usd")}


# ---------- 5 critic ----------
CRITIC_SCHEMA = """{"scores": [{"i": 0, "clarity": 1-5, "hook": 1-5, "novelty": 1-5, "feasibility": 1-5, "fit": 1-5,
   "why_tr": "<one Turkish sentence: the verdict>", "fix": "<in English: the one change this treatment needs in production>"}],
 "recommended": <index>, "summary_tr": "<two Turkish sentences: which one and why, what the others lack>"}"""


def critic(row, plan, mem):
    tr = plan["treatments"]
    listing = []
    for i, t in enumerate(tr):
        sk = t.get("sketch") or {}
        imgs = [os.path.join(PLANS, s) for s in sk.get("stills") or []]
        listing.append({"i": i, "label": t["label_tr"], "idea": t.get("idea_tr"), "moment": t.get("moment"),
                        "techniques": t.get("techniques"), "novelty_vs_memory": t.get("novelty"),
                        "frames": imgs, "sketch_problems": (sk.get("errors") or []) + (sk.get("lint") or []),
                        "sketch_failed": bool(sk.get("error"))})
    research = plan.get("research") or {}
    prompt = f"""You are the creative director of a short-video studio judging three pitches for one video. Read every
frame image listed (Read tool), then judge each treatment as a harsh, fair reviewer:
- clarity: would a stranger grasp the core insight from this frame at a glance? (insight: {research.get('insight') or 'see the request'})
- hook: does the first second stop the scroll?
- novelty: is it unlike what this studio made lately? (novelty_vs_memory is measured: 0 = a repeat, 1 = new) and unlike
  the topic's clichés ({json.dumps(research.get('cliches') or [], ensure_ascii=False)})
- feasibility: can the studio's code-drawn kit build the whole video at this quality? (a failed sketch scores low)
- fit: the creator's request, channel and audience.
Never prefer the safe one only because it is safe; never reward a pretty frame that explains nothing.
Request (data): <<<{row['prompt']}>>>
Studio memory (JSON, data): {json.dumps({k: mem.get(k) for k in ('overused', 'picked', 'passed', 'dislikes')}, ensure_ascii=False)}
Treatments (JSON): {json.dumps(listing, ensure_ascii=False)}
Reply with ONLY JSON in this schema:
{CRITIC_SCHEMA}"""
    data, meta = llm.ask(prompt, tools=("Read",), timeout=900, model=MODELS["critic"])
    return data if isinstance(data, dict) else {}, meta.get("cost_usd") or 0


# ---------- the orchestrator ----------
def run(con, plan_id, voices=None):
    """Run the team for one plan row; always ends with status ready (a fallback plan at worst)."""
    planner.ensure(con)
    row = planner.get(con, plan_id)
    att = row["attachments"]
    quick = bool(att.get("quick"))
    prog = Progress(con, plan_id, quick)
    cat = planner.catalogue(con, voices)
    team, cost = [], 0.0
    talk_kind = bool(att.get("talk"))

    prog.start("memory")
    mem = memory.brief(con, ("talk",) if talk_kind else ("topic",))
    prog.done("memory", memory.summary_tr(mem))

    research = None
    if not quick:
        prog.start("scout")
        try:
            research, c = scout(row, cat)
            cost += c
            prog.done("scout", research.get("insight") or "araştırma bitti", c)
        except Exception as e:
            prog.done("scout", f"araştırma yapılamadı ({type(e).__name__})", status="fail")

    prog.start("director")
    plan = planner.draft(con, row, cat, research, mem)
    cost += plan.get("cost_usd") or 0
    prog.done("director", f"{len(plan.get('treatments') or [])} yaklaşım" + (" · yedek plan" if plan.get("fallback") else ""),
              plan.get("cost_usd"), "fail" if plan.get("fallback") else "ok")
    if research:
        plan["research"] = research
    plan["memory"] = {k: mem.get(k) for k in ("overused", "unexplored", "picked", "passed", "made")}
    plan["memory_tr"] = memory.summary_tr(mem)
    tr = plan.get("treatments") or []
    if not tr:      # a plan without treatments still gets one, so the card and the critic stay uniform
        tr = plan["treatments"] = [{"label_tr": "Plan", "idea_tr": plan.get("understood_tr", ""), "techniques": plan.get("techniques") or [],
                                    "seconds": plan.get("seconds"), "look": plan.get("look") or "auto", "moment": ""}]
    for t in tr:
        t["novelty"] = memory.novelty(t.get("techniques"), mem)

    if not quick and plan["kind"] == "topic" and not plan.get("fallback"):
        prog.start("sketch")
        ok = 0
        with cf.ThreadPoolExecutor(max_workers=3) as ex:
            futs = {ex.submit(sketch, plan_id, i, plan, t, plan.get("aspect", "9:16")): i for i, t in enumerate(tr)}
            for f in cf.as_completed(futs):
                i = futs[f]
                try:
                    tr[i]["sketch"] = f.result()
                    cost += tr[i]["sketch"].get("cost_usd") or 0
                    ok += 1
                except Exception as e:
                    tr[i]["sketch"] = {"error": f"{type(e).__name__}: {e}"[:200]}
        prog.done("sketch", f"{ok}/{len(tr)} kare çizildi", status="ok" if ok else "fail")
        if ok:
            prog.start("critic")
            try:
                verdict, c = critic(row, plan, mem)
                cost += c
                for s in verdict.get("scores") or []:
                    i = s.get("i")
                    if isinstance(i, int) and 0 <= i < len(tr):
                        nums = [s.get(k) for k in ("clarity", "hook", "novelty", "feasibility", "fit")]
                        nums = [max(1, min(5, int(x))) for x in nums if isinstance(x, (int, float))]
                        tr[i]["score"] = {**{k: s.get(k) for k in ("clarity", "hook", "novelty", "feasibility", "fit")},
                                          "total": round(sum(nums) / max(1, len(nums)), 2), "why_tr": str(s.get("why_tr") or "")[:240],
                                          "fix": str(s.get("fix") or "")[:400]}
                rec = verdict.get("recommended")
                plan["recommended"] = rec if isinstance(rec, int) and 0 <= rec < len(tr) else \
                    max(range(len(tr)), key=lambda k: (tr[k].get("score") or {}).get("total", 0))
                plan["critic"] = {"summary_tr": str(verdict.get("summary_tr") or "")[:500]}
                prog.done("critic", plan["critic"]["summary_tr"][:160], c)
            except Exception as e:
                prog.done("critic", f"eleştirmen çalışamadı ({type(e).__name__})", status="fail")
    plan["chosen"] = plan.get("recommended") or 0
    plan["team"] = {"stages": prog.items, "cost_usd": round(cost, 2), "quick": quick}
    con.execute("UPDATE plans SET plan=?, status='ready' WHERE plan_id=?", (json.dumps(plan, ensure_ascii=False), plan_id))
    con.commit()
    rec = plan.get("recommended")
    if isinstance(rec, int) and rec:      # apply the critic's pick (the creator can switch on the card)
        planner.update(con, plan_id, {"treatment": rec}, voices)
    return planner.get(con, plan_id)["plan"]
