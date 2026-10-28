/* FX — the motion designer's recipe library for explainer scenes (loaded by explainer_shell.html).
   Everything is deterministic: tweens go on the master timeline `tl` at absolute times; per-frame drawing (canvas,
   Three.js) registers with FX.onFrame and is driven by window.render(t). No timers, no real-time loops, no randomness
   except the seeded FX.rand. Written for this factory (ideas from public motion vocabularies: split/blur/scramble
   text, shine, spotlight, glass, draw-on paths, count-ups, seeded particles, aurora fields, deterministic 3D). */
(function () {
  const FX = {};
  const frameHooks = [];
  FX._hooks = frameHooks;
  FX.onFrame = (fn) => { fn.scene = FX._scene; frameHooks.push(fn); };   // tagged with the scene being built (motion lint)
  FX.rand = (seed = 1) => () => { seed |= 0; seed = (seed + 0x6d2b79f5) | 0; let t = Math.imul(seed ^ (seed >>> 15), 1 | seed); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };

  function split(el, by) {
    const text = el.textContent;
    el.textContent = "";
    const parts = by === "chars" ? [...text] : text.split(/(\s+)/);
    return parts.map((p) => {
      if (/^\s+$/.test(p)) { el.appendChild(document.createTextNode(p)); return null; }
      const s = document.createElement("span");
      s.textContent = p; s.style.display = "inline-block"; s.style.whiteSpace = "pre";
      el.appendChild(s); return s;
    }).filter(Boolean);
  }
  FX.split = split;

  /* text entrances: blurIn (word by word from blur), rise (masked slide up), pop (scale with a little overshoot),
     typewriter, scramble (decodes into the final word). All return the spans. */
  FX.blurWords = (tl, el, at, o = {}) => { const w = split(el, o.by || "words"); tl.fromTo(w, { opacity: 0, filter: "blur(14px)", y: 18 }, { opacity: 1, filter: "blur(0px)", y: 0, duration: o.dur || 0.55, stagger: o.stagger ?? 0.06, ease: "power3.out" }, at); return w; };
  FX.rise = (tl, el, at, o = {}) => { const w = split(el, o.by || "words"); w.forEach((s) => { const m = document.createElement("span"); m.style.display = "inline-block"; m.style.overflow = "hidden"; m.style.verticalAlign = "bottom"; s.parentNode.insertBefore(m, s); m.appendChild(s); }); tl.fromTo(w, { yPercent: 110 }, { yPercent: 0, duration: o.dur || 0.6, stagger: o.stagger ?? 0.05, ease: "expo.out" }, at); return w; };
  FX.pop = (tl, el, at, o = {}) => { const w = split(el, o.by || "words"); tl.fromTo(w, { opacity: 0, scale: 0.6 }, { opacity: 1, scale: 1, duration: o.dur || 0.45, stagger: o.stagger ?? 0.05, ease: "back.out(2)" }, at); return w; };
  FX.typewriter = (tl, el, at, o = {}) => { const c = split(el, "chars"); tl.fromTo(c, { opacity: 0 }, { opacity: 1, duration: 0.01, stagger: o.cps ? 1 / o.cps : 0.035, ease: "none" }, at); return c; };
  FX.scramble = (tl, el, at, o = {}) => {
    const final = el.textContent, glyphs = o.glyphs || "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789#%&", dur = o.dur || 0.9, r = FX.rand(final.length * 7 + 3);
    const table = [...Array(40)].map(() => [...final].map((ch) => (ch === " " ? " " : glyphs[Math.floor(r() * glyphs.length)])).join(""));
    const st = { p: 0 };
    tl.fromTo(st, { p: 0 }, { p: 1, duration: dur, ease: "none", onUpdate: () => {
      const k = Math.floor(st.p * final.length), j = Math.min(39, Math.floor(st.p * 40));
      el.textContent = final.slice(0, k) + table[j].slice(k);
    } }, at);
    return el;
  };
  /* emphasis */
  FX.shine = (tl, el, at, o = {}) => { el.style.backgroundImage = `linear-gradient(110deg, ${o.base || "currentColor"} 40%, ${o.light || "#fff"} 50%, ${o.base || "currentColor"} 60%)`; el.style.backgroundSize = "250% 100%"; el.style.webkitBackgroundClip = "text"; el.style.backgroundClip = "text"; el.style.color = "transparent"; tl.fromTo(el, { backgroundPosition: "120% 0" }, { backgroundPosition: "-120% 0", duration: o.dur || 1.2, ease: "power1.inOut" }, at); };
  FX.gradientText = (el, colors) => { el.style.backgroundImage = `linear-gradient(90deg, ${colors.join(",")})`; el.style.webkitBackgroundClip = "text"; el.style.backgroundClip = "text"; el.style.color = "transparent"; };
  FX.highlight = (tl, el, at, o = {}) => { el.style.backgroundImage = `linear-gradient(${o.color || "var(--accent)"}, ${o.color || "var(--accent)"})`; el.style.backgroundRepeat = "no-repeat"; el.style.backgroundPosition = "0 88%"; tl.fromTo(el, { backgroundSize: "0% 40%" }, { backgroundSize: "100% 40%", duration: o.dur || 0.45, ease: "power2.out" }, at); };
  FX.countUp = (tl, el, at, to, o = {}) => { const st = { v: o.from || 0 }, dec = o.decimals || 0; tl.fromTo(st, { v: o.from || 0 }, { v: to, duration: o.dur || 0.9, ease: "power2.out", onUpdate: () => { el.textContent = (o.prefix || "") + st.v.toLocaleString(o.locale || "en-US", { minimumFractionDigits: dec, maximumFractionDigits: dec }) + (o.suffix || ""); } }, at); };
  /* lines + shapes: draw an SVG path / rect / circle on (stroke-dashoffset) */
  FX.drawOn = (tl, path, at, o = {}) => { const len = path.getTotalLength ? path.getTotalLength() : 1000; path.style.strokeDasharray = len; tl.fromTo(path, { strokeDashoffset: len }, { strokeDashoffset: 0, duration: o.dur || 0.8, ease: o.ease || "power2.inOut" }, at); };
  FX.svg = (root, w, h) => { const s = document.createElementNS("http://www.w3.org/2000/svg", "svg"); s.setAttribute("width", w); s.setAttribute("height", h); s.setAttribute("viewBox", `0 0 ${w} ${h}`); Object.assign(s.style, { position: "absolute", left: 0, top: 0, overflow: "visible" }); root.appendChild(s); return s; };
  FX.el = (svg, tag, attrs) => { const e = document.createElementNS("http://www.w3.org/2000/svg", tag); for (const [k, v] of Object.entries(attrs || {})) e.setAttribute(k, v); svg.appendChild(e); return e; };
  /* annotation recipes over pictures: box with a tab label, pin with a leader line */
  FX.boxLabel = (tl, root, at, b, label, o = {}) => {
    const W = root.clientWidth || 1080, H = root.clientHeight || 1920, svg = FX.svg(root, W, H), c = o.color || "#fff";
    const r = FX.el(svg, "rect", { x: b[0] * W, y: b[1] * H, width: b[2] * W, height: b[3] * H, rx: 10, fill: "none", stroke: c, "stroke-width": o.stroke || 6 });
    FX.drawOn(tl, r, at, { dur: o.dur || 0.9 });
    if (label) { const t = document.createElement("div"); t.textContent = label; Object.assign(t.style, { position: "absolute", left: b[0] * W + "px", top: b[1] * H - 46 + "px", padding: "6px 12px", background: c, color: o.ink || "#111", font: "800 26px Inter Tight", letterSpacing: ".04em", borderRadius: "8px", textTransform: "uppercase" }); root.appendChild(t); tl.fromTo(t, { opacity: 0, y: 12 }, { opacity: 1, y: 0, duration: 0.35, ease: "power3.out" }, at + 0.5); }
    return svg;
  };
  FX.pinLabel = (tl, root, at, p, label, o = {}) => {
    const W = root.clientWidth || 1080, H = root.clientHeight || 1920, c = o.color || "#fff", dx = o.dx ?? -160, dy = o.dy ?? -120;
    const svg = FX.svg(root, W, H), x = p[0] * W, y = p[1] * H;
    const dot = FX.el(svg, "circle", { cx: x, cy: y, r: 12, fill: o.dot || "#e5483f", stroke: c, "stroke-width": 4 });
    const line = FX.el(svg, "path", { d: `M${x},${y} L${x + dx},${y + dy}`, stroke: c, "stroke-width": 4, fill: "none" });
    tl.fromTo(dot, { scale: 0, transformOrigin: "50% 50%" }, { scale: 1, duration: 0.35, ease: "back.out(3)" }, at);
    FX.drawOn(tl, line, at + 0.15, { dur: 0.4 });
    const t = document.createElement("div"); t.textContent = label;
    Object.assign(t.style, { position: "absolute", left: x + dx - 70 + "px", top: y + dy - 52 + "px", padding: "6px 14px", background: c, color: o.ink || "#111", font: "900 30px Inter Tight", borderRadius: "10px" });
    root.appendChild(t); tl.fromTo(t, { opacity: 0, scale: 0.8 }, { opacity: 1, scale: 1, duration: 0.3, ease: "back.out(2)" }, at + 0.45);
    return svg;
  };
  /* camera over a full-bleed picture: push / pan / zoom into a focus point */
  FX.camera = (tl, wrap, T, o = {}) => {
    const f = o.focus || [0.5, 0.5], from = o.from || 1.08, to = o.to || 1.2, mv = o.move || "push_in";
    gsap.set(wrap, { transformOrigin: `${f[0] * 100}% ${f[1] * 100}%` });
    const v = { push_in: [{ scale: from }, { scale: to }], pull_out: [{ scale: to }, { scale: from }], pan_left: [{ scale: 1.15, xPercent: 4 }, { scale: 1.15, xPercent: -4 }],
                pan_right: [{ scale: 1.15, xPercent: -4 }, { scale: 1.15, xPercent: 4 }], tilt_up: [{ scale: 1.15, yPercent: 4 }, { scale: 1.15, yPercent: -4 }],
                tilt_down: [{ scale: 1.15, yPercent: -4 }, { scale: 1.15, yPercent: 4 }], hold: [{ scale: 1.06 }, { scale: 1.09 }] }[mv] || [{ scale: from }, { scale: to }];
    tl.fromTo(wrap, v[0], { ...v[1], duration: Math.max(0.5, T.dur), ease: "sine.inOut" }, T.start);
    if (mv === "zoom_to" && o.at != null) tl.to(wrap, { scale: o.zoom || 2.2, duration: 0.9, ease: "power3.inOut" }, o.at);
  };
  /* surfaces */
  FX.glass = (el, o = {}) => Object.assign(el.style, { background: o.bg || "rgba(255,255,255,.10)", backdropFilter: `blur(${o.blur || 18}px) saturate(1.4)`, border: "1px solid rgba(255,255,255,.22)", borderRadius: (o.r || 28) + "px", boxShadow: "0 20px 60px -20px rgba(0,0,0,.55), inset 0 1px 0 rgba(255,255,255,.25)" });
  FX.spotlight = (tl, root, at, p, o = {}) => { const d = document.createElement("div"); Object.assign(d.style, { position: "absolute", inset: 0, pointerEvents: "none", background: `radial-gradient(circle at ${p[0] * 100}% ${p[1] * 100}%, transparent 0, transparent var(--r), rgba(0,0,0,${o.dark || 0.72}) calc(var(--r) + 60px))` }); root.appendChild(d); tl.fromTo(d, { "--r": "900px" }, { "--r": (o.r || 220) + "px", duration: o.dur || 0.8, ease: "power3.inOut" }, at); return d; };
  FX.aurora = (root, T, o = {}) => {   // soft moving colour field on a canvas, seeded and time-driven
    const W = root.clientWidth || 1080, H = root.clientHeight || 1920, c = document.createElement("canvas"); c.width = W / 4; c.height = H / 4;
    Object.assign(c.style, { position: "absolute", inset: 0, width: "100%", height: "100%", filter: "blur(40px)", opacity: o.opacity || 0.8 }); root.prepend(c);
    const g = c.getContext("2d"), cols = o.colors || ["#7aa2ff", "#ff7ab6", "#5ef0c8"], r = FX.rand(o.seed || 5), blobs = cols.map((col) => ({ col, x: r(), y: r(), s: 0.3 + r() * 0.4, p: r() * 6 }));
    FX.onFrame((t) => { if (t < T.start - 0.1 || t > T.end + 0.1) return; g.clearRect(0, 0, c.width, c.height); for (const b of blobs) { const x = (b.x + 0.15 * Math.sin(t * 0.35 + b.p)) * c.width, y = (b.y + 0.12 * Math.cos(t * 0.28 + b.p)) * c.height, rad = b.s * c.width; const gr = g.createRadialGradient(x, y, 0, x, y, rad); gr.addColorStop(0, b.col); gr.addColorStop(1, "transparent"); g.fillStyle = gr; g.fillRect(0, 0, c.width, c.height); } });
    return c;
  };
  FX.particles = (root, T, o = {}) => {   // seeded drifting dots on a canvas (stars, dust, data)
    const W = root.clientWidth || 1080, H = root.clientHeight || 1920, c = document.createElement("canvas"); c.width = W; c.height = H;
    Object.assign(c.style, { position: "absolute", inset: 0 }); root.appendChild(c);
    const g = c.getContext("2d"), r = FX.rand(o.seed || 9), n = o.n || 80, ps = [...Array(n)].map(() => ({ x: r() * W, y: r() * H, v: 8 + r() * 30, s: 1 + r() * 3 }));
    FX.onFrame((t) => { if (t < T.start - 0.1 || t > T.end + 0.1) return; g.clearRect(0, 0, W, H); g.fillStyle = o.color || "rgba(255,255,255,.7)"; for (const p of ps) { const y = (p.y - p.v * t + H * 10) % H; g.beginPath(); g.arc(p.x + 6 * Math.sin(t + p.y), y, p.s, 0, 6.283); g.fill(); } });
    return c;
  };
  /* deterministic 3D (Three.js): FX.three(root, T) -> {THREE, scene, camera, renderer, frame(fn)} rendered on window.render(t) */
  FX.three = (root, T, o = {}) => {
    const THREE = window.THREE;
    if (!THREE) throw new Error("THREE not loaded");
    const W = root.clientWidth || 1080, H = root.clientHeight || 1920;
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
    renderer.setPixelRatio(1); renderer.setSize(W, H); Object.assign(renderer.domElement.style, { position: "absolute", inset: 0 });
    root.appendChild(renderer.domElement);
    const scene = new THREE.Scene(), camera = new THREE.PerspectiveCamera(o.fov || 40, W / H, 0.1, 1000);
    camera.position.set(0, 0, o.z || 10);
    const fns = [];
    FX.onFrame((t) => { if (t < T.start - 0.1 || t > T.end + 0.1) return; const lt = t - T.start; for (const f of fns) f(lt, t); renderer.render(scene, camera); });
    return { THREE, scene, camera, renderer, frame: (fn) => fns.push(fn) };
  };
  FX.globe = (root, T, o = {}) => {   // a lit sphere with a lat/long grid that turns toward a target longitude
    const tall = (root.clientHeight || 1920) > (root.clientWidth || 1080);
    const k = FX.three(root, T, { z: o.z || (tall ? 12 : 7) }), { THREE, scene } = k;
    const g = new THREE.Group(); scene.add(g);
    g.add(new THREE.Mesh(new THREE.SphereGeometry(2, 64, 64), new THREE.MeshStandardMaterial({ color: o.color || "#1d4ed8", roughness: 0.7 })));
    const wire = new THREE.LineBasicMaterial({ color: o.grid || "#93c5fd", transparent: true, opacity: 0.35 });
    for (let lat = -60; lat <= 60; lat += 30) { const r = 2.01 * Math.cos((lat * Math.PI) / 180), y = 2.01 * Math.sin((lat * Math.PI) / 180); const pts = [...Array(65)].map((_, i) => new THREE.Vector3(r * Math.cos((i / 64) * 6.283), y, r * Math.sin((i / 64) * 6.283))); g.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), wire)); }
    scene.add(new THREE.AmbientLight(0xffffff, 0.5)); const sun = new THREE.DirectionalLight(0xffffff, 1.4); sun.position.set(5, 3, 5); scene.add(sun);
    k.frame((lt) => { g.rotation.y = (o.from || 0) + Math.min(1, lt / Math.max(0.5, T.dur)) * (o.turn || 1.2); });
    return k;
  };
  /* ---- sound + music cues, declared right next to the animation that causes them. The renderer collects them after
     setup (render.mjs --cues) and the mix puts every sound exactly on its frame (factory/sfx.py kinds). ---- */
  FX._cues = []; FX._music = [];
  FX.sfx = (kind, at, o = {}) => { if (Number.isFinite(+at)) FX._cues.push(Object.assign({ kind, t: +(+at).toFixed(3) }, o.db != null ? { gain_db: o.db } : {})); };
  FX.music = (action, at) => { if (Number.isFinite(+at)) FX._music.push({ action, t: +(+at).toFixed(3) }); };   // "cut" | "back" | "drop"

  /* shake: deterministic camera / object shake (a knock, an impact) */
  FX.shake = (tl, el, at, o = {}) => {
    const r = FX.rand(o.seed || 11), n = o.n || 8, amp = o.amp || 14, dur = o.dur || 0.4;
    for (let i = 0; i < n; i++) tl.to(el, { x: i === n - 1 ? 0 : (r() - 0.5) * 2 * amp * (1 - i / n), y: i === n - 1 ? 0 : (r() - 0.5) * amp * (1 - i / n), duration: dur / n, ease: "none" }, at + (i * dur) / n);
  };

  /* ---- code-drawn characters: a round-headed stickman rig (SVG). Joints are plain numbers in man.s; every frame the
     rig writes them into the SVG `transform` attributes itself (no svgOrigin / CSS transforms on SVG, which drift).
     const man = FX.stickman(root, {x: 540, y: 1500, h: 460, color: "#eee", face: true, pose: "stand"})  (x, y = feet)
     FX.pose(tl, man, "scared", at, {dur: .35}) · man.walk(at, dur, dx) · FX.wave(tl, man, at, dur) · man.g = the group
     poses: stand, wave, point, scared, shrug, knock, hold, crouch, cheer, sad, run ---- */
  const POSES = {
    stand: { sL: 12, eL: -8, sR: -12, eR: 8, hL: 7, kL: 0, hR: -7, kR: 0, lean: 0, head: 0, y: 0 },
    wave: { sL: 12, eL: -8, sR: -150, eR: -25, hL: 7, kL: 0, hR: -7, kR: 0, lean: 0, head: -6, y: 0 },
    point: { sL: 14, eL: -10, sR: -92, eR: -4, hL: 7, kL: 0, hR: -7, kR: 0, lean: -3, head: -4, y: 0 },
    scared: { sL: 150, eL: 50, sR: -150, eR: -50, hL: 14, kL: -18, hR: -14, kR: 18, lean: 6, head: 8, y: 14 },
    shrug: { sL: 48, eL: -115, sR: -48, eR: 115, hL: 7, kL: 0, hR: -7, kR: 0, lean: 0, head: 10, y: 0 },
    knock: { sL: 12, eL: -8, sR: -78, eR: -72, hL: 7, kL: 0, hR: -7, kR: 0, lean: -5, head: -3, y: 0 },
    hold: { sL: 32, eL: -70, sR: -32, eR: 70, hL: 7, kL: 0, hR: -7, kR: 0, lean: 2, head: 14, y: 0 },
    crouch: { sL: 40, eL: -60, sR: -40, eR: 60, hL: 48, kL: -96, hR: -48, kR: 96, lean: 10, head: 4, y: 70 },
    cheer: { sL: 160, eL: 12, sR: -160, eR: -12, hL: 12, kL: 0, hR: -12, kR: 0, lean: 0, head: -10, y: -6 },
    sad: { sL: 6, eL: -4, sR: -6, eR: 4, hL: 4, kL: 0, hR: -4, kR: 0, lean: 8, head: 24, y: 4 },
    run: { sL: -60, eL: -80, sR: 60, eR: 80, hL: -40, kL: 60, hR: 40, kR: 10, lean: -14, head: -6, y: -4 },
  };
  FX.POSES = POSES;
  FX.stickman = (root, o = {}) => {
    const h = o.h || 440, k = h / 400, NS = "http://www.w3.org/2000/svg", col = o.color || "#f1f1f1", sw = (o.stroke || 13);
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("width", 260 * k); svg.setAttribute("height", 420 * k); svg.setAttribute("viewBox", "-130 -400 260 420");
    Object.assign(svg.style, { position: "absolute", left: (o.x ?? 540) - 130 * k + "px", top: (o.y ?? 1500) - 400 * k + "px", overflow: "visible", zIndex: o.z || 5 });
    root.appendChild(svg);
    const mk = (tag, attrs, parent) => { const e = document.createElementNS(NS, tag); for (const [a, v] of Object.entries(attrs)) e.setAttribute(a, v); (parent || svg).appendChild(e); return e; };
    const line = { stroke: col, "stroke-width": sw, "stroke-linecap": "round", fill: "none" };
    const g = mk("g", {}), body = mk("g", {}, g);
    // hips at (0,-170), shoulders at (0,-290), head centre (0,-340); limbs point down at angle 0
    const limb = (x, y, len1, len2) => { const a = mk("g", {}, body); mk("line", { x1: x, y1: y, x2: x, y2: y + len1, ...line }, a); const b = mk("g", {}, a); mk("line", { x1: x, y1: y + len1, x2: x, y2: y + len1 + len2, ...line }, b); return [a, b, x, y, len1]; };
    const legL = limb(0, -170, 85, 85), legR = limb(0, -170, 85, 85);
    mk("line", { x1: 0, y1: -170, x2: 0, y2: -290, ...line }, body);
    const armL = limb(0, -285, 70, 68), armR = limb(0, -285, 70, 68);
    const headG = mk("g", {}, body);
    mk("circle", { cx: 0, cy: -338, r: 44, fill: o.head || col, stroke: col, "stroke-width": 4 }, headG);
    const face = {};
    if (o.face !== false) {
      const ink = o.ink || "#111";
      face.eyes = [mk("circle", { cx: -14, cy: -344, r: 5.5, fill: ink }, headG), mk("circle", { cx: 14, cy: -344, r: 5.5, fill: ink }, headG)];
      face.mouth = mk("path", { d: "M-13,-318 Q0,-312 13,-318", stroke: ink, "stroke-width": 4, fill: "none", "stroke-linecap": "round" }, headG);
    }
    if (o.prop) mk("g", {}, armR[1]).innerHTML = o.prop;   // optional SVG markup held in the right hand (e.g. a phone)
    const s = Object.assign({ x: 0 }, POSES[o.pose || "stand"]);
    FX._men = (FX._men || 0) + 1;
    const walks = [];
    const man = { svg, g, s, face, k, seed: o.seed ?? FX._men * 1.7,
      walk(at, dur, dx, o2 = {}) { walks.push({ at, dur, dx, steps: o2.steps || Math.max(2, Math.round(dur * 2.2)) }); },
      mouth(kind) { if (!face.mouth) return; face.mouth.setAttribute("d", { smile: "M-15,-322 Q0,-306 15,-322", grin: "M-20,-324 Q0,-298 20,-324 Z", flat: "M-13,-318 L13,-318", o: "M-6,-318 a6,7 0 1,0 12,0 a6,7 0 1,0 -12,0", frown: "M-13,-312 Q0,-322 13,-312" }[kind] || kind); },
    };
    const rot = (el, a, x, y) => el.setAttribute("transform", `rotate(${a.toFixed(2)} ${x} ${y})`);
    FX.onFrame((t0) => {
      const t = o.twos ? Math.floor(t0 * 12) / 12 : t0;   // characters on twos (12 fps), camera stays smooth
      const a = man.act || {};
      let x = s.x + (a.x || 0), swing = 0;
      for (const w of walks) {
        if (t >= w.at + w.dur) x += w.dx;
        else if (t > w.at) { const p = (t - w.at) / w.dur; x += w.dx * p; swing = Math.sin(p * w.steps * Math.PI); }
      }
      const bob = swing ? Math.abs(swing) * -8 : 0;
      const sq = a.sq || 0;   // squash (+) / stretch (-), volume kept, pivots at the feet
      g.setAttribute("transform", `translate(${(x / k).toFixed(1)} ${(s.y + bob + (a.y || 0)).toFixed(1)}) scale(${(1 + sq * 0.6).toFixed(3)} ${(1 - sq).toFixed(3)})`);
      body.setAttribute("transform", `rotate(${(s.lean + (a.lean ?? 0)).toFixed(2)} 0 -170)`);
      rot(legL[0], s.hL + swing * 26, 0, -170); rot(legL[1], s.kL + Math.max(0, -swing) * 30, 0, -85);
      rot(legR[0], s.hR - swing * 26, 0, -170); rot(legR[1], s.kR + Math.max(0, swing) * -30, 0, -85);
      rot(armL[0], (a.sL ?? s.sL) - swing * 22, 0, -285); rot(armL[1], s.eL, 0, -215);
      rot(armR[0], (a.sR ?? s.sR) + swing * 22, 0, -285); rot(armR[1], a.eR ?? s.eR, 0, -215);
      rot(headG, s.head + (a.head || 0), 0, -300);
    });
    return man;
  };
  FX.pose = (tl, man, pose, at, o = {}) => { const p = typeof pose === "string" ? POSES[pose] : pose; if (p) tl.to(man.s, { ...p, duration: o.dur || 0.35, ease: o.ease || "power2.inOut" }, at); };
  FX.wave = (tl, man, at, dur = 1.2, arm = "eR") => { const n = Math.max(2, Math.round(dur / 0.3)); for (let i = 0; i < n; i++) tl.to(man.s, { [arm]: i % 2 ? -25 : -60, duration: dur / n, ease: "sine.inOut" }, at + (i * dur) / n); };

  /* ---- story HUD + cards (stickman stories, rule-based horror, part-2 hooks) ---- */
  // a small clock in the top-left: label (NIGHT 1), the time (jumps forward), the place. times: [[at, "2:17 AM"], ...]
  FX.hud = (root, o = {}) => {
    const d = document.createElement("div");
    Object.assign(d.style, { position: "absolute", left: (o.x ?? 64) + "px", top: (o.y ?? 190) + "px", font: "800 26px 'Inter Tight'", letterSpacing: ".12em", color: o.muted || "rgba(255,255,255,.62)", textTransform: "uppercase", zIndex: 30 });
    d.innerHTML = `<div style="color:${o.accent || "#ff3b30"}">● ${o.label || "NIGHT 1"}</div><div class="hud-t" style="font:900 64px/1 'Inter Tight';letter-spacing:-.02em;color:${o.ink || "#fff"};margin:6px 0 4px;font-variant-numeric:tabular-nums"></div><div>${o.place || ""}</div>`;
    root.appendChild(d);
    const tt = d.querySelector(".hud-t"), times = (o.times || [[0, "2:17 AM"]]).slice().sort((a, b) => a[0] - b[0]);
    let last = null;
    FX.onFrame((t) => { const cur = times.filter((x) => x[0] <= t).pop() || times[0]; if (cur[1] !== last) { tt.textContent = cur[1]; last = cur[1]; } });
    return d;
  };
  // a red "RULE #N" tag that slaps in + a big condensed headline rising word by word
  FX.rule = (tl, root, at, n, headline, o = {}) => {
    const d = document.createElement("div");
    Object.assign(d.style, { position: "absolute", left: "70px", right: "160px", top: (o.y ?? 330) + "px", textAlign: o.align || "center", zIndex: 20 });
    d.innerHTML = `<span class="rule-tag" style="display:inline-block;padding:8px 18px;background:${o.color || "#e5231b"};color:#fff;font:900 30px 'Inter Tight';letter-spacing:.08em;border-radius:6px;transform:rotate(-2deg)">${o.tag || "RULE #" + n}</span><div class="rule-h" style="font:400 ${o.size || 118}px/0.95 Anton;color:${o.ink || "#fff"};text-transform:uppercase;margin-top:18px;text-shadow:0 6px 30px rgba(0,0,0,.5)"></div>`;
    root.appendChild(d);
    const hd = d.querySelector(".rule-h"), lines = String(headline).split(/<br\s*\/?>|\n/i);
    lines.forEach((ln, i) => { const l = document.createElement("div"); l.textContent = ln.trim(); hd.appendChild(l); FX.rise(tl, l, at + 0.12 + i * 0.14, { stagger: 0.07 }); });
    const tag = d.querySelector(".rule-tag");
    tl.fromTo(tag, { scale: 1.5, opacity: 0 }, { scale: 1, opacity: 1, duration: 0.22, ease: "power3.out" }, at);
    if (o.sfx !== false) FX.sfx(o.sfx || "hit", at, { db: o.db ?? -11 });
    return d;
  };
  // the end choice: a question + two answer buttons + "comment below" (people answer in the comments)
  FX.choice = (tl, root, at, o = {}) => {
    const d = document.createElement("div");
    Object.assign(d.style, { position: "absolute", left: "60px", right: "160px", top: (o.y ?? 520) + "px", textAlign: "center", zIndex: 20 });
    const btn = (txt, c) => `<span class="ch-b" style="display:inline-block;margin:0 10px;padding:16px 30px;border:4px solid ${c};color:${c};border-radius:999px;font:900 34px 'Inter Tight';letter-spacing:.03em;background:rgba(0,0,0,.35)">${txt}</span>`;
    d.innerHTML = `<div class="ch-q" style="font:400 104px/0.98 Anton;color:${o.ink || "#fff"};text-transform:uppercase"></div>
      <div style="margin-top:36px;white-space:nowrap">${btn(o.a || "YES", o.ca || "#3ddc84")}${btn(o.b || "NO", o.cb || "#ff453a")}</div>
      <div class="ch-s" style="margin-top:30px;font:800 26px 'Inter Tight';letter-spacing:.14em;color:rgba(255,255,255,.75)">${o.sub || "COMMENT BELOW"} ↓</div>`;
    root.appendChild(d);
    String(o.q || "WHAT DO YOU DO?").split(/<br\s*\/?>|\n/i).forEach((ln, i) => { const l = document.createElement("div"); l.textContent = ln.trim(); d.querySelector(".ch-q").appendChild(l); FX.rise(tl, l, at + i * 0.12, { stagger: 0.06 }); });
    const b = d.querySelectorAll(".ch-b");
    tl.fromTo(b, { scale: 0.6, opacity: 0 }, { scale: 1, opacity: 1, duration: 0.35, stagger: 0.18, ease: "back.out(2)" }, at + 0.45);
    tl.fromTo(d.querySelector(".ch-s"), { opacity: 0, y: 14 }, { opacity: 1, y: 0, duration: 0.4 }, at + 0.9);
    if (o.sfx !== false) { FX.sfx("click", at + 0.45); FX.sfx("click", at + 0.63); }
    return d;
  };
  // a card that flips from one label to the next ("NIGHT 1" -> "NIGHT 2", "OPEN" -> "CLOSED")
  FX.flipCard = (tl, root, at, from, to, o = {}) => {
    const d = document.createElement("div");
    Object.assign(d.style, { position: "absolute", left: "50%", top: (o.y ?? 1150) + "px", width: (o.w || 520) + "px", height: (o.h || 170) + "px", marginLeft: -(o.w || 520) / 2 + "px", perspective: "1200px", zIndex: 20 });
    const face = (txt, bg, back) => `<div style="position:absolute;inset:0;display:grid;place-items:center;border-radius:18px;background:${bg};color:#fff;font:400 ${o.size || 92}px Anton;letter-spacing:.02em;backface-visibility:hidden;${back ? "transform:rotateX(180deg)" : ""}">${txt}</div>`;
    d.innerHTML = `<div class="fc" style="position:absolute;inset:0;transform-style:preserve-3d">${face(from, o.bgFrom || "#2a2f3a")}${face(to, o.bgTo || "#e5231b", true)}</div>`;
    root.appendChild(d);
    tl.fromTo(d.querySelector(".fc"), { rotationX: 0 }, { rotationX: 180, duration: o.dur || 0.6, ease: "power3.inOut" }, at);
    if (o.sfx !== false) FX.sfx("flip", at + 0.05);
    return d;
  };

  /* ---- devices + UI (ads, alerts) ---- */
  // a phone frame; draw the app inside `.screen` (absolute children). FX.phone(root, {x, y, w}) -> {el, screen}
  FX.phone = (root, o = {}) => {
    const w = o.w || 520, h = Math.round(w * 2.05), d = document.createElement("div");
    Object.assign(d.style, { position: "absolute", left: (o.x ?? 540) - w / 2 + "px", top: (o.y ?? 360) + "px", width: w + "px", height: h + "px", borderRadius: w * 0.13 + "px", background: o.frame || "#0c0d10", padding: w * 0.035 + "px", boxSizing: "border-box", boxShadow: "0 40px 90px -30px rgba(0,0,0,.7), inset 0 0 0 3px rgba(255,255,255,.08)", zIndex: o.z || 10 });
    d.innerHTML = `<div class="screen" style="position:relative;width:100%;height:100%;overflow:hidden;border-radius:${w * 0.1}px;background:${o.screen || "#f4f6fb"}"></div><div style="position:absolute;left:50%;top:${w * 0.055}px;width:${w * 0.28}px;height:${w * 0.07}px;margin-left:-${w * 0.14}px;border-radius:99px;background:#000"></div>`;
    root.appendChild(d);
    return { el: d, screen: d.querySelector(".screen"), w, h };
  };
  // a system alert / notification sliding down onto a phone screen (or any container)
  FX.alert = (tl, box, at, o = {}) => {
    const scr = box.screen || box, d = document.createElement("div");
    Object.assign(d.style, { position: "absolute", left: "6%", right: "6%", top: (o.top ?? 9) + "%", padding: "22px 24px", borderRadius: "26px", background: o.bg || "rgba(28,28,32,.94)", color: o.ink || "#fff", font: "600 26px/1.25 'Inter Tight'", boxShadow: "0 18px 40px -14px rgba(0,0,0,.6)" });
    d.innerHTML = `<div style="font:900 20px 'Inter Tight';letter-spacing:.1em;color:${o.accent || "#ff453a"};text-transform:uppercase">${o.app || "Emergency alert"}</div><div style="font:900 34px/1.1 'Inter Tight';margin:8px 0 4px">${o.title || ""}</div><div style="opacity:.82">${o.body || ""}</div>`;
    scr.appendChild(d);
    tl.fromTo(d, { yPercent: -160, opacity: 0 }, { yPercent: 0, opacity: 1, duration: 0.45, ease: "power3.out" }, at);
    if (o.sfx !== false) FX.sfx(o.sfx || "notify", at);
    return d;
  };
  // a finger tap: ripple at [x, y] px in root (pair it with the UI change it causes)
  FX.tap = (tl, root, at, p, o = {}) => {
    const d = document.createElement("div"), r = o.r || 46;
    Object.assign(d.style, { position: "absolute", left: p[0] - r + "px", top: p[1] - r + "px", width: 2 * r + "px", height: 2 * r + "px", borderRadius: "50%", background: o.color || "rgba(255,255,255,.55)", border: "3px solid rgba(255,255,255,.9)", zIndex: 60, opacity: 0 });
    root.appendChild(d);
    tl.fromTo(d, { scale: 0.4, opacity: 0.95 }, { scale: 1.5, opacity: 0, duration: 0.45, ease: "power2.out" }, at);
    if (o.sfx !== false) FX.sfx("click", at);
    return d;
  };

  /* ---- story events ---- */
  // the power dies: two flickers then dark (keep = how much stays visible); the music cuts out with it by default
  FX.lightsOut = (tl, root, at, o = {}) => {
    const d = document.createElement("div");
    Object.assign(d.style, { position: "absolute", inset: 0, background: o.color || "#000", opacity: 0, zIndex: o.z || 40, pointerEvents: "none" });
    root.appendChild(d);
    const dark = 1 - (o.keep ?? 0.14);
    if (o.flicker !== false) { tl.set(d, { opacity: dark }, at); tl.set(d, { opacity: 0.2 }, at + 0.07); tl.set(d, { opacity: dark }, at + 0.16); tl.set(d, { opacity: 0.35 }, at + 0.22); }
    tl.set(d, { opacity: dark }, at + (o.flicker !== false ? 0.3 : 0));
    if (o.sfx !== false) FX.sfx("clunk", at);
    if (o.music !== false) FX.music("cut", at);
    return d;
  };
  FX.lightsOn = (tl, d, at, o = {}) => { tl.to(d, { opacity: 0, duration: o.dur || 0.08 }, at); if (o.sfx !== false) FX.sfx("buzz", at); if (o.music) FX.music("back", at); };
  // a fast slash line across [x1, y1] -> [x2, y2] (px)
  FX.slash = (tl, root, at, a, o = {}) => {
    const svg = FX.svg(root, root.clientWidth || 1080, root.clientHeight || 1920);
    svg.style.zIndex = 50;
    const p = FX.el(svg, "path", { d: `M${a[0]},${a[1]} L${a[2]},${a[3]}`, stroke: o.color || "#fff", "stroke-width": o.w || 10, "stroke-linecap": "round", fill: "none" });
    FX.drawOn(tl, p, at, { dur: o.dur || 0.12, ease: "power4.in" });
    tl.to(p, { opacity: 0, duration: 0.25 }, at + 0.2);
    if (o.sfx !== false) FX.sfx("swish", at);
    return p;
  };
  // break an element into seeded shards that fly apart (no measuring needed: shards are clip-path copies)
  FX.shatter = (tl, el, at, o = {}) => {
    const r = FX.rand(o.seed || 21), cols = o.cols || 3, rows = o.rows || 3, cs = getComputedStyle(el);
    const V = [];
    for (let j = 0; j <= rows; j++) { V.push([]); for (let i = 0; i <= cols; i++) { const edge = i === 0 || j === 0 || i === cols || j === rows; V[j].push([(i / cols) * 100 + (edge ? 0 : (r() - 0.5) * 18), (j / rows) * 100 + (edge ? 0 : (r() - 0.5) * 18)]); } }
    for (let j = 0; j < rows; j++) for (let i = 0; i < cols; i++) {
      const c = el.cloneNode(true); c.removeAttribute("id");
      for (const k of ["position", "left", "top", "right", "bottom", "width", "height", "transform"]) c.style[k] = cs[k];
      const q = [V[j][i], V[j][i + 1], V[j + 1][i + 1], V[j + 1][i]];
      c.style.clipPath = `polygon(${q.map((v) => v[0].toFixed(1) + "% " + v[1].toFixed(1) + "%").join(",")})`;
      c.style.opacity = 0;
      el.parentNode.insertBefore(c, el.nextSibling);
      const dx = (i + 0.5) / cols - 0.5, dy = (j + 0.5) / rows - 0.5;
      tl.set(c, { opacity: 1 }, at);
      tl.to(c, { x: dx * (o.spread || 520) + (r() - 0.5) * 80, y: dy * (o.spread || 520) + 160 + r() * 120, rotation: (r() - 0.5) * 90, opacity: 0, duration: o.dur || 0.8, ease: "power2.out" }, at);
    }
    tl.set(el, { opacity: 0 }, at);
    if (o.sfx !== false) FX.sfx("glass", at);
  };
  /* ---- acting: emotions as data (face, colour, emote, idle motion), changed with anticipation -> take -> settle.
     FX.emotions(tl, man, [[t, "neutral"], [t2, "scared"], [t3, "relieved"]]): before each change the eyes squint and the
     body squashes (anticipation, 0.12 s), the face swaps under the squint, then a take sized to the new emotion
     (stretch + rise) and an overshoot settle; the emote pops by the head. The idle motion of the current emotion runs
     every frame (nothing is ever still), locked to FX.BPM so a crowd shares one pulse; each man has its own phase
     (seed) so two characters never move as twins. ---- */
  FX.BPM = 100;
  const EMO = {
    neutral:   { eyes: "dot", mouth: "flat", take: 0.3, idle: (b) => ({ y: -3 * b.ab }) },
    happy:     { eyes: "happy", mouth: "smile", take: 0.6, emote: null, idle: (b) => ({ y: -10 * b.ab, sL: 20 + 10 * b.s, sR: -20 + 10 * b.s }) },
    excited:   { eyes: "wide", mouth: "grin", take: 1, emote: "spark", idle: (b) => ({ y: -22 * b.ab, sL: 150 + 15 * b.s, sR: -150 + 15 * b.s }) },
    proud:     { eyes: "closed", mouth: "smile", take: 0.5, idle: (b) => ({ lean: -3, y: -2 * b.ab, head: -8 }) },
    relieved:  { eyes: "closed", mouth: "smile", take: 0.4, emote: "sweat", idle: (b) => ({ y: -2 * b.br, head: 6 }) },
    sad:       { eyes: "sad", mouth: "frown", take: 0.3, emote: "cloud", idle: (b) => ({ lean: 8 + 2 * b.slow, head: 20, sL: 4, sR: -4 }) },
    scared:    { eyes: "wide", mouth: "o", take: 1.1, emote: "sweat", idle: (b) => ({ x: 2.5 * b.shiver }) },
    nervous:   { eyes: "dot", mouth: "o", take: 0.5, emote: "sweat", idle: (b) => ({ head: 8 * b.side, x: 3 * b.s }) },
    surprised: { eyes: "wide", mouth: "o", take: 1.3, emote: "!", idle: (b) => ({ y: -6 - 3 * b.ab }) },
    confused:  { eyes: "dot", mouth: "flat", take: 0.6, emote: "?", idle: (b) => ({ head: 12 * b.slow, sR: -140 + 8 * b.s }) },
    thinking:  { eyes: "dot", mouth: "flat", take: 0.4, emote: "dots", idle: (b) => ({ head: -10, sR: -120, eR: -110 }) },
    idea:      { eyes: "wide", mouth: "grin", take: 1.1, emote: "bulb", idle: (b) => ({ y: -8 * b.ab, sR: -165, eR: -10 }) },
    angry:     { eyes: "angry", mouth: "frown", take: 0.8, emote: "anger", idle: (b) => ({ x: 1.5 * b.shiver, lean: -6 }) },
    determined:{ eyes: "angry", mouth: "flat", take: 0.7, idle: (b) => ({ lean: -8, y: -3 * b.ab }) },
    sleepy:    { eyes: "closed", mouth: "o", take: 0.2, emote: "zzz", idle: (b) => ({ head: 14 + 4 * b.br, lean: 4 }) },
    suspicious:{ eyes: "narrow", mouth: "flat", take: 0.4, idle: (b) => ({ head: 10 * b.slow, x: 6 * b.slow }) },
    love:      { eyes: "happy", mouth: "smile", take: 0.7, emote: "heart", idle: (b) => ({ lean: 5 * b.slow, y: -5 * b.ab }) },
    sly:       { eyes: "narrow", mouth: "smirk", take: 0.4, idle: (b) => ({ head: -6, sR: -50 }) },
    ko:        { eyes: "x", mouth: "o", take: 1, emote: "stars", idle: (b) => ({ lean: 14, head: 18 }) },
  };
  FX.EMOTIONS = Object.keys(EMO);
  const EYES = { dot: [5.5, 5.5], wide: [8, 9], happy: "arc", closed: "line", sad: "sad", angry: "angry", narrow: [6, 2.5], x: "x" };
  const MOUTH = { flat: "M-13,-318 L13,-318", smile: "M-15,-322 Q0,-306 15,-322", grin: "M-20,-324 Q0,-298 20,-324 Z", o: "M-6,-318 a6,7 0 1,0 12,0 a6,7 0 1,0 -12,0",
                  frown: "M-13,-312 Q0,-322 13,-312", smirk: "M-12,-318 Q4,-316 15,-324" };
  const EMOTE = { "!": "!", "?": "?", sweat: "💧", zzz: "z z", heart: "♥", bulb: "💡", anger: "✷", dots: "…", spark: "✦", stars: "✶ ✶", cloud: "☁" };
  function drawFace(man, name) {
    const e = EMO[name] || EMO.neutral, f = man.face;
    if (!f.eyes || f._name === name) return;
    f._name = name;
    const NS = "http://www.w3.org/2000/svg", ink = f.eyes[0].getAttribute("fill") || "#111", hg = f.eyes[0].parentNode;
    (f.extra || []).forEach((x) => x.remove()); f.extra = [];
    const kind = EYES[e.eyes] || EYES.dot;
    f.eyes.forEach((el, i) => {
      const cx = i ? 14 : -14;
      el.style.display = Array.isArray(kind) ? "" : "none";
      if (Array.isArray(kind)) { el.setAttribute("r", kind[0]); el.setAttribute("transform", `translate(0 ${-344 * (1 - kind[1] / kind[0])}) scale(1 ${kind[1] / kind[0]})`); }
      else {
        const d = { arc: `M${cx - 8},-342 Q${cx},-352 ${cx + 8},-342`, line: `M${cx - 8},-344 L${cx + 8},-344`, sad: `M${cx - 8},-346 Q${cx},-338 ${cx + 8},-346`,
                    angry: `M${cx - 9},${i ? -340 : -352} L${cx + 9},${i ? -352 : -340}`, x: `M${cx - 6},-350 L${cx + 6},-338 M${cx + 6},-350 L${cx - 6},-338` }[kind];
        const p = document.createElementNS(NS, "path"); p.setAttribute("d", d); p.setAttribute("stroke", ink); p.setAttribute("stroke-width", 5); p.setAttribute("fill", "none"); p.setAttribute("stroke-linecap", "round");
        hg.appendChild(p); f.extra.push(p);
      }
    });
    if (f.mouth) f.mouth.setAttribute("d", MOUTH[e.mouth] || MOUTH.flat);
  }
  FX.emotions = (tl, man, keys, o = {}) => {
    keys = keys.slice().sort((a, b) => a[0] - b[0]);
    const k = man.k, NS = "http://www.w3.org/2000/svg", seed = man.seed || 0;
    const tag = document.createElement("div");
    Object.assign(tag.style, { position: "absolute", font: "900 64px 'Inter Tight'", color: o.emoteColor || "#fff", opacity: 0, zIndex: 31, pointerEvents: "none", textShadow: "0 4px 18px rgba(0,0,0,.45)" });
    man.svg.parentNode.appendChild(tag);
    const base = Object.assign({}, man.s), beat = 60 / FX.BPM;
    FX.onFrame((t) => {
      let cur = keys[0], idx = 0;
      keys.forEach((kk, i) => { if (kk[0] <= t) { cur = kk; idx = i; } });
      const since = t - cur[0], next = keys[idx + 1];
      // anticipation before the NEXT change: squint + squash
      const pre = next ? Math.max(0, 1 - (next[0] - t) / 0.12) : 0;
      const take = (EMO[cur[1]] || EMO.neutral).take * (o.take ?? 1);
      const tk = since < 0.5 ? Math.sin(Math.min(1, since / 0.5) * Math.PI) * Math.exp(-since * 3) : 0;
      drawFace(man, pre > 0.6 && next ? next[1] : cur[1]);
      const bp = (t + seed * 0.37) / beat, ph = bp % 1;
      const b = { ab: Math.abs(Math.sin(bp * Math.PI)), s: Math.sin(bp * Math.PI * 2), br: Math.sin(t * 2.1 + seed), slow: Math.sin(t * 1.3 + seed),
                  shiver: Math.sin(t * 2 * Math.PI * 21 + seed), side: Math.floor(bp) % 2 ? 1 : -1, ph };
      const idle = (EMO[cur[1]] || EMO.neutral).idle(b);
      man.act = { y: (idle.y || 0) - 30 * take * tk + 14 * pre, sq: 0.12 * pre - 0.16 * take * tk, x: idle.x || 0,
                  lean: idle.lean, head: idle.head, sL: idle.sL, sR: idle.sR, eR: idle.eR };
      const em = EMOTE[(EMO[cur[1]] || {}).emote];
      if (em) {
        if (tag.textContent !== em) tag.textContent = em;
        const pop = Math.min(1, since / 0.2), at = man.svg.getBoundingClientRect ? null : null;
        tag.style.opacity = String(since < 0 ? 0 : Math.min(1, pop) * (since > 2.6 ? Math.max(0, 1 - (since - 2.6) / 0.3) : 1));
        tag.style.left = parseFloat(man.svg.style.left) + 190 * k + (man.s.x || 0) + "px";
        tag.style.top = parseFloat(man.svg.style.top) + (20 - 18 * Math.sin(Math.min(1, pop) * Math.PI / 2)) * k + "px";
        tag.style.transform = `scale(${0.6 + 0.4 * Math.min(1, pop) + 0.15 * Math.sin(Math.min(1, pop) * Math.PI)})`;
      } else tag.style.opacity = 0;
    });
    return man;
  };

  /* ---- hand-drawn boil: every line wobbles a little, re-drawn 12 times a second (FX.boil(root, {px})) ---- */
  FX.boil = (root, o = {}) => {
    const id = "boil" + Math.round(FX.rand(o.seed || 3)() * 1e6), NS = "http://www.w3.org/2000/svg", svg = document.createElementNS(NS, "svg");
    svg.setAttribute("width", 0); svg.setAttribute("height", 0); svg.style.position = "absolute";
    svg.innerHTML = `<filter id="${id}"><feTurbulence type="fractalNoise" baseFrequency="${o.freq || 0.02}" numOctaves="2" seed="1" result="n"/><feDisplacementMap in="SourceGraphic" in2="n" scale="${o.px || 4}"/></filter>`;
    root.appendChild(svg);
    const turb = svg.querySelector("feTurbulence"), fps = o.fps || 12;
    (o.targets || [root]).forEach((el) => { el.style.filter = `url(#${id})`; });
    FX.onFrame((t) => turb.setAttribute("seed", String(1 + (Math.floor(t * fps) % 6))));
  };

  /* ---- transitions with a cause (seams): iris from a point, fat brush wipe, whip smear, dip cut, colour flood ---- */
  FX.iris = (tl, root, at, p, o = {}) => {   // the scene opens from a point (a click, a character's eye): call at scene start
    const out = o.out;   // out: true closes onto the point at `at`
    tl.fromTo(root, { clipPath: `circle(${out ? 150 : 0}% at ${p[0] * 100}% ${p[1] * 100}%)` }, { clipPath: `circle(${out ? 0 : 150}% at ${p[0] * 100}% ${p[1] * 100}%)`, duration: o.dur || 0.45, ease: out ? "power3.in" : "power3.out" }, at);
  };
  FX.brushWipe = (tl, root, at, o = {}) => {   // fat strokes cover the frame then drag off (cut under full cover)
    const W = root.clientWidth || 1080, H = root.clientHeight || 1920, svg = FX.svg(root, W, H), n = o.n || 5, c = o.color || "var(--ink, #111)";
    svg.style.zIndex = 90;
    for (let i = 0; i < n; i++) {
      const y = (H / n) * (i + 0.5), p = FX.el(svg, "path", { d: `M-80,${y} L${W + 80},${y + (i % 2 ? 40 : -40)}`, stroke: c, "stroke-width": H / n + 60, "stroke-linecap": "round", fill: "none" });
      FX.drawOn(tl, p, at + i * 0.04, { dur: 0.32, ease: "power2.in" });
    }
    if (o.sfx !== false) FX.sfx("swish", at + 0.1);
    return svg;
  };
  FX.whip = (tl, el, at, o = {}) => { const dx = (o.dir || 1) * (o.dist || 900); tl.to(el, { x: -dx, filter: "blur(18px)", duration: o.dur || 0.18, ease: "power3.in" }, at); if (o.sfx !== false) FX.sfx("whoosh", at + 0.12); };
  FX.whipIn = (tl, el, at, o = {}) => { const dx = (o.dir || 1) * (o.dist || 900); tl.fromTo(el, { x: dx, filter: "blur(18px)" }, { x: 0, filter: "blur(0px)", duration: o.dur || 0.22, ease: "power3.out" }, at); };
  FX.dipCut = (tl, root, at) => { const d = document.createElement("div"); Object.assign(d.style, { position: "absolute", inset: 0, background: "#000", opacity: 0, zIndex: 95 }); root.appendChild(d); tl.to(d, { opacity: 0.4, duration: 0.1, ease: "none" }, at - 0.1); return d; };
  FX.colorFlood = (tl, root, at, color, o = {}) => { const d = document.createElement("div"); Object.assign(d.style, { position: "absolute", inset: 0, background: color, zIndex: o.z ?? 0, clipPath: "circle(0% at 50% 50%)" }); root.prepend(d); tl.to(d, { clipPath: "circle(150% at 50% 50%)", duration: o.dur || 0.4, ease: "power2.inOut" }, at); return d; };

  /* ---- 3D sets (Three.js): block out at real-world scale, light like a set, shoot with a real lens.
     const set = FX.set3d(root, T, {lens: 35, light: "night_interior", fog: "#0b1020"}); set.box([w, h, d], [x, y, z], color);
     set.floor(20, color); set.room([8, 3, 6], color); set.practical([x, y, z], "#ffd59a", 1.5) (a lamp); set.dolly(from, to)
     metres, y up; lights: three_point | night_interior | moonlight | product | daylight ---- */
  FX.set3d = (root, T, o = {}) => {
    const k = FX.three(root, T, { fov: 2 * Math.atan(12 / (o.lens || 35)) * 180 / Math.PI * ((root.clientHeight || 1920) > (root.clientWidth || 1080) ? 1.6 : 1), z: 1 });
    const { THREE, scene, camera, renderer } = k;
    renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    if (o.fog) { scene.fog = new THREE.Fog(o.fog, o.fogNear || 6, o.fogFar || 30); scene.background = new THREE.Color(o.fog); }
    const add = (l, pos, shadow) => { if (pos) l.position.set(...pos); if (shadow) { l.castShadow = true; l.shadow.mapSize.set(1024, 1024); l.shadow.radius = 4; } scene.add(l); return l; };
    const rigs = {
      three_point: () => { add(new THREE.DirectionalLight(0xffffff, 2.2), [4, 6, 5], true); add(new THREE.DirectionalLight(0xbfd4ff, 0.7), [-5, 3, 4]); add(new THREE.DirectionalLight(0xffffff, 1.4), [0, 5, -6]); add(new THREE.AmbientLight(0xffffff, 0.15)); },
      product: () => { add(new THREE.DirectionalLight(0xffffff, 2.6), [3, 5, 4], true); add(new THREE.DirectionalLight(0xffffff, 0.5), [-4, 2, 3]); add(new THREE.DirectionalLight(0xffffff, 2), [-2, 4, -5]); add(new THREE.HemisphereLight(0xffffff, 0x222222, 0.35)); },
      night_interior: () => { add(new THREE.AmbientLight(0x223355, 0.35)); add(new THREE.DirectionalLight(0x6f88ff, 0.6), [-6, 5, 3], true); },
      moonlight: () => { add(new THREE.HemisphereLight(0x5a78c8, 0x0a0d18, 0.5)); add(new THREE.DirectionalLight(0x9db4ff, 1.1), [-8, 10, 4], true); },
      daylight: () => { add(new THREE.HemisphereLight(0xdfefff, 0x8a7a5a, 0.9)); add(new THREE.DirectionalLight(0xfff1d6, 2.4), [6, 10, 3], true); },
    };
    (rigs[o.light] || rigs.three_point)();
    const mat = (c, r = 0.75) => new THREE.MeshStandardMaterial({ color: c, roughness: r });
    const set = Object.assign(k, {
      box(size, pos, c = "#888", r) { const m = new THREE.Mesh(new THREE.BoxGeometry(...size), mat(c, r)); m.position.set(pos[0], pos[1] + size[1] / 2, pos[2]); m.castShadow = m.receiveShadow = true; scene.add(m); return m; },
      floor(sz = 30, c = "#555") { const m = new THREE.Mesh(new THREE.PlaneGeometry(sz, sz), mat(c, 0.9)); m.rotation.x = -Math.PI / 2; m.receiveShadow = true; scene.add(m); return m; },
      room(dim = [8, 3, 6], c = "#6b6f7a") { const [w, h, d] = dim, g = new THREE.Group(), side = mat(c, 0.95); side.side = THREE.BackSide; const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), side); m.position.y = h / 2; m.receiveShadow = true; g.add(m); scene.add(g); return m; },
      practical(pos, c = "#ffd59a", power = 1.5) { const l = add(new THREE.PointLight(c, power * 8, 8, 2), pos, true); const bulb = new THREE.Mesh(new THREE.SphereGeometry(0.06), new THREE.MeshBasicMaterial({ color: c })); bulb.position.set(...pos); scene.add(bulb); return l; },
      look(from, at) { camera.position.set(...from); camera.lookAt(...at); },
      dolly(from, to, at, ease = (x) => x * x * (3 - 2 * x)) { k.frame((lt) => { const p = ease(Math.min(1, lt / Math.max(0.5, T.dur))); camera.position.set(...from.map((v, i) => v + (to[i] - v) * p)); camera.lookAt(...at); }); },
    });
    set.look(o.camera || [0, 1.6, 6], o.target || [0, 1.2, 0]);
    return set;
  };
  window.FX = FX;
})();
