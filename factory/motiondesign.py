"""Opus as motion designer: for an explainer whose look is "auto" it researches visual references for the topic, then
WRITES the scenes itself (HTML + CSS + GSAP per scene) instead of picking from the fixed Pillow element set.

Loop: author (WebSearch/WebFetch) -> render free stills of every scene in headless Chromium -> Opus looks at the stills
(Read) + the page's JS errors and fixes what is wrong (1 round) -> design saved to data/auto/<prod>/design.json.
Final render = bin/htmlmotion.py (shell template + bundle). References are inspiration only (nothing is downloaded or
copied); photos come only from the open-licence Wikimedia Commons pipeline (`stock`).
"""
import json, os, re, shutil, sys

from . import capabilities, illustrate, layoutlint, llm, sheets, stock

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
          phone: p = FX.phone(root, {img|html, w, x (centre), y}) -> {el, screen}; animate p.el, scroll content inside p.screen
          checklist: FX.checklist(tl, root, at, ["item", ..], {every, strike, size, y})
          headline wall: FX.headlineWall(tl, root, at, [{title, source}], {highlight: i}) (newspaper clippings slam in)
          zoom-through: FX.zoomThrough(tl, fromEl, toEl, at, {focus: [x, y]}) (dive into a point, next layer grows out)
          charts: FX.chart(tl, root, at, {type: bar|line|area|donut, data, labels, highlight, prefix, suffix, x, y, w, h})
          paper cut: FX.paperCut(tl, root, at, {colors, top, dur}) (torn layered hills) · FX.paperSheet(root, {x, y, w, h,
            html, color}) (torn note with grain + shadow)
          doodle boil: FX.boil(el, T, {amount}) or FX.boil(root, {px, targets}) (hand-drawn wobble at 12 fps) · FX.doodle(tl, root, at, "M.. path", {T, color})
          vertigo: FX.vertigo(tl, bgEl, cutoutEl, T, {amount, inward, focus}) (dolly zoom: bg moves, subject holds)
          cover story: FX.coverStory(tl, root, at, {img, cutout, masthead, issue, kicker, headline, lines})
          glass type: FX.glassType(tl, root, at, "WORD", {bg: same picture URL, size, y}) (frosted glass letters)
          freeze frame: FX.freezeFrame(tl, root, at, {target: pictureEl, label}) (stop your other tweens at `at`)
          (pull-back reveal = FX.camera move pull_out; digital zoom = zoom_to)

  characters (code-drawn, round-headed stickmen; YOU draw every person/prop, no images needed):
          man = FX.stickman(root, {x, y (feet), h, color, head, ink, face, pose, prop: "<svg markup in the right hand>"}) ·
          FX.pose(tl, man, "stand|wave|point|scared|shrug|knock|hold|crouch|cheer|sad|run", at, {dur}) · man.walk(at, dur, dx) ·
          FX.wave(tl, man, at, dur) · man.mouth("smile|grin|flat|o|frown") · FX.shake(tl, el, at, {amp, dur})
          kid = FX.character(root, {x, y (feet), h, skin, hair, style: pigtails|bob|short|bald, hat: colour|false, shirt,
          pants, shoes, stripes, bow: colour|false, prop}) = an ILLUSTRATED character with a live face (eye whites +
          sliding pupils, lids, happy-squint cheek, a mouth that opens); same poses / FX.act / FX.alive as the stickman.
          Use it when the film needs a lead people care about (a mascot, a kid, a customer); the stickman for diagrams
          and crowds. species: "dog"|"cat"|"budgie" = an upright cartoon animal on the same rig (skin = fur / feathers;
          dog {belly, ear, nose, collar}, cat {belly, ear, nose, stripe, whisker}, budgie {belly, face, bars, cheek, beak,
          cere, tail, feet}; blue budgie: skin #6fb6e8, belly #9fd0f2, face #f4f4f4, tail #2f4fa8; hen cere #c9a27a):
          its tail sways by itself (a dog wags harder on cheek), ears drag / twitch, budgie wings are the arms (wave
          = a wing wave) and its beak opens for talk.
  life (drawn things that feel alive; seconds of the render clock; see ALIVE in the doctrine):
          FX.alive(man, {look: [[t, gx, gy], ...] (-1..1), lid, amount, cheek: [[t, 0..1]], talk: [[from, to]]}) gliding
          gaze + blinks + breathing + moving holds (+ happy squint and talking mouth on FX.character) ·
          FX.act(man, [[t, "pose" | {sR: -90, ...}], ...]) a pose chain that FLOWS (use instead of several FX.pose; FX.wave
          rides on it) · FX.land(man, at, {from}) · FX.hop(man, at, {h}) · FX.float(el | man, {at, out, shadow: el})
          idle loops on any element / SVG group, pivot = CSS origin or [x, y] drawing units: FX.sway(el | [root..tip],
          {deg, period, pivot}) · FX.breathe(el) · FX.bob(el) · FX.flicker(flame, {inner}) · FX.glow(el) · FX.spin(el,
          {period}) · FX.drift(el, {period, span}) · FX.steam(root, {x, y}) · FX.ripples(root, {x, y, r}) ·
          FX.weather(root, {kind: rain|snow|leaves|stars, n}) · FX.buzz(el, at, {bursts}) · FX.jiggle(el, {from, to})
          math: FX.life.wave / loop / bell / seg / seeded / track (one move) / flow (through poses) / EASE_IO / EASE_OUT
  kinetic (type on the beat; FX.B(k) = beat k of the music, beat 0 = the drop; see KINETIC in the doctrine):
          FX.kinetic(tl, root, at, {style: slam|punch3d|stack|split|pair|cut, text: "WORD" | [a, b], until, ground, color,
          y, fx: punch|hit|beat|none, big}) (fits the frame width, keeps moving after it lands) · FX.ground(tl, root, at,
          colour) · FX.hitFx(tl, root, at, {rays, ring, flash, shake}) · FX.charge(tl, root, at, dur) · FX.cutRun(tl,
          root, at, ["NO", "TIMELINE", ...]) (accelerating cuts + flash) · FX.tvOff(tl, el, at) · FX.zoomLetter(tl,
          wrapEl, letterSpan, at) (fly through a letter's hole) · FX.typePrompt(tl, root, at, {label, text: [["plain "],
          ["keyword", 1]]}) -> {enter} (the push into Enter floods the accent: the drop) · FX.picture(tl, root, at, dur,
          {src, words: [[t, "TEXT", colour]], focus, tint, cutIns: [[t, scale, [x, y], dur]], weather: rain|snow|dust})
  story kit: FX.hud(root, {label: "NIGHT 1", place, times: [[t, "2:17 AM"], ...]}) (top-left clock that jumps forward) ·
          FX.rule(tl, root, at, n, "KILL THE\nBIG LIGHTS", {y}) (red RULE #N tag + condensed headline) ·
          FX.choice(tl, root, at, {q, a, b, sub}) (end question + two answer buttons + "comment below") ·
          FX.flipCard(tl, root, at, "NIGHT 1", "NIGHT 2", {y}) · d = FX.lightsOut(tl, root, at, {keep}) (flicker, dark, cuts the
          music) · FX.lightsOn(tl, d, at, {music: true}) · FX.slash(tl, root, at, [x1, y1, x2, y2]) · FX.shatter(tl, el, at)
  devices / UI (ads, alerts): FX.phone above (build the app inside ph.screen) ·
          FX.alert(tl, ph, at, {app, title, body}) · FX.tap(tl, root, at, [x, y]) (finger tap ripple + click)
  SOUND (every visible action gets ONE sound, declared next to its tween): FX.sfx(kind, at, {db}) with kind =
          {sfx_kinds}. FX.music("cut", at) / FX.music("back", at) cut the music out and in on story events;
          FX.music("drop", at) = where the track's drop must land (the key line / reveal). The kit helpers above already
          add their own sound (rule: hit, lightsOut: clunk + music cut, choice: clicks, flipCard: flip, tap: click, alert:
          notify, slash: swish, shatter: glass); pass {sfx: false} to silence one."""

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

MOTION_DOCTRINE = """MOTION DOCTRINE (character-animation and motion-design craft, binding):
- Emotion -> motion: joy = bouncy arcs, ease-out-back 0.2-0.4 s · calm = sine in-out 0.5-1 s · urgency = sharp straight
  ease-out 0.1-0.2 s · sadness = slow, downward 0.6-1.2 s · surprise / impact = radial burst, expo.out 0.15-0.3 s ·
  confidence = direct horizontal ease-out 0.2-0.4 s · elegance = long arcs (0.4,0,0.2,1) 0.4-0.7 s. Decide the emotion
  of each scene BEFORE its properties.
- Durations: micro 80-120 ms · tap / toggle 120-180 · card 200-350 · panel 300-400 · scene change 400-600 · dramatic
  reveal 0.6-1.2 s; exits are 65-75 % of their entrance; distance scales the time (full screen ~1.8x of 100 px).
- Disney principles in code: anticipation (a 10-20 % move the other way, 0.1-0.2 s) before big moves; squash / stretch
  on impacts (keep the volume); follow-through: children 50-150 ms behind their parent, trailing parts stop 100-200 ms
  later; arcs (10-20 px off the straight line); secondary action at 30-50 % of the primary, 50-100 ms later; staging:
  dim what is not the hero; one primary action per beat. NEVER linear easing on spatial moves (only rotation, progress,
  timers). Overshoot budget: feedback 2-5 %, success 5-10 %, celebration 15-25 %, error / premium 0 %.
- The 1/3 rules: nothing travels more than a third of the frame without a direction or speed change; with 3+ moving
  elements at most a third are active at once (element 1 settles as element 3 starts). Total stagger under 0.5 s.
- Sequence: setup 20-30 % -> action 30-40 % -> resolution 30-40 %, then 0.1-0.2 s of stillness before new motion.
- BANNED defaults (they read as generated): breathing / floating / pulsing loops standing in for motion on titles and
  UI; titles that keep sliding or scaling after they land; a slow creeping scale late in a scene; bounce on UI; click
  rings; every scene entering the same way; everything fading and sliding up; three cards in a row; a dark void with
  small floating things and glow; a logo docked small in a corner. A character's idle breathing and overshoot are acting
  and are fine.
- ALIVE (drawn characters, creatures and sets; method after rossark-motion-skill): never teleport (everything
  interpolates; a face never swaps drawings without a squint or blink to hide it) · never a frozen frame while a
  character is on screen (FX.alive: breathing, drifting limbs, a blink every 3-4 s; close 0.11 s, reopen 0.19 s) · poses
  flow (FX.act), they never stop dead at each key · parts turn around their real pivots and the outer parts follow a
  beat later (0.06-0.15 s at 0.3-0.6 strength) · left and right never mirror · the eyes lead, the head follows, the body
  last; blink on a head turn · small amplitudes (breath 1-2 %, sway 1.5-4°, head tilt 3-6°) · landings squash 15-20 %
  and keep the volume; anything in the air hangs its feet and its shadow shrinks with the height · props enter from
  off frame already moving and the eyes follow them · one main action per scene + 2-3 idle loops, out of phase, seeded,
  never on titles / UI · every move gets enough frames (nothing under ~0.1 s except a cut).
- KINETIC (when the film is type on the beat; method after the scenario-kinetic-film skill): one idea per beat or
  half beat, one or two words filling the frame width (split a phrase rather than shrink a word); one new thing per
  beat (a word, a colour, a cut, a hit: two at once cancel out); flip the ground on phrase changes; runs of cuts
  accelerate (1, 1, 1, ½, ½, ¼ beat, then a flash); transitions are moves (whips alternating horizontal / vertical, a
  zoom through a letter's counter, a collapse to a point, a TV switch-off), fades only on the end card's small lines;
  outlined words for what is not yet true, filled when it is; rays and rings only on the biggest hits; NEVER PARK: the
  camera always drifts and a landed word keeps scaling 2-5 %/s (a draft render is measured: <= 40 % still frames, no
  hold over 0.6 s before the end card). Here the breathing / scaling of landed type is the craft, not a banned default.
- Every seam has a transition with a cause (3-5 kinds per film, at most a third hard cuts); every on-screen line
  holds ~0.3 s a word + 0.5 s; something meaningful changes at least every 3 s."""

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


def fx_doc():
    from . import sfx
    return FX_DOC.replace("{sfx_kinds}", " | ".join(f"{k} ({v})" for k, v in sfx.KINDS.items()))


SOUND_RULES = """SOUND DESIGN (you are also the sound designer; the mix is automatic from your cues):
- One sound for every visible action (a light clunking off, knuckles on glass, a sign flipping, a tap, a card landing),
  timed to the frame of the action. No random whooshes: a sound must match something you see. Silence is a tool: let a
  quiet beat breathe before the scare / reveal; cut the music (FX.music("cut")) when the story says so (the power dies).
- Effects never cover a word (the mix pulls them under speech); keep them sparse inside sentences, put the big ones
  (impact, glass, clunk) in the gaps between lines. 6-20 cues for 30 s, up to ~40 for 90 s."""


def rules(aspect, captions=None):
    c = dict(CANVAS.get(aspect, CANVAS["9:16"]))
    if (captions or {}).get("pos") == "mid":     # story captions sit in the middle of the frame, one word at a time
        c["capband"] = "y 1080-1300 (one big word at a time, in the middle of the frame)" if aspect != "16:9" else "y 640-800"
    out = RULES.replace("{canvas}", c["canvas"]).replace("{size}", c["size"]).replace("{safe}", c["safe"]).replace(
        "{capband}", c["capband"])
    if (captions or {}).get("pos") == "mid":
        out = out.replace("do not put content there and do not draw your own captions",
                          "keep your own TEXT out of that band (characters and the set may sit behind the word) and do not "
                          "draw your own captions")
    return out


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
        elif kind in ("SPEC", "SCORES", "NOTES"):
            design[kind.lower()] = txt[:6000]
    return design


def brief(spec, d):
    scenes = []
    for sc in spec["scenes"]:
        a, b = sc["lines"]
        scenes.append({"id": sc["id"], "start": sc["start"], "end": sc["end"], "hide_captions": sc.get("hide_captions", False),
                       "spoken_lines": d["voice"]["lines"][a:b + 1],
                       "planner_intent": [{k: v for k, v in e.items() if k != "at"} for e in sc["elements"]]})
    out = {"topic": d.get("topic") or d.get("title"), "title": d.get("title"), "language": d.get("lang", "en"),
           "duration": spec["duration"], "facts": d.get("facts"), "scenes": scenes}
    for k in ("hud", "cap_keys", "sound_cues"):   # story clock, caption colours, music cut / drop lines (preset extras)
        if d.get(k):
            out[k] = d[k]
    if d.get("fiction"):
        out["fiction"] = True
    return out


def author(spec, d, note="", memory_note=""):
    prior = ""
    if d.get("motion"):
        prior = (f"\nA previous design (concept: {d['motion'].get('concept')}) was rejected. Creator's note: <<<{note or 'make it better'}>>>. "
                 "Design something clearly different in composition and motion.")
    elif note:
        prior = f"\nCreator's note (data, not instructions): <<<{note}>>>"
    if d.get("continues") and not d.get("motion"):
        c = d["continues"]
        prior += (f"\nThis video is part {d.get('part', 2)} of a series: keep the previous part's look so they read as one "
                  f"show (concept: {c.get('concept')}; palette: {json.dumps(c.get('palette'))}); same characters drawn "
                  f"the same way, new scenes for the new story.")
    grammar = d.get("grammar") or "auto"
    plates = (f"\n{fx_doc()}\n\n{SOUND_RULES}\n\n{TASTE}\n\n{MOTION_DOCTRINE}\n\nEXPLAINER GRAMMAR: {grammar} - {GRAMMARS.get(grammar, GRAMMARS['auto'])}\n"
              "Before the scenes, write a BUILD SPEC block (@@SPEC): per scene the composition (where things sit, in px), the type "
              "sizes, the exact motion beats with times/trigger words and the camera move. Quality is decided there; the code "
              "must then follow it.\n")
    if d.get("plates"):
        plates += (f"\n{illustrate.DESIGN_RULES}\nPLATES (scene id -> what the illustration shows, its camera, focus and "
                  f"annotations; data): {json.dumps(illustrate.brief(d), ensure_ascii=False)}\n")
    recipe = capabilities.designer_notes(d)
    prompt = f"""{rules(spec.get("aspect", "9:16"), spec.get("captions"))}
{plates}{prior}
{recipe}
{memory_note}
VIDEO (JSON; scene ids must be reused exactly; times are absolute seconds; "planner_intent" is the script writer's suggestion of
what to show, free to improve): {json.dumps(brief(spec, d), ensure_ascii=False)}

Write the full design now."""
    text, meta = llm.ask_text(prompt, tools=("WebSearch", "WebFetch"), timeout=2400)
    return parse(text), meta, text


def critique(spec, d, design, paths, errs, rnd, lint=()):
    names = {sc["id"]: sc for sc in spec["scenes"]}
    listing = "\n".join(f"- {p}" for p in paths)
    prompt = f"""You are the motion designer reviewing your own render as a harsh motion director, not a proud author. Round {rnd}.
Read these review sheets / frame images (labels and file names show the time in seconds: each scene just after it starts
and at its middle, a strip across every cut, and a phone-width sheet to judge what is readable at 360 px):
{listing}
First describe each scene's frame in ONE sentence as a stranger would, naming every object: an object you would have to
explain is a problem. Then check that the frames, with the words covered, still tell the story, and name every banned
default (MOTION DOCTRINE) you see.
Scenes (id: start-end s): {json.dumps({k: [v['start'], v['end']] for k, v in names.items()})}
JS/page errors from the render: {json.dumps(errs)}
Automatic layout check (measured on these frames; fix every one unless it is clearly intended, e.g. a mask reveal):
{json.dumps(list(lint), ensure_ascii=False)}
Check against the brief: legible text (contrast, size, not clipped, {CANVAS.get(spec.get("aspect", "9:16"), CANVAS["9:16"])["zones"]}), nothing overlapping by accident, the hook frame already readable, each scene actually explains its idea with a
real diagram/visual (not just text on a gradient), good use of space, consistent palette. Fix every real problem.
Score each frame-pair 1-5 on: legibility, composition, explains-the-idea, motion-implied (does it look like it moves, or a
static slide?), consistency. Any scene scoring <= 2 on any criterion, or looking like a PowerPoint slide, MUST be rebuilt.
Current design (scene blocks, your own output):
{blocks_text(design)}

Reply in the same block format: first "@@VERDICT ok" (nothing to fix) or "@@VERDICT fix", then "@@SCORES" with one line per
scene "<id>: legibility n, composition n, explains n, motion n, consistency n", then "@@NOTES" with one line per problem
"P0|P1|P2 · t=4.2s · where · problem -> exact change · what stays" (P0 breaks the read, P1 weakens the film, P2 polish;
fix every P0 and the P1s worth it), then ONLY the @@SCENE blocks
(complete @@HTML/@@CSS/@@JS) of scenes that must change, and optionally an @@GLOBAL_CSS block. Do not repeat unchanged scenes.
@@END"""
    text, meta = llm.ask_text(prompt, tools=("Read",), timeout=1500)
    fixed = parse(text)
    ok = "@@VERDICT ok" in text and not fixed["scenes"]
    return ok, fixed, meta


def review_sheets(paths, times, labels, outdir):
    """The stills as 2 sheets (all review frames + the same at phone width) instead of dozens of separate images."""
    at = sheets.by_time(paths)
    ordered = [at.get(round(t, 2)) for t in times]
    keep = [(p, lab) for p, lab in zip(ordered, labels) if p]
    if not keep:
        return paths
    full = sheets.tile([p for p, _ in keep], os.path.join(outdir, "sheet_review.png"), cols=6, width=300,
                       labels=[lab for _, lab in keep], title="review: scene start / middle + strips across every cut")
    phone = sheets.tile([p for p, lab in keep if not lab.startswith("cut")], os.path.join(outdir, "sheet_phone.png"),
                        cols=6, width=180, labels=[lab for _, lab in keep if not lab.startswith("cut")],
                        title="phone width: can every line meant to be read be read?")
    return [x for x in (full, phone) if x]


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


KINETIC = ("look.kinetic_type", "story.beat_film")


def draft_qa(htmlmotion, bundle, spec, d, outdir):
    """The measured checks the final QA would fail, run on a cheap draft render BEFORE anyone sees a preview (quarter
    size, 15 fps, no sound, no Claude cost): flashing, frozen holds, how much of the film stands still, and the motion
    lint of the characters. -> (blocking findings for the designer, metrics). Kinetic films are held to the never-park
    gates (<= 40 % still frames, no hold over 0.6 s); other films to no hold over 1.2 s."""
    from . import qa
    os.makedirs(outdir, exist_ok=True)
    mp4 = os.path.join(outdir, "draft.mp4")
    total = spec["duration"]
    r = htmlmotion._node(bundle, mp4, round(total, 3), ["--opaque", "--scale=0.25"], 15)
    if r.returncode or not os.path.exists(mp4):
        return [], {"error": (r.stderr or "")[-300:]}
    kinetic = any(capabilities.has(d, k) for k in KINETIC)
    en, fc = qa.energy(mp4, fps=15), qa.frame_checks(mp4)
    scene_at = lambda t: next((sc["id"] for sc in spec["scenes"] if sc["start"] <= t < sc["end"]), spec["scenes"][-1]["id"])  # noqa: E731
    out = []
    if kinetic:   # never park: under 1.5 % of the frame changing counts as still (idle life is not enough here)
        holds = [(t, dur) for t, dur in en["holds"] if dur > 0.6 and t < total - 1.5]   # the end card may rest
    else:         # the same frozen-frame bar the final QA applies (qa.technical): idle life and slow pushes pass
        fz = qa.frozen_time(mp4)
        en["frozen_s"] = fz["frozen_s"]
        holds = [(t, dur) for t, dur in fz["holds"] if dur > 1.2 and t < total - 1.5]
        if fz["frozen_s"] > max(1.0, total / 30) and not holds:
            out.append(f"P1 · whole film · {fz['frozen_s']}s near-frozen in total (final QA limit {max(1.0, total / 30):.1f}s) "
                       f"around {fz['first_frozen_at'][:6]} s -> a slow push, idle life or a sooner cut there")
    for t, dur in holds:
        out.append(f"P0 · t={t}s · scene {scene_at(t)} · the frame stands still for {dur}s (limit {0.6 if kinetic else 1.2}s) "
                   "-> keep something moving: a camera drift, the word scaling 2-5 %/s, idle life, the next beat sooner")
    if kinetic and en["still_share"] > 0.40:
        out.append(f"P0 · whole film · {round(100 * en['still_share'])} % of frames stand still (kinetic limit 40 %) -> "
                   "never park: move the camera every frame, keep landed words alive, cut on more beats")
    for t in fc["flash_windows"]:
        out.append(f"P0 · t={t}s · scene {scene_at(t)} · more than 3 flashes in one second (photosensitivity risk) -> "
                   "fewer white flashes / colour flips in a row, or slower ones")
    for t in fc["broken_frames"]:
        out.append(f"P1 · t={t}s · scene {scene_at(t)} · a frame looks broken (half drawn / corrupt) -> check that scene's JS")
    return out, {**en, "flash_windows": fc["flash_windows"], "kinetic": kinetic}


def build(con, p, note=""):
    """Design, check and save the motion for production `p` (mutates p['data']; the caller saves)."""
    from . import productions
    sys.path.insert(0, os.path.join(ROOT, "bin"))
    import htmlmotion
    d = p["data"]
    spec, _, _, _ = productions.timeline(con, p)          # draft or real timing, look_pack "auto" compiles like any explainer
    from . import memory
    design, meta, raw = author(spec, d, note or d.get("motion_note", ""), memory.designer_note(con))
    keep = os.path.join(ROOT, "data", "auto", f"{p['prod_id']}")
    os.makedirs(keep, exist_ok=True)
    with open(os.path.join(keep, "author_raw.txt"), "w") as f:   # an expensive reply: never lose it to a parse error
        f.write(raw)
    missing = [sc["id"] for sc in spec["scenes"] if not (design["scenes"].get(sc["id"]) or {}).get("html")]
    if missing:
        raise RuntimeError(f"design has no markup for scenes {missing}")
    resolve_stock(design, d)
    resolve_plates(design, d)
    cost = meta.get("cost_usd") or 0
    shotdir = os.path.join(ROOT, "work", "explainer", f"auto-{p['prod_id']}")
    spec["name"] = f"auto-{p['prod_id']}"
    log = []
    hide = [sc["id"] for sc in spec["scenes"] if sc.get("hide_captions")]
    gates, energy = [], {}
    for rnd in range(1, 3):   # self-check: round 1 always; round 2 only when a measured gate still fails (a free
        shutil.rmtree(shotdir, ignore_errors=True)   # 2nd look cost ~$0.7 and rarely found anything new)
        bundle = htmlmotion.write_bundle(spec, design)
        times, labels = sheets.review_times(spec["scenes"])
        paths, errs, found = layoutlint.run(bundle, times, shotdir, spec.get("aspect", "9:16"), hide)
        gates, energy = draft_qa(htmlmotion, bundle, spec, d, os.path.join(shotdir, "draft"))
        if rnd > 1 and not gates and not errs:
            break
        lint = layoutlint.as_text(found) + [f"MEASURED ON A DRAFT RENDER (blocking): {g}" for g in gates]
        ok, fixed, m = critique(spec, d, design, review_sheets(paths, times, labels, shotdir), errs, rnd, lint)
        cost += m.get("cost_usd") or 0
        log.append({"round": rnd, "errors": errs, "lint": lint, "gates": gates, "energy": energy, "ok": ok,
                    "fixed": sorted(fixed["scenes"]), "scores": fixed.get("scores"), "notes": (fixed.get("notes") or "")[:2000]})
        if ok and not errs and not gates:
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
    paths, errs, found = layoutlint.run(bundle, times, shotdir, spec.get("aspect", "9:16"), hide)
    if log and log[-1]["fixed"]:   # measure the fixed design too, so the card shows what the preview will be
        gates, energy = draft_qa(htmlmotion, bundle, spec, d, os.path.join(shotdir, "draft"))
    review = review_sheets(paths, times, labels, shotdir)
    rel = os.path.join("data", "auto", f"{p['prod_id']}", "design.json")
    os.makedirs(os.path.join(ROOT, os.path.dirname(rel)), exist_ok=True)
    json.dump(design, open(os.path.join(ROOT, rel), "w"), ensure_ascii=False, indent=1)
    d["motion"] = {"design": rel, "concept": design["meta"].get("concept"), "refs": design["meta"].get("refs") or [],
                   "spec": (design.get("spec") or "")[:3000], "grammar": d.get("grammar") or "auto",
                   "palette": design["meta"].get("palette"), "log": log, "errors": errs, "lint": layoutlint.as_text(found),
                   "gates": gates, "energy": energy,
                   "cost_usd": round(cost, 2),
                   "shots": [os.path.relpath(x, os.path.join(ROOT, "work", "explainer")) for x in paths],
                   "sheets": [os.path.relpath(x, os.path.join(ROOT, "work", "explainer")) for x in review if x.endswith(".png")]}
    d.pop("motion_note", None)
    d["look_pack"] = "html"
    return d["motion"]
