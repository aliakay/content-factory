LINE-ART KIT (FX.ink, hand-inked animated drawings; `const LA = FX.ink;` — loaded automatically when the scene JS mentions FX.ink)
- Stage: `S = LA.stage(root, T, {ground: 0.8})` makes one SVG in FIGURE UNITS (1 unit = 5 px: 216x384 portrait, 384x216 landscape; test `S.w < S.h`).
  S.gy = ground line y. All times are ABSOLUTE film seconds (`T.start + 1.2`), like every FX helper. Layers: S.layer('back'|'mid'|'front').
- Proportions: a grown person at scale 1 is ~95 units tall, feet exactly on their y; child ~66; head is 1/7 of the height. Door ~50 units, tree 60-90,
  building 110-200 tall. Portrait: ground at 0.7-0.8 of H leaves the lower third for captions. Nearer people get a larger y (S.gy+8..+30) and scale.
- Figures: `f = LA.figure(S, {who: man|woman|child, x, y, dir, scale, hat, scarf, prop})`; `f.walk(at, x, {gait: walk|shuffle|run}) -> arrival time`
  (duration comes from the distance, so feet never slide); `f.face`, `f.act(at, wave|tipHat|point|bow|cheer|shrug|think|look|present)`, `f.sit/stand`;
  `LA.bike(S, f).ride(at, x)`. Chain the arrival time into the next action.
- Scenes: LA.street(S,{seed}) · LA.building · LA.skyline · LA.tree({kind: round|pine|willow}) · LA.lamp · LA.room · LA.bench · LA.cat · LA.birds · LA.laundry · LA.smoke · LA.sky.
  Day to night: `S.daynight([[t, tau], ...])` (tau 0.5 noon, 0.75 dusk, 1.0 midnight) and windows/lamps light up by themselves. Wind: S.wind.gust(at, {dur, amp}) bend trees, scarves, laundry, smoke.
- Explaining: LA.label (hand lettering) · LA.arrow · LA.circleAround · LA.bars · LA.gear / LA.drivetrain (a mechanism that turns) · LA.drawIn(S, group, {at, dur}) draws it stroke by stroke.
  The picture must carry the idea: a figure that points at the thing, a ring, a label that arrives with the narration word.
- Strokes: pen width ~0.9 unit, never thinner than 0.5; always two open lines per limb/outline (the kit does it); paper-white fills hide what is behind.
  Ink is near-black on warm paper (#fdfcf8); colour is rare: ONE accent (red #b3412d) plus at most 2-3 muted flats; at night ink turns pale on deep blue.
- Motion: slow and legible. 2-4 people at once, each with its own start and pace; background life (cat, birds, smoke, trees) never steals the main move.
- Never: Math.random / Date / requestAnimationFrame / setInterval (everything is a pure function of t; use the seeds); straight ruler lines (use LA.line/LA.rect);
  figures floating above or sunk below their ground; feet sliding (move only through walk/ride); emoji or photos inside the drawing; thin grey type; a full-bleed fill
  that hides the paper; every person walking the same way in a row; empty frames (a ground line alone is not a scene).
- Sound: walking registers quiet footstep ticks (FX.sfx) by itself; `f.walk(at, x, {steps: false})` silences them.
