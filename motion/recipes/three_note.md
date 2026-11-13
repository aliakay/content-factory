3D KIT (real WebGL, Three.js, motion/templates/fx3d.js). The page loads it only when a scene's js says FX.stage3.
  k = FX.stage3(tl, root, T, {look, cam, bg, fog, drift, exposure, seed})   ONE stage per scene (there is one canvas)
  look: 'clay' (matte, soft shadow, transparent canvas: your CSS background shows) | 'studio' (glossy, rim light,
        reflections) | 'paper' (flat-shaded craft) | 'blueprint' (edges + faint fill, floor grid) | 'neon' (glowing
        edges on the film's bg). Colours come from the film palette (--accent, --accent2, --hot, --ink, --muted).
  Builders, each (tl, at, ...) with `at` in ABSOLUTE film seconds like the rest of FX; one idea per scene:
    k.text3d(tl, at, 'BIG\nIDEA', {font: 'anton'|'poppins'|'serif', anim: 'rise'|'drop'|'spin'|'pop', y, w, pos})
        fills the safe width by default: when it shares the frame with an object give it w (world units, e.g.
        k.safeW * 0.6) and a y that keeps it clear of the object, or it covers the object and a camera pan crops it
    k.number3d(tl, at, 2.4, {prefix: '$', suffix: 'M', decimals: 1, dur, from, sep, w, y})   counts up from `from`;
        a year is not a quantity: draw it with text3d ('1989'), or it counts through 1,3xx on its way
    k.bars(tl, at, [{v, label}], {highlight, prefix, suffix})
    g = k.globe(tl, at, {focus: [lon, lat], routes: [{from, to, at, fromLabel, toLabel}], marks: [{p, label, at}]})
        g.turn(at, [lon, lat]); g.route(at, a, b, {...}); g.mark(at, p, label)
    k.product(tl, at, 'phone'|'can'|'box'|'laptop'|'bottle', {label, color, callouts: [{part, label, side, at}]})
    k.explode(tl, at, [{label, color}], {gap})          k.city(tl, at, {n, data, mark: [[i, j, label]]})
    k.flythrough(tl, at, [{kicker, title, sub}], {every})   (owns the camera: no k.move in that scene)
    k.swarm(tl, at, {text: '87%' | shape: 'sphere'|'ring'|'grid'|'cube', then: {at, text | shape}})
    k.stack(tl, at, [{n, label, value}], {unit: 'coin'|'cash'|'block', prefix, suffix, highlight})
  Camera (factory/camera.py names): k.move('push_in'|'pull_out'|'orbit'|'pan_left'|'pan_right'|'tilt_up'|
    'tilt_down'|'zoom_to'|'rack_focus'|'hold'|'dolly_zoom', {at, dur, ease, amount, turn, to}); moves chain.
    k.cam({az, el, dist}) sets the opening pose. A slow drift is always on, so a held shot is never dead.
    A move changes the whole frame: push_in with amount a shows 1/a of the set (0.7 enlarges everything 1.4x), so a
    headline wider than a * k.safeW ends up cropped; with a full-width headline use amount 0.9 or pull_out / orbit.
  Labels: k.tag(tl, at, [x, y, z] | () => point, 'html', {size, color, dx, dy}) is DOM text glued to a 3D point.
  Own objects: k.solid(geometry, color) / k.rbox(w, h, d, r) / k.mat(color) dress meshes in the look;
    k.add(mesh); k.eachFrame((lt, t) => ...) for motion as a pure function of t; k.THREE is the library.
    Build the film's subject once (a carton, a machine) and reuse it in every 3D scene with the SAME sizes and
    colours: the same object in a new state reads as one film. Do not guess world units for it: right after building
    the group call h = k.fitTo(group, {h: 0.5, y: -0.25, x: 0}) -- h = share of the safe height, y / x = centre in
    -1..1 of the safe area (y: -0.25 is a little below the middle). It returns a holder already in the scene (no
    k.add); animate the group's own scale 0 -> 1, rotation and position as usual. The subject is on screen from the
    scene's first frame; a 3D scene never opens on an empty set.
    On 9:16 the safe area is about 8.1 wide and 12.3 tall, so y runs from -6.1 to +6.1. A headline's y is its centre
    (text3d / number3d keep the block inside the safe area): put the headline in the top third (y about 3.5) and the
    object below it, or the reverse; never both in the same band.
  The canvas sits behind the scene's text and in front of a full-frame wrapper that paints the background, so the
    film's usual `.w` background shows behind the 3D set. DOM text placed over the object hides it: put text beside it.
  World units: the frame is 10 wide on 9:16 (17.8 tall) and 16 wide on 16:9 (9 tall) at the focal plane; the origin
    is the middle of the platform-safe area; k.safeW / k.safeH / k.fit give the safe size. Builders size themselves.

TEXT IN 3D AND THE LINT: words drawn in WebGL (text3d, number3d, swarm text, flythrough cards) carry an invisible DOM
  twin (class x3t, data-ink = the colour drawn) that follows their projected box every frame, so the layout lint and
  the read-check see them like DOM text. Never also write the same words in the DOM. Tags are plain DOM text.

FRAME BUDGET (software WebGL, measured at 1080x1920): a stage costs 0.25-0.5 s per frame in clay / paper / blueprint /
  neon and 0.5-0.8 s in studio (its reflections are the expensive part), against ~0.1 s for a DOM-only frame; the
  first frame of a stage adds 1-4 s of shader compiling, once. Pick studio only for a glossy hero object. Keep it there:
  - one stage per scene, one builder (two at most: a title + one object), no more than ~150 meshes or 3000 particles;
  - do not raise pixel ratio, shadow size or segment counts; no post effects, no real-time physics, no fetch;
  - a 3D scene of 3-6 s in a 60 s film is fine; a film of only 3D scenes doubles the render time.

NEVER: Math.random / Date / performance.now (use k.rand or FX.rand(seed)); state carried from the previous frame
  (everything must be computed from t: frames render out of order); a second FX.stage3 in the same scene;
  new THREE.WebGLRenderer yourself (contexts are capped; the kit shares one and frees each scene's GPU memory when
  the scene ends); text over the 3D object; a 3D object in the lower caption band (builders already avoid it).
