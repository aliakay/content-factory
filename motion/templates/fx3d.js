/* FX 3D kit — real WebGL (Three.js r170) for explainer scenes. Loaded by explainer_shell.html ONLY when a scene's JS
   mentions FX.stage3 (or the older FX.three family); pages without 3D never download or compile any of it.

   k = FX.stage3(tl, root, T, {look: "clay"|"studio"|"blueprint"|"neon"|"paper", cam: {az, el, dist, fov}, bg, seed})
   then ONE builder per idea (each takes the timeline `tl` and an absolute start time `at`, like the rest of FX):
     k.text3d(tl, at, "WORD", {font, anim, color, side, y})       extruded headline, letters rise in   (DOM twin, linted)
     k.number3d(tl, at, 2400000, {prefix, suffix, decimals, dur}) extruded number that counts up       (DOM twin, linted)
     k.bars(tl, at, [{v, label}], {highlight, suffix})            3D columns that grow + value / label tags
     k.globe(tl, at, {focus, routes: [{from, to, at}], marks: [{p, label, at}]})  dotted-continent globe, great circles
     k.product(tl, at, "phone"|"can"|"box"|"laptop"|"bottle", {color, label, callouts})  turntable hero object
     k.explode(tl, at, [{label}], {gap})                          layered slabs that separate into an exploded view
     k.city(tl, at, {data, n, mark: [[i, j, label]]})             isometric block city / data landscape rising in a wave
     k.flythrough(tl, at, [{title, sub}], {every})                cards in depth, the camera flies from one to the next
     k.swarm(tl, at, {shape: "text"|"sphere"|"ring"|"grid", text, then: {at, text|shape}})  particles form a shape
     k.stack(tl, at, [{n, label, value}], {unit: "coin"|"cash"|"block"})  piles that drop in, for scale comparisons
     k.move("push_in" | "pull_out" | "orbit" | "pan_left" | ..., {at, dur, ease, amount})   camera.py vocabulary
     k.tag(tl, at, [x, y, z] | () => Vector3, "HTML", {size, dx, dy, align})   HTML label glued to a 3D point
     k.figure(spec, {x, z, size, facing})   a 3D toy character with a pose / gesture / walk / talk API  (fx3d_figure.js, loaded with this file)
     k.hero(obj) / k.beat(tl, at, kind, o) / k.cadence(tl, o) / k.dust(o)   the idle layer: every stage sways, drifts and floats for its whole
         length (opt out: FX.stage3(..., {idle: false}); strengthen: {idle: 1.5}); beats schedule a second and third visible action
   Everything is a pure function of t: GSAP tweens on tl + closed-form maths + seeded FX.rand. No clocks, no physics.
   One WebGL context serves the whole film (browsers cap contexts at ~16): the canvas moves into the active scene and
   the scene's GPU buffers are freed when it leaves the screen, so a 12-scene film never piles contexts or memory up.
   ONE stage per scene (the shared canvas can only sit in one place at a time). */
(function () {
  const FX = window.FX, X = (FX.x3 = {});
  let THREE, EX = {}, R = null;
  X.PR_MAX = 1;                       // drawing-buffer pixels per CSS pixel, never more (SwiftShader fill cost is per pixel)
  X.SHADOW = 1024;                    // shadow map size; 1024 is enough for one soft directional light
  const JSM = "/motion/node_modules/three/examples/jsm/";
  const FONTS = { anton: "Anton-Regular.ttf", poppins: "Poppins-Bold.ttf", serif: "DMSerifDisplay-Regular.ttf" };
  const FONTCSS = { anton: "Anton", poppins: "Poppins", serif: "'DM Serif Display'", inter: "'Inter Tight'" };
  X.fonts = {};
  const D2R = Math.PI / 180;
  const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
  const lerp = (a, b, p) => a + (b - a) * p;
  const E = {                         // easings, the names of factory/camera.py
    linear: (p) => p, ease_in: (p) => p * p * p, ease_out: (p) => 1 - Math.pow(1 - p, 3),
    ease_in_out: (p) => (p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2), inertia: (p) => FX.INERTIA(p),
    sine: (p) => 0.5 - Math.cos(Math.PI * p) / 2, steps: (p) => Math.floor(p * 6) / 6,
  };
  X.EASE = E;

  /* ---- loader: three + the few addons we need + the project fonts, awaited through window.ready by the shell ---- */
  FX.load3d = async () => {
    if (THREE && EX.ready) return;
    const URL3 = "/motion/node_modules/three/build/three.module.min.js";
    if (!THREE) {
      if (!document.querySelector('script[type="importmap"]')) {   // addons say `from "three"`: map it to the SAME module instance
        const m = document.createElement("script"); m.type = "importmap"; m.textContent = JSON.stringify({ imports: { three: URL3 } }); document.head.appendChild(m);
      }
      THREE = window.THREE = await import(URL3);
    }
    const [rb, l2, lg, lm, re, ot] = await Promise.all([
      import(JSM + "geometries/RoundedBoxGeometry.js"), import(JSM + "lines/LineSegments2.js"), import(JSM + "lines/LineSegmentsGeometry.js"),
      import(JSM + "lines/LineMaterial.js"), import(JSM + "environments/RoomEnvironment.js"), import(JSM + "libs/opentype.module.js")]);
    Object.assign(EX, { RoundedBoxGeometry: rb.RoundedBoxGeometry, LineSegments2: l2.LineSegments2, LineSegmentsGeometry: lg.LineSegmentsGeometry,
                        LineMaterial: lm.LineMaterial, RoomEnvironment: re.RoomEnvironment, opentype: ot.default });
    await Promise.all(Object.entries(FONTS).map(async ([k, f]) => { X.fonts[k] = EX.opentype.parse(await (await fetch("/fonts/" + f)).arrayBuffer()); }));
    // canvas textures (cards, labels, particle text) draw with the page's fonts: load them before the first frame
    if (document.fonts) await Promise.all(["40px Anton", "700 40px Poppins", '40px "DM Serif Display"', '800 40px "Inter Tight"', '600 40px "Inter Tight"'].map((f) => document.fonts.load(f).catch(() => {})));
    X.EX = EX;
    // characters (k.figure) live in their own file; it registers on X.kit like the builders below and needs THREE (set above)
    if (!X.figureKit) await new Promise((ok) => { const sc = document.createElement("script"); sc.src = "/motion/templates/fx3d_figure.js"; sc.onload = ok; sc.onerror = () => { console.error("fx3d_figure.js not found"); ok(); }; document.head.appendChild(sc); });
    EX.ready = true;
  };

  /* ---- the one shared renderer ---- */
  const renderer = (W, H) => {
    if (!R) {
      const cv = document.createElement("canvas");
      // preserveDrawingBuffer: the screenshot is taken after render() returns, in another task; without it the
      // compositor may already have swapped the buffer away and the frame comes out blank
      R = new THREE.WebGLRenderer({ canvas: cv, antialias: true, alpha: true, premultipliedAlpha: true, preserveDrawingBuffer: true, powerPreference: "high-performance" });
      R.setPixelRatio(1); R.shadowMap.enabled = true; R.shadowMap.type = THREE.PCFShadowMap;   // PCF honours shadow.radius (soft clay shadows); PCFSoft ignores it
      cv.className = "x3cv";
      Object.assign(cv.style, { position: "absolute", left: 0, top: 0, pointerEvents: "none" });
    }
    const pr = Math.min(window.devicePixelRatio || 1, X.PR_MAX), bw = Math.round(W * pr), bh = Math.round(H * pr);
    if (R.domElement.width !== bw || R.domElement.height !== bh) R.setSize(bw, bh, false);
    R.domElement.style.width = W + "px"; R.domElement.style.height = H + "px";
    R._pr = pr;
    return R;
  };
  X.contexts = () => (R ? 1 : 0);      // for the leak test: always 0 or 1
  X.renderer = () => R;
  let ENV = null;
  const env = (r) => { if (!ENV) { const g = new THREE.PMREMGenerator(r); ENV = g.fromScene(new EX.RoomEnvironment(), 0.04).texture; g.dispose(); } return ENV; };

  /* release every GPU resource of a stage that left the screen (they upload again by themselves if it comes back,
     so a frame of this scene requested later is still identical) */
  const release = (k) => {
    k._live = false;
    k.scene.traverse((o) => {
      if (o.geometry) o.geometry.dispose();
      for (const m of [].concat(o.material || [])) { for (const v of Object.values(m)) if (v && v.isTexture) v.dispose(); m.dispose(); }
      if (o.shadow && o.shadow.map) { o.shadow.map.dispose(); o.shadow.map = null; }   // a 1024² target per lit stage otherwise
    });
    if (R) R.renderLists.dispose();
    if (k._cv && k._cv.parentNode === k.root) k.root.removeChild(k._cv);
  };

  /* ---- looks: the lighting, materials and ground of a set. Colours come from the film's palette (CSS variables). ---- */
  const css = (v, fb) => (getComputedStyle(document.documentElement).getPropertyValue("--" + v).trim() || fb);
  const mix = (a, b, p) => new THREE.Color(a).lerp(new THREE.Color(b), p);
  const LOOKS = {
    clay: { tm: "None", rough: 0.88, metal: 0, round: 1, edges: false, shadow: 0.22, light(k) {
      k.add(new THREE.HemisphereLight(0xffffff, mix(k.pal.bg, "#ffffff", 0.35).getHex(), 1.25));
      const key = k.sun([-3, 12, 6], 0xfff2e2, 2.3, 8);
      const fill = new THREE.DirectionalLight(0xdbe6ff, 0.6); fill.position.set(6, 3, 5); k.add(fill); return key; } },
    studio: { tm: "ACESFilmic", rough: 0.26, metal: 0.18, round: 0.8, edges: false, shadow: 0.38, env: 0.9, light(k) {
      k.add(new THREE.HemisphereLight(0xffffff, 0x1a1a22, 0.35));
      const key = k.sun([-4, 8, 6], 0xfff4e6, 2.4, 4);
      const rim = new THREE.DirectionalLight(0xbfd4ff, 2.6); rim.position.set(5, 4, -7); k.add(rim); return key; } },
    paper: { tm: "None", rough: 1, metal: 0, round: 0.35, edges: false, flat: true, shadow: 0.34, light(k) {
      k.add(new THREE.HemisphereLight(0xffffff, mix(k.pal.paper, "#8a7f70", 0.4).getHex(), 1.2));
      return k.sun([-3, 10, 4], 0xffffff, 2.2, 2.5); } },
    blueprint: { tm: "None", rough: 1, metal: 0, round: 0, edges: "line", shadow: 0, fill: 0.14, light(k) { k.add(new THREE.AmbientLight(0xffffff, 1)); } },
    neon: { tm: "ACESFilmic", rough: 0.35, metal: 0.5, round: 0, edges: "glow", shadow: 0, light(k) {
      k.add(new THREE.HemisphereLight(0x6a7bff, 0x08080f, 0.7));
      const a = new THREE.DirectionalLight(mix(k.pal.accent, "#ffffff", 0.2).getHex(), 2.2); a.position.set(-6, 4, 5); k.add(a);
      const b = new THREE.DirectionalLight(new THREE.Color(k.pal.accent2).getHex(), 2.2); b.position.set(6, 2, -4); k.add(b); } },
  };
  X.LOOKS = LOOKS;

  /* ---- camera rig: orbit coordinates around a target; moves are segments, every pose a pure function of t ---- */
  const POSE = ["az", "el", "dist", "tx", "ty", "tz", "fov"];
  const MOVES = {           // name -> (pose at the start, options, stage) -> end pose
    push_in: (p, o) => ({ dist: p.dist * (o.amount ?? 0.7) }),
    pull_out: (p, o) => ({ dist: p.dist * (o.amount ?? 1.45) }),
    // turn is in degrees; a value under 3 can only be radians (0.3 degrees would be no move at all)
    orbit: (p, o) => { const d = o.turn ?? 60; return { az: p.az + (Math.abs(d) < 3 ? d : (d * Math.PI) / 180) }; },
    // a tall frame has 60-150 px of side margin around a full-width headline: a pan there is a nudge, not a truck
    pan_left: (p, o, k) => ({ tx: p.tx - (o.dx ?? (k.tall ? 0.05 : 0.2) * k.w), az: p.az - (k.tall ? 0.05 : 0.08) }),
    pan_right: (p, o, k) => ({ tx: p.tx + (o.dx ?? (k.tall ? 0.05 : 0.2) * k.w), az: p.az + (k.tall ? 0.05 : 0.08) }),
    tilt_up: (p, o, k) => ({ ty: p.ty + (o.dy ?? (k.tall ? 0.05 : 0.12) * k.h), el: p.el - 0.1 }),
    tilt_down: (p, o, k) => ({ ty: p.ty - (o.dy ?? (k.tall ? 0.05 : 0.12) * k.h), el: p.el + 0.1 }),
    zoom_to: (p, o) => ({ tx: o.to[0], ty: o.to[1], tz: o.to[2] || 0, dist: p.dist * (o.amount ?? 0.45) }),
    // no depth of field in SwiftShader's budget: a rack is the aim moving to the other plane with a slight tighten
    rack_focus: (p, o) => ({ tx: o.to[0], ty: o.to[1], tz: o.to[2] || 0, fov: p.fov * 0.92 }),
    follow: (p) => ({}),      // the aim tracks o.target() (see evalPose)
    hold: (p, o) => ({ dist: p.dist * (o.amount ?? 0.97) }),
    // dolly zoom: the camera backs off while the lens tightens, the subject keeps its size and the room bends around it
    dolly_zoom: (p, o) => { const d = p.dist * (o.amount ?? 1.7), fov = (2 * Math.atan(Math.tan((p.fov * Math.PI) / 360) * p.dist / d) * 180) / Math.PI; return { dist: d, fov }; },
  };
  X.MOVES = Object.keys(MOVES);
  X.stages = [];

  /* Where the canvas goes so the picture is seen: behind the scene's own text, but in front of a full-frame wrapper
     that paints a background (the usual `.w` of a film's global CSS would otherwise cover the whole 3D set). */
  const backdrop = (root, W, H) => {
    for (const el of root.children) {
      if (el.tagName === "CANVAS" || el.classList.contains("x3t")) continue;
      const cs = getComputedStyle(el), r = el.getBoundingClientRect(), rr = root.getBoundingClientRect();
      const painted = cs.backgroundImage !== "none" || !/rgba\([^)]*,\s*0\)|transparent/.test(cs.backgroundColor);
      if (painted && r.width >= rr.width * 0.9 && r.height >= rr.height * 0.9) return el;
    }
    return root;
  };
  FX.stage3 = (tl, root, T, o = {}) => {
    if (!EX.ready) throw new Error("FX.stage3: three is not loaded (the shell loads it when a scene mentions FX.stage3)");
    const W = FX._W || 1080, H = FX._H || 1920, tall = H > W, look = LOOKS[o.look] || LOOKS.clay, lookName = LOOKS[o.look] ? o.look : "clay";
    const pal = { bg: css("bg", "#0f1220"), ink: css("ink", "#f4efe6"), muted: css("muted", "#9aa3b5"), accent: css("accent", "#ffb347"),
                  accent2: css("accent2", "#7c5cff"), paper: css("paper", "#f3eee3"), hot: css("hot", "#ff5a5f"), ...(o.palette || {}) };
    const FOV = o.fov || 30, FH = tall ? 17.78 : 9;           // world height of the frame at the focal plane (width 10 / 16)
    const SAFE = tall ? { x: [60, 930], y: [170, 1500] } : { x: [80, 1840], y: [60, 850] };   // factory/layoutlint.SAFE
    const scene = new THREE.Scene(), camera = new THREE.PerspectiveCamera(FOV, W / H, 0.5, 400);
    const ppu = H / FH;
    const k = { THREE, scene, camera, root, T, tl, W, H, tall, look, lookName, pal, w: W / ppu, h: FH, ppu, _fns: [], _post: [], _twins: [], _lines: [], _mats: {}, _live: false,
                safeW: (SAFE.x[1] - SAFE.x[0]) / ppu, safeH: (SAFE.y[1] - SAFE.y[0]) / ppu, rand: FX.rand(o.seed || 7) };
    const d0 = FH / 2 / Math.tan((FOV * Math.PI) / 360);
    k.d0 = d0;
    k.fit = Math.min(k.safeW, k.safeH);                       // the side of the biggest square that fits the safe area
    k.colors = [pal.accent, pal.accent2, pal.hot, pal.ink, pal.muted];
    k.c = (i) => k.colors[((i % k.colors.length) + k.colors.length) % k.colors.length];
    // the principal point moves so the origin sits in the middle of the platform-safe area, not of the raw frame
    const sx = W / 2 - (SAFE.x[0] + SAFE.x[1]) / 2, sy = H / 2 - (SAFE.y[0] + SAFE.y[1]) / 2;
    camera.setViewOffset(W, H, sx, sy, W, H);
    k.add = (x) => { scene.add(x); return x; };
    /* An own object sized and placed by the frame instead of by guessed world units: wraps it in a holder scaled so it
       is `h` of the safe height (and at most `w` of the safe width), centred at x / y in -1..1 of the safe area and
       never outside it. The object keeps its own scale, rotation and position for animation (scale 0 -> 1 grows it to
       the fitted size). Returns the holder, already in the scene. */
    k.fitTo = (obj, fo = {}) => {
      const keep = obj.scale.clone(), par = obj.parent; if (par) par.remove(obj);
      obj.scale.set(1, 1, 1); obj.updateMatrixWorld(true);
      const box = new THREE.Box3().setFromObject(obj), size = box.getSize(new THREE.Vector3()), c = box.getCenter(new THREE.Vector3());
      obj.scale.copy(keep);
      const holder = new THREE.Group(); holder.add(obj); scene.add(holder);
      if (!(size.y > 0)) return holder;
      const f = Math.min(((fo.h ?? 0.5) * k.safeH) / size.y, ((fo.w ?? 0.8) * k.safeW) / Math.max(size.x, 1e-6));
      const hh = (size.y * f) / 2, hw = (size.x * f) / 2, lim = (v, half, span) => Math.max(-span / 2 + half, Math.min(span / 2 - half, v));
      const ty = lim(((fo.y ?? 0) * k.safeH) / 2, hh, k.safeH), tx = lim(((fo.x ?? 0) * k.safeW) / 2, hw, k.safeW);
      holder.scale.setScalar(f); holder.position.set(tx - c.x * f, ty - c.y * f, 0);
      if (fo.hero !== false) k.hero(holder, typeof fo.hero === "object" ? fo.hero : {});
      return holder;
    };
    /* a headline's centre, held so the whole block stays inside the safe area (with room for a push-in) */
    k.inY = (y, h) => { const top = (k.safeH / 2) * 0.9 - h / 2, bot = -k.safeH / 2 + h / 2; return top < bot ? 0 : Math.max(bot, Math.min(top, y)); };
    k.sun = (pos, color, intensity, radius) => {
      const l = new THREE.DirectionalLight(color, intensity); l.position.set(...pos); l.castShadow = look.shadow > 0;
      const s = l.shadow, e = Math.max(k.safeW, k.safeH) * 0.8; s.mapSize.set(X.SHADOW, X.SHADOW); s.radius = radius; s.bias = -0.0004; s.normalBias = 0.03;
      Object.assign(s.camera, { left: -e, right: e, top: e, bottom: -e, near: 1, far: 60 }); scene.add(l); k.key = l; return l;
    };
    look.light(k);
    k.bg = o.bg === undefined ? (lookName === "neon" ? pal.bg : null) : o.bg;   // null = transparent, the scene's CSS shows through
    k.fog = (near, far, color) => { scene.fog = new THREE.Fog(new THREE.Color(color || k.bg || pal.bg), near, far); return k; };
    if (o.fog) k.fog(d0 * 0.9, d0 * 2.2);

    /* camera: base pose (builders may suggest one, the scene's own o.cam / k.cam always wins) + move segments */
    const userCam = Object.assign({}, o.cam || {});
    const base = Object.assign({ az: 0.3, el: 0.32, dist: d0, tx: 0, ty: 0, tz: 0, fov: FOV }, userCam);
    const segs = [];
    const chain = () => { let p = { ...base }; for (const s of segs) { s.from = p; s.to = { ...p, ...MOVES[s.name](p, s.mo, k) }; p = s.to; } };   // each move starts where the one before ended
    k.cam = (p) => { Object.assign(base, p); Object.assign(userCam, p); chain(); return k; };
    k.camDefault = (p) => { for (const [n, v] of Object.entries(p)) if (!(n in userCam)) base[n] = v; chain(); return k; };
    k.pose0 = () => ({ ...base });
    const evalPose = (t) => {
      let p = { ...base };
      for (const s of segs) {
        if (t < s.at) break;
        const e = s.ease(clamp((t - s.at) / s.dur)); p = Object.fromEntries(POSE.map((n) => [n, lerp(s.from[n], s.to[n], e)]));
        if (s.name === "follow" && s.mo.target) { const q = s.mo.target(t); p.tx = lerp(s.from.tx, q[0], e); p.ty = lerp(s.from.ty, q[1], e); p.tz = lerp(s.from.tz, q[2] || 0, e); }
      }
      return p;
    };
    k.move = (name, mo = {}) => {
      if (!MOVES[name]) throw new Error("FX.stage3 move: unknown '" + name + "' (" + Object.keys(MOVES).join(", ") + ")");
      const at = mo.at ?? T.start;
      segs.push({ name, mo, at, dur: mo.dur ?? Math.max(0.6, T.end - at), ease: E[mo.ease] || E.ease_in_out }); segs.sort((a, b) => a.at - b.at); chain();
      return k;
    };
    k.path = (fn) => { k._pathFn = fn; return k; };   // camera on a rail: fn(t) -> {pos, look, fov?}; replaces the rig (flythrough)
    const drift = o.drift ?? 0.012;                   // a barely moving camera: nothing on screen is ever fully dead

    /* ---- the idle layer: a 3D scene that does one move and then holds read as a slideshow (the first real 3D film
       counted 73 % of its frames as still). Everything below runs for the whole scene as closed-form functions of the
       timeline time (no clock, no state), additive to the scene's own moves; opt out with {idle: false} or scale it
       with {idle: {cam, hero, light}} (1 = default, 0 = off). Measured with factory/qa.energy: a held scene must not
       count as still (tests/test_three.py). ---- */
    const IDLE = o.idle === false ? null : Object.assign({ cam: 1, hero: 1, light: 1, dust: 1 }, typeof o.idle === "object" ? o.idle : typeof o.idle === "number" ? { cam: o.idle, hero: o.idle, light: o.idle, dust: o.idle } : {});
    k.idleOn = !!IDLE;
    const TAU = Math.PI * 2;
    // a slow handheld-crane breath: an orbit swing (parallax between the set and what is behind it), a tilt, a dolly
    const idleCam = (lt) => IDLE && IDLE.cam ? [IDLE.cam * (0.12 * Math.sin((TAU * lt) / 10.5 + 0.6)), IDLE.cam * (0.03 * Math.sin((TAU * lt) / 8.3 + 1.9)), 1 + IDLE.cam * 0.02 * Math.sin((TAU * lt) / 6.7)] : [0, 0, 1];
    k.idleCam = idleCam;
    // beats: scheduled visible actions (see k.beat below); the camera ones are summed here
    const camBeats = [];
    const camBeat = {
      dist: (t) => camBeats.reduce((a, b) => (b.kind === "push" ? a * (1 - b.amount * ease(b.ease)(clamp((t - b.at) / b.dur))) : a), 1),
      az: (t) => camBeats.reduce((a, b) => (b.kind === "swing" ? a + b.amount * ease(b.ease)(clamp((t - b.at) / b.dur)) : a), 0),
      el: (t) => camBeats.reduce((a, b) => (b.kind === "rise" ? a + b.amount * ease(b.ease)(clamp((t - b.at) / b.dur)) : a), 0),
    };
    const place = (t, back = 1) => {
      let p = null;
      if (k._pathFn) { const r = k._pathFn(t), ic = idleCam(t - T.start); r.pos = [r.pos[0] + ic[0] * 8, r.pos[1] + ic[1] * 8, r.pos[2]]; camera.position.set(...r.pos); camera.up.set(0, 1, 0); camera.lookAt(...r.look); if (r.roll) camera.rotateZ(-r.roll); camera.fov = r.fov || base.fov; }
      else {
        p = evalPose(t); const lt = t - T.start, ic = idleCam(lt), az = p.az + drift * Math.sin(lt * 0.9) + ic[0] + camBeat.az(t), el = p.el + drift * 0.6 * Math.sin(lt * 0.7 + 1) + ic[1] + camBeat.el(t), d = p.dist * back * ic[2] * camBeat.dist(t);
        camera.position.set(p.tx + d * Math.sin(az) * Math.cos(el), p.ty + d * Math.sin(el), p.tz + d * Math.cos(az) * Math.cos(el));
        camera.lookAt(p.tx, p.ty, p.tz); camera.fov = p.fov;
      }
      camera.updateProjectionMatrix(); camera.updateMatrixWorld(true);
      return p;
    };
    /* Headlines stay in the frame whatever the camera does: when a push-in, zoom or pan would carry a kept block
       (every text3d / number3d headline) past the safe area, the camera backs off along its own line of sight just
       enough for it to fit, frame by frame, so the move still reads but never crops the words. */
    k._keep = [];
    k.keep = (obj, mn, mx) => { k._keep.push({ obj, mn, mx }); return k; };
    const over = (p) => {
      const c = k.px([p.tx, p.ty, p.tz]); let r = 1;
      if (!(c[0] > SAFE.x[0] && c[0] < SAFE.x[1] && c[1] > SAFE.y[0] && c[1] < SAFE.y[1])) return 1;
      for (const kp of k._keep) {
        if (!kp.obj.visible) continue;
        const b = projBox(k, kp.obj, kp.mn, kp.mx); if (!b) continue;
        if (b[1] < SAFE.y[0]) r = Math.max(r, (c[1] - b[1]) / (c[1] - SAFE.y[0]));
        if (b[1] + b[3] > SAFE.y[1]) r = Math.max(r, (b[1] + b[3] - c[1]) / (SAFE.y[1] - c[1]));
        if (b[0] < SAFE.x[0]) r = Math.max(r, (c[0] - b[0]) / (c[0] - SAFE.x[0]));
        if (b[0] + b[2] > SAFE.x[1]) r = Math.max(r, (b[0] + b[2] - c[0]) / (SAFE.x[1] - c[0]));
      }
      return r;
    };
    const placeKept = (t) => {
      let p = place(t);
      if (!p || !k._keep.length || o.keep === false) return;
      scene.updateMatrixWorld(true);
      let back = 1;
      for (let i = 0; i < 6; i++) { const r = over(p); if (r <= 1.002) break; back *= Math.min(r * 1.01, 1.6); p = place(t, back); }
    };
    /* hero: the object the scene is about. Wrapped in an identity holder (the object keeps its own transform for the
       builder's moves) that sways, tilts and bobs a little all scene long and takes the beats. Builders call it on their
       group; sway 0 for the ones that already turn by themselves. */
    k.heroes = [];
    k.hero = (obj, ho = {}) => {
      if (!obj || obj._hero) return obj;
      const par = obj.parent || scene, w = new THREE.Group();
      w.position.set(obj.position.x, 0, obj.position.z); par.add(w); w.add(obj); obj.position.x -= w.position.x; obj.position.z -= w.position.z;
      const h = { obj, w, beats: [], opt: { sway: 0.27, tilt: 0.04, bob: 0.014 * k.fit, period: 7.2, scale: 0.014, turn: true, beat: true, ...ho }, phase: 0.7 * k.heroes.length };
      obj._hero = h;
      h._frame = (lt, t) => {
        const a = IDLE ? IDLE.hero : 0, op = h.opt, P = op.period, ph = (TAU * lt) / P + h.phase;
        let ry = a * op.sway * Math.sin(ph), rx = a * op.tilt * Math.sin(ph * 0.73 + 1.1), rz = a * op.tilt * 0.7 * Math.sin(ph * 0.61 + 2.3), sc = 1 + a * op.scale * Math.sin(ph * 1.3 + 0.4), py = a * op.bob * Math.sin(ph * 0.9 + 0.5);
        for (const b of h.beats) {
          const p = clamp((t - b.at) / b.dur), e = ease(b.ease)(p), pk = Math.sin(Math.PI * p);
          if (b.kind === "turn") ry += b.amount * e; else if (b.kind === "pulse") sc *= 1 + b.amount * pk; else if (b.kind === "hop") py += b.amount * pk * pk; else if (b.kind === "tilt") rz += b.amount * pk;
        }
        w.rotation.set(rx, ry, rz); w.position.y = py; w.scale.setScalar(sc);
      };
      k.heroes.push(h); return obj;
    };
    /* beat: a second / third visible action on a long scene, in one line. The target defaults to the scene's hero.
         k.beat(tl, at, 'turn',  {amount: rad, dur})    hero turns (stays turned)       'pulse' {amount} scale pop
         k.beat(tl, at, 'hop' | 'tilt', {amount})       hero jumps / leans and settles
         k.beat(tl, at, 'push' | 'swing' | 'rise', {amount})  camera dolly in (fraction) / orbit (rad) / tilt (rad), stays
         k.beat(tl, at, 'flash', {target: mesh|group, color})  a part lights up (emissive) and settles
         k.beat(tl, at, 'label', {target: tag element})  a tag pulses (CSS scale)
       Pure functions of t, so frames stay order-independent. */
    k.beat = (tl, at, kind, bo = {}) => {
      const dflt = { turn: 1.0, pulse: 0.8, hop: 0.7, tilt: 0.8, push: 1.3, swing: 1.4, rise: 1.3, flash: 0.9, label: 0.6 }, b = { kind, at, dur: bo.dur ?? dflt[kind] ?? 1, ease: bo.ease || "power2.inOut", amount: bo.amount };
      if (["turn", "pulse", "hop", "tilt"].includes(kind)) {
        b.amount = bo.amount ?? { turn: 1.3, pulse: 0.12, hop: 0.5, tilt: 0.14 }[kind];
        const h = bo.target ? bo.target._hero : [...k.heroes].reverse().find((x) => x.opt.beat && (kind !== "turn" || x.opt.turn));
        if (h) h.beats.push(b);
      } else if (["push", "swing", "rise"].includes(kind)) {
        b.amount = bo.amount ?? { push: 0.08, swing: 0.24, rise: 0.06 }[kind]; camBeats.push(b);
      } else if (kind === "flash") {
        const tg = bo.target, mats = new Set(); (tg.traverse ? tg : { traverse: (f) => f(tg) }).traverse((m) => { for (const x of [].concat(m.material || [])) if (x && x.emissive) mats.add(x); });
        const col = new THREE.Color(bo.color || pal.accent), peak = bo.peak ?? 0.9, base = [...mats].map((m) => [m, m.emissive.clone(), m.emissiveIntensity]);
        k.eachFrame((lt, t) => { const p = clamp((t - at) / b.dur), v = p > 0 && p < 1 ? Math.sin(Math.PI * p) * peak : 0; for (const [m, c0, i0] of base) { if (v > 0) { m.emissive.copy(col); m.emissiveIntensity = Math.max(v, i0); } else { m.emissive.copy(c0); m.emissiveIntensity = i0; } } });
      } else if (kind === "label") {
        const el = bo.target; k.eachFrame((lt, t) => { const p = clamp((t - at) / b.dur); el.style.scale = String(1 + (bo.amount ?? 0.25) * Math.sin(Math.PI * p)); });
      } else throw new Error("k.beat: unknown kind '" + kind + "' (turn, pulse, hop, tilt, push, swing, rise, flash, label)");
      return k;
    };
    /* cadence: a visible action every few seconds across a long scene (a scene of 6.5 s or more gets one by itself:
       pass {cadence: false} to FX.stage3 to opt out, or {cadence: {from, every, kinds}} to tune it) */
    k.cadence = (tl, co = {}) => {
      const every = co.every ?? 2.4, from = co.from ?? T.start + Math.max(3.0, (T.end - T.start) * 0.34), until = co.until ?? T.end - 0.9;
      const kinds = co.kinds || (k.heroes.some((h) => h.opt.turn && h.opt.beat) ? ["turn", "pulse", "push", "turn", "swing", "pulse"] : k.heroes.some((h) => h.opt.beat) ? ["pulse", "push", "swing", "hop"] : ["push", "swing", "rise", "swing"]);
      let i = 0;
      for (let t = from; t < until; t += every, i++) {
        let kind = kinds[i % kinds.length]; if (k._pathFn && ["push", "swing", "rise"].includes(kind)) continue;   // a camera on a rail is not nudged
        k.beat(tl, t, kind, { amount: kind === "turn" ? (i % 2 ? -1.2 : 1.3) : kind === "swing" ? (i % 2 ? -0.22 : 0.24) : undefined });
      }
      return k;
    };
    /* dust: slow motes drifting through the set, soft discs facing the camera (instanced, closed-form, wrapped in a
       box so there is always the same number on screen). They are what keeps a composition alive when the main object
       holds, and the biggest share of what the stillness metric (factory/qa.energy) sees as motion. On by default
       (idle.dust: 0 turns it off): k.dust({n, color, size, opacity, speed}) adds another layer. */
    k.dust = (dopt = {}) => {
      const n = dopt.n ?? Math.round(160 * Math.min(2.5, IDLE ? IDLE.dust || 1 : 1)), r = FX.rand(dopt.seed || 17), bx = [k.w * 1.1, k.h * 1.25, k.fit * 1.1], base = [], u = dopt.size ?? k.fit * 0.038, sp = dopt.speed ?? 1.9 * Math.sqrt(IDLE ? IDLE.dust || 1 : 1);
      for (let i = 0; i < n; i++) base.push([r() * bx[0] - bx[0] / 2, r() * bx[1] - bx[1] / 2, (r() - 0.85) * bx[2], 0.45 + r() * 0.7, r() * TAU, 0.5 + r(), 0.5 + r() * 1.5]);
      const dark = new THREE.Color(pal.bg).getHSL({}).l > 0.5, col = new THREE.Color(dopt.color || (dark ? pal.ink === pal.bg ? "#000" : mix(pal.ink, pal.bg, 0.2) : pal.ink));
      const tex = k.texture(64, 64, (g, w, h) => { const gr = g.createRadialGradient(w / 2, h / 2, 0, w / 2, h / 2, w / 2); gr.addColorStop(0, "rgba(255,255,255,1)"); gr.addColorStop(0.62, "rgba(255,255,255,0.9)"); gr.addColorStop(1, "rgba(255,255,255,0)"); g.fillStyle = gr; g.fillRect(0, 0, w, h); });
      const m = new THREE.MeshBasicMaterial({ color: col, map: tex, transparent: true, opacity: dopt.opacity ?? 0.3, depthWrite: false, fog: false });
      const mesh = new THREE.InstancedMesh(new THREE.PlaneGeometry(1, 1), m, n), m4 = new THREE.Matrix4(), P = new THREE.Vector3(), Sc = new THREE.Vector3(); mesh.frustumCulled = false; mesh.renderOrder = 5; scene.add(mesh);
      k.eachFrame((lt) => {
        const q = camera.quaternion;
        for (let i = 0; i < n; i++) { const b = base[i], y = ((b[1] + bx[1] / 2 + lt * b[3] * 0.9 * sp) % bx[1] + bx[1]) % bx[1] - bx[1] / 2; P.set(b[0] + 0.6 * Math.sin(lt * 0.45 * b[5] + b[4]), y, b[2] + 0.4 * Math.cos(lt * 0.33 * b[5] + b[4])); mesh.setMatrixAt(i, m4.compose(P, q, Sc.setScalar(u * b[6]))); }
        mesh.instanceMatrix.needsUpdate = true;
      });
      return mesh;
    };
    k.eachFrame = (fn) => { k._fns.push(fn); return k; };
    k.frame = k.eachFrame;                              // same name the older FX.three kit uses
    k.px = (v) => { const q = (v.isVector3 ? v.clone() : new THREE.Vector3(...v)).project(camera); return [(q.x * 0.5 + 0.5) * W, (-q.y * 0.5 + 0.5) * H, q.z]; };

    /* materials and meshes in the active look */
    k.mat = (color, mo = {}) => {
      const key = new THREE.Color(color).getHexString() + "|" + (mo.rough ?? "") + "|" + (mo.emissive || "") + "|" + (mo.metal ?? "") + "|" + (mo.glow ?? "") + (mo.double ? "d" : "");
      if (k._mats[key]) return k._mats[key];
      const c = new THREE.Color(color);
      let m;
      if (lookName === "blueprint") m = new THREE.MeshBasicMaterial({ color: c, transparent: true, opacity: mo.fill ?? look.fill, depthWrite: false, side: THREE.DoubleSide });
      else if (lookName === "neon") m = new THREE.MeshStandardMaterial({ color: c.clone().multiplyScalar(0.16), roughness: look.rough, metalness: look.metal, emissive: c, emissiveIntensity: mo.glow ?? 0.3 });   // faces glow faintly in their own colour, the edges carry the light
      else m = new THREE.MeshStandardMaterial({ color: c, roughness: mo.rough ?? look.rough, metalness: mo.metal ?? look.metal, flatShading: !!look.flat, side: mo.double ? THREE.DoubleSide : THREE.FrontSide, emissive: mo.emissive || 0x000000, envMapIntensity: look.env || 1 });
      return (k._mats[key] = m);
    };
    const lineMat = (color, px, op = 1, add = false) => {
      const m = new EX.LineMaterial({ color: new THREE.Color(color).getHex(), linewidth: px, transparent: op < 1 || add, opacity: op, depthTest: !add,
                                      blending: add ? THREE.AdditiveBlending : THREE.NormalBlending });
      k._lines.push([m, px]); return m;
    };
    k.lineMat = lineMat;
    k.edges = (geo, color, px = 2.4, op = 1, add = false, ang = 28) => {
      const g = new EX.LineSegmentsGeometry().setPositions(new THREE.EdgesGeometry(geo, ang).attributes.position.array);
      return new EX.LineSegments2(g, lineMat(color, px, op, add));
    };
    k.line = (pts, color, px = 3, op = 1, add = false) => {   // a polyline as fat lines (px stay px whatever the depth)
      const arr = []; for (let i = 0; i + 1 < pts.length; i++) arr.push(...pts[i], ...pts[i + 1]);
      const g = new EX.LineSegmentsGeometry().setPositions(arr); return new EX.LineSegments2(g, lineMat(color, px, op, add));
    };
    k.solid = (geo, color, so = {}) => {          // a mesh dressed for the look (outlined in blueprint, glowing edges in neon)
      const m = new THREE.Mesh(geo, so.material || k.mat(color, so)); m.castShadow = !so.noShadow && look.shadow > 0; m.receiveShadow = look.shadow > 0;
      if (look.edges && !so.noEdges) {
        const ink = lookName === "blueprint" ? mix(color, pal.ink, 0.35) : new THREE.Color(color).lerp(new THREE.Color("#ffffff"), 0.25);
        m.add(k.edges(geo, ink, lookName === "blueprint" ? 2.6 : 2.2, 1));
        if (look.edges === "glow") m.add(k.edges(geo, new THREE.Color(color), 9, 0.22, true));
      }
      return m;
    };
    k.rbox = (w, h, d, r = 0.12, seg = 3) => {      // rounded box, rounded by the look (sharp in blueprint)
      const rr = Math.min(r * look.round, Math.min(w, h, d) * 0.49);
      return rr > 0.004 ? new EX.RoundedBoxGeometry(w, h, d, seg, rr) : new THREE.BoxGeometry(w, h, d);
    };
    k.ground = (go = {}) => {                       // a floor that only shows shadows (clay/studio/paper) or a grid (blueprint/neon)
      if (k._ground && !go.force) return k._ground; // one floor per stage: two shadow catchers would double the shadow
      const S = go.size || Math.max(k.w, k.h) * 2.2, y = go.y ?? 0; let g;
      if (look.shadow > 0) { g = new THREE.Mesh(new THREE.PlaneGeometry(S, S), new THREE.ShadowMaterial({ opacity: go.opacity ?? look.shadow })); g.receiveShadow = true; g.rotation.x = -Math.PI / 2; }
      else {
        const n = go.cells || 24, c = go.cell || Math.max(0.5, k.fit / 10), half = (n * c) / 2, arr = [];
        for (let i = 0; i <= n; i++) { const a = -half + i * c; arr.push(a, 0, -half, a, 0, half, -half, 0, a, half, 0, a); }
        g = new EX.LineSegments2(new EX.LineSegmentsGeometry().setPositions(arr), lineMat(lookName === "neon" ? pal.accent2 : pal.ink, 1.4, lookName === "neon" ? 0.55 : 0.22));
      }
      g.position.y = y; scene.add(g); return (k._ground = g);
    };
    /* canvas texture: text and flat graphics on 3D surfaces (cards, labels). Drawn once, deterministic. */
    k.texture = (w, h, draw) => {
      const c = document.createElement("canvas"); c.width = w; c.height = h; const g = c.getContext("2d"); draw(g, w, h);
      const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4; return t;
    };
    /* twins: invisible DOM text that mirrors text drawn inside WebGL, so layoutlint (safe zone, caption band, overlap,
       contrast, tiny) and the read-check see it. get(t) -> {box: [x, y, w, h] in CSS px, alpha, text}. */
    k.twin = (text, get, ink, font) => {
      const el = document.createElement("div"); el.className = "x3t"; el.setAttribute("aria-hidden", "true"); el.dataset.ink = ink || pal.ink;
      Object.assign(el.style, { position: "absolute", left: 0, top: 0, whiteSpace: "nowrap", color: "transparent", pointerEvents: "none", lineHeight: 1, transformOrigin: "0 0",
                                font: `${font || "800 100px 'Inter Tight'"}`, opacity: 0 });
      el.textContent = text; root.appendChild(el);
      const tw = { el, get, nat: 0, txt: text }; k._twins.push(tw); return tw;
    };
    const syncTwin = (tw, t) => {
      const r = tw.get(t); if (!r || !r.box || !(r.alpha > 0.02)) { tw.el.style.opacity = 0; return; }
      if (r.text !== undefined && r.text !== tw.txt) { tw.el.textContent = tw.txt = r.text; tw.nat = 0; }
      const [x, y, w, h] = r.box, fs = Math.max(2, Math.round(h));
      if (!tw.nat || tw.fs !== fs) { tw.el.style.fontSize = fs + "px"; tw.fs = fs; tw.nat = tw.el.offsetWidth || w; }
      const sxx = clamp(w / tw.nat, 0.2, 5);
      tw.el.style.transform = `translate(${x.toFixed(1)}px,${y.toFixed(1)}px) scaleX(${sxx.toFixed(3)})`; tw.el.style.opacity = clamp(r.alpha, 0, 1);
    };
    /* tag: an HTML label glued to a 3D point (point() returning null hides it); fades in on tl at `at` */
    k.tag = (tl2, at, point, html, to = {}) => {
      const el = document.createElement("div"); el.className = "x3tag";
      const al = to.align || "center", tx = { center: "-50%", left: "0%", right: "-100%" }[al];
      Object.assign(el.style, { position: "absolute", left: 0, top: 0, whiteSpace: "nowrap", font: `${to.weight || 800} ${to.size || (tall ? 44 : 36)}px/1.1 ${to.font || '"Inter Tight"'}`, color: to.color || pal.ink,
                                transform: `translate(${tx},-50%)`, pointerEvents: "none", textAlign: al, ...(to.css || {}) });
      el.innerHTML = html;
      const holder = document.createElement("div"); Object.assign(holder.style, { position: "absolute", left: 0, top: 0, width: 0, height: 0, pointerEvents: "none" });
      root.appendChild(holder); holder.appendChild(el);
      const pt = typeof point === "function" ? point : () => point, dx = to.dx ?? 0, dy = to.dy ?? 0;
      // placed AFTER the frame's matrices are updated (k._post): reading matrixWorld inside k._fns would glue the label
      // to the previous rendered frame, which lags a turning object and breaks out-of-order determinism
      k._post.push(() => { const v = pt(); if (!v) { holder.style.display = "none"; return; } const q = k.px(v); holder.style.display = q[2] > 1 ? "none" : "block"; holder.style.transform = `translate(${(q[0] + dx).toFixed(1)}px,${(q[1] + dy).toFixed(1)}px)`; });
      if (at !== null && at !== undefined) tl2.fromTo(el, { opacity: 0, y: 14 }, { opacity: 1, y: 0, duration: to.dur ?? 0.4, ease: "power2.out" }, at); else el.style.opacity = 1;
      el.updateText = (s) => { if (el._s !== s) { el.innerHTML = s; el._s = s; } };
      return el;
    };
    k.label = k.tag;

    /* the per-frame renderer */
    FX.onFrame((t) => {
      const on = t >= T.start - 1e-6 && t < T.end;
      if (!on) { if (k._live) release(k); return; }
      const r = renderer(W, H);
      if (!k._cv) k._cv = r.domElement;
      if (!k._host) k._host = o.front ? root : backdrop(root, W, H);
      if (k._cv.parentNode !== k._host) { if (o.front) root.appendChild(k._cv); else k._host.insertBefore(k._cv, k._host.firstChild); }
      k._live = true;
      if (look.env && !scene.environment) { scene.environment = env(r); }
      r.toneMapping = { None: THREE.NoToneMapping, ACESFilmic: THREE.ACESFilmicToneMapping }[look.tm]; r.toneMappingExposure = o.exposure ?? 1;
      r.setClearColor(k.bg ? new THREE.Color(k.bg) : 0x000000, k.bg ? 1 : 0);
      // the automatic cadence is scheduled on the first frame, BEFORE the camera is placed (camera beats shape it)
      if (!k._cadenced) { k._cadenced = true; if (o.cadence !== false && IDLE && T.end - T.start > 6.5) k.cadence(null, o.cadence && typeof o.cadence === "object" ? o.cadence : {}); }
      place(t);
      const lt = t - T.start;
      if (IDLE && IDLE.light && k.key) {   // the key light breathes and drifts a hair: soft shadows and highlights slide over the set
        const kb = k.key.userData.base || (k.key.userData.base = { p: k.key.position.clone(), i: k.key.intensity }), a = IDLE.light;
        k.key.position.set(kb.p.x + a * 1.1 * Math.sin(lt * 0.62), kb.p.y + a * 0.35 * Math.sin(lt * 0.9 + 1), kb.p.z + a * 0.8 * Math.cos(lt * 0.5)); k.key.intensity = kb.i * (1 + a * 0.05 * Math.sin(lt * 1.4));
      }
      for (const f of k._fns) f(lt, t);
      for (const h of k.heroes) h._frame(lt, t);
      if (k._keep.length) placeKept(t);
      scene.updateMatrixWorld(true);
      for (const f of k._post) f(lt, t);
      for (const [m, px] of k._lines) { m.resolution.set(W * r._pr, H * r._pr); m.linewidth = px * r._pr; }
      r.render(scene, camera);
      for (const tw of k._twins) syncTwin(tw, t);
    });
    for (const f of X.kit) f(k, o);
    if (IDLE && IDLE.dust) k.dust(typeof IDLE.dust === "object" ? IDLE.dust : {});
    X.stages.push(k);
    return k;
  };
  X.kit = [];                          // builders register themselves here and are added to every stage

  /* ---- text: project fonts -> extruded glyphs (opentype.js outlines through three's ShapePath, no typeface JSON) ---- */
  const glyphCache = new Map();
  const glyph = (fk, ch, depth, bevel) => {
    const key = fk + ch + depth + "|" + bevel, hit = glyphCache.get(key); if (hit) return hit;
    const font = X.fonts[fk] || X.fonts.anton, g = font.charToGlyph(ch), adv = (g.advanceWidth * 100) / font.unitsPerEm;
    const sp = new THREE.ShapePath();
    for (const c of g.getPath(0, 0, 100).commands) {
      if (c.type === "M") sp.moveTo(c.x, -c.y); else if (c.type === "L") sp.lineTo(c.x, -c.y);
      else if (c.type === "Q") sp.quadraticCurveTo(c.x1, -c.y1, c.x, -c.y); else if (c.type === "C") sp.bezierCurveTo(c.x1, -c.y1, c.x2, -c.y2, c.x, -c.y);
    }
    const shapes = sp.toShapes(false);
    let geo = null;
    if (shapes.length) {
      geo = new THREE.ExtrudeGeometry(shapes, { depth, bevelEnabled: bevel > 0, bevelThickness: bevel, bevelSize: bevel * 0.8, bevelSegments: 2, curveSegments: 5 });
      geo.translate(0, 0, -depth / 2); geo.computeBoundingBox();
    }
    const out = { geo, adv, font, box: geo ? geo.boundingBox : null };
    glyphCache.set(key, out); return out;
  };
  X.glyph = glyph;
  const capH = (fk) => { const g = glyph(fk, "H", 1, 0); return g.box.max.y - g.box.min.y; };
  const layout = (fk, str, depth, bevel) => {      // pen positions of one line at 100 units font size, kerning included
    const font = X.fonts[fk] || X.fonts.anton; let x = 0, prev = null; const items = [];
    for (const ch of str) { const g = glyph(fk, ch, depth, bevel), gl = font.charToGlyph(ch); if (prev) x += (font.getKerningValue(prev, gl) * 100) / font.unitsPerEm; items.push({ ch, x, g }); x += g.adv; prev = gl; }
    return { items, width: x };
  };
  X.layout = layout; X.capH = capH;

  /* =============================== builders =============================== */
  const fmtNum = (v, dec, sep) => { const s = Math.abs(v).toFixed(dec), [i, f] = s.split("."); return (v < 0 ? "-" : "") + i.replace(/\B(?=(\d{3})+(?!\d))/g, sep) + (f ? "." + f : ""); };
  X.fmt = fmtNum;
  // projected pixel box of a local-space box under an object's world matrix (null when behind the camera)
  const projBox = (k, obj, mn, mx) => {
    let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9, behind = false;
    for (const x of [mn.x, mx.x]) for (const y of [mn.y, mx.y]) for (const z of [mn.z, mx.z]) {
      const q = k.px(new THREE.Vector3(x, y, z).applyMatrix4(obj.matrixWorld)); if (q[2] > 1) behind = true;
      x0 = Math.min(x0, q[0]); y0 = Math.min(y0, q[1]); x1 = Math.max(x1, q[0]); y1 = Math.max(y1, q[1]);
    }
    return behind ? null : [x0, y0, x1 - x0, y1 - y0];
  };
  X.projBox = projBox;
  const ENTER = {   // how a letter / block arrives: [from-state of the mesh, ease]
    rise: (c) => [{ y: -c * 0.9, rx: -1.15, s: 0.001 }, "back.out(1.5)"],
    drop: (c) => [{ y: c * 3.2, rx: 0.5, s: 0.001 }, "bounce.out"],
    spin: () => [{ y: 0, ry: Math.PI * 1.6, s: 0.001 }, "power3.out"],
    pop: () => [{ y: 0, s: 0.001 }, "back.out(2.4)"],
  };
  X.ENTER = ENTER;
  const V3 = (x = 0, y = 0, z = 0) => new THREE.Vector3(x, y, z);
  const ease = (name) => gsap.parseEase(name);     // GSAP easings as pure functions for closed-form motion

  X.kit.push((k) => {
    const { pal } = k;
    const twinFont = (fk) => `400 100px ${FONTCSS[fk] || "Anton"}`;
    /* extruded headline: letters arrive one by one; each line has a DOM twin for the layout lint */
    k.text3d = (tl, at, str, o = {}) => {
      const fk = o.font || "anton", depth = o.depth ?? 22, bevel = o.bevel ?? 3, ch = capH(fk), lines = String(str).split("\n");
      const lays = lines.map((l) => layout(fk, l, depth, bevel)), maxW = Math.max(...lays.map((l) => l.width)), lh = ch * 1.32;
      const s = Math.min((o.w ?? k.safeW * 0.94) / maxW, (o.maxH ?? k.safeH * (k.tall ? 0.55 : 0.75)) / (ch + lh * (lines.length - 1)));
      const g = new THREE.Group(), color = o.color || pal.ink, sideC = o.side || (k.lookName === "clay" || k.lookName === "paper" ? pal.accent : color);
      const [from, ez] = (ENTER[o.anim || "rise"] || ENTER.rise)(ch), stag = o.stagger ?? 0.06, letters = [];
      const twoTone = k.lookName !== "blueprint" && k.lookName !== "neon";
      lines.forEach((line, li) => {
        const L = lays[li], lineY = ((lines.length - 1) / 2 - li) * lh, own = [];
        L.items.forEach((it, i) => {
          if (!it.g.geo) return;
          const geo = it.g.geo.clone(), b = it.g.box, cx = (b.min.x + b.max.x) / 2, cy = (b.min.y + b.max.y) / 2; geo.translate(-cx, -cy, 0);
          const m = k.solid(geo, color); if (twoTone) m.material = [k.mat(color), k.mat(sideC)];   // faces ink, extrusion sides accent
          m.position.set(-L.width / 2 + it.x + cx, lineY + cy - ch / 2, 0); g.add(m); own.push(m); letters.push(m);
          const t0 = at + li * 0.15 + i * stag;
          m.scale.setScalar(from.s); m.rotation.set(from.rx || 0, from.ry || 0, 0); const y0 = m.position.y; m.position.y = y0 + from.y;
          tl.to(m.scale, { x: 1, y: 1, z: 1, duration: 0.55, ease: ez }, t0); tl.to(m.rotation, { x: 0, y: 0, duration: 0.6, ease: ez }, t0); tl.to(m.position, { y: y0, duration: 0.6, ease: ez }, t0);
        });
        const half = L.width / 2;
        k.twin(line, () => {
          const bx = projBox(k, g, V3(-half, lineY - ch / 2, -depth / 2), V3(half, lineY + ch / 2, depth / 2));
          const a = own.length ? Math.min(...own.map((m) => m.scale.x)) : 0; return { box: bx, alpha: a > 0.6 ? 1 : 0 };
        }, color, twinFont(fk));
      });
      const yy = k.inY(o.y ?? 0, (ch + lh * (lines.length - 1)) * s);
      g.scale.setScalar(s); g.position.set(...(o.pos || [0, yy, 0])); k.scene.add(g);
      { const hy = ((lines.length - 1) / 2) * lh + ch / 2; if (o.keep !== false) k.keep(g, V3(-maxW / 2, -hy, -depth / 2), V3(maxW / 2, hy, depth / 2)); }
      const sway = o.sway ?? 0.1; if (sway) k.eachFrame((lt) => { g.rotation.y = sway * Math.sin(lt * 0.8); g.rotation.x = -sway * 0.3 * Math.sin(lt * 0.6 + 1); });
      if (o.shadow !== false && k.look.shadow > 0) k.ground({ y: (o.pos ? o.pos[1] : yy) - (ch * s * lines.length * 0.75) - 0.4 });
      k.hero(g, { sway: 0, tilt: 0.012, turn: false });
      g.letters = letters; g.s = s; return g;
    };

    /* extruded number that counts up from `from` to `value` */
    k.number3d = (tl, at, value, o = {}) => {
      const fk = o.font || "anton", depth = o.depth ?? 24, bevel = o.bevel ?? 3, dec = o.decimals ?? 0, ch = capH(fk), sep = o.sep ?? (Math.abs(value) < 10000 ? "" : ","), dur = o.dur ?? 1.6;   // 1989 is a year, not "1,989"
      const fmt = (v) => (o.prefix || "") + fmtNum(v, dec, sep) + (o.suffix || ""), proxy = { v: o.from ?? 0 };
      tl.to(proxy, { v: value, duration: dur, ease: o.ease || "power3.out" }, at);
      const finalW = layout(fk, fmt(value), depth, bevel).width, s = Math.min((o.w ?? k.safeW * 0.94) / finalW, (o.maxH ?? k.safeH * 0.5) / ch);
      const g = new THREE.Group(), color = o.color || pal.ink, pool = new Map();   // "slot|char" -> mesh, made on first use
      const twoTone = k.lookName !== "blueprint" && k.lookName !== "neon";
      const get = (slot, c, gl) => {
        const key = slot + "|" + c; let m = pool.get(key);
        if (!m) { m = k.solid(gl.geo, color); if (twoTone) m.material = [k.mat(color), k.mat(o.side || pal.accent)]; g.add(m); pool.set(key, m); }
        return m;
      };
      let txt = fmt(proxy.v), W0 = finalW;
      k.eachFrame((lt, t) => {
        txt = fmt(proxy.v); const L = layout(fk, txt, depth, bevel); W0 = L.width;
        for (const m of pool.values()) m.visible = false;
        L.items.forEach((it, i) => { if (!it.g.geo) return; const m = get(i, it.ch, it.g); m.visible = true; m.position.set(-L.width / 2 + it.x, -ch / 2, 0); });
        const appear = ease("back.out(1.6)")(clamp((t - at) / 0.45)), land = Math.max(0, 1 - Math.abs(t - (at + dur)) * 3);
        g.scale.setScalar(s * Math.max(0.001, appear) * (1 + 0.06 * land));
        g.rotation.y = (o.sway ?? 0.1) * Math.sin(lt * 0.8);
      });
      const yy = k.inY(o.y ?? 0, ch * s);
      g.position.set(...(o.pos || [0, yy, 0])); k.scene.add(g);
      if (o.keep !== false) k.keep(g, V3(-finalW / 2, -ch / 2, -depth / 2), V3(finalW / 2, ch / 2, depth / 2));   // g carries the scale itself
      if (o.shadow !== false && k.look.shadow > 0) k.ground({ y: (o.pos ? o.pos[1] : yy) - ch * s * 0.8 - 0.4 });
      k.twin(txt, (t) => ({ box: projBox(k, g, V3(-W0 / 2, -ch / 2, -depth / 2), V3(W0 / 2, ch / 2, depth / 2)), alpha: t >= at + 0.3 ? 1 : 0, text: txt }), color, twinFont(fk));
      k.hero(g, { sway: 0, tilt: 0.012, turn: false });
      g.value = proxy; return g;
    };

    /* columns that grow from the floor, value and label tags glued to them */
    k.bars = (tl, at, data, o = {}) => {
      const items = data.map((d) => (typeof d === "number" ? { v: d } : d)), n = items.length, vmax = o.max ?? Math.max(...items.map((d) => d.v));
      const totalW = o.w ?? Math.min(k.safeW * 0.92, k.safeH * 1.5), step = totalW / n, bw = step * (o.fill ?? 0.62), bd = bw * 0.9;
      const Hm = o.hmax ?? (k.tall ? k.safeH * 0.48 : k.safeH * 0.62);
      const g = new THREE.Group(), stag = o.stagger ?? 0.12, dur = o.dur ?? 0.9, y0 = o.y ?? -Hm * 0.5;
      k.camDefault({ ty: o.y ?? 0 });
      g.position.y = y0; k.scene.add(g);
      if (o.ground !== false) k.ground({ y: y0 });
      const bars = items.map((it, i) => {
        const h = Math.max(0.05, (it.v / vmax) * Hm), x = (i - (n - 1) / 2) * step, hi = o.highlight === i;
        const col = it.color || (o.highlight === undefined ? k.c(o.color ?? 0) : hi ? k.c(2) : mix(k.c(1), pal.bg, 0.15).getStyle());
        const geo = k.rbox(bw, h, bd, 0.2); geo.translate(0, h / 2, 0);
        const m = k.solid(geo, col); m.position.x = x; m.scale.y = 0.001; g.add(m);
        const t0 = at + i * stag; tl.to(m.scale, { y: 1, duration: dur, ease: o.ease || "back.out(1.15)" }, t0);
        const val = k.tag(null, null, () => g.localToWorld(V3(x, h * m.scale.y + 0.55, 0)), "", { size: k.tall ? 52 : 40, color: hi ? k.c(2) : pal.ink });
        k.eachFrame(() => { const p = clamp(m.scale.y); val.updateText((o.prefix || "") + fmtNum(it.v * p, o.decimals ?? 0, ",") + (o.suffix || "")); val.style.opacity = p > 0.25 ? 1 : 0; });
        if (it.label !== undefined) { const lab = k.tag(null, null, () => g.localToWorld(V3(x, -0.15, bd / 2 + 0.55)), it.label, { size: k.tall ? 36 : 30, color: pal.muted }); k.eachFrame(() => { lab.style.opacity = m.scale.y > 0.05 ? 1 : 0; }); }
        return m;
      });
      k.hero(g, { sway: 0.17 });
      g.bars = bars; return g;
    };

    /* ---- globe: ocean sphere, dotted continents (coarse outlines below, no network), graticule, a rim of
       atmosphere, great-circle routes drawn on, marks with labels. The globe turns to face o.focus [lon, lat]. ---- */
    const ll = (lon, lat, r) => { const a = lon * D2R, b = lat * D2R; return V3(r * Math.cos(b) * Math.sin(a), r * Math.sin(b), r * Math.cos(b) * Math.cos(a)); };
    k.globe = (tl, at, o = {}) => {
      const R0 = o.r ?? k.fit * (k.tall ? 0.44 : 0.46), g = new THREE.Group(), spin = new THREE.Group(); g.add(spin); k.scene.add(g);
      k.camDefault({ az: 0, el: 0.06 });
      const ocean = o.ocean || (k.lookName === "clay" || k.lookName === "paper" ? pal.accent2 : mix(pal.bg, pal.accent2, 0.35).getStyle());
      const land = o.land || (k.lookName === "neon" ? pal.accent : k.lookName === "blueprint" ? pal.ink : pal.paper);
      // no shadow pass for the globe: nothing casts on it, and PCF taps over the whole sphere cost ~0.1 s a frame
      const oceanM = k.solid(new THREE.SphereGeometry(R0, 64, 40), ocean, { noEdges: true, rough: 0.7 }); oceanM.castShadow = oceanM.receiveShadow = false; spin.add(oceanM);
      const lat0 = [], gr = [];                                           // graticule every 30 degrees
      for (let la = -60; la <= 60; la += 30) { const pts = []; for (let i = 0; i <= 96; i++) pts.push(ll(i * 3.75, la, R0 * 1.002).toArray()); gr.push(pts); }
      for (let lo = 0; lo < 360; lo += 30) { const pts = []; for (let i = 0; i <= 48; i++) pts.push(ll(lo, -90 + i * 3.75, R0 * 1.002).toArray()); gr.push(pts); }
      for (const pts of gr) spin.add(k.line(pts, k.lookName === "blueprint" || k.lookName === "neon" ? land : pal.ink, 1.2, 0.18));
      // land as dots on a Fibonacci lattice (even spacing, no pole crowding), one InstancedMesh
      const N = o.dots ?? 12000, inst = [], dot = new THREE.CircleGeometry(R0 * 0.0105, 6);
      for (let i = 0; i < N; i++) {
        const y = 1 - (2 * (i + 0.5)) / N, lon = ((i * 137.50776) % 360) - 180, lat = Math.asin(y) / D2R;
        if (isLand(lon, lat)) inst.push([lon, lat]);
      }
      const dm = new THREE.InstancedMesh(dot, k.lookName === "blueprint" || k.lookName === "neon" ? new THREE.MeshBasicMaterial({ color: new THREE.Color(land) }) : k.mat(land, { double: true }), inst.length);
      const o3 = new THREE.Object3D();
      inst.forEach(([lo, la], i) => { o3.position.copy(ll(lo, la, R0 * 1.004)); o3.lookAt(ll(lo, la, R0 * 2)); o3.updateMatrix(); dm.setMatrixAt(i, o3.matrix); });
      spin.add(dm);
      // atmosphere: a back-face shell, brightest at the planet's edge and fading to nothing at its own rim
      const sh = 1.14, edge = Math.sqrt(1 - 1 / (sh * sh));
      g.add(new THREE.Mesh(new THREE.SphereGeometry(R0 * sh, 48, 32), new THREE.ShaderMaterial({
        uniforms: { c: { value: new THREE.Color(o.glow || mix(ocean, "#ffffff", 0.35)) }, e: { value: edge }, a: { value: o.glowAlpha ?? (k.lookName === "paper" ? 0.5 : 0.8) } },
        vertexShader: "varying vec3 vN; varying vec3 vV; void main(){ vec4 mv = modelViewMatrix * vec4(position, 1.0); vN = normalize(normalMatrix * normal); vV = normalize(-mv.xyz); gl_Position = projectionMatrix * mv; }",
        fragmentShader: "uniform vec3 c; uniform float e; uniform float a; varying vec3 vN; varying vec3 vV; void main(){ float d = clamp(-dot(vN, vV) / e, 0.0, 1.0); gl_FragColor = vec4(c, a * pow(d, 2.2)); }",
        side: THREE.BackSide, transparent: true, depthWrite: false, blending: k.lookName === "paper" ? THREE.NormalBlending : THREE.AdditiveBlending })));   // additive: a white halo with normal blending reads as grey fog on a dark ground
      // turning: face o.focus at `at` (from 40 degrees east of it), then g.turn(at, [lon, lat]) for later beats; slow spin on top
      const f0 = o.focus || [10, 25], view = { lon: (o.from || [f0[0] + 45, f0[1] - 10])[0], lat: (o.from || [f0[0] + 45, f0[1] - 10])[1] };
      spin.rotation.order = "XYZ";
      g.turn = (at2, to, dur = 1.4) => { tl.to(view, { lon: to[0], lat: to[1], duration: dur, ease: "power2.inOut" }, at2); return g; };
      g.turn(at, f0, o.turnDur ?? 1.6);
      const rate = o.spin ?? 1.5;   // degrees per second, always turning a little
      k.eachFrame((lt) => { spin.rotation.y = -(view.lon + rate * lt) * D2R; spin.rotation.x = clamp(view.lat, -60, 60) * D2R; });
      const pop = ease("back.out(1.4)");
      k.eachFrame((lt, t) => { g.scale.setScalar(Math.max(0.001, pop(clamp((t - at + 0.25) / 0.7)))); });
      const facing = (v) => { const w = v.clone().applyMatrix4(spin.matrixWorld), n = w.clone().sub(g.position).normalize(), c = k.camera.position.clone().sub(w).normalize(); return n.dot(c) > 0.12 ? w : null; };
      g.mark = (at2, p, label, mo = {}) => {
        const col = mo.color || pal.hot, pin = new THREE.Group(); pin.position.copy(ll(p[0], p[1], R0)); pin.lookAt(ll(p[0], p[1], R0 * 2)); spin.add(pin);
        const disc = new THREE.Mesh(new THREE.CircleGeometry(R0 * 0.035, 24), new THREE.MeshBasicMaterial({ color: new THREE.Color(col) })); disc.position.z = R0 * 0.006; pin.add(disc);
        const ring = new THREE.Mesh(new THREE.RingGeometry(R0 * 0.05, R0 * 0.062, 40), new THREE.MeshBasicMaterial({ color: new THREE.Color(col), transparent: true, depthWrite: false })); ring.position.z = R0 * 0.007; pin.add(ring);
        k.eachFrame((lt, t) => { const a = clamp((t - at2) / 0.3), ph = ((t - at2) % 1.4) / 1.4; disc.scale.setScalar(Math.max(0.001, ease("back.out(2)")(a))); ring.scale.setScalar(Math.max(0.001, a * (1 + 1.6 * ph))); ring.material.opacity = a * (1 - ph); });
        if (label) k.tag(tl, at2 + 0.15, () => facing(ll(p[0], p[1], R0 * 1.05)), label, { dy: mo.dy ?? -(k.tall ? 46 : 38), size: mo.size, color: mo.labelColor || pal.ink, css: { textShadow: "0 2px 10px rgba(0,0,0,.45)" } });
        return pin;
      };
      g.route = (at2, a, b, ro = {}) => {
        const va = ll(a[0], a[1], 1), vb = ll(b[0], b[1], 1), ang = va.angleTo(vb), lift = ro.lift ?? 0.06 + 0.32 * (ang / Math.PI), n = 64, pts = [];
        for (let i = 0; i <= n; i++) { const s = i / n, v = new THREE.Vector3().copy(va).multiplyScalar(Math.sin((1 - s) * ang) / Math.sin(ang)).add(vb.clone().multiplyScalar(Math.sin(s * ang) / Math.sin(ang))); pts.push(v.normalize().multiplyScalar(R0 * (1.004 + lift * Math.sin(Math.PI * s))).toArray()); }
        const col = ro.color || pal.accent, ln = k.line(pts, col, ro.px ?? (k.tall ? 6 : 5)); spin.add(ln);
        const head = new THREE.Mesh(new THREE.SphereGeometry(R0 * 0.028, 16, 12), new THREE.MeshBasicMaterial({ color: new THREE.Color(col) })); spin.add(head);
        const dur = ro.dur ?? 1.2, e = ease("power2.inOut");
        k.eachFrame((lt, t) => { const p = e(clamp((t - at2) / dur)); ln.geometry.instanceCount = Math.max(0, Math.round(p * n)); ln.visible = p > 0; head.visible = p > 0 && p < 1; head.position.fromArray(pts[Math.min(n, Math.round(p * n))]); });
        if (ro.marks !== false) { g.mark(at2 - 0.1, a, ro.fromLabel, ro); g.mark(at2 + dur * 0.9, b, ro.toLabel, ro); }
        return ln;
      };
      for (const m of o.marks || []) g.mark(m.at ?? at + 0.8, m.p, m.label, m);
      for (const r of o.routes || []) g.route(r.at ?? at + 1, r.from, r.to, r);
      k.hero(g, { sway: 0, tilt: 0.02 });
      return g;
    };

    /* ---- product turntable: an object built from primitives, spins in, keeps turning; callouts glued to parts ---- */
    const PRODUCTS = {
      phone(k, o, g) {
        const body = k.solid(k.rbox(3.1, 6.4, 0.34, 0.5, 5), o.color || "#2b2c31"); g.add(body);
        const scr = k.texture(512, 1056, (c, w, h) => {
          const gr = c.createLinearGradient(0, 0, w, h); gr.addColorStop(0, pal.accent2); gr.addColorStop(1, pal.accent); c.fillStyle = gr; c.fillRect(0, 0, w, h);
          c.fillStyle = "rgba(255,255,255,.92)"; c.font = "800 64px 'Inter Tight'"; c.textAlign = "center"; c.fillText(o.label || "9:41", w / 2, 230);
          c.fillStyle = "rgba(255,255,255,.22)"; for (let i = 0; i < 4; i++) { c.beginPath(); c.roundRect(48, 420 + i * 140, w - 96, 110, 26); c.fill(); }
        });
        const screen = new THREE.Mesh(new THREE.PlaneGeometry(2.86, 6.1), new THREE.MeshBasicMaterial({ map: scr })); screen.position.z = 0.172; g.add(screen);
        const isl = new THREE.Mesh(new THREE.CapsuleGeometry(0.11, 0.5, 4, 12), new THREE.MeshBasicMaterial({ color: 0x050505 })); isl.rotation.z = Math.PI / 2; isl.position.set(0, 2.8, 0.175); g.add(isl);
        const bump = k.solid(k.rbox(1.25, 1.25, 0.12, 0.3), mix(o.color || "#2b2c31", "#ffffff", 0.08)); bump.position.set(-0.75, 2.4, -0.2); g.add(bump);
        for (const [x, y] of [[-1.02, 2.66], [-0.5, 2.66], [-1.02, 2.14]]) { const l = k.solid(new THREE.CylinderGeometry(0.2, 0.2, 0.12, 28), "#15161a", { noEdges: true, rough: 0.2 }); l.rotation.x = Math.PI / 2; l.position.set(x, y, -0.28); g.add(l); }
        for (const y of [1.6, 0.9]) { const b = k.solid(k.rbox(0.06, 0.5, 0.12, 0.03), o.color || "#2b2c31", { noEdges: true }); b.position.set(1.57, y, 0); g.add(b); }
        return { screen: [0, 0, 0.2], camera: [-0.75, 2.4, -0.3], button: [1.6, 1.25, 0] };
      },
      can(k, o, g) {
        const r = 1.25, h = 4.2, lab = k.texture(1024, 512, (c, w, hh) => {
          c.fillStyle = o.color || pal.accent; c.fillRect(0, 0, w, hh); c.fillStyle = pal.accent2; c.fillRect(0, hh * 0.72, w, hh * 0.1);
          c.fillStyle = pal.ink; c.font = `${Math.round(hh * 0.3)}px Anton`; c.textAlign = "center"; c.textBaseline = "middle";
          for (const x of [w * 0.25, w * 0.75]) c.fillText(o.label || "FIZZ", x, hh * 0.45);
        });
        const side = new THREE.Mesh(new THREE.CylinderGeometry(r, r, h * 0.86, 64, 1, true), new THREE.MeshStandardMaterial({ map: lab, roughness: k.look.rough * 0.6, metalness: 0.25 }));
        side.castShadow = k.look.shadow > 0; g.add(side);
        const metal = { rough: 0.25, metal: 0.85 }, alu = "#c9ccd2";
        for (const s of [1, -1]) {
          const neck = k.solid(new THREE.CylinderGeometry(s > 0 ? r * 0.82 : r, s > 0 ? r : r * 0.86, h * 0.07, 64), alu, metal); neck.position.y = s * h * 0.465; g.add(neck);
          const lid = k.solid(new THREE.TorusGeometry(s > 0 ? r * 0.8 : r * 0.84, 0.06, 10, 64), alu, metal); lid.rotation.x = Math.PI / 2; lid.position.y = s * h * 0.5; g.add(lid);
        }
        const top = k.solid(new THREE.CircleGeometry(r * 0.8, 48), "#b8bcc4", { ...metal, noEdges: true }); top.rotation.x = -Math.PI / 2; top.position.y = h * 0.49; g.add(top);
        const tab = k.solid(k.rbox(0.5, 0.04, 0.8, 0.02), "#aeb2ba", metal); tab.position.set(0, h * 0.5, 0.25); g.add(tab);
        return { top: [0, h * 0.52, 0.25], label: [0, 0, r] };
      },
      box(k, o, g) {
        const w = 4, h = 2.8, d = 3, face = k.texture(800, 560, (c, W2, H2) => {
          c.fillStyle = o.color || pal.paper; c.fillRect(0, 0, W2, H2); c.fillStyle = pal.accent; c.fillRect(0, H2 * 0.68, W2, H2 * 0.14);
          c.fillStyle = "#1b1b1f"; c.font = `${Math.round(H2 * 0.24)}px Anton`; c.textAlign = "center"; c.textBaseline = "middle"; c.fillText(o.label || "PARCEL", W2 / 2, H2 * 0.38);
        });
        const b = k.solid(k.rbox(w, h, d, 0.12), o.color || pal.paper); g.add(b);
        // RoundedBoxGeometry has no face groups (a material array would draw nothing): the label is a decal plane
        if (!k.look.edges) { const dec = new THREE.Mesh(new THREE.PlaneGeometry(w * 0.9, h * 0.9), new THREE.MeshStandardMaterial({ map: face, roughness: k.look.rough })); dec.position.z = d / 2 + 0.005; g.add(dec); }
        const tape = k.solid(new THREE.BoxGeometry(0.7, 0.03, d + 0.02), pal.accent2, { noEdges: true }); tape.position.y = h / 2 + 0.01; g.add(tape);
        return { label: [0, 0, d / 2], top: [0, h / 2, 0] };
      },
      laptop(k, o, g) {
        const w = 5.6, base = k.solid(k.rbox(w, 0.24, 3.8, 0.12), o.color || "#c9ccd2", { rough: 0.35, metal: 0.4 }); base.position.y = 0.12; g.add(base);
        const kb = new THREE.Mesh(new THREE.PlaneGeometry(w * 0.86, 1.7), k.mat("#2a2c31")); kb.rotation.x = -Math.PI / 2; kb.position.set(0, 0.245, -0.25); g.add(kb);
        const hinge = new THREE.Group(); hinge.position.set(0, 0.24, -1.9); g.add(hinge);
        const lid = k.solid(k.rbox(w, 3.7, 0.16, 0.12), o.color || "#c9ccd2", { rough: 0.35, metal: 0.4 }); lid.position.set(0, 1.85, 0); hinge.add(lid);
        const scr = k.texture(1024, 640, (c, W2, H2) => {
          const gr = c.createLinearGradient(0, 0, W2, H2); gr.addColorStop(0, pal.accent2); gr.addColorStop(1, pal.accent); c.fillStyle = gr; c.fillRect(0, 0, W2, H2);
          c.fillStyle = "rgba(255,255,255,.9)"; c.font = "800 70px 'Inter Tight'"; c.textAlign = "center"; c.fillText(o.label || "", W2 / 2, H2 / 2 + 24);
        });
        const s = new THREE.Mesh(new THREE.PlaneGeometry(w * 0.9, 3.3), new THREE.MeshBasicMaterial({ map: scr })); s.position.set(0, 1.85, 0.085); hinge.add(s);
        hinge.rotation.x = Math.PI / 2 - 0.02;                      // closed, opens at o.openAt
        k.tl.to(hinge.rotation, { x: -0.22, duration: 1.0, ease: "power3.inOut" }, o.openAt ?? (o.at + 0.7));
        return { screen: [0, 2.2, -1.6], keyboard: [0, 0.3, 0.2] };
      },
      bottle(k, o, g) {
        const prof = [[0, 0], [1.05, 0], [1.15, 0.12], [1.15, 2.9], [1.0, 3.5], [0.5, 4.1], [0.46, 4.6], [0, 4.6]].map(([x, y]) => new THREE.Vector2(x, y - 2.3));
        const b = k.solid(new THREE.LatheGeometry(prof, 64), o.color || pal.accent2, { rough: 0.15, metal: 0.05 }); g.add(b);
        const lab = k.solid(new THREE.CylinderGeometry(1.17, 1.17, 1.4, 64, 1, true), pal.paper, { noEdges: true }); lab.position.y = -0.6; g.add(lab);
        const cap = k.solid(new THREE.CylinderGeometry(0.52, 0.52, 0.5, 40), pal.ink, { rough: 0.5 }); cap.position.y = 2.55; g.add(cap);
        return { cap: [0, 2.6, 0.5], label: [0, -0.6, 1.2] };
      },
    };
    k.product = (tl, at, kind = "phone", o = {}) => {
      const g = new THREE.Group(), inner = new THREE.Group(); g.add(inner); k.scene.add(g);
      const parts = (PRODUCTS[kind] || PRODUCTS.phone)(k, { ...o, at }, inner) || {};
      const bb = new THREE.Box3().setFromObject(inner), sz = bb.getSize(V3()), ctr = bb.getCenter(V3());
      const fitH = (o.size ?? (k.tall ? 0.58 : 0.72)) * k.safeH, fitW = 0.6 * k.safeW, s = Math.min(fitH / sz.y, fitW / Math.max(sz.x, sz.z));
      inner.position.sub(ctr); inner.position.y += sz.y / 2;          // base on y = 0
      g.scale.setScalar(s); const lift = o.y ?? -fitH * 0.5;
      k.camDefault({ ty: 0, el: 0.18 });
      if (o.ground !== false) k.ground({ y: lift });
      const spinIn = ease("power3.out"), pop = ease("back.out(1.3)"), turn = (o.turn ?? 40) * D2R, from = (o.from ?? -200) * D2R;
      k.eachFrame((lt, t) => {
        const p = clamp((t - at) / 1.3);
        g.rotation.y = from * (1 - spinIn(p)) + turn * Math.max(0, t - at) / 3 + (o.face ?? 0.35);   // spins in, then a slow turntable
        g.position.y = lift + (1 - pop(clamp((t - at) / 0.8))) * -fitH * 0.4 + (o.bob ?? 0.06) * Math.sin((t - at) * 1.7) * (p > 0 ? 1 : 0);
        g.scale.setScalar(s * Math.max(0.001, pop(clamp((t - at) / 0.8))));
      });
      // callouts: a dot on the part, a leader line out past the object's silhouette, the label clear of the object
      // (a label sitting on the part covers the very thing it names)
      const halfW = (Math.max(sz.x, sz.z) / 2) * s * 1.02, Rt = V3();
      for (const c of o.callouts || []) {   // {part: "camera" | [x, y, z] in object units, label, at, side}
        const lp = typeof c.part === "string" ? parts[c.part] : c.part; if (!lp) continue;
        const v = V3(...lp).add(inner.position), side = c.side === "left" ? -1 : 1, fs = c.size || (k.tall ? 42 : 34), ac = pal.accent;
        const wrap = document.createElement("div"); wrap.className = "x3tag"; Object.assign(wrap.style, { position: "absolute", left: 0, top: 0, width: 0, height: 0, pointerEvents: "none" });
        const mk = (css) => { const e = document.createElement("div"); Object.assign(e.style, { position: "absolute", left: 0, top: 0, ...css }); wrap.appendChild(e); return e; };
        const line = mk({ height: "4px", background: ac, borderRadius: "2px", transformOrigin: "0 50%" });
        const dot = mk({ width: "18px", height: "18px", borderRadius: "50%", background: ac, boxShadow: "0 0 0 6px rgba(0,0,0,.28)" });
        const txt = mk({ whiteSpace: "nowrap", font: `800 ${fs}px/1.1 "Inter Tight"`, color: pal.ink, textShadow: "0 2px 12px rgba(0,0,0,.5)" });
        txt.textContent = c.label; k.root.appendChild(wrap); let tw0 = null;   // the label's one-line width, measured once
        k._post.push(() => {
          const p = k.px(g.localToWorld(v.clone())), mid = V3(g.position.x, g.position.y + (sz.y * s) / 2, g.position.z);   // the object's axis, half way up
          Rt.setFromMatrixColumn(k.camera.matrixWorld, 0); const cx = k.px(mid)[0], rx = Math.abs(k.px(mid.clone().addScaledVector(Rt, halfW))[0] - cx);
          // a label never leaves the frame: it goes to the side it was asked for when it fits there, else to the other
          // side, else it wraps inside the room the wider side has (a long part name beside a big object on a phone)
          const gap = k.tall ? 50 : 70, room = (d) => (d > 0 ? k.W - 40 - (cx + rx + gap + 14) : cx - rx - gap - 14 - 40);
          if (tw0 == null) tw0 = txt.offsetWidth;
          let sd = side;
          if (tw0 > room(sd)) { if (tw0 <= room(-sd) || room(-sd) > room(sd)) sd = -sd; }
          const wrapW = tw0 > room(sd) ? Math.max(120, room(sd)) : 0;
          txt.style.whiteSpace = wrapW ? "normal" : "nowrap"; txt.style.width = wrapW ? wrapW.toFixed(0) + "px" : ""; txt.style.textAlign = sd > 0 ? "left" : "right";
          const ex = cx + sd * (rx + gap);
          dot.style.transform = `translate(${(p[0] - 9).toFixed(1)}px,${(p[1] - 9).toFixed(1)}px)`;
          line.style.width = Math.abs(ex - p[0]).toFixed(1) + "px"; line.style.transform = `translate(${Math.min(p[0], ex).toFixed(1)}px,${(p[1] - 2).toFixed(1)}px)`;
          txt.style.transform = `translate(${(sd > 0 ? ex + 14 : ex - 14).toFixed(1)}px,${p[1].toFixed(1)}px) translate(${sd > 0 ? 0 : -100}%,-50%)`;
        });
        tl.fromTo(wrap, { opacity: 0 }, { opacity: 1, duration: 0.4, ease: "power2.out" }, c.at ?? at + 1.4);
      }
      k.hero(g, { sway: 0 });
      g.parts = parts; g.inner = inner; return g;
    };

    /* ---- exploded view: slabs stacked tight, then they separate so every layer can be named ---- */
    k.explode = (tl, at, layers, o = {}) => {
      const n = layers.length, Wd = o.w ?? k.safeW * (k.tall ? 0.56 : 0.34), D = Wd * 0.72, th = o.th ?? Wd * 0.07, gap = o.gap ?? (k.tall ? k.safeH * 0.62 : k.safeH * 0.66) / Math.max(1, n - 1) - th;
      const g = new THREE.Group(), cx = o.x ?? (k.tall ? -k.safeW * 0.17 : -k.safeW * 0.12); g.position.x = cx; k.scene.add(g);
      k.camDefault({ az: 0.55, el: 0.42 });
      const total = n * th + (n - 1) * gap, stag = o.stagger ?? 0.08, dur = o.dur ?? 1.0, slabs = [];
      if (o.ground !== false) k.ground({ y: -total / 2 - 0.6 });
      layers.forEach((L, i) => {
        const tk = (L.th ?? 1) * th, geo = L.shape === "disc" ? new THREE.CylinderGeometry(Wd / 2, Wd / 2, tk, 64) : k.rbox(Wd, tk, D, Math.min(0.25, tk * 0.45));
        const m = k.solid(geo, L.color || k.c(i % 2 ? 1 : 0), L.glass ? { rough: 0.1 } : {}); g.add(m); slabs.push(m);
        const yc = (n / 2 - i - 0.5) * th, ye = total / 2 - i * (th + gap) - th / 2;   // compact / exploded height of layer i (top first)
        m.position.y = yc; tl.to(m.position, { y: ye, duration: dur, ease: "power3.inOut" }, at + i * stag);
        const zz = L.shape === "disc" ? [0] : [D / 2, -D / 2];   // the right corner that is further right on screen this frame
        if (L.label) k.tag(tl, at + dur * 0.6 + i * stag, () => zz.map((z) => g.localToWorld(V3(Wd / 2 + 0.1, m.position.y, z))).reduce((a, b) => (k.px(b)[0] > k.px(a)[0] ? b : a)),
          `<span style="display:inline-block;width:56px;height:5px;border-radius:3px;background:${L.color || k.c(i % 2 ? 1 : 0)};vertical-align:middle;margin-right:16px"></span>${L.label}`,
          { align: "left", dx: 12, size: o.size || (k.tall ? 42 : 36) });
      });
      k.eachFrame((lt) => { g.rotation.y = (o.sway ?? 0.12) * Math.sin(lt * 0.5); });
      k.hero(g, { sway: 0.03 });
      g.slabs = slabs; return g;
    };

    /* ---- city / data landscape: a grid of blocks rising in a wave from the centre; data[i][j] = 0..1 heights ---- */
    k.city = (tl, at, o = {}) => {
      const r = FX.rand(o.seed || 5), n = o.n ?? (o.data ? o.data.length : 9), m2 = o.data ? o.data[0].length : n, span = o.size ?? k.fit * 0.82, cell = span / Math.max(n, m2);
      const Hm = o.hmax ?? span * 0.45, g = new THREE.Group(); k.scene.add(g);
      k.camDefault({ az: Math.PI / 4, el: 0.6, fov: 20, dist: (k.d0 * Math.tan(15 * D2R)) / Math.tan(10 * D2R), ty: Hm * 0.12 });
      const hAt = (i, j) => { if (o.data) return o.data[i][j]; const x = i / (n - 1) - 0.5, y = j / (m2 - 1) - 0.5; return clamp(0.12 + 0.75 * Math.exp(-(x * x + y * y) * 5) + 0.25 * r(), 0.05, 1); };
      const plate = k.solid(k.rbox(span + cell * 0.6, cell * 0.25, span + cell * 0.6, cell * 0.12), o.base || (k.lookName === "neon" ? mix(pal.bg, pal.accent2, 0.25).getStyle() : k.lookName === "blueprint" ? pal.accent2 : pal.paper)); plate.position.y = -cell * 0.125; g.add(plate);
      const unit = k.rbox(cell * 0.8, 1, cell * 0.8, cell * 0.1); unit.translate(0, 0.5, 0);
      const marks = new Map((o.mark || []).map(([i, j, lab]) => [i + "," + j, lab])), wave = o.wave ?? 1.0, e = ease("back.out(1.2)"), blocks = [];
      const lo = new THREE.Color(o.low || pal.accent2), hi = new THREE.Color(o.high || pal.accent);
      for (let i = 0; i < n; i++) for (let j = 0; j < m2; j++) {
        const v = hAt(i, j), key = i + "," + j, col = marks.has(key) ? pal.hot : "#" + lo.clone().lerp(hi, v).getHexString();
        const b = k.solid(unit, col); b.position.set((i - (n - 1) / 2) * cell, 0, (j - (m2 - 1) / 2) * cell); g.add(b);
        const d = Math.hypot(i - (n - 1) / 2, j - (m2 - 1) / 2) / Math.hypot((n - 1) / 2, (m2 - 1) / 2), t0 = at + d * wave, h = Math.max(0.02, v * Hm);
        blocks.push([b, t0, h]);
        if (marks.get(key)) k.tag(tl, t0 + 0.5, () => g.localToWorld(V3(b.position.x, h + cell * 0.6, b.position.z)), marks.get(key), { color: pal.ink, css: { textShadow: "0 2px 12px rgba(0,0,0,.4)" } });
      }
      k.eachFrame((lt, t) => { for (const [b, t0, h] of blocks) { b.scale.y = Math.max(0.001, h * e(clamp((t - t0) / 0.7))); b.visible = t >= t0; } });
      if (o.ground !== false) k.ground({ y: -cell * 0.25 });
      k.hero(g, { sway: 0.17 });
      g.blocks = blocks; g.cell = cell; return g;
    };

    /* ---- fly-through: cards placed in depth, the camera travels from one to the next and holds on each.
       Card text is drawn on canvas textures; each title / sub has a DOM twin so the lint reads it. ---- */
    k.flythrough = (tl, at, cards, o = {}) => {
      const n = cards.length, cw = o.cw ?? (k.tall ? k.safeW * 0.86 : k.safeH * 1.15), chh = cw * (o.ratio ?? (k.tall ? 0.66 : 0.56));
      const every = o.every ?? (k.T.end - at) / n, hold = o.hold ?? 0.55, g = new THREE.Group(); k.scene.add(g);
      // a wide lens (50 degrees) so depth reads: at the stage's 30 degrees the viewing distance dwarfs the spacing
      const fov = o.fov ?? 50, dF = k.h / 2 / Math.tan((fov * D2R) / 2), Dv = dF * Math.max(cw / (0.9 * k.safeW), chh / (0.85 * k.safeH)), S = o.spacing ?? Dv * 1.3;
      const TX = 1100, TY = Math.round(TX * chh / cw);
      if (o.fog !== false) k.fog(Dv * 1.1, Dv + S * 2.4);
      // zigzag wide enough that the camera's straight flight passes beside each card, never through it
      const pos = cards.map((c, i) => V3(c.x ?? (o.zigzag === false ? 0 : (i % 2 ? 1 : -1) * cw * 0.6), c.y ?? 0, -i * S));
      cards.forEach((c, i) => {
        const col = c.color || (i % 2 ? pal.accent2 : pal.accent), ink = c.ink || "#111318";
        const lay = { pad: 80 };
        const tex = k.texture(TX, TY, (x, w, h) => {   // kicker / big title / sub, the block centred vertically
          x.fillStyle = col; x.beginPath(); x.roundRect(0, 0, w, h, 60); x.fill();
          x.fillStyle = ink; x.textBaseline = "alphabetic";
          let fs = c.size || 230; x.font = `${fs}px Anton`; while (x.measureText(c.title).width > w - 2 * lay.pad && fs > 40) { fs -= 4; x.font = `${fs}px Anton`; }
          let sf = 66; if (c.sub) { x.font = `600 ${sf}px 'Inter Tight'`; while (x.measureText(c.sub).width > w - 2 * lay.pad && sf > 30) { sf -= 2; x.font = `600 ${sf}px 'Inter Tight'`; } }
          const kh = c.kicker ? 90 : 0, block = kh + fs * 0.9 + (c.sub ? sf * 1.6 : 0), y0 = (h - block) / 2;
          if (c.kicker) { x.font = "700 60px 'Inter Tight'"; x.globalAlpha = 0.72; x.fillText(c.kicker, lay.pad, y0 + 56); x.globalAlpha = 1; }
          x.font = `${fs}px Anton`; lay.tfs = fs; lay.ty = y0 + kh + fs * 0.9; lay.tw = x.measureText(c.title).width; x.fillText(c.title, lay.pad, lay.ty);
          if (c.sub) { x.font = `600 ${sf}px 'Inter Tight'`; lay.sfs = sf; lay.sy = lay.ty + sf * 1.6; lay.sw = x.measureText(c.sub).width; x.fillText(c.sub, lay.pad, lay.sy); }
        });
        const card = new THREE.Group(); card.position.copy(pos[i]); card.rotation.y = (pos[i].x > 0 ? -1 : 1) * (o.yaw ?? 0.2); g.add(card);
        const slab = k.solid(k.rbox(cw, chh, 0.12, 0.25), col, { noShadow: true }); card.add(slab);
        const face = new THREE.Mesh(new THREE.PlaneGeometry(cw, chh), new THREE.MeshBasicMaterial({ map: tex, transparent: true, fog: true })); face.position.z = 0.065; card.add(face);
        const u = cw / TX, toL = (px, py) => V3(-cw / 2 + px * u, chh / 2 - py * u, 0.07);   // canvas px -> card space
        const vis = () => { const d = k.camera.position.distanceTo(card.position); return d < Dv * 2.2 ? 1 : 0; };
        k.twin(c.title, () => { card.updateMatrixWorld(true); const a = toL(lay.pad, lay.ty - lay.tfs * 0.74), b = toL(lay.pad + lay.tw, lay.ty); return { box: projBox(k, card, V3(a.x, b.y, 0.07), V3(b.x, a.y, 0.07)), alpha: vis() }; }, ink, "400 100px Anton");
        if (c.sub) k.twin(c.sub, () => { const a = toL(lay.pad, lay.sy - lay.sfs * 0.75), b = toL(lay.pad + lay.sw, lay.sy); return { box: projBox(k, card, V3(a.x, b.y, 0.07), V3(b.x, a.y, 0.07)), alpha: vis() }; }, ink, "600 100px 'Inter Tight'");
      });
      // the rail: hold on card i for `hold` of its slot, travel to i + 1 in the rest (ease in-out), start pushed back
      const view = (i) => { const p = pos[Math.max(0, Math.min(n - 1, i))]; return { pos: [p.x, p.y + chh * 0.04, p.z + Dv], look: [p.x, p.y, p.z], fov }; };
      const start = { pos: [pos[0].x * 0.4, chh * 0.5, Dv + S * 0.8], look: [pos[0].x, 0, 0], fov }, e = E.ease_in_out;
      const L3 = (a, b, p) => a.map((v, j) => lerp(v, b[j], p));
      k.path((t) => {
        const u2 = (t - at) / every;
        if (u2 < 0) return start;
        if (u2 < 0.6) { const p = e(clamp(u2 / 0.6)), v = view(0); return { pos: L3(start.pos, v.pos, p), look: L3(start.look, v.look, p), fov }; }
        const s = u2 - 0.6, i = Math.floor(s), f = s - i;
        if (i >= n - 1) return view(n - 1);
        const p = f < hold ? 0 : e((f - hold) / (1 - hold)), a = view(i), b = view(i + 1);
        const arc = Math.sin(Math.PI * p) * cw * 0.06, roll = (o.bank ?? 0.07) * Math.sin(Math.PI * p) * Math.sign(b.pos[0] - a.pos[0]);   // lift + bank: a flight, not a slide
        return { pos: L3(a.pos, b.pos, p).map((v, j) => v + (j === 1 ? arc : 0)), look: L3(a.look, b.look, p), fov, roll };
      });
      return g;
    };

    /* ---- swarm: instanced particles fly from a seeded cloud into a shape (a word or number, a sphere, a ring, a grid) ---- */
    const textPoints = (str, n, r, font) => {   // pixels of the text on a canvas -> n points, seeded pick, centred, unit width
      const c = document.createElement("canvas"), x = c.getContext("2d", { willReadFrequently: true }), fs = 220;
      x.font = `${fs}px ${font || "Anton"}`; const w = Math.ceil(x.measureText(str).width) + 20; c.width = w; c.height = fs * 1.2;
      x.font = `${fs}px ${font || "Anton"}`; x.fillStyle = "#fff"; x.textBaseline = "middle"; x.fillText(str, 10, c.height / 2);
      const d = x.getImageData(0, 0, c.width, c.height).data, px = [];
      for (let yy = 0; yy < c.height; yy += 3) for (let xx = 0; xx < c.width; xx += 3) if (d[(yy * c.width + xx) * 4 + 3] > 128) px.push([xx, yy]);
      const out = []; for (let i = 0; i < n; i++) { const p = px[Math.floor(r() * px.length)] || [0, 0]; out.push([(p[0] - c.width / 2) / c.width, -(p[1] - c.height / 2) / c.width, (r() - 0.5) * 0.03]); }
      return { pts: out, aspect: c.height / c.width };
    };
    const shapePoints = (sh, n, r, S, k) => {
      const out = [];
      if (sh.text !== undefined || sh.shape === "text") {
        const tp = textPoints(String(sh.text ?? "3D"), n, r, sh.font), Wt = Math.min(S * 1.9, (k.safeH * 0.4) / tp.aspect);
        return tp.pts.map(([x, y, z]) => [x * Wt, y * Wt, z * Wt]);
      }
      for (let i = 0; i < n; i++) {
        const u = r(), v = r();
        if (sh.shape === "ring") { const a = u * Math.PI * 2, rr = S * (0.8 + 0.12 * (v - 0.5)); out.push([rr * Math.cos(a), rr * Math.sin(a), (r() - 0.5) * S * 0.12]); }
        else if (sh.shape === "grid") { const q = Math.ceil(Math.sqrt(n)), gi = i % q, gj = Math.floor(i / q); out.push([(gi / (q - 1) - 0.5) * S * 1.7, (gj / (q - 1) - 0.5) * S * 1.7, 0]); }
        else if (sh.shape === "cube") { const f = Math.floor(u * 6), a = (r() - 0.5) * 2, b = (r() - 0.5) * 2, c3 = [a, b, f % 2 ? 1 : -1]; out.push([c3[(f >> 1) % 3], c3[((f >> 1) + 1) % 3], c3[((f >> 1) + 2) % 3]].map((q) => q * S * 0.6)); }
        else { const y = 1 - (2 * (i + 0.5)) / n, rr = Math.sqrt(1 - y * y), a = i * 2.39996; out.push([S * rr * Math.cos(a), S * y, S * rr * Math.sin(a)]); }   // sphere (Fibonacci)
      }
      return out;
    };
    k.swarm = (tl, at, o = {}) => {
      const r = FX.rand(o.seed || 11), n = o.n ?? (o.text !== undefined ? 2200 : 1400), S = o.size ?? k.fit * 0.42, dur = o.dur ?? 1.6, spread = o.spread ?? 0.7;
      const A = shapePoints(o, n, r, S, k), B = o.then ? shapePoints(o.then, n, r, S, k) : null;
      const cloud = []; for (let i = 0; i < n; i++) { const a = r() * Math.PI * 2, b = Math.acos(2 * r() - 1), rr = Math.max(k.w, k.h) * (0.45 + 0.5 * r()); cloud.push([rr * Math.sin(b) * Math.cos(a), rr * Math.cos(b) * 0.8, rr * Math.sin(b) * Math.sin(a) - 2]); }
      const delay = [], wob = []; for (let i = 0; i < n; i++) { delay.push(r() * spread); wob.push([r() - 0.5, r() - 0.5, r() - 0.5, r() * 6.28]); }
      const geo = o.cube ? new THREE.BoxGeometry(1, 1, 1) : new THREE.IcosahedronGeometry(0.5, 1), sz = o.dot ?? S * (o.text !== undefined ? 0.034 : 0.05);
      const mesh = new THREE.InstancedMesh(geo, k.lookName === "blueprint" || k.lookName === "neon" ? new THREE.MeshBasicMaterial({ color: 0xffffff }) : k.mat("#ffffff"), n);
      mesh.castShadow = k.look.shadow > 0; mesh.frustumCulled = false;
      const ca = new THREE.Color(o.color || pal.accent), cb = new THREE.Color(o.color2 || pal.accent2), tmp = new THREE.Color();
      for (let i = 0; i < n; i++) { mesh.setColorAt(i, tmp.copy(ca).lerp(cb, clamp(0.5 + A[i][0] / (S * 2)) * 0.9 + 0.1 * r())); }
      k.scene.add(mesh);
      const e = ease(o.ease || "power3.inOut"), m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), P = V3(), Sc = V3();
      const tB = o.then ? o.then.at : Infinity;
      k.eachFrame((lt, t) => {
        for (let i = 0; i < n; i++) {
          const pa = e(clamp((t - at - delay[i]) / dur)), w = wob[i], amp = Math.sin(Math.PI * pa) * S * 0.6;
          let x = lerp(cloud[i][0], A[i][0], pa) + w[0] * amp, y = lerp(cloud[i][1], A[i][1], pa) + w[1] * amp, z = lerp(cloud[i][2], A[i][2], pa) + w[2] * amp;
          if (B) { const pb = e(clamp((t - tB - delay[i] * 0.6) / dur)), ab = Math.sin(Math.PI * pb) * S * 0.5; x = lerp(x, B[i][0], pb) + w[2] * ab; y = lerp(y, B[i][1], pb) + w[0] * ab; z = lerp(z, B[i][2], pb) + w[1] * ab; }
          const br = 0.04 * S * Math.sin(lt * 1.3 + w[3]);   // breathing once formed: alive, but the shape still reads
          P.set(x + w[0] * br, y + w[1] * br, z + w[2] * br); q.setFromAxisAngle(Sc.set(0, 1, 0), w[3] + lt * 0.8); const sc = sz * (0.7 + 0.6 * Math.abs(w[1]) + 0.3); Sc.set(sc, sc, sc);
          mesh.setMatrixAt(i, m4.compose(P, q, Sc));
        }
        mesh.instanceMatrix.needsUpdate = true;
        mesh.rotation.y = (o.turn ?? (o.text !== undefined ? 0.1 : 0.35)) * Math.sin(lt * 0.45);
      });
      // a word or number made of particles gets a DOM twin once it has formed
      for (const [sh, t0, t1] of [[o, at + spread + dur * 0.8, B ? tB : Infinity], ...(B ? [[o.then, tB + 0.6 * spread + dur * 0.8, Infinity]] : [])]) {
        if (sh.text === undefined) continue;
        const pts = sh === o ? A : B; let x0 = 1e9, x1 = -1e9, y0 = 1e9, y1 = -1e9; for (const p of pts) { x0 = Math.min(x0, p[0]); x1 = Math.max(x1, p[0]); y0 = Math.min(y0, p[1]); y1 = Math.max(y1, p[1]); }
        k.twin(String(sh.text), (t) => ({ box: projBox(k, mesh, V3(x0, y0, 0), V3(x1, y1, 0)), alpha: t >= t0 && t < t1 ? 1 : 0 }), sh.color || pal.accent, twinFont("anton"));
      }
      if (o.ground !== false && k.look.shadow > 0) k.ground({ y: -S * 1.35 });
      k.hero(mesh, { sway: 0.05 });
      return mesh;
    };

    /* ---- stack: piles of coins / bills / blocks dropping in, one column per item, for "how much bigger" ---- */
    const UNITS = {
      // a minted coin: raised rim, recessed face (a lathe profile), not a plain cylinder
      coin: (k) => ({ geo: new THREE.LatheGeometry([[0, -0.05], [0.4, -0.05], [0.43, -0.065], [0.5, -0.065], [0.5, 0.065], [0.43, 0.065], [0.4, 0.05], [0, 0.05]].map(([x, y]) => new THREE.Vector2(x, y)).reverse(), 40), h: 0.135, w: 1.0, color: "#e8b13a", jit: 0.05, metal: { rough: 0.3, metal: 0.75 } }),
      cash: (k) => ({ geo: k.rbox(1.25, 0.07, 0.6, 0.02), h: 0.072, w: 1.3, color: "#5fae6e", jit: 0.03, metal: {} }),
      block: (k) => ({ geo: k.rbox(0.62, 0.62, 0.62, 0.1), h: 0.64, w: 0.7, color: null, jit: 0.0, metal: {} }),
    };
    k.stack = (tl, at, items, o = {}) => {
      const U = (UNITS[o.unit] || UNITS.coin)(k), n = items.length, r = FX.rand(o.seed || 3), cap = o.cap ?? 60;
      const counts = items.map((it) => Math.max(1, Math.min(cap, Math.round(it.n)))), maxN = Math.max(...counts);
      // height carries the ratio, so one stack per item; past 40 pieces a column would be a needle on a phone, so it
      // splits into 2 (or o.piles: 1, 2, 4) side-by-side stacks
      const m = o.piles ?? (maxN > 40 ? 2 : 1), OFF = { 1: [[0, 0]], 2: [[-0.53, 0], [0.53, 0]], 4: [[-0.53, -0.53], [0.53, -0.53], [-0.53, 0.53], [0.53, 0.53]] }[m] || [[0, 0]];
      const lv = (c) => Math.ceil(c / m), Hm = o.hmax ?? (k.tall ? k.safeH * 0.6 : k.safeH * 0.68), foot = U.w * (m > 1 ? 2.1 : 1), step = foot * 1.45;
      const s = Math.min(Hm / (lv(maxN) * U.h), (Math.min(k.safeW * 0.92, k.safeH * 1.6) / n) / step);
      const g = new THREE.Group(), y0 = o.y ?? -(lv(maxN) * U.h * s) / 2; g.scale.setScalar(s); g.position.y = y0; k.scene.add(g);
      k.camDefault({ el: 0.3 });
      if (o.ground !== false) k.ground({ y: y0 });
      const drop = ease("bounce.out"), dur = o.dur ?? 1.4, mat0 = k.mat(o.color || U.color || pal.accent, U.metal), m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), P = V3(), one = V3(1, 1, 1), tiny = V3(1e-4, 1e-4, 1e-4), Y = V3(0, 1, 0);
      items.forEach((it, i) => {
        const c = counts[i], x = (i - (n - 1) / 2) * step, mesh = new THREE.InstancedMesh(U.geo, it.color ? k.mat(it.color, U.metal) : U.color ? mat0 : k.mat(k.c(i), U.metal), c);
        mesh.castShadow = mesh.receiveShadow = k.look.shadow > 0; mesh.frustumCulled = false; g.add(mesh);
        const t0 = at + i * (o.colStagger ?? 0.35), dt = Math.min(0.06, dur / c), jit = []; for (let j = 0; j < c; j++) jit.push([(r() - 0.5) * U.jit * 2, (r() - 0.5) * U.jit * 2, r() * 6.28]);
        const landed = (t) => clamp(Math.floor((t - t0) / dt + 1), 0, c), fall = U.h * lv(maxN) * 1.2 + 2;
        k.eachFrame((lt, t) => {
          for (let j = 0; j < c; j++) {
            const p = clamp((t - t0 - j * dt) / 0.45), o2 = OFF[j % m], yy = U.h * (Math.floor(j / m) + 0.5) + (1 - drop(p)) * fall;
            P.set(x + o2[0] * U.w + jit[j][0], yy, o2[1] * U.w + jit[j][1]); q.setFromAxisAngle(Y, jit[j][2]); mesh.setMatrixAt(j, m4.compose(P, q, p > 0 ? one : tiny));
          }
          mesh.instanceMatrix.needsUpdate = true;
        });
        let now = 0; k.eachFrame((lt, t) => { now = landed(t); });   // registered before the tag, which reads it this frame
        const top = k.tag(null, null, () => g.localToWorld(V3(x, U.h * Math.max(1, lv(now)) + 0.35 / s * 0.6, 0)), "", { size: k.tall ? 56 : 44, color: i === o.highlight ? pal.hot : pal.ink, dy: -14 });
        k.eachFrame((lt, t) => { const f = now / c; top.updateText(it.value !== undefined ? (o.prefix || "") + fmtNum(it.value * f, o.decimals ?? 0, ",") + (o.suffix || "") : fmtNum(Math.round(it.n * f), 0, ",")); top.style.opacity = f > 0 ? 1 : 0; });
        if (it.label) k.tag(tl, t0, () => g.localToWorld(V3(x, 0, foot * 0.75)), it.label, { size: k.tall ? 40 : 32, color: pal.muted, dy: k.tall ? 40 : 30 });
      });
      k.hero(g, { sway: 0.17 });
      return g;
    };
  });

  /* coarse continent outlines [lon, lat] for the dotted globe (our own simplification, ~10° accuracy: it reads as Earth
     at phone size; not a map for borders) */
  const LAND = [
    [[-168, 66], [-162, 70], [-140, 70], [-120, 72], [-95, 72], [-80, 73], [-65, 62], [-60, 55], [-53, 47], [-66, 44], [-70, 41], [-76, 35], [-81, 31], [-80, 25], [-82, 28], [-84, 30], [-90, 29], [-97, 26], [-97, 22], [-92, 18], [-87, 21], [-88, 16], [-83, 10], [-79, 9], [-82, 8], [-86, 12], [-92, 14], [-105, 20], [-110, 24], [-112, 30], [-118, 34], [-124, 40], [-124, 48], [-130, 55], [-140, 60], [-150, 60], [-158, 57], [-165, 60]],
    [[-45, 60], [-20, 70], [-18, 80], [-35, 83], [-60, 82], [-72, 77], [-55, 68]],
    [[-80, 9], [-72, 12], [-62, 10], [-50, 0], [-35, -5], [-39, -13], [-41, -22], [-48, -26], [-53, -34], [-58, -38], [-62, -41], [-65, -46], [-68, -52], [-72, -50], [-74, -42], [-71, -30], [-70, -18], [-76, -14], [-81, -5], [-80, 0], [-77, 4]],
    [[-10, 36], [-9, 43], [-2, 44], [-4, 48], [2, 51], [8, 54], [10, 58], [5, 62], [14, 67], [25, 71], [40, 68], [60, 70], [70, 73], [80, 73], [100, 78], [115, 73], [140, 72], [160, 70], [180, 68], [180, 65], [170, 60], [160, 55], [156, 51], [142, 47], [140, 40], [130, 34], [122, 30], [120, 22], [108, 21], [106, 10], [100, 13], [100, 3], [104, 1], [98, 8], [94, 16], [90, 22], [80, 15], [77, 8], [72, 20], [66, 25], [57, 25], [56, 27], [50, 30], [48, 29], [52, 24], [56, 22], [59, 22], [52, 16], [43, 13], [39, 20], [35, 28], [33, 31], [35, 36], [27, 37], [26, 40], [23, 36], [21, 40], [19, 42], [12, 44], [14, 41], [16, 38], [10, 44], [3, 43], [-1, 37]],
    [[-17, 15], [-17, 21], [-13, 28], [-6, 36], [10, 37], [11, 33], [20, 31], [32, 31], [35, 28], [39, 20], [43, 12], [51, 12], [48, 5], [40, -3], [40, -10], [35, -24], [32, -29], [27, -34], [20, -35], [18, -30], [12, -17], [13, -6], [9, 0], [9, 4], [4, 6], [-8, 4], [-13, 8], [-17, 13]],
    [[114, -22], [122, -18], [130, -12], [137, -12], [142, -11], [146, -19], [153, -26], [151, -34], [146, -39], [140, -38], [135, -35], [129, -32], [115, -34]],
    [[-5, 50], [1, 51], [2, 53], [-3, 56], [-2, 58], [-5, 58], [-6, 55], [-5, 53]],
    [[130, 31], [135, 34], [140, 36], [142, 40], [141, 45], [144, 44], [140, 41], [137, 37], [132, 34]],
    [[44, -25], [47, -25], [50, -15], [49, -12], [44, -17]],
    [[109, 1], [114, 4], [118, 6], [119, 0], [116, -4], [110, -3]], [[95, 5], [98, 4], [106, -6], [102, -4]], [[131, -1], [141, -3], [150, -10], [142, -9], [138, -8]],
    [[172, -34], [178, -38], [174, -42], [167, -46], [171, -44]], [[-24, 64], [-14, 64], [-14, 66], [-22, 66]],
  ];
  function isLand(lon, lat) {
    if (lat < -70) return true;   // Antarctica
    for (const poly of LAND) {
      let inside = false;
      for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
        const [xi, yi] = poly[i], [xj, yj] = poly[j];
        if ((yi > lat) !== (yj > lat) && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) inside = !inside;
      }
      if (inside) return true;
    }
    return false;
  }
  X.isLand = isLand;
})();
