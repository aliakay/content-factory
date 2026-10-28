# Art direction playbook (footage videos)

**The factory does this itself (built 2026-10-27): `factory/artdirector.py`.** Every footage production gets an Opus
art direction before its first preview (or Studio → production → "🎨 Yeniden yönet", job `p_direct`): it Reads the
contact sheets, researches with WebSearch/WebFetch and headless Chromium (`motion/browse.mjs` → screenshots in
`work/research/p<id>/` that it Reads), writes concept + brief + signature moves, and decides look, title, every shot's
transition/effects and the music brief. After the preview renders it checks frames around every cut
(`work/artstills/p<id>/`) and fixes once (`review`). It never repeats itself (`data/art/history.jsonl`) and grows its
skill library (`data/art/skills.json`: learned custom masks / HTML treatments / rules + a wishlist of effects the
renderer still lacks = build roadmap). `data.art = false` on a production switches it off. This file is background
for humans; the vocabulary the director actually gets is `artdirector.VOCAB`.

Started 2026-10-27 after the user asked for real art direction on their raw footage: not copying references, not
"join clips + add text". The art director (Claude) researches, picks a concept, and decides design, edit and effects
for THIS footage. This file is the effect vocabulary + the research notes it draws on; extend it after every research
pass.

## Process for every video
1. **Read the footage**: contact sheets, motion profile, steady segments, light/colour, what moves inside the frame
   (people walking past, hands, doors, trees, water = natural wipe/mask material), shapes that repeat (arches, circles,
   horizons = match-cut material), where the subject is (text-behind-subject candidates).
2. **Research** (WebSearch/WebFetch + headless Chromium screenshots of public galleries/articles; no logins, nothing
   downloaded, refs are taste only): how strong creators edit this kind of place/theme right now.
3. **Brief** (one page, shown to the user before rendering): concept + hook (first 2 s), story arc, frame/grade/type
   system, cut rhythm (where it breathes, where it hits the music), and the 2-4 signature effects chosen for this
   footage, each with the reason. Restraint: one signature transition family per video, not a catalogue.
4. Build -> stills of key moments -> self-critique -> preview -> user OK -> final.

## Effect vocabulary
Status: ✅ in `bin/stylecut.py` / overlay today · 🔧 planned · 🧠 planned (needs subject segmentation)

### Transitions
- ✅ cut, flash, dip, whip (motion smear), glitch, tiles
- ✅ **shape mask reveal** (`enter: mask`, shapes circle/iris/band/split/strips/bars/custom, `line` edge): the next shot opens inside a growing circle / rounded rect / diagonal band / parallelogram
  strips / vertical bars, optionally with a thin editorial line tracing the mask edge (CapCut "mask transition"
  gallery: circle portal with white rings, tilted stacked strips, vertical bar strips).
- ✅ **luma wipe** (`mask.shape: luma`): the next shot appears through the brightness of the current one (sky first, then land)
  or along a soft gradient; feels organic for landscapes.
- ✅ **object wipe (natural mask)** (`enter: object`): a person/pole/tree passing close to the lens fills the frame ->
  the previous shot ends at the occlusion peak and the new shot opens through the dark object. Occlusions are measured
  per clip (`factory/fxdetect.py`, clips.fx) and handed to the art director.
- ✅ **match cut** (`enter: match`): two shots with the same shape/position/movement (horizon line, walking direction)
  joined by a 4-frame dissolve; horizons and motion direction are measured (`fxdetect.match_pairs`), the AD aligns
  them with `focus`.
- ✅ **speed ramp** (`ramp: {in, out, x}`): normal -> fast (x4-x8 with blur) into the cut -> slow out on the new place. Works on 50/60 fps
  clips; slow down on arrival at the landmark, speed up while leaving (Splice travel guides).
- ✅ **J-cut / L-cut audio** (`audio: {lead, tail}`): the next place's ambient sound starts before its picture / the
  current one runs on over the next shot, faded.

### Text & graphic treatments
- ✅ title_serif, title_bold, scramble, editorial, words, quote, pin, hook, caption (motion/templates/overlay.html)
- ✅ **text as window** (layer `window`): huge letters ("ALPS") filled with the footage, the rest black/blurred, then the letters
  scale up until the footage fills the frame.
- 🔧 **split reveal**: title revealed by a diagonal band that crosses the frame (CapCut "Your name" speedramp tile).
- ✅ **text behind subject** (layer `behind: true`): title sits between background and the person/mountain; 3-layer
  stack (original -> text -> masked subject) with a per-frame matte from `factory/matte.py` (rembg u2netp; install
  `rembg[cpu]` on the VM; without it the text is drawn on top).
- 🧠 **subject pop / outline**: person cut out with a thin white stroke, background darkened or frozen.

### Footage set pieces (`bin/stylecut.py` shot fields)
- ✅ **zoom-through cut** (`enter: zoom`): the previous shot dives 2.5x into its focus point with blur, the new one lands
  out of a zoom. Aim both focus points at the matching spot (window, doorway, screen, eye).
- ✅ **freeze frame** (`freeze: {at, dur, flash, mono, punch}`): the frame holds with a white flash, grey look and a small
  punch-in, then plays on. Pair it with a label layer.
- ✅ **vertigo / dolly zoom** (`vertigo: {amount, inward}`): background pulls away (or rushes in) while the subject keeps
  its size. Scaled about the subject matte's centre (rembg); without a matte a soft ellipse around `focus` is held.
- ✅ **green screen** (`chroma: {bg, color, sim, blend, spill}`): chromakey + despill over another clip, a photo or the
  previous shot's last frame.
- ✅ **frame break** (`frame_break: {box, border, color, bg}`): the shot sits in a framed card on a blurred copy and the
  matted subject breaks out over the edge (needs rembg; without it the card alone).
- ✅ speed ramp, digital zoom (`push` + `focus`) as above.

### Motion-design set pieces (`motion/templates/fxlib.js`, explainer scenes)
- ✅ orbit (`FX.orbit`, `FX.orbit3d`), screen wall (`FX.screenWall`), UI world (`FX.uiWorld`), frame break
  (`FX.frameBreak`, cut-out PNG), phone mockup (`FX.phone`), checklist (`FX.checklist`), headline wall
  (`FX.headlineWall`), zoom-through (`FX.zoomThrough`), chart grow (`FX.chart` bar/line/area/donut), paper cut
  (`FX.paperCut`, `FX.paperSheet`), doodle boil (`FX.boil`, `FX.doodle`), vertigo (`FX.vertigo`), cover story
  (`FX.coverStory`), glass type (`FX.glassType`), freeze frame (`FX.freezeFrame`); pull-back reveal = `FX.camera`
  `pull_out`; kinetic captions are drawn by the explainer shell.

### Looks
- ✅ grades natural/film/golden/moody/vivid/mono + grain, vignette, letterbox/scope frames
- ✅ light leak (`leak: true`); 🔧 film burn, halation.
- ✅ **own HTML/JS layers** (layer `html`): the director designs titles, lower thirds, route lines etc. per video.

## Implementation notes
- ffmpeg on the VM (`~/opt/bin/ffmpeg`) has `maskedmerge`, `alphamerge`, `geq`, `overlay`: shape masks can be drawn
  as animated alpha videos (ProRes 4444 from the Chromium overlay renderer, or geq) and merged.
- Segmentation: onnxruntime is installed; a small video-matting model (e.g. Robust Video Matting mobilenet) on CPU.
  4 cores, no GPU -> only on short shots, at 1080p or lower, cached per clip.

## Research log
- 2026-10-27: CapCut template galleries (speedramp-cinematic, mask-transition) viewed in Chromium; Splice travel-reel
  guides (hand/object mask reveals, walking match cuts, slow-mo on arrival); browser-use/video-use README (audio-led
  cuts, 30 ms audio fades at every cut, self-check of every cut boundary on the render, fixed rules + free taste);
  Premiere/AE text-behind-subject = duplicate layer + object mask/roto, text in the middle.
