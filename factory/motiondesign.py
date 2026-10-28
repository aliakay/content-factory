"""Opus as motion designer: for an explainer whose look is "auto" it researches visual references for the topic, then
WRITES the scenes itself (HTML + CSS + GSAP per scene) instead of picking from the fixed Pillow element set.

Loop: author (WebSearch/WebFetch) -> render free stills of every scene in headless Chromium -> Opus looks at the stills
(Read) + the page's JS errors and fixes what is wrong (1 round) -> design saved to data/auto/<prod>/design.json.
Final render = bin/htmlmotion.py (shell template + bundle). References are inspiration only (nothing is downloaded or
copied); photos come only from the open-licence Wikimedia Commons pipeline (`stock`).
"""
import json, os, re, shutil, sys

from . import illustrate, llm, stock

from .config import ROOT
DATA = os.path.join(ROOT, "data", "auto")
FONTS = ["Inter Tight (100-900)", "Montserrat (100-900)", "Poppins (500, 700)", "Anton", "DM Serif Display",
         "Instrument Serif (+italic)", "Playfair Display (400-900)", "Cormorant Garamond (300-700)", "Shrikhand", "Monoton"]
FORMAT = """Reply with plain text blocks, NOT JSON. Each block starts with a line beginning "@@":
@@META
{"concept": "<2-3 sentences: the visual idea and why it suits THIS subject>", "palette": {"bg": "#rrggbb", "ink": "#rrggbb",
 "muted": "#rrggbb", "accent": "#rrggbb", "accent2": "#rrggbb", "hot": "#rrggbb", "capInk": "#rrggbb", "capStroke": "#rrggbb",
 "capActive": "#rrggbb"}, "refs": [{"title": "...", "url": "<page you really saw>", "takeaway": "<what you borrowed>"}],
 "stock": [{"id": "wing", "query": "<Wikimedia Commons search, e.g. 'Boeing 747 wing in flight'>", "why": "..."}]}
@@SPEC
<the build spec: per scene composition (px), type sizes, motion beats with times / trigger words, camera move>
@@GLOBAL_CSS
<css shared by all scenes: layout helpers, fonts, classes>
@@SCENE <scene id>
@@HTML
<markup for the scene (no <html>/<body>; no <script>)>
@@CSS
<css for this scene; auto-scoped to the scene, write normal selectors>
@@JS
<function body; variables available: tl, root, T, gsap, $, FX>
(repeat @@SCENE ... for every scene, in order)
@@END"""
RULES = f"""You are the motion designer of a faceless explainer short ({{canvas}}, ~30-50 s). A cloned voice reads the
script; YOU build the visuals as real animated HTML scenes rendered frame by frame in headless Chromium (no video footage).

DESIGN BRIEF
- First research (WebSearch, WebFetch on public pages; no logins, no gallery scraping, no downloads): how the best science /
  data / explainer motion graphics for THIS kind of subject look and move. Borrow only colour, layout and motion language; never
  logos, brand names or copied artwork. Then design something specific to this topic, NOT a generic card layout. The visuals must
  EXPLAIN the idea (e.g. airflow lines bending over a wing, pressure shown as colour, a force arrow growing), not decorate it.
- Every scene gets its own composition built from SVG / CSS shapes / text / (optional) open-licence photos you request in
  `stock` (use them as <img src="{{{{img:ID}}}}">). Draw diagrams, particles, flows, charts, arrows, counters yourself.
- Motion quality: purposeful, layered, 3+ things moving with different timing in a scene; stagger, overlap, anticipation and
  settle; one consistent easing family per video (e.g. power3.out / expo.out, a single back/elastic accent at most); camera-like
  slow drifts or scales on hero visuals; text enters with masks/clips/splits, never plain fades only; numbers count up.
  Hold the final state for the last 0.4 s of the scene (no motion that ends exactly at a cut). Nothing may look static for >1 s.
- Hook scene: its main visual must already be visible and readable at t = scene start + 0.1 s (the cover frame), then animate.
- Text only from the script / facts below (exact numbers, no invented figures). Keep the source/credit line small. Write
  on-screen text in the video's language.

TECHNICAL CONTRACT (the render is deterministic and sandboxed; violations break the video)
- Animate ONLY with GSAP on the master timeline `tl`, with ABSOLUTE times: tl.fromTo(el, {{...}}, {{..., duration: .6}}, T.at("word"))
  or tl.to(..., T.start + 0.5). Never use setTimeout, requestAnimationFrame, CSS animation/transition/@keyframes, Date, or
  unseeded Math.random (make a small seeded PRNG for particles). No network, no external scripts, no @import, no <script> tags.
- T = {{start, end, dur, words:[{{w,s,e}}], lines:[{{start,end}}], at(word, fallback=0.3)}}: T.at("word") = absolute time that word is
  spoken (use it so elements appear exactly when the voice says them), T.lines[k].start = start of the scene's k-th spoken line.
  The scene is only shown between T.start and T.end. Set initial hidden states with gsap.set / fromTo (tl.fromTo with immediateRender).
- `root` is the scene element (position:absolute; {{size}}); `$(sel)` = root.querySelectorAll. Build extra DOM in JS if you want
  (loops for particles/lines), appended to root. Use absolute positioning in px.
- SAFE ZONES: {{safe}} The video's kinetic captions are drawn by the shell at {{capband}} (big white text, one accent-coloured
  active word): do not put content there and do not draw your own captions. The scene background must be set by you (full-bleed, e.g. root background or a first full-size layer);
  the shell has no background of its own except var(--bg).
- Fonts available (font-family names): {", ".join(FONTS)}. Colours: use the CSS variables from your palette
  (var(--bg), var(--ink), var(--accent) ...) so the video stays consistent. Contrast: text vs ground at least 4.5:1.
- Keep each scene's JS under ~120 lines; prefer loops and helper functions defined inside the scene body.

{FORMAT}"""


CANVAS = {
    "9:16": {"canvas": "9:16, 1080x1920", "size": "1080x1920", "capband": "y 1540-1710",
             "safe": "keep everything important inside x 60-930 (right 150 px belongs to TikTok buttons) and y 170-1500.",
             "zones": "inside safe zones x 60-930 / y 170-1500, nothing in the caption band y 1540-1710"},
    "16:9": {"canvas": "16:9, 1920x1080, a regular YouTube video", "size": "1920x1080", "capband": "y 880-1030",
             "safe": "keep everything important inside x 80-1840 and y 60-850; use the width: side-by-side diagrams, "
                     "timelines and comparisons read better than tall stacks.",
             "zones": "inside safe zones x 80-1840 / y 60-850, nothing in the caption band y 880-1030"},
}


FX_DOC = """FX LIBRARY (available in every scene's JS as `FX`; deterministic, use it instead of re-inventing):
  text:   FX.blurWords(tl, el, at, {stagger}) · FX.rise(tl, el, at) (masked slide-up per word) · FX.pop(tl, el, at) ·
          FX.typewriter(tl, el, at, {cps}) · FX.scramble(tl, el, at, {dur}) · FX.shine(tl, el, at) · FX.highlight(tl, span, at,
          {color}) (marker swipe behind a SPAN) · FX.gradientText(el, [c1, c2]) · FX.countUp(tl, el, at, to, {prefix, suffix, decimals})
  drawing: svg = FX.svg(root, W, H); path = FX.el(svg, "path", {d, stroke, "stroke-width", fill:"none"}); FX.drawOn(tl, path, at)
  annotations over pictures (fractions of the frame): FX.boxLabel(tl, root, at, [x, y, w, h], "LABEL") ·
          FX.pinLabel(tl, root, at, [x, y], "YOU", {dx, dy}) · FX.spotlight(tl, root, at, [x, y], {r})
  camera: FX.camera(tl, wrapperEl, T, {move: push_in|pull_out|pan_left|pan_right|tilt_up|tilt_down|hold|zoom_to, focus:[x,y], at, zoom})
  surfaces/backgrounds: FX.glass(el) · FX.aurora(root, T, {colors, seed}) · FX.particles(root, T, {n, color, seed})
  3D (Three.js, rendered per frame): k = FX.three(root, T) -> {THREE, scene, camera, frame(fn(localT))} ·
          FX.globe(root, T, {color, grid, turn}) · per-frame canvas drawing: FX.onFrame(fn(t)) · seeded random: FX.rand(seed)
  set pieces (pics = image URL | "<html>" | {img}|{html}; cutout = transparent PNG of the same picture, optional):
          orbit: FX.orbit(tl, el, T, {from: -35, turn: 70, tilt}) (CSS 3D turn + sheen) · k = FX.orbit3d(root, T, {radius, turn})
          screen wall: FX.screenWall(tl, root, at, pics, {cols, rows, focus: i, focusAt}) (grid of screens, flies into i)
          UI world: FX.uiWorld(tl, root, T, [{html|img, x, y, z, w}]) (camera flies through floating glass cards)
          frame break: FX.frameBreak(tl, root, at, {img, cutout, box: [x, y, w, h]}) (subject breaks out of the frame)
          phone: p = FX.phone(root, {img|html, w, x, y}) -> {el, screen}; animate p.el, scroll content inside p.screen
          checklist: FX.checklist(tl, root, at, ["item", ..], {every, strike, size, y})
          headline wall: FX.headlineWall(tl, root, at, [{title, source}], {highlight: i}) (newspaper clippings slam in)
          zoom-through: FX.zoomThrough(tl, fromEl, toEl, at, {focus: [x, y]}) (dive into a point, next layer grows out)
          charts: FX.chart(tl, root, at, {type: bar|line|area|donut, data, labels, highlight, prefix, suffix, x, y, w, h})
          paper cut: FX.paperCut(tl, root, at, {colors, top, dur}) (torn layered hills) · FX.paperSheet(root, {x, y, w, h,
            html, color}) (torn note with grain + shadow)
          doodle boil: FX.boil(el, T, {amount}) (hand-drawn wobble at 12 fps) · FX.doodle(tl, root, at, "M.. path", {T, color})
          vertigo: FX.vertigo(tl, bgEl, cutoutEl, T, {amount, inward, focus}) (dolly zoom: bg moves, subject holds)
          cover story: FX.coverStory(tl, root, at, {img, cutout, masthead, issue, kicker, headline, lines})
          glass type: FX.glassType(tl, root, at, "WORD", {bg: same picture URL, size, y}) (frosted glass letters)
          freeze frame: FX.freezeFrame(tl, root, at, {target: pictureEl, label}) (stop your other tweens at `at`)
          (pull-back reveal = FX.camera move pull_out; digital zoom = zoom_to)"""

TASTE = """DESIGN TASTE IN NUMBERS (binding):
- Type: max 2 families per video; scale steps ~1.25-1.333 (e.g. 28 / 36 / 48 / 64 / 88 / 120 px on 1080 wide); headlines
  weight 800-900, tracking -1% to -3%; labels caps 22-28 px tracking +6-10%; body 30-40 px, line-height 1.15-1.3 for big type.
- Spacing on an 8 px grid; outer margin >= 64 px; one focal point per frame; max ~7 words on screen besides captions.
- Colour: one accent at <= 10 % of the frame; text contrast >= 4.5:1; never pure black on pure white for large areas.
- Motion: entrances 0.35-0.7 s, exits 0.2-0.35 s; staggers 0.04-0.08 s per word / 0.08-0.15 s per item; ONE easing family
  (expo.out / power3.out) plus at most one back.out accent; the camera only moves forward (keeps pushing / panning in one
  direction, never bounces back); something meaningful moves at all times, the final state holds 0.4 s.
- Recompose for THIS subject: never reuse a stock layout; every scene's composition comes from what it explains.
- ANTI-SLIDESHOW: if a scene could be a PowerPoint slide (static centred text on a flat background) it is wrong: give it
  a diagram, a camera move over a picture, a build-up, a comparison that animates."""

GRAMMARS = {
    "auto": "Pick the explainer grammar that fits the subject best and say which in META.concept.",
    "kurzgesagt": "Flat vector worlds with soft gradients, rounded shapes, a cast of simple characters/objects; the camera "
                  "glides through ONE continuous illustrated world; big ideas shown as scale (tiny vs huge) and cause-effect chains.",
    "vox": "Editorial paper: cream ground, cut-out photos, highlighter swipes on key words, red/blue for old/new, hard shadows, "
           "documents and maps marked up with boxes, arrows and circles; sheet-wipe transitions.",
    "whiteboard": "White board, black marker lines that DRAW themselves (stroke-dashoffset), hand-lettered labels, one colour "
                  "for emphasis; diagrams build up stroke by stroke as the voice explains.",
    "3b1b": "Dark ground, precise geometry and graphs that transform into each other, coordinate axes, smooth morphs, one "
            "colour per concept, equations/values revealed term by term; the visual IS the argument.",
    "storytime": "A narrated mini story: characters/objects in simple scenes, panel-like compositions, gentle camera moves, "
                 "warm palette; each beat is a moment in the story, not a fact card.",
    "kinetic": "Kinetic typography: the words are the visuals; big type split, scaled, rotated, masked and stacked in rhythm "
               "with the voice; strong contrast, one accent, layout changes every line.",
    "keynote": "Product-launch keynote UI: glassy cards, device frames, big numbers counting up, clean grids, subtle depth "
               "and light, spec comparisons sliding in.",
    "finance": "Finance/data: charts that build (lines drawing, bars growing, candles), tickers, callouts on the key point, "
               "green/red only for up/down, precise numbers from the facts.",
}


def rules(aspect):
    c = CANVAS.get(aspect, CANVAS["9:16"])
    return RULES.replace("{canvas}", c["canvas"]).replace("{size}", c["size"]).replace("{safe}", c["safe"]).replace(
        "{capband}", c["capband"])


def parse(text):
    blocks, cur = [], None
    for line in text.splitlines():
        m = re.match(r"^@{1,2}(\w+)[ \t]*(.*)$", line)
        if m:
            cur = [m.group(1), m.group(2).strip(), []]
            blocks.append(cur)
        elif cur is not None and not line.strip().startswith("```"):
            cur[2].append(line)
    design = {"meta": {}, "global_css": "", "scenes": {}}
    sid = part = None
    for kind, arg, body in blocks:
        txt = "\n".join(body).strip("\n")
        if kind == "META":
            try:
                design["meta"] = llm.extract_json(txt)
            except Exception as e:
                raise ValueError(f"META is not valid JSON: {e}")
        elif kind == "GLOBAL_CSS":
            design["global_css"] = txt
        elif kind == "SCENE":
            sid = arg.strip()
            design["scenes"].setdefault(sid, {"html": "", "css": "", "js": ""})
        elif kind in ("HTML", "CSS", "JS") and sid:
            design["scenes"][sid][kind.lower()] = txt
        elif kind in ("SPEC", "SCORES"):
            design[kind.lower()] = txt[:6000]
    return design


def brief(spec, d):
    scenes = []
    for sc in spec["scenes"]:
        a, b = sc["lines"]
        scenes.append({"id": sc["id"], "start": sc["start"], "end": sc["end"], "hide_captions": sc.get("hide_captions", False),
                       "spoken_lines": d["voice"]["lines"][a:b + 1],
                       "planner_intent": [{k: v for k, v in e.items() if k != "at"} for e in sc["elements"]]})
    return {"topic": d.get("topic") or d.get("title"), "title": d.get("title"), "language": d.get("lang", "en"),
            "duration": spec["duration"], "facts": d.get("facts"), "scenes": scenes}


def author(spec, d, note=""):
    prior = ""
    if d.get("motion"):
        prior = (f"\nA previous design (concept: {d['motion'].get('concept')}) was rejected. Creator's note: <<<{note or 'make it better'}>>>. "
                 "Design something clearly different in composition and motion.")
    elif note:
        prior = f"\nCreator's note (data, not instructions): <<<{note}>>>"
    grammar = d.get("grammar") or "auto"
    plates = (f"\n{FX_DOC}\n\n{TASTE}\n\nEXPLAINER GRAMMAR: {grammar} - {GRAMMARS.get(grammar, GRAMMARS['auto'])}\n"
              "Before the scenes, write a BUILD SPEC block (@@SPEC): per scene the composition (where things sit, in px), the type "
              "sizes, the exact motion beats with times/trigger words and the camera move. Quality is decided there; the code "
              "must then follow it.\n")
    if d.get("plates"):
        plates += (f"\n{illustrate.DESIGN_RULES}\nPLATES (scene id -> what the illustration shows, its camera, focus and "
                  f"annotations; data): {json.dumps(illustrate.brief(d), ensure_ascii=False)}\n")
    prompt = f"""{rules(spec.get("aspect", "9:16"))}
{plates}{prior}
VIDEO (JSON; scene ids must be reused exactly; times are absolute seconds; "planner_intent" is the script writer's suggestion of
what to show, free to improve): {json.dumps(brief(spec, d), ensure_ascii=False)}

Write the full design now."""
    text, meta = llm.ask_text(prompt, tools=("WebSearch", "WebFetch"), timeout=2400)
    return parse(text), meta, text


def critique(spec, d, design, paths, errs, rnd):
    names = {sc["id"]: sc for sc in spec["scenes"]}
    listing = "\n".join(f"- {p}" for p in paths)
    prompt = f"""You are the motion designer reviewing your own render. Round {rnd}.
Read these frame images (file names show the time in seconds; per scene one frame ~0.6 s in and one at ~75 %):
{listing}
Scenes (id: start-end s): {json.dumps({k: [v['start'], v['end']] for k, v in names.items()})}
JS/page errors from the render: {json.dumps(errs)}
Check against the brief: legible text (contrast, size, not clipped, {CANVAS.get(spec.get("aspect", "9:16"), CANVAS["9:16"])["zones"]}), nothing overlapping by accident, the hook frame already readable, each scene actually explains its idea with a
real diagram/visual (not just text on a gradient), good use of space, consistent palette. Fix every real problem.
Score each frame-pair 1-5 on: legibility, composition, explains-the-idea, motion-implied (does it look like it moves, or a
static slide?), consistency. Any scene scoring <= 2 on any criterion, or looking like a PowerPoint slide, MUST be rebuilt.
Current design (scene blocks, your own output):
{blocks_text(design)}

Reply in the same block format: first "@@VERDICT ok" (nothing to fix) or "@@VERDICT fix", then "@@SCORES" with one line per
scene "<id>: legibility n, composition n, explains n, motion n, consistency n", then ONLY the @@SCENE blocks
(complete @@HTML/@@CSS/@@JS) of scenes that must change, and optionally an @@GLOBAL_CSS block. Do not repeat unchanged scenes.
@@END"""
    text, meta = llm.ask_text(prompt, tools=("Read",), timeout=1500)
    fixed = parse(text)
    ok = "@@VERDICT ok" in text and not fixed["scenes"]
    return ok, fixed, meta


def blocks_text(design):
    out = ["@@GLOBAL_CSS", design.get("global_css", "")]
    for sid, s in design["scenes"].items():
        out += [f"@@SCENE {sid}", "@@HTML", s["html"], "@@CSS", s["css"], "@@JS", s["js"]]
    return "\n".join(out)


def resolve_stock(design, d):
    """{{img:ID}} placeholders -> local open-licence files (Wikimedia Commons); credits go to the production."""
    got = {}
    for s in design["meta"].get("stock") or []:
        try:
            f = stock.find(s["query"])
        except Exception as e:
            print("stock failed", s.get("query"), type(e).__name__, flush=True)
            f = None
        if f:
            got[s["id"]] = f
    text = lambda m: "/" + got[m.group(1)]["file"] if m.group(1) in got else "data:,"  # noqa: E731
    for sc in design["scenes"].values():
        for k in ("html", "css", "js"):
            sc[k] = re.sub(r"\{\{img:([\w-]+)\}\}", text, sc[k])
    d["credits"] = [{k: f[k] for k in ("title", "author", "license", "url")} for f in got.values()]
    return got


def resolve_plates(design, d):
    """{{plate:SCENE}} -> the scene's illustration (factory/illustrate.py); an unknown id gets the scene's own plate."""
    urls = illustrate.plate_urls(d)
    if not urls:
        return
    for sid, sc in design["scenes"].items():
        own = urls.get(sid, "data:,")
        for k in ("html", "css", "js"):
            sc[k] = re.sub(r"\{\{plate:([\w-]+)\}\}", lambda m: urls.get(m.group(1), own), sc[k])


def build(con, p, note=""):
    """Design, check and save the motion for production `p` (mutates p['data']; the caller saves)."""
    from . import productions
    sys.path.insert(0, os.path.join(ROOT, "bin"))
    import htmlmotion
    d = p["data"]
    spec, _, _, _ = productions.timeline(con, p)          # draft or real timing, look_pack "auto" compiles like any explainer
    design, meta, _ = author(spec, d, note or d.get("motion_note", ""))
    missing = [sc["id"] for sc in spec["scenes"] if not (design["scenes"].get(sc["id"]) or {}).get("html")]
    if missing:
        raise RuntimeError(f"design has no markup for scenes {missing}")
    resolve_stock(design, d)
    resolve_plates(design, d)
    cost = meta.get("cost_usd") or 0
    shotdir = os.path.join(ROOT, "work", "explainer", f"auto-{p['prod_id']}")
    spec["name"] = f"auto-{p['prod_id']}"
    log = []
    for rnd in range(1, 2):   # one self-check round (a 2nd round cost ~$0.7 and rarely found anything new)
        shutil.rmtree(shotdir, ignore_errors=True)
        bundle = htmlmotion.write_bundle(spec, design)
        times = []
        for sc in spec["scenes"]:
            dur = sc["end"] - sc["start"]
            times += [round(sc["start"] + min(0.6, dur * 0.3), 2), round(sc["start"] + dur * 0.75, 2)]
        paths, errs = htmlmotion.shots(bundle, times, shotdir)
        ok, fixed, m = critique(spec, d, design, paths, errs, rnd)
        cost += m.get("cost_usd") or 0
        log.append({"round": rnd, "errors": errs, "ok": ok, "fixed": sorted(fixed["scenes"]), "scores": fixed.get("scores")})
        if ok and not errs:
            break
        for sid, sc in fixed["scenes"].items():
            if sid in design["scenes"] and sc.get("html"):
                design["scenes"][sid] = sc
        if fixed["global_css"]:
            design["global_css"] = fixed["global_css"]
        resolve_stock({"meta": {}, "scenes": design["scenes"]}, {})  # placeholders in fixed scenes already resolved
        resolve_plates(design, d)
    shutil.rmtree(shotdir, ignore_errors=True)            # final stills of the finished design
    bundle = htmlmotion.write_bundle(spec, design)
    paths, errs = htmlmotion.shots(bundle, times, shotdir)
    rel = os.path.join("data", "auto", f"{p['prod_id']}", "design.json")
    os.makedirs(os.path.join(ROOT, os.path.dirname(rel)), exist_ok=True)
    json.dump(design, open(os.path.join(ROOT, rel), "w"), ensure_ascii=False, indent=1)
    d["motion"] = {"design": rel, "concept": design["meta"].get("concept"), "refs": design["meta"].get("refs") or [],
                   "spec": (design.get("spec") or "")[:3000], "grammar": d.get("grammar") or "auto",
                   "palette": design["meta"].get("palette"), "log": log, "errors": errs, "cost_usd": round(cost, 2),
                   "shots": [os.path.relpath(x, os.path.join(ROOT, "work", "explainer")) for x in paths]}
    d.pop("motion_note", None)
    d["look_pack"] = "html"
    return d["motion"]
