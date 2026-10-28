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
      // whitespace in its own (plain inline) span, never a bare text node: GSAP measures transforms in a hidden scene by
      // re-inserting each element before its next ELEMENT sibling, which would hop a letter over a text-node space
      if (/^\s+$/.test(p)) { const g = document.createElement("span"); g.textContent = p; el.appendChild(g); return null; }
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
  /* ---- set pieces: orbit, screen wall, UI world, frame break, phone, checklist, headline wall, zoom-through, charts,
     paper cut, doodle boil, vertigo, cover story, glass type, freeze frame. Items/pictures are an image URL, an HTML
     string ("<div>..") or {img} / {html}. Sizes are 1080x1920 px unless given. ---- */
  const NS = "http://www.w3.org/2000/svg";
  let uid = 0;
  const dims = (root) => [root.clientWidth || 1080, root.clientHeight || 1920];
  const div = (parent, css, html) => { const d = document.createElement("div"); if (css) Object.assign(d.style, css); if (html != null) d.innerHTML = html; parent.appendChild(d); return d; };
  FX.div = div;
  const media = (it) => { if (it == null) return ""; if (typeof it === "object") return it.html ?? media(it.img); return /^\s*</.test(it) ? it : `<img src="${it}" style="width:100%;height:100%;object-fit:cover;display:block">`; };
  FX.media = media;
  const ease2 = (p) => (p < 0.5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2);
  const GRAIN = `url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='240' height='240'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='.85' numOctaves='3' stitchTiles='stitch'/><feColorMatrix values='0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 .10 0'/></filter><rect width='100%' height='100%' filter='url(%23n)'/></svg>")`;

  /* orbit: the camera circles an element (product shot, phone, card): CSS 3D turn + a light sheen sliding over it */
  FX.orbit = (tl, el, T, o = {}) => {
    const at = o.at ?? T.start, d = o.dur || Math.max(0.5, T.dur), from = o.from ?? -35, turn = o.turn ?? 70, tilt = o.tilt ?? 10;
    const stage = document.createElement("div"); el.parentNode.insertBefore(stage, el); stage.appendChild(el);
    Object.assign(stage.style, { position: "absolute", inset: 0, perspective: (o.perspective || 1800) + "px" });
    if (o.shadow !== false) el.style.filter = "drop-shadow(0 50px 60px rgba(0,0,0,.5))";
    tl.fromTo(el, { rotationY: from, rotationX: tilt }, { rotationY: from + turn, rotationX: -tilt * 0.5, duration: d, ease: o.ease || "sine.inOut" }, at);
    if (o.sheen !== false) {
      const sh = div(el, { position: "absolute", inset: 0, pointerEvents: "none", borderRadius: "inherit", mixBlendMode: "screen", backgroundSize: "300% 100%",
                           background: "linear-gradient(105deg, transparent 35%, rgba(255,255,255,.30) 50%, transparent 65%)" });
      sh.style.backgroundSize = "300% 100%";
      tl.fromTo(sh, { backgroundPosition: "100% 0" }, { backgroundPosition: "0% 0", duration: d, ease: "sine.inOut" }, at);
    }
    return stage;
  };
  /* orbit in Three.js: k = FX.orbit3d(root, T, {radius, height, turn}); add meshes to k.scene, the camera circles 0,0,0 */
  FX.orbit3d = (root, T, o = {}) => {
    const k = FX.three(root, T, o), r = o.radius || 8, h = o.height ?? 2, a0 = o.from || 0, turn = o.turn ?? 1.6;
    k.frame((lt) => { const a = a0 + turn * ease2(Math.min(1, lt / Math.max(0.5, T.dur))); k.camera.position.set(r * Math.sin(a), h, r * Math.cos(a)); k.camera.lookAt(0, o.lookY || 0, 0); });
    return k;
  };

  /* screen wall: a tilted grid of glowing screens switching on one by one; {focus: i} then flies into screen i */
  FX.screenWall = (tl, root, at, items, o = {}) => {
    const [W] = dims(root), cols = o.cols || 3, rows = o.rows || Math.ceil(items.length / cols), gap = o.gap ?? 18;
    const ww = W * (o.scale || 1.3), cw = (ww - gap * (cols - 1)) / cols, ch = cw * (o.ratio || 0.62), wh = rows * ch + gap * (rows - 1);
    const stage = div(root, { position: "absolute", inset: 0, perspective: "2200px", overflow: "hidden" });
    const wall = div(stage, { position: "absolute", left: "50%", top: "50%", width: ww + "px", height: wh + "px", marginLeft: -ww / 2 + "px", marginTop: -wh / 2 + "px",
                              display: "grid", gridTemplateColumns: `repeat(${cols}, 1fr)`, gridAutoRows: ch + "px", gap: gap + "px" });
    const r = FX.rand(o.seed || 3), n = rows * cols;
    const cells = [...Array(n)].map((_, i) => {
      const c = div(wall, { position: "relative", borderRadius: "14px", overflow: "hidden", background: "#0b0d12", border: "2px solid rgba(255,255,255,.16)",
                            boxShadow: `0 0 50px ${o.glow || "rgba(120,170,255,.22)"}` }, media(items[i % items.length]));
      div(c, { position: "absolute", inset: 0, pointerEvents: "none", background: "repeating-linear-gradient(0deg, rgba(0,0,0,.18) 0 2px, transparent 2px 5px), linear-gradient(160deg, rgba(255,255,255,.14), transparent 40%)" });
      return c;
    });
    const order = cells.map((c, i) => [r(), i]).sort((a, b) => a[0] - b[0]).map((x) => x[1]), every = o.every ?? 0.07;
    order.forEach((i, k) => tl.fromTo(cells[i], { opacity: 0, filter: "brightness(3)" }, { opacity: 1, filter: "brightness(1)", duration: 0.14, ease: "none" }, at + k * every));
    const rx = o.rotX ?? 8, ry = o.rotY ?? -18, fat = o.focusAt ?? at + n * every + 0.5;
    tl.fromTo(wall, { rotationY: ry, rotationX: rx, scale: 0.9 }, { rotationY: ry * 0.4, rotationX: rx * 0.4, scale: 1, duration: o.focus != null ? Math.max(0.3, fat - at) : o.dur || 3, ease: "sine.inOut" }, at);
    if (o.focus != null) {
      const col = o.focus % cols, row = Math.floor(o.focus / cols), z = o.zoom || (W / cw) * 0.92;
      const dx = (col - (cols - 1) / 2) * (cw + gap), dy = (row - (rows - 1) / 2) * (ch + gap);
      tl.to(wall, { x: -dx * z, y: -dy * z, scale: z, rotationY: 0, rotationX: 0, duration: o.focusDur || 1.0, ease: "power3.inOut" }, fat);
      tl.to(cells.filter((_, i) => i !== o.focus), { opacity: 0.3, duration: 0.5 }, fat);
    }
    return { stage, wall, cells };
  };

  /* UI world: interface cards float at different depths and the camera flies through them.
     cards: [{html | img, x, y, z, w, h, ry}] (x/y px from the centre, z <= 0 = further away; omitted = seeded layout) */
  FX.uiWorld = (tl, root, T, cards, o = {}) => {
    const [W, H] = dims(root), sp = o.spacing || 700, r = FX.rand(o.seed || 11);
    const stage = div(root, { position: "absolute", inset: 0, perspective: (o.perspective || 1400) + "px", overflow: "hidden" });
    const world = div(stage, { position: "absolute", left: W / 2 + "px", top: H / 2 + "px", width: 0, height: 0, transformStyle: "preserve-3d" });
    const els = cards.map((c, i) => {
      const it = c && typeof c === "object" ? c : { html: c }, w = it.w || 520, img = it.img && !it.html;
      const x = it.x ?? (r() - 0.5) * W * 0.6, y = it.y ?? (r() - 0.5) * H * 0.55, z = it.z ?? -i * sp, ry = it.ry ?? (r() - 0.5) * 24;
      const e = div(world, { position: "absolute", width: w + "px", left: -w / 2 + "px", top: 0, boxSizing: "border-box", overflow: "hidden",
                             padding: img ? 0 : it.pad ?? "28px", height: img ? (it.h || w * 0.62) + "px" : it.h ? it.h + "px" : "auto",
                             transform: `translate3d(${x}px, ${y}px, ${z}px) rotateY(${ry}deg)` }, media(it));
      if (o.glass !== false) FX.glass(e, { r: 24 });
      return e;
    });
    tl.fromTo(world, { z: o.fromZ ?? -400, rotationY: 8, rotationX: -4 }, { z: o.toZ ?? (cards.length - 1) * sp + 500, rotationY: -6, rotationX: 3,
                                                                             duration: o.dur || Math.max(0.5, T.dur), ease: o.ease || "power1.inOut" }, o.at ?? T.start);
    return { stage, world, cards: els };
  };

  /* frame break: the picture sits in a frame, its subject (cutout = transparent PNG of the same picture) breaks out over
     the edge. box = [x, y, w, h] fractions of the frame */
  FX.frameBreak = (tl, root, at, o = {}) => {
    const [W, H] = dims(root), b = o.box || [0.12, 0.32, 0.76, 0.38], bw = o.border ?? 16;
    const x = b[0] * W, y = b[1] * H, w = b[2] * W, h = b[3] * H;
    const frame = div(root, { position: "absolute", left: x + "px", top: y + "px", width: w + "px", height: h + "px", overflow: "hidden", background: "#111",
                              outline: `${bw}px solid ${o.color || "#fff"}`, boxShadow: "0 40px 90px -20px rgba(0,0,0,.6)" });
    const pic = div(frame, { position: "absolute", left: -x + "px", top: -y + "px", width: W + "px", height: H + "px" }, media(o.img));
    tl.fromTo(frame, { scale: 0.85, opacity: 0 }, { scale: 1, opacity: 1, duration: 0.5, ease: "back.out(1.6)" }, at);
    let cut = null;
    if (o.cutout) {
      cut = div(root, { position: "absolute", left: 0, top: 0, width: W + "px", height: H + "px", pointerEvents: "none",
                        transformOrigin: `${(b[0] + b[2] / 2) * 100}% ${(b[1] + b[3]) * 100}%`, filter: "drop-shadow(0 20px 26px rgba(0,0,0,.45))" },
                `<img src="${o.cutout}" style="width:100%;height:100%;object-fit:cover;display:block">`);
      tl.fromTo(cut, { opacity: 0, scale: 0.97 }, { opacity: 1, scale: o.pop || 1.06, duration: 0.6, ease: "back.out(2)" }, at + (o.delay ?? 0.5));
    }
    return { frame, pic, cut };
  };

  /* phone mockup: p = FX.phone(root, {w, x, y, img | html, bg}); p.screen is the display (put content in it, scroll it
     with tl.to(inner, {y: -600})); animate p.el like any element (or FX.orbit(tl, p.el, T)) */
  FX.phone = (root, o = {}) => {
    const w = o.w || 520, h = Math.round(w * 2.05), x = (o.x ?? 540) - w / 2, y = o.y ?? 360;   // x = centre of the phone
    const el = div(root, { position: "absolute", left: x + "px", top: y + "px", width: w + "px", height: h + "px", borderRadius: w * 0.16 + "px", boxSizing: "border-box",
                           padding: w * 0.035 + "px", background: o.frame || "linear-gradient(145deg,#3a3d45,#0d0e11 60%)", zIndex: o.z || 10,
                           boxShadow: "0 60px 120px -30px rgba(0,0,0,.65), inset 0 0 0 3px rgba(255,255,255,.14)" });
    const screen = div(el, { position: "relative", width: "100%", height: "100%", borderRadius: w * 0.13 + "px", overflow: "hidden", background: o.bg || o.screen || "#f4f6fb" }, o.html ?? media(o.img));
    screen.className = "screen";
    div(screen, { position: "absolute", top: w * 0.03 + "px", left: "50%", width: w * 0.3 + "px", height: w * 0.085 + "px", marginLeft: -w * 0.15 + "px", borderRadius: "999px", background: "#000", zIndex: 5 });
    div(el, { position: "absolute", right: "-5px", top: h * 0.22 + "px", width: "6px", height: h * 0.1 + "px", background: "#1b1d22", borderRadius: "3px" });
    div(el, { position: "absolute", left: "-5px", top: h * 0.18 + "px", width: "6px", height: h * 0.06 + "px", background: "#1b1d22", borderRadius: "3px" });
    div(el, { position: "absolute", inset: 0, borderRadius: "inherit", pointerEvents: "none", background: "linear-gradient(120deg, rgba(255,255,255,.16), transparent 32%)" });
    return { el, screen, w, h };
  };

  /* checklist: rows come in one by one, each box fills and its tick draws on; {strike: true} crosses the text out */
  FX.checklist = (tl, root, at, items, o = {}) => {
    const [W] = dims(root), c = o.color || "var(--accent, #22c55e)", size = o.size || 56, every = o.every ?? 0.5, s = size * 1.1;
    const box = div(root, { position: "absolute", left: (o.x ?? 96) + "px", top: (o.y ?? 560) + "px", width: (o.w ?? W - 192) + "px", display: "flex", flexDirection: "column",
                            gap: (o.gap ?? 36) + "px", font: o.font || `800 ${size}px "Inter Tight"`, color: o.ink || "#fff", lineHeight: 1.1 });
    return items.map((txt, i) => {
      const t = at + i * every, row = div(box, { display: "flex", alignItems: "center", gap: size * 0.45 + "px" });
      const svg = document.createElementNS(NS, "svg"); svg.setAttribute("width", s); svg.setAttribute("height", s); svg.style.flex = "none"; row.appendChild(svg);
      const rect = FX.el(svg, "rect", { x: 3, y: 3, width: s - 6, height: s - 6, rx: s * 0.22, "stroke-width": 5 });
      Object.assign(rect.style, { fill: c, fillOpacity: 0, stroke: o.ink || "#fff", strokeOpacity: 0.55 });
      const tick = FX.el(svg, "path", { d: `M${s * 0.25},${s * 0.52} L${s * 0.43},${s * 0.7} L${s * 0.77},${s * 0.3}`, fill: "none", stroke: o.tickInk || "#fff", "stroke-width": s * 0.11, "stroke-linecap": "round", "stroke-linejoin": "round" });
      const label = div(row, { position: "relative" }); label.textContent = txt;
      tl.fromTo(row, { opacity: 0, x: -30 }, { opacity: 1, x: 0, duration: 0.35, ease: "power3.out" }, t);
      tl.to(rect, { fillOpacity: 1, strokeOpacity: 0, duration: 0.18, ease: "none" }, t + 0.2);
      tl.fromTo(svg, { scale: 0.8 }, { scale: 1, duration: 0.35, ease: "back.out(3)" }, t + 0.2);
      FX.drawOn(tl, tick, t + 0.25, { dur: 0.28 });
      if (o.strike) { const l = div(label, { position: "absolute", left: 0, top: "52%", height: Math.max(4, size * 0.08) + "px", width: "100%", background: o.ink || "#fff", transformOrigin: "0 50%" });
                      tl.fromTo(l, { scaleX: 0 }, { scaleX: 1, duration: 0.3, ease: "power2.inOut" }, t + 0.4); tl.to(label, { opacity: 0.55, duration: 0.3 }, t + 0.4); }
      return row;
    });
  };

  /* headline wall: newspaper clippings slam in, slightly rotated, stacking down the frame.
     heads: ["title"] or [{title, source, color, size}]; {highlight: i} marks one with a marker swipe */
  FX.headlineWall = (tl, root, at, heads, o = {}) => {
    const [W, H] = dims(root), r = FX.rand(o.seed || 21), every = o.every ?? 0.35, step = o.step ?? H * 0.12;
    return heads.map((h, i) => {
      const it = typeof h === "string" ? { title: h } : h, w = W * (0.74 + r() * 0.14), t = at + i * every;
      const e = div(root, { position: "absolute", left: (W - w) / 2 + (r() - 0.5) * W * 0.1 + "px", top: H * (o.top ?? 0.14) + i * step + (r() - 0.5) * 40 + "px", width: w + "px",
                            boxSizing: "border-box", padding: "24px 30px 30px", color: "#111", backgroundColor: it.bg || "#f3efe6", backgroundImage: GRAIN,
                            boxShadow: "0 18px 40px -12px rgba(0,0,0,.55)", fontFamily: o.serif || '"DM Serif Display", "Playfair Display", serif' },
                    `<div style="font:800 22px 'Inter Tight';letter-spacing:.16em;text-transform:uppercase;color:${it.color || "#b91c1c"};margin-bottom:10px">${it.source || ""}</div>` +
                    `<div class="hl" style="font-size:${it.size || 56}px;line-height:1.04;letter-spacing:-.01em"><span>${it.title}</span></div>`);
      gsap.set(e, { rotation: (r() - 0.5) * (o.tilt ?? 7) });
      tl.fromTo(e, { scale: 1.5, opacity: 0, y: -30 }, { scale: 1, opacity: 1, y: 0, duration: 0.26, ease: "power4.in" }, t);
      if (i > 0) tl.to(root.querySelectorAll(".hl"), { opacity: (k) => (k < i ? 0.75 : 1), duration: 0.2 }, t + 0.2);
      if (o.highlight === i) FX.highlight(tl, e.querySelector(".hl span"), t + 0.4, { color: o.marker || "#fde047" });
      return e;
    });
  };

  /* zoom-through cut: dive into a point of `fromEl` (a window, a screen, an eye) and the next layer `toEl` grows out of it */
  FX.zoomThrough = (tl, fromEl, toEl, at, o = {}) => {
    const f = o.focus || [0.5, 0.5], d = o.dur || 0.7;
    gsap.set(fromEl, { transformOrigin: `${f[0] * 100}% ${f[1] * 100}%` });
    tl.to(fromEl, { scale: o.zoom || 9, filter: "blur(10px)", duration: d, ease: "power4.in" }, at);
    tl.to(fromEl, { opacity: 0, duration: d * 0.25, ease: "none" }, at + d * 0.75);
    if (toEl) tl.fromTo(toEl, { scale: 0.35, opacity: 0, filter: "blur(14px)", transformOrigin: `${f[0] * 100}% ${f[1] * 100}%` },
                        { scale: 1, opacity: 1, filter: "blur(0px)", duration: d * 0.9, ease: "power3.out" }, at + d * 0.7);
  };

  /* chart grow: FX.chart(tl, root, at, {type: bar|line|area|donut, data: [..], labels, x, y, w, h, color, colors,
     highlight: i, prefix, suffix, decimals, max}) -> svg. Bars grow with counting values, lines draw on, donut arcs sweep */
  FX.chart = (tl, root, at, o) => {
    const [W, H] = dims(root), type = o.type || "bar", data = o.data || [], n = data.length, ink = o.ink || "#fff", c = o.color || "#60a5fa";
    const x = o.x ?? 96, y = o.y ?? 560, w = o.w ?? W - 192, h = o.h ?? 680, dur = o.dur || 1.0, font = o.font || "Inter Tight";
    const max = o.max ?? Math.max(...data) * 1.12, min = o.min ?? 0, Y = (v) => y + h - ((v - min) / (max - min)) * h;
    const svg = FX.svg(root, W, H), num = { prefix: o.prefix, suffix: o.suffix, decimals: o.decimals, dur };
    const text = (s, px, py, size, wt, op = 1) => { const t = FX.el(svg, "text", { x: px, y: py, fill: ink, "font-family": font, "font-size": size, "font-weight": wt, "text-anchor": "middle", opacity: op }); t.textContent = s; return t; };
    const labels = (xs) => (o.labels || []).forEach((l, i) => { const t = text(l, xs(i), y + h + 48, o.labelSize || 28, 600, 0.75); tl.fromTo(t, { opacity: 0 }, { opacity: 0.75, duration: 0.3 }, at + 0.2 + i * 0.05); });
    if (type === "donut") {
      const cx = x + w / 2, cy = y + h / 2, R = Math.min(w, h) * 0.38, sw = R * 0.34, C = 2 * Math.PI * R, tot = data.reduce((a, b) => a + b, 0) || 1;
      const cols = o.colors || [c, "#f472b6", "#facc15", "#34d399", "#a78bfa"];
      let acc = 0;
      data.forEach((v, i) => {
        const len = (v / tot) * C, arc = FX.el(svg, "circle", { cx, cy, r: R, fill: "none", stroke: cols[i % cols.length], "stroke-width": sw, transform: `rotate(${-90 + (acc / tot) * 360} ${cx} ${cy})` });
        tl.fromTo(arc, { attr: { "stroke-dasharray": `0 ${C}` } }, { attr: { "stroke-dasharray": `${len} ${C}` }, duration: dur * 0.6, ease: "power2.out" }, at + (acc / tot) * dur * 0.8);
        acc += v;
      });
      const mid = text("0", cx, cy + (o.valueSize || 96) * 0.35, o.valueSize || 96, 900);
      FX.countUp(tl, mid, at, o.center ?? data[o.highlight ?? 0], num);
      return svg;
    }
    const base = FX.el(svg, "path", { d: `M${x},${y + h} L${x + w},${y + h}`, stroke: ink, "stroke-opacity": 0.35, "stroke-width": 3, fill: "none" });
    FX.drawOn(tl, base, at, { dur: 0.5 });
    if (type === "bar") {
      const slot = w / n, bw = slot * 0.72;
      data.forEach((v, i) => {
        const bx = x + i * slot + (slot - bw) / 2, t = at + 0.2 + i * (o.stagger ?? 0.08), on = o.highlight == null || o.highlight === i;
        const bar = FX.el(svg, "rect", { x: bx, y: y + h, width: bw, height: 0, rx: Math.min(14, bw / 4), fill: on ? c : o.dim || "rgba(255,255,255,.28)" });
        tl.fromTo(bar, { attr: { y: y + h, height: 0 } }, { attr: { y: Y(v), height: y + h - Y(v) }, duration: dur, ease: "power3.out" }, t);
        const val = text("0", bx + bw / 2, y + h - 18, o.valueSize || 40, 800);
        tl.fromTo(val, { attr: { y: y + h - 18 } }, { attr: { y: Y(v) - 18 }, duration: dur, ease: "power3.out" }, t);
        FX.countUp(tl, val, t, v, num);
      });
      labels((i) => x + i * slot + slot / 2);
    } else {
      const X = (i) => x + (n > 1 ? (i * w) / (n - 1) : w / 2), pts = data.map((v, i) => `${X(i)},${Y(v)}`), d = "M" + pts.join(" L");
      if (type === "area") { const a = FX.el(svg, "path", { d: `${d} L${X(n - 1)},${y + h} L${X(0)},${y + h} Z`, fill: c, opacity: 0 }); tl.to(a, { attr: { opacity: 0.22 }, duration: dur * 0.6 }, at + dur * 0.6); }
      const line = FX.el(svg, "path", { d, fill: "none", stroke: c, "stroke-width": o.stroke || 8, "stroke-linecap": "round", "stroke-linejoin": "round" });
      FX.drawOn(tl, line, at + 0.1, { dur: dur * 1.2, ease: "power1.inOut" });
      const dot = FX.el(svg, "circle", { cx: X(n - 1), cy: Y(data[n - 1]), r: 14, fill: c, stroke: ink, "stroke-width": 4 });
      tl.fromTo(dot, { scale: 0, transformOrigin: "50% 50%" }, { scale: 1, duration: 0.35, ease: "back.out(3)" }, at + 0.1 + dur * 1.2);
      const val = text("0", X(n - 1), Y(data[n - 1]) - 34, o.valueSize || 48, 900);
      FX.countUp(tl, val, at + 0.1 + dur * 0.6, data[n - 1], num);
      labels(X);
    }
    return svg;
  };

  /* paper cut: torn-edged paper with grain and a soft shadow. FX.paperSheet(root, {x, y, w, h, color, edges: "tblr",
     tear, seed, html}) -> sheet; FX.paperCut(tl, root, at, {colors, top, dur}) = layered torn hills sliding up + swaying */
  const torn = (seed, edges, amp, hills = 0) => {
    const r = FX.rand(seed), n = 46, pts = [], j = (k) => (r() - 0.5) * amp + (hills ? Math.sin((k / n) * Math.PI * hills + seed) * amp * 3 : 0);
    for (let k = 0; k <= n; k++) pts.push([(k / n) * 100, edges.includes("t") ? amp * 3 + j(k) : 0]);
    for (let k = 1; k <= n; k++) pts.push([edges.includes("r") ? 100 - amp - (r() - 0.5) * amp : 100, (k / n) * 100]);
    for (let k = n - 1; k >= 0; k--) pts.push([(k / n) * 100, edges.includes("b") ? 100 - amp - (r() - 0.5) * amp : 100]);
    for (let k = n - 1; k > 0; k--) pts.push([edges.includes("l") ? amp + (r() - 0.5) * amp : 0, (k / n) * 100]);
    return `polygon(${pts.map((p) => `${p[0].toFixed(2)}% ${p[1].toFixed(2)}%`).join(",")})`;
  };
  FX.paperSheet = (root, o = {}) => {
    const wrap = div(root, { position: "absolute", left: (o.x ?? 96) + "px", top: (o.y ?? 600) + "px", width: (o.w ?? 888) + "px", height: (o.h ?? 500) + "px",
                             filter: `drop-shadow(0 ${o.lift ?? 14}px ${(o.lift ?? 14) * 1.4}px rgba(0,0,0,.35))` });
    const sheet = div(wrap, { position: "absolute", inset: 0, backgroundColor: o.color || "#f3efe6", backgroundImage: GRAIN, clipPath: torn(o.seed || 7, o.edges ?? "tblr", o.tear ?? 1.2),
                              boxSizing: "border-box", padding: o.pad ?? "48px", color: o.ink || "#1b1b1b" }, o.html ?? null);
    wrap.sheet = sheet;
    return wrap;
  };
  FX.paperCut = (tl, root, at, o = {}) => {
    const [W, H] = dims(root), cols = o.colors || ["#f6d7a7", "#eea47f", "#d1665a", "#7b3f61", "#2e294e"], top = o.top ?? 0.42;
    return cols.map((col, i) => {
      const y = H * top + (i * H * (1 - top)) / (cols.length + 1);
      const l = FX.paperSheet(root, { x: -W * 0.05, y, w: W * 1.1, h: H - y + 40, color: col, edges: "t", tear: 1.4 + i * 0.3, seed: (o.seed || 5) + i * 13, pad: 0, lift: 10 + i * 3 });
      l.sheet.style.clipPath = torn((o.seed || 5) + i * 13, "t", 1.2, 2 + (i % 3));
      tl.fromTo(l, { yPercent: 70 + i * 8 }, { yPercent: 0, duration: 0.9, ease: "power3.out" }, at + i * 0.12);
      if (o.dur) tl.to(l, { x: (i % 2 ? -1 : 1) * (10 + i * 6), duration: o.dur, ease: "sine.inOut" }, at + 0.9);
      return l;
    });
  };

  /* doodle boil: hand-drawn wobble, the drawing re-jitters ~12x a second (cycling turbulence seeds, deterministic).
     FX.boil(el, T, {amount, freq, fps}) on any element/svg; FX.doodle(tl, root, at, "M..path", {T, color, width}) draws a
     boiling marker line */
  FX.boil = (el, T, o) => {   // FX.boil(el, T, {amount}) or FX.boil(root, {px, targets, freq, fps})
    if (o === undefined && T && typeof T.start !== "number") { o = T; T = null; }
    o = o || {};
    const id = "fxboil" + uid++, svg = document.createElementNS(NS, "svg");
    Object.assign(svg.style, { position: "absolute", width: 0, height: 0 });
    svg.innerHTML = `<filter id="${id}" x="-10%" y="-10%" width="120%" height="120%"><feTurbulence type="turbulence" baseFrequency="${o.freq || 0.025}" numOctaves="2" seed="1"/>` +
                    `<feDisplacementMap in="SourceGraphic" scale="${o.amount ?? o.px ?? 7}" xChannelSelector="R" yChannelSelector="G"/></filter>`;
    document.body.appendChild(svg);
    (o.targets || [el]).forEach((e) => { e.style.filter = `url(#${id})`; });
    const turb = svg.querySelector("feTurbulence"), fps = o.fps || 12, frames = o.frames || 3;
    FX.onFrame((t) => { if (T && (t < T.start - 0.1 || t > T.end + 0.1)) return; turb.setAttribute("seed", 1 + (Math.floor(t * fps) % frames)); });
    return el;
  };
  FX.doodle = (tl, root, at, d, o = {}) => {
    const [W, H] = dims(root), svg = FX.svg(root, W, H);
    const p = FX.el(svg, "path", { d, fill: "none", stroke: o.color || "#fff", "stroke-width": o.width || 8, "stroke-linecap": "round", "stroke-linejoin": "round" });
    FX.drawOn(tl, p, at, { dur: o.dur || 0.8 });
    FX.boil(svg, o.T, o);
    return p;
  };

  /* vertigo (dolly zoom): the background pulls away (or rushes in, {inward: true}) while the subject holds its size.
     bg = full-frame picture element, subject = cut-out element of the same picture (transparent PNG) or null */
  FX.vertigo = (tl, bg, subject, T, o = {}) => {
    const a = o.amount || 0.3, f = o.focus || [0.5, 0.5], d = o.dur || Math.max(0.5, T.dur), at = o.at ?? T.start, org = `${f[0] * 100}% ${f[1] * 100}%`;
    const [s0, s1] = o.inward ? [1, 1 + a] : [1 + a, 1];
    gsap.set(bg, { transformOrigin: org });
    tl.fromTo(bg, { scale: s0, filter: "blur(0px)" }, { scale: s1, duration: d, ease: o.ease || "power1.inOut" }, at);
    tl.to(bg, { filter: "blur(1.5px)", duration: d / 2, yoyo: true, repeat: 1, ease: "sine.inOut" }, at);
    if (subject) gsap.set(subject, { transformOrigin: org, scale: 1 + a });   // never smaller than the subject in bg
  };

  /* cover story: a magazine cover drops in (masthead, cover lines, headline, barcode); a cutout PNG of the picture puts
     the subject in front of the masthead. FX.coverStory(tl, root, at, {img, cutout, masthead, issue, kicker, headline,
     lines: [..], color, accent}) -> cover element */
  FX.coverStory = (tl, root, at, o = {}) => {
    const [W, H] = dims(root), cw = o.w || W * 0.82, ch = cw * 1.32, ac = o.accent || "#facc15", ink = o.color || "#fff";
    const cover = div(root, { position: "absolute", left: (W - cw) / 2 + "px", top: (o.y ?? (H - ch) / 2 - 60) + "px", width: cw + "px", height: ch + "px", overflow: "hidden",
                              background: "#111", boxShadow: "0 50px 110px -30px rgba(0,0,0,.75)", color: ink, fontFamily: '"Inter Tight"' });
    div(cover, { position: "absolute", inset: 0 }, media(o.img));
    const mast = div(cover, { position: "absolute", left: 0, right: 0, top: cw * 0.03 + "px", textAlign: "center", lineHeight: 0.9, letterSpacing: "-.02em", textTransform: "uppercase",
                              font: `${o.mastSize || cw * 0.22}px ${o.mastFont || '"DM Serif Display", serif'}`, color: o.mastColor || ink });
    mast.textContent = o.masthead || "STORY";
    if (o.cutout) div(cover, { position: "absolute", inset: 0 }, `<img src="${o.cutout}" style="width:100%;height:100%;object-fit:cover;display:block">`);
    const issue = div(cover, { position: "absolute", left: cw * 0.05 + "px", top: cw * 0.26 + "px", font: "700 20px 'Inter Tight'", letterSpacing: ".2em", textTransform: "uppercase" });
    issue.textContent = o.issue || "";
    const lines = (o.lines || []).map((l, i) => div(cover, { position: "absolute", left: cw * 0.05 + "px", top: cw * (0.42 + i * 0.13) + "px", width: cw * 0.36 + "px",
                                                            borderLeft: `6px solid ${ac}`, paddingLeft: "14px", font: "800 30px/1.1 'Inter Tight'", textShadow: "0 2px 12px rgba(0,0,0,.5)" }, l));
    const head = div(cover, { position: "absolute", left: cw * 0.05 + "px", right: cw * 0.05 + "px", bottom: cw * 0.08 + "px", textShadow: "0 4px 24px rgba(0,0,0,.55)" },
                     `<div style="font:800 24px 'Inter Tight';letter-spacing:.18em;text-transform:uppercase;color:${ac}">${o.kicker || ""}</div>` +
                     `<div style="font:900 ${o.headSize || 76}px/0.95 'Inter Tight';letter-spacing:-.02em;text-transform:uppercase">${o.headline || ""}</div>`);
    div(cover, { position: "absolute", right: cw * 0.05 + "px", bottom: cw * 0.04 + "px", width: "120px", height: "54px", background: "repeating-linear-gradient(90deg,#111 0 3px,#fff 3px 5px,#111 5px 6px,#fff 6px 10px)", border: "6px solid #fff" });
    div(cover, { position: "absolute", inset: 0, pointerEvents: "none", background: "linear-gradient(125deg, rgba(255,255,255,.18), transparent 30%, transparent 70%, rgba(255,255,255,.06))" });
    tl.fromTo(cover, { y: 180, rotation: -7, scale: 1.08, opacity: 0 }, { y: 0, rotation: o.tilt ?? -2, scale: 1, opacity: 1, duration: 0.7, ease: "power4.out" }, at);
    tl.fromTo(mast, { yPercent: -40, opacity: 0 }, { yPercent: 0, opacity: 1, duration: 0.5, ease: "power3.out" }, at + 0.3);
    tl.fromTo([issue, ...lines], { x: -30, opacity: 0 }, { x: 0, opacity: 1, duration: 0.35, stagger: 0.12 }, at + 0.55);
    tl.fromTo(head, { y: 40, opacity: 0 }, { y: 0, opacity: 1, duration: 0.45 }, at + 0.7);
    return cover;
  };

  /* glass type: frosted-glass letters: the picture behind (bg = image URL, same framing as the scene background) shows
     through blurred and brightened inside the glyphs, with a bright rim, a top highlight and a shine sweep */
  FX.glassType = (tl, root, at, text, o = {}) => {
    const [W, H] = dims(root), size = o.size || 230, x = o.x ?? W / 2, y = o.y ?? H * 0.42, id = "fxg" + uid++, lines = String(text).split("\n");
    const font = `font-family="${o.font || "Inter Tight"}" font-weight="${o.weight || 900}" font-size="${size}" text-anchor="middle" letter-spacing="${o.tracking ?? -4}"`;
    const T = (attrs) => `<text x="${x}" y="${y}" ${font} ${attrs}>${lines.map((l, i) => `<tspan x="${x}" dy="${i ? size * 0.92 : 0}">${l}</tspan>`).join("")}</text>`;
    const svg = FX.svg(root, W, H);
    svg.innerHTML = `<defs><clipPath id="${id}c">${T("")}</clipPath>` +
      `<filter id="${id}f"><feGaussianBlur stdDeviation="${o.blur || 14}"/><feColorMatrix type="matrix" values="1.15 0 0 0 .06  0 1.15 0 0 .06  0 0 1.15 0 .08  0 0 0 1 0"/></filter>` +
      `<linearGradient id="${id}g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".55"/><stop offset=".45" stop-color="#fff" stop-opacity="0"/></linearGradient>` +
      `<linearGradient id="${id}s" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".5" stop-color="#fff" stop-opacity=".7"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient></defs>` +
      `<g class="gt" style="filter:drop-shadow(0 24px 40px rgba(0,0,0,.35))">` +
      (o.bg ? `<image href="${o.bg}" width="${W}" height="${H}" preserveAspectRatio="xMidYMid slice" clip-path="url(#${id}c)" filter="url(#${id}f)"/>` : "") +
      T(`fill="${o.tint || "rgba(255,255,255,.16)"}"`) + T(`fill="url(#${id}g)"`) +
      `<rect class="sh" x="${-W}" y="0" width="${W * 0.5}" height="${H}" fill="url(#${id}s)" clip-path="url(#${id}c)" transform="skewX(-15)"/>` +
      T(`fill="none" stroke="rgba(255,255,255,.7)" stroke-width="2"`) + `</g>`;
    const g = svg.querySelector(".gt");
    tl.fromTo(g, { opacity: 0, y: 50 }, { opacity: 1, y: 0, duration: 0.7, ease: "power3.out" }, at);
    tl.fromTo(svg.querySelector(".sh"), { attr: { x: -W * 0.6 } }, { attr: { x: W * 1.2 }, duration: o.shineDur || 1.4, ease: "power2.inOut" }, at + 0.5);
    return svg;
  };

  /* freeze frame: the moment stops: a white flash, the picture (target) turns grey-contrasty, a white inset frame snaps
     in and a stamp label lands. End the scene's other motion at `at` so it really holds still */
  FX.freezeFrame = (tl, root, at, o = {}) => {
    const flash = div(root, { position: "absolute", inset: 0, background: "#fff", opacity: 0, pointerEvents: "none", zIndex: 20 });
    tl.fromTo(flash, { opacity: 0.95 }, { opacity: 0, duration: 0.3, ease: "power2.out", immediateRender: false }, at);
    if (o.target) tl.to(o.target, { filter: o.filter || "grayscale(1) contrast(1.25) brightness(.95)", duration: 0.05, ease: "none" }, at);
    const fr = div(root, { position: "absolute", inset: (o.inset ?? 40) + "px", border: `${o.border ?? 10}px solid #fff`, pointerEvents: "none", zIndex: 19 });
    tl.fromTo(fr, { opacity: 0, scale: 1.06 }, { opacity: 1, scale: 1, duration: 0.25, ease: "power3.out" }, at);
    let stamp = null;
    if (o.label) {
      stamp = div(root, { position: "absolute", left: (o.x ?? 90) + "px", top: (o.y ?? 260) + "px", padding: "12px 22px", background: o.color || "var(--accent, #e5483f)",
                          color: o.ink || "#fff", font: `900 ${o.size || 54}px "Inter Tight"`, textTransform: "uppercase", letterSpacing: ".02em", zIndex: 21 });
      stamp.textContent = o.label; gsap.set(stamp, { rotation: o.tilt ?? -4 });
      tl.fromTo(stamp, { scale: 2.2, opacity: 0 }, { scale: 1, opacity: 1, duration: 0.25, ease: "power4.in" }, at + 0.25);
    }
    return { flash, frame: fr, stamp };
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
  const rot = (el, a, x, y) => el.setAttribute("transform", `rotate(${a.toFixed(2)} ${x} ${y})`);
  // one rig's joint values at t: base pose (FX.pose tweens, or FX.act's flow) + emotion acting (man.act) + additive
  // layers (FX.alive idle, FX.wave, FX.land / FX.hop / FX.float) + walking; y in drawing units, x in px
  function solve(man, walks, t) {
    const s = man.s, a = man.act || {}, P = man.poseAt ? Object.assign({}, s, man.poseAt(t)) : s;
    const L = {};
    for (const f of man.layers) { const v = f(t) || {}; for (const key in v) L[key] = (L[key] || 0) + v[key]; }
    const l = (key) => L[key] || 0;
    let x = s.x + (a.x || 0) + l("x"), swing = 0;
    for (const w of walks) {
      if (t >= w.at + w.dur) x += w.dx;
      else if (t > w.at) { const p = (t - w.at) / w.dur; x += w.dx * p; swing = Math.sin(p * w.steps * Math.PI); }
    }
    const lift = (a.y || 0) + l("y");
    man._x = x; man._lift = lift;
    return { x, y: P.y + (swing ? Math.abs(swing) * -8 : 0) + lift, lift, sq: (a.sq || 0) + l("sq"),   // squash (+) / stretch (-), volume kept, pivots at the feet
             lean: P.lean + (a.lean ?? 0) + l("lean"), head: P.head + (a.head || 0) + l("head"),
             hL: P.hL + l("hL") + swing * 26, kL: P.kL + l("kL") + Math.max(0, -swing) * 30,
             hR: P.hR + l("hR") - swing * 26, kR: P.kR + l("kR") + Math.max(0, swing) * -30,
             sL: (a.sL ?? P.sL) + l("sL") - swing * 22, eL: P.eL + l("eL"),
             sR: (a.sR ?? P.sR) + l("sR") + swing * 22, eR: (a.eR ?? P.eR) + l("eR") };
  }
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
    if (o.face !== false) {   // the face turns a little with the gaze (faceG), the eyes glide and blink on their own (eyeG)
      const ink = o.ink || "#111";
      face.g = mk("g", {}, headG); face.eyeG = mk("g", {}, face.g);
      face.eyes = [mk("circle", { cx: -14, cy: -344, r: 5.5, fill: ink }, face.eyeG), mk("circle", { cx: 14, cy: -344, r: 5.5, fill: ink }, face.eyeG)];
      face.mouth = mk("path", { d: "M-13,-318 Q0,-312 13,-318", stroke: ink, "stroke-width": 4, fill: "none", "stroke-linecap": "round" }, face.g);
    }
    if (o.prop) mk("g", {}, armR[1]).innerHTML = o.prop;   // optional SVG markup held in the right hand (e.g. a phone)
    const s = Object.assign({ x: 0 }, POSES[o.pose || "stand"]);
    FX._men = (FX._men || 0) + 1;
    const walks = [];
    const man = { svg, g, s, face, k, seed: o.seed ?? FX._men * 1.7, layers: [], gaze: [0, 0], lid: 0,
      walk(at, dur, dx, o2 = {}) { walks.push({ at, dur, dx, steps: o2.steps || Math.max(2, Math.round(dur * 2.2)) }); },
      mouth(kind) { if (!face.mouth) return; face.mouth.setAttribute("d", { smile: "M-15,-322 Q0,-306 15,-322", grin: "M-20,-324 Q0,-298 20,-324 Z", flat: "M-13,-318 L13,-318", o: "M-6,-318 a6,7 0 1,0 12,0 a6,7 0 1,0 -12,0", frown: "M-13,-312 Q0,-322 13,-312" }[kind] || kind); },
    };
    FX.onFrame((t0) => {
      const t = o.twos ? Math.floor(t0 * 12) / 12 : t0;   // characters on twos (12 fps), camera stays smooth
      const R = solve(man, walks, t);
      g.setAttribute("transform", `translate(${(R.x / k).toFixed(1)} ${R.y.toFixed(1)}) scale(${(1 + R.sq * 0.6).toFixed(3)} ${(1 - R.sq).toFixed(3)})`);
      body.setAttribute("transform", `rotate(${R.lean.toFixed(2)} 0 -170)`);
      rot(legL[0], R.hL, 0, -170); rot(legL[1], R.kL, 0, -85);
      rot(legR[0], R.hR, 0, -170); rot(legR[1], R.kR, 0, -85);
      rot(armL[0], R.sL, 0, -285); rot(armL[1], R.eL, 0, -215);
      rot(armR[0], R.sR, 0, -285); rot(armR[1], R.eR, 0, -215);
      rot(headG, R.head, 0, -300);
      if (face.eyeG) {   // gaze -1..1 slides the eyes (they lead) and the face a little; lid 0..1 closes them at their middle
        const [gx, gy] = man.gaze, sy = 1 - 0.9 * Math.min(1, Math.max(0, man.lid));
        face.g.setAttribute("transform", `translate(${(4 * gx).toFixed(2)} ${(2 * gy).toFixed(2)})`);
        face.eyeG.setAttribute("transform", `translate(${(5 * gx).toFixed(2)} ${(3 * gy - 344 * (1 - sy)).toFixed(2)}) scale(1 ${sy.toFixed(3)})`);
      }
    });
    (FX._cast = FX._cast || []).push({ man, scene: FX._scene });   // motion lint: a character with no idle life is frozen
    return man;
  };
  /* ---- an illustrated character (SVG puppet) with a LIVE face, for scenes that need more than a stickman: eye whites
     with pupils that slide (clipped), skin lids and a happy-squint cheek that rise over them (clipped 2 units larger than
     the white, so a closed eye never shows a ring), a mouth that opens and closes (never swapped), hair, optional hat,
     shirt + overalls, hands, boots and a floor shadow that shrinks as it leaves the ground. Same joints and poses as
     FX.stickman, so FX.pose / FX.act / FX.wave / FX.alive / FX.land / FX.hop / FX.float / man.walk all drive it.
     const kid = FX.character(root, {x: 540, y: 1500, h: 520, skin: "#c98a5e", hair: "#2b1a12", style: "pigtails" | "bob" |
       "short" | "bald", hat: "#f4a6b8" | false, shirt: "#e8645a", pants: "#3d6fd6", shoes: "#3f9a55", stripes: true,
       bow: "#b57cf0" | false})
     species: "dog" | "cat" | "budgie" draws an upright cartoon animal on the same rig instead (no clothes; hair / shirt /
     pants / shoes are ignored; skin = fur or body feathers). Its tail sways on its own (a dog wags harder when happy:
     cheek), dog ears drag behind the head, cat ears twitch now and then, the budgie's wings are its arms and its beak
     opens for the mouth. Colours: dog {skin, belly, ear, nose, collar | false}; cat {skin, belly, ear (inner), nose,
     stripe | false, whisker}; budgie {skin, belly, face (mask + wing base), bars, cheek, beak, cere, tail, feet}
       (a blue budgie: skin "#6fb6e8", belly "#9fd0f2", face "#f4f4f4", tail "#2f4fa8"; a hen's cere: "#c9a27a").
     Face channels (FX.alive sets them): kid.gaze [-1..1, -1..1], kid.lid 0..1, kid.cheek 0..1, kid.mouth 0..1. ---- */
  const SPECIES = {
    human: {},
    dog: { skin: "#c8894a", belly: "#f4dfbf", ear: "#8a5530", nose: "#2b1d18", collar: "#e8483f" },
    cat: { skin: "#e8964b", belly: "#fbe8d3", ear: "#f7a8b8", nose: "#f28aa0", stripe: "#c46f2c", whisker: "rgba(60,35,25,.55)" },
    budgie: { skin: "#79c84a", belly: "#a6dc6a", face: "#f4dc3c", bars: "#2b2b2b", cheek: "#5a5fd8", beak: "#f1c27d",
              cere: "#5b8fe0", tail: "#3a63c4", feet: "#d9a7a0" },
  };
  FX.character = (root, o = {}) => {
    const h = o.h || 440, k = h / 400, NS = "http://www.w3.org/2000/svg", id = "fxc" + ((FX._men = (FX._men || 0) + 1));
    const sp = SPECIES[o.species] ? o.species : "human", furry = sp === "dog" || sp === "cat", bird = sp === "budgie";
    const C = Object.assign({ skin: "#c98a5e", hair: "#2b1a12", shirt: "#e8645a", pants: "#3d6fd6", shoes: "#3f9a55", ink: "#1e1414",
                              white: "#ffffff", mouth: "#6b2222", blush: "#ff7a7a", hat: false, bow: false, style: "bob" }, SPECIES[sp], o);
    // where the joints sit (drawing units, feet at y 0): the budgie is an egg on short legs, its wings hang from the body
    const L = bird ? { hip: -60, neck: [0, -214], legTop: -48, thigh: 24, shoulder: -200, upper: 60, arm: 64, eye: [30, -296, 28, 36] }
                   : { hip: -112, neck: [0, -206], legTop: -112, thigh: 54, shoulder: -192, upper: 44, arm: 46, eye: furry ? [32, -288, 34, 44] : [31, -282, 34, 44] };
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("width", 320 * k); svg.setAttribute("height", 500 * k); svg.setAttribute("viewBox", "-160 -470 320 500");
    Object.assign(svg.style, { position: "absolute", left: (o.x ?? 540) - 160 * k + "px", top: (o.y ?? 1500) - 470 * k + "px", overflow: "visible", zIndex: o.z || 5 });
    root.appendChild(svg);
    const mk = (tag, attrs, parent) => { const e = document.createElementNS(NS, tag); for (const [a, v] of Object.entries(attrs)) e.setAttribute(a, v); (parent || svg).appendChild(e); return e; };
    const pill = (cx, cy, w, hh) => { const r = Math.min(w, hh) / 2, x = cx - w / 2, y = cy - hh / 2; return `M${x + r} ${y}H${x + w - r}A${r} ${r} 0 0 1 ${x + w} ${y + r}V${y + hh - r}A${r} ${r} 0 0 1 ${x + w - r} ${y + hh}H${x + r}A${r} ${r} 0 0 1 ${x} ${y + hh - r}V${y + r}A${r} ${r} 0 0 1 ${x + r} ${y}Z`; };
    const round = { "stroke-linecap": "round", fill: "none" };
    const defs = mk("defs", {});
    const shadow = mk("ellipse", { cx: 0, cy: 2, rx: bird ? 70 : 78, ry: 13, fill: o.shadow || "rgba(0,0,0,.16)" });
    const g = mk("g", {}), body = mk("g", {}, g);
    // the tail sits behind everything and sways from its base on its own clock: [group, base x, base y, angle(t, cheek)]
    let tail = null;
    if (furry || bird) {
      const tg = mk("g", {}, body);
      if (sp === "dog") {
        mk("path", { d: "M22,-118 Q72,-118 80,-186", stroke: C.skin, "stroke-width": 18, ...round }, tg);
        mk("circle", { cx: 80, cy: -188, r: 9, fill: C.belly }, tg);
        tail = [tg, 22, -118, (t, ch) => 6 * Math.sin(t * 2 * Math.PI / 1.6) + 16 * ch * Math.sin(t * 2 * Math.PI / 0.36)];
      } else if (sp === "cat") {
        mk("path", { d: "M24,-116 C92,-112 66,-204 104,-252", stroke: C.skin, "stroke-width": 15, ...round }, tg);
        if (C.stripe) for (const [x1, y1, x2, y2] of [[66, -150, 82, -146], [80, -192, 94, -190], [94, -226, 106, -228]])
          mk("line", { x1, y1, x2, y2, stroke: C.stripe, "stroke-width": 6, ...round }, tg);
        tail = [tg, 24, -116, (t) => 7 * Math.sin(t * 2 * Math.PI / 2.8) + 3 * Math.sin(t * 2 * Math.PI / 1.1)];
      } else {
        mk("path", { d: "M10,-104 L36,-120 L104,-26 Q100,-12 86,-16 Z", fill: C.tail }, tg);   // long tail feathers out to one side
        mk("path", { d: "M24,-110 L94,-22", stroke: "rgba(0,0,0,.18)", "stroke-width": 3, ...round }, tg);
        tail = [tg, 22, -110, (t) => 3 * Math.sin(t * 2 * Math.PI / 3.2)];
      }
    }
    // back hair turns with the head but sits behind the body
    const back = mk("g", {}, body);
    if (sp === "human") {
      if (C.style === "bob" || C.style === "pigtails") mk("ellipse", { cx: 0, cy: -282, rx: 94, ry: 88, fill: C.hair }, back);
      if (C.style === "pigtails") for (const sx of [-1, 1]) { mk("circle", { cx: 100 * sx, cy: -238, r: 27, fill: C.hair }, back); mk("circle", { cx: 84 * sx, cy: -254, r: 8, fill: C.shirt }, back); }
      if (C.style === "short") mk("ellipse", { cx: 0, cy: -298, rx: 86, ry: 80, fill: C.hair }, back);
    }
    // legs (thigh + shin with a boot, a paw or bird toes) from the hips
    const leg = (x) => {
      const a = mk("g", {}, body), top = L.legTop, knee = top + L.thigh;
      if (bird) {
        mk("line", { x1: x, y1: top, x2: x, y2: knee, stroke: C.feet, "stroke-width": 9, ...round }, a);
        const b = mk("g", {}, a);
        mk("line", { x1: x, y1: knee, x2: x, y2: -5, stroke: C.feet, "stroke-width": 8, ...round }, b);
        for (const dx of [-13, 0, 13]) mk("line", { x1: x, y1: -5, x2: x + dx, y2: 2, stroke: C.feet, "stroke-width": 6, ...round }, b);
        return [a, b, x];
      }
      mk("line", { x1: x, y1: top, x2: x, y2: knee, stroke: C.skin, "stroke-width": 22, "stroke-linecap": "round" }, a);
      const b = mk("g", {}, a);
      mk("line", { x1: x, y1: knee, x2: x, y2: top + 98, stroke: C.skin, "stroke-width": 21, "stroke-linecap": "round" }, b);
      if (furry) {
        mk("ellipse", { cx: x + Math.sign(x) * 4, cy: top + 104, rx: 19, ry: 10, fill: C.skin }, b);
        for (const dx of [-6, 4]) mk("line", { x1: x + dx + Math.sign(x) * 4, y1: top + 99, x2: x + dx + Math.sign(x) * 4, y2: top + 106, stroke: "rgba(0,0,0,.2)", "stroke-width": 2.5, ...round }, b);
      } else mk("path", { d: `M${x - 15},${top + 82} h30 v14 q0,10 -10,10 h-24 q-12,0 -12,-10 q0,-8 10,-8 Z`, fill: C.shoes }, b);
      return [a, b, x];
    };
    const legL = leg(bird ? -22 : -20), legR = leg(bird ? 22 : 20);
    // torso: shirt + overalls, a furry body with a belly patch (and a dog's collar), or the budgie's egg
    const torso = mk("g", {}, body);
    if (bird) {
      mk("ellipse", { cx: 0, cy: -150, rx: 80, ry: 112, fill: C.skin }, torso);
      mk("ellipse", { cx: 0, cy: -126, rx: 54, ry: 80, fill: C.belly }, torso);
    } else if (furry) {
      mk("path", { d: "M-48,-198 Q-50,-210 -36,-210 H36 Q50,-210 48,-198 L52,-112 Q52,-90 30,-88 H-30 Q-52,-90 -52,-112 Z", fill: C.skin }, torso);
      mk("ellipse", { cx: 0, cy: -138, rx: 30, ry: 42, fill: C.belly }, torso);
      if (sp === "dog" && C.collar) { mk("rect", { x: -40, y: -214, width: 80, height: 13, rx: 6.5, fill: C.collar }, torso); mk("circle", { cx: 0, cy: -196, r: 7, fill: "#f5d36b" }, torso); }
    } else {
      mk("path", { d: "M-50,-196 Q-52,-206 -40,-208 H40 Q52,-206 50,-196 L46,-104 Q46,-96 38,-96 H-38 Q-46,-96 -46,-104 Z", fill: C.shirt }, torso);
      if (o.stripes !== false) for (const y of [-186, -170, -154, -138, -122]) mk("rect", { x: -48, y, width: 96, height: 5, fill: "rgba(255,255,255,.35)" }, torso);
      mk("path", { d: `M-34,-160 H34 V-112 H52 Q54,-84 30,-80 H-30 Q-54,-84 -52,-112 H-34 Z`, fill: C.pants }, torso);
      for (const sx of [-1, 1]) { mk("line", { x1: 30 * sx, y1: -158, x2: 40 * sx, y2: -204, stroke: C.pants, "stroke-width": 9, "stroke-linecap": "round" }, torso); mk("circle", { cx: 26 * sx, cy: -150, r: 4.5, fill: "#f5d36b" }, torso); }
      mk("rect", { x: -14, y: -140, width: 28, height: 18, rx: 4, fill: "rgba(0,0,0,.12)" }, torso);
    }
    // arms: sleeve + forearm + hand, a furry arm with a paw, or a wing (covert feathers + the flight-feather tip)
    const arm = (x) => {
      const a = mk("g", {}, body), top = L.shoulder, elbow = top + L.upper;
      if (bird) {
        mk("path", { d: `M${x},${top - 6} Q${x + 22},${top + 10} ${x + 20},${elbow - 10} L${x + 14},${elbow + 2} H${x - 14} L${x - 20},${elbow - 10} Q${x - 22},${top + 10} ${x},${top - 6} Z`, fill: C.face }, a);
        for (const y of [top + 16, top + 32, top + 48]) mk("path", { d: `M${x - 16},${y} Q${x},${y + 10} ${x + 16},${y}`, stroke: C.bars, "stroke-width": 4, ...round }, a);
        const b = mk("g", {}, a);
        mk("path", { d: `M${x - 14},${elbow} H${x + 14} Q${x + 12},${elbow + 40} ${x},${elbow + 56} Q${x - 12},${elbow + 40} ${x - 14},${elbow} Z`, fill: C.tail }, b);
        mk("path", { d: `M${x},${elbow + 4} V${elbow + 46}`, stroke: "rgba(0,0,0,.2)", "stroke-width": 3, ...round }, b);
        return [a, b, x];
      }
      mk("line", { x1: x, y1: top, x2: x, y2: elbow, stroke: furry ? C.skin : C.shirt, "stroke-width": furry ? 17 : 19, "stroke-linecap": "round" }, a);
      const b = mk("g", {}, a);
      mk("line", { x1: x, y1: elbow, x2: x, y2: -110, stroke: C.skin, "stroke-width": 15, "stroke-linecap": "round" }, b);
      mk("circle", { cx: x, cy: -104, r: furry ? 13.5 : 12.5, fill: C.skin }, b);
      if (furry) mk("ellipse", { cx: x, cy: -101, rx: 6, ry: 4.5, fill: C.belly }, b);
      return [a, b, x];
    };
    const armL = arm(-L.arm), armR = arm(L.arm);
    if (o.prop) mk("g", {}, armR[1]).innerHTML = o.prop;   // optional SVG markup in the right hand (around (46, -104); a wing tip ~(64, -90))
    // head (ears that move on their own: [group, pivot x, pivot y, angle(t, head)])
    const headG = mk("g", {}, body), ears = [];
    const ph = (o.seed ?? FX._men * 1.7) * 0.37;
    if (sp === "cat") for (const sx of [-1, 1]) {
      const eg = mk("g", {}, headG);
      mk("path", { d: `M${36 * sx},-336 L${70 * sx},-392 L${86 * sx},-318 Z`, fill: C.skin, "stroke-linejoin": "round", stroke: C.skin, "stroke-width": 8 }, eg);
      mk("path", { d: `M${48 * sx},-334 L${69 * sx},-374 L${78 * sx},-326 Z`, fill: C.ear }, eg);
      // a twitch every ~4 s, each ear on its own phase
      ears.push([eg, 62 * sx, -330, (t) => { const p = (t + ph + (sx > 0 ? 1.9 : 0)) % 4.3; return p < 0.28 ? -10 * sx * Math.sin((p / 0.28) * Math.PI) : 0; }]);
    }
    if (sp === "human") {
      mk("rect", { x: -13, y: -222, width: 26, height: 22, fill: C.skin }, headG);
      for (const sx of [-1, 1]) mk("circle", { cx: 80 * sx, cy: -274, r: 15, fill: C.skin }, headG);
      mk("ellipse", { cx: 0, cy: -280, rx: 82, ry: 76, fill: C.skin }, headG);
    } else if (furry) {
      mk("ellipse", { cx: 0, cy: -282, rx: 86, ry: 74, fill: C.skin }, headG);
      if (sp === "cat") for (const sx of [-1, 1]) mk("path", { d: `M${80 * sx},-262 L${98 * sx},-248 L${82 * sx},-238 L${94 * sx},-226 L${72 * sx},-224 Z`, fill: C.skin }, headG);
      if (sp === "cat" && C.stripe) for (const [x, len] of [[-18, 18], [0, 24], [18, 18]]) mk("line", { x1: x, y1: -352, x2: x * 0.8, y2: -352 + len, stroke: C.stripe, "stroke-width": 7, ...round }, headG);
    } else {
      mk("circle", { cx: 0, cy: -290, r: 84, fill: C.skin }, headG);
      const hc = mk("clipPath", { id: id + "h" }, defs); mk("circle", { cx: 0, cy: -290, r: 84 }, hc);
      const barsG = mk("g", { "clip-path": `url(#${id}h)` }, headG);   // the barred crown and nape, around the yellow mask
      for (const sx of [-1, 1]) for (const y of [-350, -330, -310, -290]) mk("path", { d: `M${50 * sx},${y - 8} Q${70 * sx},${y + 4} ${90 * sx},${y - 12}`, stroke: C.bars, "stroke-width": 4, ...round }, barsG);
      mk("ellipse", { cx: 0, cy: -332, rx: 52, ry: 32, fill: C.face }, headG);
      mk("ellipse", { cx: 0, cy: -262, rx: 72, ry: 64, fill: C.face }, headG);
    }
    const lidCol = bird ? C.face : C.skin, [ex, ey, ew, eh] = L.eye;
    const faceG = mk("g", {}, headG), eyes = [];
    for (const sx of [-1, 1]) {
      const cx = ex * sx, cy = ey, w = ew, hh = eh, cid = `${id}e${sx > 0 ? "R" : "L"}`;
      const c1 = mk("clipPath", { id: cid }, defs); mk("path", { d: pill(cx, cy, w, hh) }, c1);
      const c2 = mk("clipPath", { id: cid + "s" }, defs); mk("path", { d: pill(cx, cy, w + 2, hh + 2) }, c2);
      mk("path", { d: pill(cx, cy, w, hh), fill: C.white }, faceG);
      const inner = mk("g", { "clip-path": `url(#${cid})` }, faceG);
      const pupil = mk("g", {}, inner);
      const pw = w * 0.53, ph2 = hh * 0.57;
      mk("rect", { x: cx - pw / 2, y: cy - hh / 2 + hh * 0.25, width: pw, height: ph2, rx: pw / 2, fill: C.ink }, pupil);
      mk("circle", { cx: cx - pw / 6, cy: cy - hh / 2 + hh * 0.41, r: w * 0.124, fill: C.white }, pupil);
      const skinG = mk("g", { "clip-path": `url(#${cid}s)` }, faceG);
      const lid = mk("rect", { x: cx - w / 2 - 2, y: cy - hh / 2 - 2, width: w + 4, height: 0, fill: lidCol }, skinG);
      const lash = mk("line", { x1: cx - w / 2 - 2, x2: cx + w / 2 + 2, y1: 0, y2: 0, stroke: C.ink, "stroke-width": 3.5, "stroke-opacity": 0 }, skinG);
      const cheek = mk("rect", { x: cx - w / 2 - 2, y: cy + hh / 2 + 2, width: w + 4, height: 0, fill: lidCol }, skinG);
      const closed = mk("path", { d: `M${cx - sx * w * 0.4} ${cy + 2}H${cx + sx * w * 0.12}Q${cx + sx * w * 0.34} ${cy + 2} ${cx + sx * w * 0.4} ${cy + 2 + hh * 0.16}`, stroke: C.ink, "stroke-width": 5, "stroke-linecap": "round", fill: "none", "stroke-opacity": 0 }, faceG);
      const happy = mk("path", { d: `M${cx - w * 0.42} ${cy + 4}Q${cx} ${cy - hh * 0.5} ${cx + w * 0.42} ${cy + 4}`, stroke: C.ink, "stroke-width": 5, "stroke-linecap": "round", fill: "none", "stroke-opacity": 0 }, faceG);
      eyes.push({ cx, cy, w, hh, pupil, lid, lash, cheek, closed, happy });
    }
    if (!bird) for (const sx of [-1, 1]) mk("ellipse", { cx: 54 * sx, cy: -248, rx: 14, ry: 8, fill: C.blush, opacity: 0.45 }, faceG);
    let mouth = null, beakLo = null, mw = 1;
    if (sp === "human") {
      mk("path", { d: "M-6,-258 Q0,-252 6,-258", stroke: "rgba(0,0,0,.28)", "stroke-width": 4, fill: "none", "stroke-linecap": "round" }, faceG);
    } else if (sp === "dog") {
      mk("ellipse", { cx: 0, cy: -246, rx: 42, ry: 28, fill: C.belly }, faceG);
      mw = 0.9;
    } else if (sp === "cat") {
      for (const sx of [-1, 1]) mk("ellipse", { cx: 13 * sx, cy: -246, rx: 17, ry: 12, fill: C.belly }, faceG);
      mw = 0.75;
    } else {   // budgie: cheek patches, throat spots, the cere, a lower beak that drops to talk, the hooked upper beak over it
      for (const sx of [-1, 1]) mk("ellipse", { cx: 50 * sx, cy: -246, rx: 13, ry: 17, fill: C.cheek }, faceG);
      for (const [x, y] of [[-40, -218], [-15, -210], [15, -210], [40, -218]]) mk("circle", { cx: x, cy: y, r: 5, fill: C.bars }, faceG);
      beakLo = mk("g", {}, faceG);
      mk("path", { d: "M-9,-252 Q0,-248 9,-252 Q7,-236 0,-232 Q-7,-236 -9,-252 Z", fill: "#d9a564" }, beakLo);
      mk("path", { d: "M-15,-266 Q0,-272 15,-266 Q14,-246 2,-230 Q-12,-244 -15,-266 Z", fill: C.beak }, faceG);
      mk("rect", { x: -14, y: -280, width: 28, height: 11, rx: 5.5, fill: C.cere }, faceG);
    }
    if (!bird) mouth = mk("path", { fill: C.mouth, stroke: C.mouth, "stroke-width": 4.5, "stroke-linejoin": "round" }, faceG);
    if (sp === "dog") mk("path", { d: "M-12,-268 Q0,-275 12,-268 Q11,-256 0,-252 Q-11,-256 -12,-268 Z", fill: C.nose }, faceG);
    if (sp === "cat") {
      mk("path", { d: "M-8,-260 H8 L0,-251 Z", fill: C.nose, stroke: C.nose, "stroke-width": 3, "stroke-linejoin": "round" }, faceG);
      for (const sx of [-1, 1]) for (const dy of [-12, 0, 12]) mk("line", { x1: 28 * sx, y1: -248 + dy * 0.3, x2: 100 * sx, y2: -250 + dy, stroke: C.whisker, "stroke-width": 2.5, ...round }, faceG);
    }
    // dog ears hang in front of the head and drag behind its turns
    if (sp === "dog") for (const sx of [-1, 1]) {
      const eg = mk("g", {}, headG);
      mk("path", { d: `M${58 * sx},-346 Q${100 * sx},-344 ${106 * sx},-282 Q${108 * sx},-236 ${84 * sx},-234 Q${62 * sx},-238 ${58 * sx},-292 Z`, fill: C.ear }, eg);
      ears.push([eg, 70 * sx, -340, (t, head) => -0.6 * head + 2.5 * Math.sin((t + ph) * 2 * Math.PI / 2.4 + sx)]);
    }
    // front hair over the forehead, then the hat or a bow
    if (sp === "human" && C.style !== "bald") mk("path", { d: C.style === "short" ? "M-84,-292 Q-80,-370 0,-366 Q80,-370 84,-292 Q70,-326 40,-322 Q10,-342 -20,-322 Q-60,-332 -84,-292 Z"
      : "M-86,-284 Q-84,-372 0,-368 Q84,-372 86,-284 Q64,-330 30,-318 Q0,-340 -30,-318 Q-64,-330 -86,-284 Z", fill: C.hair }, headG);
    if (C.hat) {
      mk("path", { d: "M-70,-338 Q-70,-424 0,-424 Q70,-424 70,-338 Z", fill: C.hat }, headG);
      mk("rect", { x: -70, y: -356, width: 140, height: 14, fill: "rgba(255,255,255,.55)" }, headG);
      mk("ellipse", { cx: 0, cy: -338, rx: 124, ry: 22, fill: C.hat }, headG);
      mk("circle", { cx: 42, cy: -350, r: 9, fill: "#fff" }, headG); mk("circle", { cx: 42, cy: -350, r: 4, fill: "#f5c542" }, headG);
    } else if (C.bow) {
      const bx = bird ? 34 : 46, by = bird ? -362 : -350;
      for (const sx of [-1, 1]) mk("path", { d: `M${bx},${by} L${bx + 30 * sx},${by - 20} Q${bx + 36 * sx},${by} ${bx + 30 * sx},${by + 20} Z`, fill: C.bow, "stroke-linejoin": "round", stroke: C.bow, "stroke-width": 5 }, headG);
      mk("circle", { cx: bx, cy: by, r: 9, fill: C.bow, stroke: "rgba(0,0,0,.15)", "stroke-width": 3 }, headG);
    }
    const s = Object.assign({ x: 0 }, POSES[o.pose || "stand"]);
    const walks = [];
    const man = { svg, g, s, k, face: {}, seed: o.seed ?? FX._men * 1.7, layers: [], gaze: [0, 0], lid: 0, cheek: 0, mouth: 0, rig: "character", species: sp,
      walk(at, dur, dx, o2 = {}) { walks.push({ at, dur, dx, steps: o2.steps || Math.max(2, Math.round(dur * 2.2)) }); },
      mouthShape() {} };
    FX.onFrame((t0) => {
      const t = o.twos ? Math.floor(t0 * 12) / 12 : t0;
      const R = solve(man, walks, t);
      g.setAttribute("transform", `translate(${(R.x / k).toFixed(1)} ${R.y.toFixed(1)}) scale(${(1 + R.sq * 0.6).toFixed(3)} ${(1 - R.sq).toFixed(3)})`);
      const up = Math.max(0, -R.lift), sh = Math.max(0.35, 1 - up / 520);
      shadow.setAttribute("transform", `translate(${(R.x / k).toFixed(1)} 0) scale(${sh.toFixed(3)})`);
      body.setAttribute("transform", `rotate(${R.lean.toFixed(2)} 0 ${L.hip})`);
      rot(legL[0], R.hL, legL[2], L.legTop); rot(legL[1], R.kL, legL[2], L.legTop + L.thigh);
      rot(legR[0], R.hR, legR[2], L.legTop); rot(legR[1], R.kR, legR[2], L.legTop + L.thigh);
      rot(armL[0], R.sL, armL[2], L.shoulder); rot(armL[1], R.eL, armL[2], L.shoulder + L.upper);
      rot(armR[0], R.sR, armR[2], L.shoulder); rot(armR[1], R.eR, armR[2], L.shoulder + L.upper);
      rot(headG, R.head, ...L.neck); rot(back, R.head, ...L.neck);
      const [gx, gy] = man.gaze, lid = Math.min(1, Math.max(0, man.lid)), ch = Math.min(1, Math.max(0, man.cheek)), m = Math.max(0, man.mouth);
      if (tail) rot(tail[0], tail[3](t + ph, ch), tail[1], tail[2]);
      for (const [eg, px, py, f] of ears) rot(eg, f(t, R.head), px, py);
      faceG.setAttribute("transform", `translate(${(3 * gx).toFixed(2)} ${(2 * gy).toFixed(2)})`);
      for (const e of eyes) {
        const H = e.hh + 4, y = e.cy - e.hh / 2 - 2 + lid * H;
        e.pupil.setAttribute("transform", `translate(${(7 * gx).toFixed(2)} ${(6 * gy).toFixed(2)})`);
        e.lid.setAttribute("height", (lid * H).toFixed(2));
        e.lash.setAttribute("y1", y.toFixed(2)); e.lash.setAttribute("y2", y.toFixed(2));
        e.lash.setAttribute("stroke-opacity", (Math.min(1, lid / 0.06) * Math.min(1, Math.max(0, (0.95 - lid) / 0.08))).toFixed(3));
        e.closed.setAttribute("stroke-opacity", Math.min(1, Math.max(0, (lid - 0.88) / 0.12)).toFixed(3));
        e.cheek.setAttribute("y", (e.cy + e.hh / 2 + 2 - ch * H).toFixed(2)); e.cheek.setAttribute("height", (ch * H).toFixed(2));
        e.happy.setAttribute("stroke-opacity", Math.min(1, Math.max(0, (ch - 0.86) / 0.14)).toFixed(3));
      }
      if (beakLo) beakLo.setAttribute("transform", `translate(0 ${(10 * Math.min(1, m)).toFixed(2)})`);   // the beak drops open
      if (mouth) {
        const wd = (15 + 3 * ch) * mw, smile = 5 + 3 * ch;   // the mouth opens downward from a smile line
        mouth.setAttribute("d", `M${-wd},-238 Q0,${-238 + smile} ${wd},-238 Q0,${(-238 + smile + 1 + 26 * m * mw).toFixed(2)} ${-wd},-238 Z`);
      }
    });
    (FX._cast = FX._cast || []).push({ man, scene: FX._scene });
    return man;
  };
  FX.pose = (tl, man, pose, at, o = {}) => { man.poses = (man.poses || 0) + 1; const p = typeof pose === "string" ? POSES[pose] : pose; if (p) tl.to(man.s, { ...p, duration: o.dur || 0.35, ease: o.ease || "power2.inOut" }, at); };
  FX.wave = (tl, man, at, dur = 1.2, arm = "eR") => {   // an accent layer (forearm swings 35° per 0.6 s), so it also rides FX.act
    const per = dur / Math.max(1, Math.round(dur / 0.6));
    man.layers.push((t) => (t > at && t < at + dur ? { [arm]: -17.5 * (1 - Math.cos((2 * Math.PI * (t - at)) / per)) } : {}));
  };

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
    man.live = true;
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

  /* ---- LIFE: drawn things that feel alive, never a slideshow (method after rossark-motion-skill, MIT: one clock, parts
     turn around their real pivots, trailing parts follow a beat later, idle life that never stops, smooth paths through
     key poses, small amplitudes, strong curves, nothing random per frame). Times are seconds of the render clock.
     Math: L = FX.life · L.wave(t, period, phase) -1..1 · L.loop(t, period, phase) 0..1 · L.bell(p) fade in+out over a
     loop · L.seg(t, a, b) 0..1 inside one beat · L.seeded(i, salt) stable variety · L.track(t, [[s, v, "out"?], ...])
     eases into EVERY key (one move: a blink, a lid, a door) · L.flow(t, [[s, v], ...]) passes through key poses with a
     continuous speed and never overshoots (acting) · L.EASE_IO / L.EASE_OUT / L.EASE_IN. ---- */
  const bezier = (x1, y1, x2, y2) => {
    const B = (a, b, u) => 3 * a * u * (1 - u) ** 2 + 3 * b * u * u * (1 - u) + u ** 3;
    return (x) => { if (x <= 0) return 0; if (x >= 1) return 1; let lo = 0, hi = 1, u = x; for (let i = 0; i < 24; i++) { u = (lo + hi) / 2; if (B(x1, x2, u) < x) lo = u; else hi = u; } return B(y1, y2, u); };
  };
  const LIFE = FX.life = {
    EASE_IO: bezier(0.77, 0, 0.175, 1),   // things that travel: gaze, sway, a door, a lid closing
    EASE_OUT: bezier(0.23, 1, 0.32, 1),   // things that open or arrive: a mouth, a lid reopening, a prop appearing
    EASE_IN: bezier(0.55, 0, 1, 0.45),    // only things leaving or falling away
    wave: (t, period, phase = 0) => Math.sin((t / period + phase) * Math.PI * 2),
    loop: (t, period, phase = 0) => { const p = (t / period + phase) % 1; return p < 0 ? p + 1 : p; },
    bell: (p) => Math.sin(Math.PI * Math.min(1, Math.max(0, p))),
    seg: (t, a, b, curve = "out") => (t <= a ? 0 : t >= b ? 1 : (curve === "out" ? LIFE.EASE_OUT : LIFE.EASE_IO)((t - a) / (b - a))),
    seeded: (i, salt = 0) => { const x = Math.sin(i * 12.9898 + salt * 78.233) * 43758.5453; return x - Math.floor(x); },
    track(t, keys) {
      if (t <= keys[0][0]) return keys[0][1];
      for (let i = 1; i < keys.length; i++) {
        const k1 = keys[i];
        if (t <= k1[0]) { const k0 = keys[i - 1], span = k1[0] - k0[0], p = span > 0 ? (t - k0[0]) / span : 1; return k0[1] + (k1[1] - k0[1]) * (k1[2] === "out" ? LIFE.EASE_OUT : LIFE.EASE_IO)(p); }
      }
      return keys[keys.length - 1][1];
    },
    flow(t, k) {   // monotone cubic (Fritsch-Carlson) through the keys
      const n = k.length;
      if (n === 1 || t <= k[0][0]) return k[0][1];
      if (t >= k[n - 1][0]) return k[n - 1][1];
      let i = 0;
      while (k[i + 1][0] < t) i++;
      const slope = (j) => (k[j + 1][1] - k[j][1]) / Math.max(1e-6, k[j + 1][0] - k[j][0]);
      const tangent = (j) => {
        if (j === 0 || j === n - 1) return 0;
        const a = slope(j - 1), b = slope(j);
        if (a * b <= 0) return 0;
        const h0 = k[j][0] - k[j - 1][0], h1 = k[j + 1][0] - k[j][0], w0 = 2 * h1 + h0, w1 = h1 + 2 * h0;
        return (w0 + w1) / (w0 / a + w1 / b);
      };
      const h = k[i + 1][0] - k[i][0], s = (t - k[i][0]) / h, s2 = s * s, s3 = s2 * s;
      return (2 * s3 - 3 * s2 + 1) * k[i][1] + (s3 - 2 * s2 + s) * h * tangent(i) + (-2 * s3 + 3 * s2) * k[i + 1][1] + (s3 - s2) * h * tangent(i + 1);
    },
  };

  /* One transform writer per element: every life recipe on it adds its part (x, y; rot in degrees; sx, sy multiply),
     written as the CSS translate / rotate / scale properties, so GSAP tweens on the same element (its transform)
     still compose with it. The pivot is solved here (not with transform-origin, which GSAP also uses): pivot = a CSS
     origin string ("50% 100%" = the base, default) measured on the element's own box (SVG: its bbox), or [x, y] in
     drawing units (SVG: the parent's user units, e.g. a stem's base, a hinge, a neck, a lamp's hook; HTML: px in the
     element's box). The first recipe on an element sets its pivot. */
  const bodies = new Map();
  const pct = (v, size) => (/%$/.test(v) ? (parseFloat(v) / 100) * size : parseFloat(v) || 0);
  const pivotOf = (el, pivot) => {
    if (typeof pivot === "function") return pivot(el);
    if (Array.isArray(pivot)) return pivot;
    const [px, py] = String(pivot || "50% 100%").replace(/\bleft\b|\btop\b/g, "0%").replace(/\bcenter\b/g, "50%").replace(/\bright\b|\bbottom\b/g, "100%").split(/\s+/);
    if (el instanceof SVGGraphicsElement) { const bb = el.getBBox(); return [bb.x + pct(px, bb.width), bb.y + pct(py ?? "50%", bb.height)]; }
    return [pct(px, el.offsetWidth), pct(py ?? "50%", el.offsetHeight)];
  };
  const living = (el, fn, pivot) => {
    if (!el) return el;
    let b = bodies.get(el);
    if (!b) {
      b = { fns: [], pivot: null }; bodies.set(el, b);
      const svgEl = el instanceof SVGElement && el.tagName.toLowerCase() !== "svg";
      if (svgEl) el.style.transformBox = "view-box";
      FX.onFrame((t) => {
        let x = 0, y = 0, r = 0, sx = 1, sy = 1;
        for (const f of b.fns) { const v = f(t) || {}; x += v.x || 0; y += v.y || 0; r += v.rot || 0; sx *= v.sx ?? 1; sy *= v.sy ?? 1; }
        if (!b.pivot) { if (!el.getClientRects().length) return; b.pivot = pivotOf(el, pivot); }   // measured once, on the first frame it is laid out (a hidden scene measures 0)
        // CSS applies translate · rotate · scale around the element's transform-origin o; turn "around the pivot p" into
        // a translate: T = (x, y) + (p - o) - R·S·(p - o)
        const cs = getComputedStyle(el), [ox, oy] = cs.transformOrigin.split(" ").map(parseFloat);
        const dx = b.pivot[0] - (ox || 0), dy = b.pivot[1] - (oy || 0), c = Math.cos((r * Math.PI) / 180), sn = Math.sin((r * Math.PI) / 180);
        const tx = x + dx - (c * sx * dx - sn * sy * dy), ty = y + dy - (sn * sx * dx + c * sy * dy);
        el.style.translate = `${tx.toFixed(2)}px ${ty.toFixed(2)}px`; el.style.rotate = `${(r % 360).toFixed(3)}deg`; el.style.scale = `${sx.toFixed(4)} ${sy.toFixed(4)}`;
      });
    }
    b.fns.push(fn);
    return el;
  };
  FX.living = living;
  const W = (t, p, ph) => LIFE.wave(t, p, ph);
  // idle loops (seconds; amplitudes are starting points: when unsure, halve them)
  FX.sway = (el, o = {}) => {   // plants, grass, a hanging sign, a lamp, ears, a tail: rotation around the base, 1.5-4° over 3-6 s.
    // An array = a chain from root to tip (each part inside the previous): every part a phase later (lag), the tip moves most.
    const els = Array.isArray(el) ? el : [el], deg = o.deg ?? 2.5, per = o.period ?? 4.2, lag = o.lag ?? 0.15, ph = o.phase ?? 0;
    els.forEach((e, i) => living(e, (t) => ({ rot: deg * (o.grow ?? 1) ** i * W(t, per * (1 + 0.04 * i), ph - lag * i) }), o.pivot));
    return el;
  };
  FX.breathe = (el, o = {}) => living(el, (t) => {   // a body / creature / bag breathing: height +1-2 % over 3-5 s, volume kept
    const sy = 1 + (o.amp ?? 0.015) * (W(t, o.period ?? 3.4, o.phase ?? 0) + 1) / 2;
    return { sy, sx: 1 / sy ** 0.6 };
  }, o.pivot || "50% 100%");
  FX.bob = (el, o = {}) => living(el, (t) => ({   // floating on water, a vehicle's body, a buoy: bob 1-4 px and rock ~2°
    y: (o.px ?? 3) * W(t, o.period ?? 2.8, o.phase ?? 0), rot: (o.rock ?? 2) * W(t, (o.period ?? 2.8) * 1.6, (o.phase ?? 0) + 0.25),
  }), o.pivot || "50% 50%");
  FX.flicker = (el, o = {}) => {   // fire, a candle: lean 2-4° and stretch 3-6 % on two waves (0.7 s, 1.1 s); the inner flame on a third
    const ph = o.phase ?? 0, a = o.amount ?? 1;
    living(el, (t) => ({ rot: a * (2.6 * W(t, 0.7, ph) + 1.2 * W(t, 1.1, ph + 0.3)), sy: 1 + a * (0.035 * W(t, 0.7, ph + 0.2) + 0.02 * W(t, 1.1, ph + 0.6)) }), o.pivot || "50% 100%");
    if (o.inner) living(o.inner, (t) => ({ rot: a * 1.8 * W(t, 0.53, ph + 0.5), sy: 1 + a * 0.05 * W(t, 0.53, ph + 0.1) }), o.pivot || "50% 100%");
    return el;
  };
  FX.glow = (el, o = {}) => living(el, (t) => {   // a lamp's halo, a screen, a sun: grows 2-5 % over 2-4 s (never dims halfway)
    const k = 1 + (o.amp ?? 0.035) * (W(t, o.period ?? 3, o.phase ?? 0) + 1) / 2;
    return { sx: k, sy: k };
  }, o.pivot || "50% 50%");
  FX.spin = (el, o = {}) => living(el, (t) => ({ rot: (o.dir ?? 1) * 360 * (t / (o.period ?? 6) + (o.phase ?? 0)) }), o.pivot || "50% 50%");
  // gears / fans / sun rays: linear; meshing gears turn opposite ways with periods in their tooth ratio
  FX.drift = (el, o = {}) => living(el, (t) => ({   // clouds, far hills: a slow linear drift; layers further back drift slower
    x: (o.dir ?? 1) * (LIFE.loop(t, o.period ?? 40, o.phase ?? 0) - 0.5) * (o.span ?? 1400),
  }), o.pivot);
  FX.steam = (root, o = {}) => {   // steam, smoke: 2-3 wisps rise 60-120 px, fading in and out (bell), out of phase
    const n = o.n ?? 3, per = o.period ?? 2.6, rise = o.rise ?? 90, w = o.w ?? 26, out = [];
    for (let i = 0; i < n; i++) {
      const d = document.createElement("div");
      Object.assign(d.style, { position: "absolute", left: (o.x ?? 540) - w / 2 + (i - (n - 1) / 2) * w * 0.7 + "px", top: (o.y ?? 900) - w * 2 + "px", width: w + "px", height: w * 2 + "px",
        borderRadius: "50%", background: o.color || "rgba(255,255,255,.55)", filter: `blur(${(w / 3).toFixed(1)}px)`, opacity: 0, pointerEvents: "none", zIndex: o.z ?? 4 });
      root.appendChild(d); out.push(d);
      const ph = i / n + LIFE.seeded(i, o.seed ?? 3) * 0.2;
      FX.onFrame((t) => {
        const p = LIFE.loop(t, per, ph);
        d.style.opacity = (LIFE.bell(p) * (o.alpha ?? 0.8)).toFixed(3);
        d.style.translate = `${(8 * W(t, per * 1.3, ph)).toFixed(1)}px ${(-rise * p).toFixed(1)}px`;
        d.style.scale = (1 + 0.5 * p).toFixed(3);
      });
    }
    return out;
  };
  FX.ripples = (root, o = {}) => {   // water: rings grow 0 -> 1 and fade (bell); flat = the ellipse's height / width (the camera angle)
    const n = o.n ?? 3, per = o.period ?? 2.4, r = o.r ?? 140, flat = o.flat ?? 0.35, out = [];
    for (let i = 0; i < n; i++) {
      const d = document.createElement("div");
      Object.assign(d.style, { position: "absolute", left: (o.x ?? 540) - r + "px", top: (o.y ?? 1200) - r * flat + "px", width: 2 * r + "px", height: 2 * r * flat + "px", borderRadius: "50%",
        border: `${o.stroke ?? 4}px solid ${o.color || "rgba(255,255,255,.7)"}`, boxSizing: "border-box", opacity: 0, pointerEvents: "none", zIndex: o.z ?? 3 });
      root.appendChild(d); out.push(d);
      FX.onFrame((t) => { const p = LIFE.loop(t, per, i / n); d.style.scale = (0.1 + 0.9 * p).toFixed(3); d.style.opacity = (LIFE.bell(p) * (1 - 0.4 * p)).toFixed(3); });
    }
    return out;
  };
  FX.weather = (root, o = {}) => {   // rain | snow | leaves | stars on ONE canvas: each item its own seeded phase, speed (±20 %), size, drift
    const W0 = root.clientWidth || 1080, H0 = root.clientHeight || 1920, kind = o.kind || "snow", S = LIFE.seeded, sd = o.seed ?? 7;
    const n = o.n ?? { rain: 140, snow: 90, leaves: 16, stars: 110 }[kind] ?? 80, per = o.period ?? { rain: 0.9, snow: 9, leaves: 7, stars: 3.5 }[kind] ?? 6;
    const [ax, ay, aw, ah] = o.area || [0, 0, 1, kind === "stars" ? 0.55 : 1], wind = o.wind ?? (kind === "rain" ? 0.12 : 0), sz = o.size ?? 1;
    const c = document.createElement("canvas"); c.width = W0; c.height = H0;
    Object.assign(c.style, { position: "absolute", left: 0, top: 0, pointerEvents: "none", zIndex: o.z ?? 6 });
    root.appendChild(c);
    const ctx = c.getContext("2d"), col = o.color || { rain: "rgba(200,220,255,.55)", snow: "#ffffff", leaves: "#d9822b", stars: "#ffffff" }[kind];
    FX.onFrame((t) => {
      ctx.clearRect(0, 0, W0, H0); ctx.fillStyle = col; ctx.strokeStyle = col; ctx.lineCap = "round";
      for (let i = 0; i < n; i++) {
        const sp = 0.8 + S(i, sd) * 0.4, ph = S(i, sd + 3), x0 = (ax + S(i, sd + 1) * aw) * W0, s = (0.6 + S(i, sd + 2) * 0.8) * sz;
        if (kind === "stars") {   // twinkle: a small scale and brightness dip at seeded times
          const p = LIFE.loop(t, per * sp, ph), dip = p < 0.18 ? LIFE.bell(p / 0.18) : 0, y = (ay + S(i, sd + 4) * ah) * H0;
          ctx.globalAlpha = 0.85 - 0.6 * dip; ctx.beginPath(); ctx.arc(x0, y, 2.2 * s * (1 - 0.35 * dip), 0, 7); ctx.fill(); continue;
        }
        const p = LIFE.loop(t * sp, per, ph), y = (ay * H0 - 40) + p * (ah * H0 + 80);
        ctx.globalAlpha = 1;
        if (kind === "rain") { const x = x0 + wind * y, len = 30 * s; ctx.lineWidth = 2.2 * s; ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x - wind * len, y - len); ctx.stroke(); }
        else if (kind === "snow") { ctx.beginPath(); ctx.arc(x0 + 22 * s * W(t, 3 + 2 * S(i, sd + 5), ph), y, 3.2 * s, 0, 7); ctx.fill(); }
        else { ctx.save(); ctx.translate(x0 + 70 * s * W(t, 4 + 2 * S(i, sd + 5), ph), y); ctx.rotate(0.8 * W(t, 2.6 + S(i, sd + 6), ph)); ctx.beginPath(); ctx.ellipse(0, 0, 14 * s, 6 * s, 0, 0, 7); ctx.fill(); ctx.restore(); }
      }
      ctx.globalAlpha = 1;
    });
    return c;
  };
  FX.buzz = (el, at, o = {}) => {   // a phone / alarm: bursts of ±3° (4 cycles in ~0.45 s), then a pause; nothing between bursts
    const n = o.bursts ?? 2, gap = o.gap ?? 0.55, len = 0.45, deg = o.deg ?? 3;
    living(el, (t) => {
      const k = Math.floor((t - at) / (len + gap)), u = t - at - k * (len + gap);
      return k >= 0 && k < n && u < len ? { rot: deg * Math.sin((u / len) * 8 * Math.PI) * Math.sqrt(LIFE.bell(u / len)) } : {};
    }, o.pivot || "50% 50%");
    if (o.sfx !== false) FX.sfx(o.sfx || "notify", at);
    return el;
  };
  FX.jiggle = (el, o = {}) => {   // a box / gift / card waiting to be tapped: a quick squash-and-widen pulse (1.5-3 %) on a 0.2-0.35 s
    // beat, the bulge leaning one side then the other; it finishes its beat after `to` (stop it for the tap's anticipation)
    const beat = o.beat ?? 0.28, a = o.amp ?? 0.025, from = o.from ?? 0, to = o.to ?? 1e9, end = from + Math.ceil((to - from) / beat) * beat;
    let w = o.w;
    return living(el, (t) => {
      if (t < from || t >= end) return {};
      if (w == null) w = (el.getBBox ? el.getBBox().width : el.offsetWidth) || 100;
      const k = (t - from) / beat, b = Math.sin((k % 1) * Math.PI), side = Math.floor(k) % 2 ? 1 : -1;
      return { sy: 1 - a * b, sx: 1 + a * b, x: side * b * 0.01 * w };
    }, o.pivot || "50% 100%");
  };

  /* Characters (works with FX.stickman; the ideas carry to anything drawn):
     FX.alive(man, {look: [[t, gx, gy], ...], lid, amount, cheek: [[t, 0..1], ...], talk: [[from, to], ...], mouth}) ·
       never a frozen frame: the eyes glide to each look
       (-1..1, ~0.45 s, ease-in-out) and the head follows a beat later; blinks every 3-4 s (close 0.11 s, hold 0.04, reopen
       0.19 s ease-out: slower than closing), now and then a double, always one on a big glance; the body breathes and
       every limb drifts on its own period, left and right out of phase (moving holds). lid = resting lid 0..1 (tired 0.35).
     FX.act(man, [[t, "pose" | {joint: deg}], ...], {follow, lag}) · a chain of key poses read with FLOW (no dead stop at
       each pose, repeat a pose to hold it); forearms and shins trail their upper limb ~0.09 s, the head rights itself
       0.11 s after the body leans. Use it instead of several FX.pose tweens.
     FX.land(man, at, {from, hover, dur}) · hover, fall with gravity and a stretch, arms up just before contact, squash
       ~18 % (volume kept), one small overshoot, settle. FX.hop(man, at, {h, dur}) · crouch, stretch, arc, the same squash.
     FX.float(el | man, {at, h, out, shadow}) · levitate: rise in from well below and slow, drift a few % down and back,
       leave rising as it fades; a man's legs hang limp; the shadow stays on the floor and shrinks with the height. */
  FX.alive = (man, o = {}) => {
    man.live = true;
    const sd = man.seed || 0, amt = o.amount ?? 1, S = LIFE.seeded, glide = o.glide ?? 0.45, ph = S(sd, 11);
    const looks = (o.look || []).slice().sort((a, b) => a[0] - b[0]).map(([t, gx, gy]) => [t, gx, gy ?? 0]);
    const starts = [];   // where each glide starts from = the gaze at that moment
    let cur = [0, 0];
    looks.forEach(([t, gx, gy], i) => {
      if (i) { const [t0, x0, y0] = looks[i - 1], s0 = starts[i - 1], p = LIFE.seg(t, t0, t0 + glide, "inOut"); cur = [s0[0] + (x0 - s0[0]) * p, s0[1] + (y0 - s0[1]) * p]; }
      starts.push(cur);
    });
    const gaze = (t) => {
      let i = -1; while (i + 1 < looks.length && looks[i + 1][0] <= t) i++;
      if (i < 0) return [0, 0];
      const [t0, gx, gy] = looks[i], s0 = starts[i], p = LIFE.seg(t, t0, t0 + glide, "inOut");
      return [s0[0] + (gx - s0[0]) * p, s0[1] + (gy - s0[1]) * p];
    };
    const blinks = [];
    for (let b = (o.blinkFrom ?? 0) + 0.6 + 1.6 * S(sd, 5), j = 0; b < (o.blinkTo ?? 600); j++) {
      blinks.push(b);
      if (S(j, sd + 7) < 0.2) blinks.push(b + 0.36);   // now and then a double blink
      b += 3 + 1.1 * S(j, sd + 9);
    }
    looks.forEach(([t, gx, gy], i) => { const s0 = starts[i]; if (Math.hypot(gx - s0[0], gy - s0[1]) > 0.6) blinks.push(t - 0.02); });   // blink on a big glance
    blinks.sort((a, b) => a - b);
    const lidOf = (u) => (u < 0 || u > 0.34 ? 0 : u < 0.11 ? LIFE.EASE_IO(u / 0.11) : u < 0.15 ? 1 : 1 - LIFE.EASE_OUT((u - 0.15) / 0.19));
    man.layers.push((t) => {
      let blink = 0;
      for (const b of blinks) { if (b > t) break; blink = Math.max(blink, lidOf(t - b)); }
      const base = o.lid ?? 0, [gx, gy] = gaze(t), [hx] = gaze(t - 0.12);
      man.gaze = [gx, gy]; man.lid = base + (1 - base) * blink;
      if (o.cheek) man.cheek = LIFE.track(t, o.cheek);   // [[t, 0..1], ...] happy squint (illustrated characters)
      let m = o.mouth ?? 0;                              // talking: syllables of ~0.18 s, each its own depth
      for (const [a, b] of o.talk || []) if (t > a && t < b) { const k2 = (t - a) / 0.18; m = Math.max(m, (0.3 + 0.6 * S(Math.floor(k2), sd + 13)) * LIFE.bell(k2 % 1) * Math.min(1, (b - t) / 0.1)); }
      man.mouth = m;
      return {
        y: -amt * 4 * (W(t, 2.6, ph) + 1) / 2,                                    // breathing, ~1 % of the height
        lean: amt * 1.2 * W(t, 4.6, ph + 0.1),                                    // weight drifting
        head: amt * 2 * W(t, 4.4, ph + 0.3) + 4 * hx,                             // head tilt; turns after the eyes
        sL: amt * (3 * W(t, 3.0, ph) + 1.5 * W(t, 1.8, ph + 0.3)), sR: -amt * (3 * W(t, 3.3, ph + 0.45) + 1.5 * W(t, 2.0, ph + 0.7)),
        eL: amt * 4 * W(t, 2.25, ph + 0.6), eR: -amt * 4 * W(t, 2.5, ph + 0.15),
        kL: amt * 2 * (W(t, 4.6, ph + 0.1) + 1), kR: amt * 2 * (1 - W(t, 4.6, ph + 0.1)),   // the unloaded knee eases
      };
    });
    return man;
  };
  const JOINTS = ["sL", "eL", "sR", "eR", "hL", "kL", "hR", "kR", "lean", "head", "y"];
  FX.act = (man, keys, o = {}) => {
    const ks = keys.slice().sort((a, b) => a[0] - b[0]).map(([t, p]) => [t, Object.assign({}, typeof p === "string" ? POSES[p] : p)]);
    let prev = man.s;
    for (const k of ks) { for (const j of JOINTS) if (k[1][j] == null) k[1][j] = prev[j]; prev = k[1]; }
    const ch = {};
    for (const j of JOINTS) ch[j] = ks.map(([t, p]) => [t, p[j]]);
    const f = (t, j) => LIFE.flow(t, ch[j]), lag = o.lag ?? 0.09, ft = o.follow ?? 0.45;
    man.poseAt = (t) => {
      const P = {};
      for (const j of JOINTS) P[j] = f(t, j);
      P.eL += ft * (f(t - lag, "sL") - f(t, "sL")); P.eR += ft * (f(t - lag, "sR") - f(t, "sR"));   // forearms trail
      P.kL += ft * (f(t - lag, "hL") - f(t, "hL")); P.kR += ft * (f(t - lag, "hR") - f(t, "hR"));   // shins trail
      P.head -= ft * f(t - 0.11, "lean");                                                          // counter-motion
      return P;
    };
    return man;
  };
  const contact = (c, amt) => (c < 0 || c > 0.9 ? 0 : amt * Math.exp(-c * 7) * Math.cos((c * 2 * Math.PI) / 0.42));   // squash, one overshoot, settle
  FX.land = (man, at, o = {}) => {
    const top = o.from ?? 520, hover = o.hover ?? 0.25, fall = o.dur ?? 0.5, hit = at + hover + fall;
    man.layers.push((t) => {
      if (t < at + hover) return { y: -top - 6 * W(t, 1.6, 0), hL: 3, hR: -3, kL: 14, kR: 4 };   // hovering: legs hang
      if (t < hit) { const k = (t - at - hover) / fall, up = LIFE.seg(t, hit - 0.18, hit - 0.02); return { y: -top * (1 - k * k), sq: -0.08 * k, sL: 50 * up, sR: -50 * up }; }
      const c = t - hit, out = Math.exp(-c * 5);
      return { sq: contact(c, o.squash ?? 0.18), sL: 60 * out, sR: -60 * out };
    });
    if (o.sfx !== false) FX.sfx(o.sfx || "hit", hit, { db: o.db ?? -10 });
    return man;
  };
  FX.hop = (man, at, o = {}) => {
    const h = o.h ?? 70, air = o.dur ?? 0.42, crouch = 0.14;
    man.layers.push((t) => {
      const u = t - at;
      if (u < 0) return {};
      if (u < crouch) return { sq: 0.08 * LIFE.seg(u, 0, crouch, "inOut") };
      if (u < crouch + air) { const p = (u - crouch) / air; return { y: -4 * h * p * (1 - p), sq: -0.08 * (1 - p), sL: 25 * LIFE.bell(p), sR: -25 * LIFE.bell(p) }; }
      return { sq: contact(u - crouch - air, o.squash ?? 0.15) };
    });
    return man;
  };
  FX.float = (el, o = {}) => {
    const isMan = !!(el && el.layers), h = o.h ?? (isMan ? 400 : 300), at = o.at ?? 0, inDur = o.dur ?? 1.1, out = o.out;
    const lift = o.lift ?? 0.14 * h, low = o.from ?? 0.3 * h;
    const height = (t) => lift + 0.03 * h * W(t - at, o.period ?? 2.8, 0.75) - low * (1 - LIFE.seg(t, at, at + inDur)) + (out != null ? 0.5 * h * LIFE.seg(t, out, out + 0.8, "inOut") : 0);
    const vis = (t) => LIFE.seg(t, at, at + inDur * 0.5) * (out != null ? 1 - LIFE.seg(t, out, out + 0.8) : 1);
    if (isMan) {
      const k = h / 400;
      el.layers.push((t) => ({ y: -height(t) / k, hL: 5 + 3 * W(t, 3.1, 0.2), hR: -4 + 3 * W(t, 3.7, 0.6), kL: 16 + 8 * W(t, 3.1, 0.2), kR: 6 - 6 * W(t, 3.7, 0.6),
                                sL: 14 + 4 * W(t, 2.4, 0.1), sR: -14 - 4 * W(t, 2.7, 0.5) }));   // limp legs, one knee folded, arms a little out
      FX.onFrame((t) => { el.svg.style.opacity = vis(t).toFixed(3); });
    } else {
      living(el, (t) => ({ y: -height(t) }), o.pivot || "50% 100%");
      if (o.fade !== false) FX.onFrame((t) => { el.style.opacity = vis(t).toFixed(3); });
    }
    if (o.shadow) living(o.shadow, (t) => { const s = Math.max(0.3, 1 - (0.5 * Math.max(0, height(t))) / h); return { sx: s, sy: s }; }, "50% 50%");
    return el;
  };


  /* ---- KINETIC: high-energy type on the beat (launch films, teasers, promos, hooks; craft after the
     scenario-kinetic-film method): one idea per beat, one or two words that fill the frame width, the ground flips
     colour on phrase changes, transitions are moves (whips, a zoom through a letter, a collapse to a point), runs of
     cuts accelerate (1, 1, 1, ½, ½, ¼ beat, flash), and nothing parks: after a word lands it keeps scaling or sliding.
     FX.B(k) = the time of beat k (FX.BPM, anchored on FX.beat0 = the music's drop when the bundle knows it).
     FX.kinetic(tl, root, at, {style: slam | punch3d | stack | split | pair | cut, text: "WORD" | [a, b], until, ground,
       color, accent, y, font, fx: punch | hit | beat | none, second, big, sfx}) -> {el}
     FX.ground(tl, root, at, colour) · FX.hitFx(tl, root, at, {rays, ring, flash, shake}) · FX.charge(tl, root, at, dur)
     FX.cutRun(tl, root, at, ["WORDS", ...], {beats: [1, 1, 1, .5, .5, .25, .25], grounds}) · FX.tvOff(tl, el, at)
     FX.zoomLetter(tl, wrapEl, letterSpan, at, {dur}) (fly through a letter's counter: O D 0 A B P R)
     FX.typePrompt(tl, root, at, {label, text: [["plain "], ["keyword", 1]], cps, enterAt}) (a brief typed with a caret,
       keywords pop, then the camera pushes into Enter and the accent floods the frame: the drop)
     FX.picture(tl, root, at, dur, {src, words: [[t, "TEXT", colour]], focus: [fx, fy], tint, weather, cutIns: [[t, scale,
       [fx, fy], dur]]}) (a picture never parks: push, pan, slight 3D tilt, punch-in on every word, cut-ins to details) ---- */
  FX.BPM = FX.BPM || 100; FX.beat0 = 0;
  FX.B = (k) => FX.beat0 + (k * 60) / FX.BPM;
  const KW = () => FX._W || 1080, KH = () => FX._H || 1920;
  const box = (root, css) => { const d = document.createElement("div"); Object.assign(d.style, { position: "absolute", left: 0, top: 0, width: "100%", height: "100%", pointerEvents: "none" }, css || {}); root.appendChild(d); return d; };
  const NI = { immediateRender: false };   // a tween whose start state is visible must not show before it plays
  const word = (parent, text, o) => {
    // a full-width row centred by layout (transforms stay free for the motion), the word in a measured inline block
    const el = document.createElement("div"), inner = document.createElement("span");
    Object.assign(el.style, { position: "absolute", left: 0, width: "100%", textAlign: "center", top: (o.y ?? KH() * 0.45) + "px", marginTop: "-0.45em", whiteSpace: "nowrap",
      font: `${o.weight || 900} ${o.size || 200}px/0.9 ${o.font || "'Anton', 'Inter Tight', sans-serif"}`, textTransform: "uppercase", letterSpacing: o.track || "-0.01em",
      color: o.color || "var(--ink, #fff)", opacity: 0 });
    inner.style.display = "inline-block"; inner.textContent = text; el.appendChild(inner); parent.appendChild(el);
    const spans = split(inner, "chars");
    // fit to the frame width on the first visible frame (fonts are loaded by then), never before it is laid out
    let fitted = false;
    FX.onFrame(() => { if (fitted || !inner.offsetWidth) return; const want = (o.width ?? 0.86) * KW(); el.style.fontSize = Math.max(60, Math.min(o.max || 520, (parseFloat(el.style.fontSize) * want) / inner.offsetWidth)) + "px"; fitted = true; });
    return { el, spans };
  };
  FX.ground = (tl, root, at, color) => { const g = box(root, { background: color, opacity: 0, zIndex: 0 }); root.prepend(g); tl.set(g, { opacity: 1 }, at); return g; };
  FX.hitFx = (tl, root, at, o = {}) => {
    const W0 = KW(), H0 = KH(), [cx, cy] = o.at || [W0 / 2, H0 * 0.45], col = o.color || "var(--accent, #ffc21a)";
    if (o.rays !== false) {
      const svg = FX.svg(root, W0, H0); svg.style.zIndex = 40; const n = o.n || 14, r = FX.rand(o.seed || 5);
      const rays = [...Array(n)].map((_, i) => { const a = (i / n) * Math.PI * 2 + r() * 0.2, l = FX.el(svg, "line", { x1: cx + Math.cos(a) * 140, y1: cy + Math.sin(a) * 140, x2: cx + Math.cos(a) * (420 + r() * 300), y2: cy + Math.sin(a) * (420 + r() * 300), stroke: col, "stroke-width": 10, "stroke-linecap": "round", opacity: 0 }); return l; });
      rays.forEach((l) => { const len = 600; l.style.strokeDasharray = len; tl.fromTo(l, { opacity: 1, strokeDashoffset: len }, { strokeDashoffset: -len, duration: 0.32, ease: "power3.out", ...NI }, at); tl.set(l, { opacity: 0 }, at + 0.32); });
    }
    if (o.ring !== false) {
      const ring = box(root, { left: cx - 100 + "px", top: cy - 100 + "px", width: "200px", height: "200px", borderRadius: "50%", border: `10px solid ${col}`, opacity: 0, zIndex: 40, boxSizing: "border-box" });
      tl.fromTo(ring, { opacity: 1, scale: 0.4 }, { opacity: 0, scale: 5, duration: 0.45, ease: "expo.out", ...NI }, at);
    }
    if (o.flash !== false) { const f = box(root, { background: o.flashColor || "#fff", opacity: 0, zIndex: 60 }); tl.fromTo(f, { opacity: 0.85 }, { opacity: 0, duration: 0.12, ease: "power2.out", ...NI }, at); }
    if (o.shake !== false) FX.shake(tl, o.target || root.firstElementChild || root, at, { amp: o.amp || 16, dur: 0.3 });
    if (o.sfx !== false) FX.sfx(o.sfx || (o.big ? "impact" : "hit"), at);
  };
  FX.kinetic = (tl, root, at, o = {}) => {
    const st = o.style || "slam", texts = Array.isArray(o.text) ? o.text : [o.text], until = o.until ?? at + 1.2, sec = o.second ?? 0.18;
    const layer = box(root, { zIndex: 20, display: "none" });
    tl.set(layer, { display: "block" }, at); tl.set(layer, { display: "none" }, until);
    if (o.ground) FX.ground(tl, layer, at, o.ground);
    const col = o.color || "var(--ink, #fff)", acc = o.accent || "var(--accent, #ffc21a)", y = o.y ?? KH() * 0.45, out = { el: layer, words: [] };
    const alive = (el, from) => living(el, (t) => (t > from && t < until ? { sx: 1 + 0.03 * (t - from), sy: 1 + 0.03 * (t - from) } : {}), "50% 50%");   // never park
    const land = (w, t0, o2 = {}) => {
      tl.set(w.el, { opacity: 1 }, t0);
      if (o2.tumble !== false) tl.fromTo(w.spans, { opacity: 0, y: -90, rotation: (i) => (i % 2 ? 30 : -30) }, { opacity: 1, y: 0, rotation: 0, duration: 0.2, stagger: 0.018, ease: "power3.out" }, t0);
      tl.fromTo(w.el, { scale: o2.from ?? 1.6 }, { scale: 1, duration: 0.2, ease: "expo.out" }, t0);
      alive(w.el, t0 + 0.2);
    };
    if (st === "slam" || st === "cut") {
      const w = word(layer, texts[0], { y, color: col, ...o }); out.words.push(w);
      if (st === "cut") { tl.set(w.el, { opacity: 1 }, at); alive(w.el, at); } else land(w, at, o);
      if (st === "slam" && o.echo !== false) for (const dy of [-1, 1]) {   // ghost rows scroll past above and below
        const g = word(layer, `${texts[0]} ${texts[0]} ${texts[0]}`, { y: y + dy * (o.rowGap || 0.16) * KH(), color: "transparent", width: 2.4, ...o });
        g.el.style.webkitTextStroke = `3px ${col}`; g.el.style.opacity = 0;
        tl.set(g.el, { opacity: 0.22 }, at + 0.1);
        living(g.el, (t) => ({ x: dy * 70 * (t - at) }), "50% 50%");
      }
    } else if (st === "punch3d") {
      const w = word(layer, texts[0], { y, color: col, ...o }); out.words.push(w);
      const side = o.side || "var(--accent2, #8a5a00)";
      w.el.style.textShadow = [...Array(14)].map((_, i) => `${i + 1}px ${i + 1}px 0 ${side}`).join(",");
      tl.set(w.el, { opacity: 1 }, at);
      tl.fromTo(w.el, { scale: 0.15, rotationX: 35, filter: "blur(10px)" }, { scale: 1, rotationX: 0, filter: "blur(0px)", duration: 0.28, ease: "expo.out" }, at);
      for (let i = 1; i <= 2; i++) {   // echo trail: copies that lag behind and fade
        const e = word(layer, texts[0], { y, color: acc, ...o }); e.el.style.zIndex = -i;
        tl.fromTo(e.el, { opacity: 0.5 / i, scale: 0.15 }, { opacity: 0, scale: 1 + 0.12 * i, duration: 0.28 + 0.08 * i, ease: "expo.out", ...NI }, at + 0.03 * i);
      }
      alive(w.el, at + 0.28);
    } else {   // stack [kicker, word] · split [small, big] · pair [line1, line2]
      const a = word(layer, texts[0], { y: y - 0.09 * KH(), color: st === "stack" ? acc : col, width: st === "pair" ? 0.8 : 0.5, ...o });
      const b = word(layer, texts[1] || "", { y: y + (st === "stack" ? 0.04 : 0.07) * KH(), color: col, width: st === "pair" ? 0.8 : 0.9, ...o });
      out.words.push(a, b);
      if (st === "pair") {
        tl.set([a.el, b.el], { opacity: 1 }, at);
        tl.fromTo(a.el, { x: -KW() }, { x: 0, duration: 0.24, ease: "expo.out" }, at);
        tl.fromTo(b.el, { x: KW() }, { x: 0, duration: 0.24, ease: "expo.out" }, at + sec);
        alive(a.el, at + 0.24); alive(b.el, at + sec + 0.24);
      } else {
        land(a, at, { from: 1.3 });
        tl.set(b.el, { opacity: 1 }, at + sec);
        tl.fromTo(b.el, { x: st === "split" ? KW() : 0, scale: st === "split" ? 1 : 1.8 }, { x: 0, scale: 1, duration: 0.2, ease: "expo.out" }, at + sec);
        alive(b.el, at + sec + 0.2);
        if (st === "stack") { const bar = box(layer, { left: "8%", width: "84%", top: y - 0.035 * KH() + "px", height: "14px", background: acc, transformOrigin: "0 50%" }); tl.fromTo(bar, { scaleX: 0 }, { scaleX: 1, duration: 0.2, ease: "expo.out" }, at + sec); }
      }
    }
    const fx = o.fx || (st === "cut" ? "beat" : "hit"), hitT = st === "stack" || st === "split" || st === "pair" ? at + sec : at;
    if (fx === "punch") FX.hitFx(tl, layer, hitT, { big: o.big, sfx: o.sfx });
    else if (fx === "hit") FX.hitFx(tl, layer, hitT, { rays: false, ring: false, sfx: o.sfx || "hit", amp: 10 });
    else if (fx === "beat") { tl.fromTo(layer, { scale: 1.04 }, { scale: 1, duration: 0.15, ease: "power2.out", ...NI }, hitT); if (o.sfx !== false) FX.sfx(o.sfx || "tick", hitT); }
    return out;
  };
  FX.cutRun = (tl, root, at, words, o = {}) => {   // runs of beat cuts accelerate, then a flash
    const beats = o.beats || [1, 1, 1, 0.5, 0.5, 0.25, 0.25, 0.25], b = 60 / FX.BPM, grounds = o.grounds || ["var(--bg, #0b1020)", "var(--accent, #ffc21a)", "var(--paper, #f3eee3)"];
    const inks = o.inks || ["var(--paper, #f3eee3)", "var(--bg, #0b1020)", "var(--bg, #0b1020)"];   // type follows the ground
    let t = at;
    words.forEach((w, i) => { const d = beats[Math.min(i, beats.length - 1)] * b; FX.kinetic(tl, root, t, { style: "cut", text: w, until: t + d, ground: grounds[i % grounds.length], color: inks[i % inks.length], fx: "beat" }); t += d; });
    FX.hitFx(tl, root, t, { rays: false, ring: false, shake: false, sfx: "whoosh" });
    return t;
  };
  FX.charge = (tl, root, at, dur = 0.8, o = {}) => {   // converging speed lines into a glowing point before the first hit
    const W0 = KW(), H0 = KH(), [cx, cy] = o.at || [W0 / 2, H0 * 0.45], svg = FX.svg(root, W0, H0), r = FX.rand(o.seed || 9), col = o.color || "var(--accent, #ffc21a)";
    svg.style.zIndex = 30; svg.style.opacity = 0;
    tl.set(svg, { opacity: 1 }, at); tl.set(svg, { opacity: 0 }, at + dur);
    for (let i = 0; i < (o.n || 26); i++) {
      const a = r() * Math.PI * 2, R = 700 + r() * 600, l = FX.el(svg, "line", { x1: cx + Math.cos(a) * R, y1: cy + Math.sin(a) * R, x2: cx + Math.cos(a) * (R + 260), y2: cy + Math.sin(a) * (R + 260), stroke: col, "stroke-width": 4 + r() * 6, "stroke-linecap": "round" });
      tl.fromTo(l, { attr: { x1: cx + Math.cos(a) * R, y1: cy + Math.sin(a) * R, x2: cx + Math.cos(a) * (R + 260), y2: cy + Math.sin(a) * (R + 260) } },
        { attr: { x1: cx, y1: cy, x2: cx + Math.cos(a) * 40, y2: cy + Math.sin(a) * 40 }, duration: dur * (0.6 + 0.4 * r()), ease: "power2.in" }, at);
    }
    const dot = FX.el(svg, "circle", { cx, cy, r: 18, fill: "#fff", style: `filter: drop-shadow(0 0 30px ${col})` });
    tl.fromTo(dot, { attr: { r: 2 } }, { attr: { r: 26 }, duration: dur, ease: "power2.in" }, at);
    FX.sfx("riser", at);
    return svg;
  };
  FX.tvOff = (tl, el, at, o = {}) => {   // squash to a glowing line, then to a point (out of a section)
    tl.to(el, { scaleY: 0.012, filter: "brightness(3)", duration: 0.12, ease: "power3.in" }, at);
    tl.to(el, { scaleX: 0, duration: 0.12, ease: "power3.in" }, at + 0.12);
    if (o.sfx !== false) FX.sfx("swish", at);
  };
  FX.zoomLetter = (tl, wrap, letter, at, o = {}) => {   // fly through a letter's counter into what is behind it
    const dur = o.dur || 0.45;
    living(wrap, (t) => { const k = 1 + (o.zoom || 60) * LIFE.EASE_IN(LIFE.seg(t, at, at + dur, "inOut") ** 1.6); return { sx: k, sy: k }; },
      () => { const a = wrap.getBoundingClientRect(), b = letter.getBoundingClientRect(), sc = a.width / (wrap.offsetWidth || 1) || 1; return [(b.left + b.width / 2 - a.left) / sc, (b.top + b.height * (o.cy ?? 0.55) - a.top) / sc]; });
    if (o.sfx !== false) FX.sfx("whoosh", at);
  };
  FX.typePrompt = (tl, root, at, o = {}) => {
    const W0 = KW(), H0 = KH(), cps = o.cps || 22, acc = o.accent || "var(--accent, #ffc21a)";
    const push = box(root, { zIndex: 10 }), cam = box(push), panel = box(cam, { left: "7%", width: "86%", top: H0 * 0.32 + "px", height: "auto", minHeight: "260px", border: "6px solid var(--ink, #fff)", borderRadius: "28px", padding: "70px 44px 50px", boxSizing: "border-box",
      font: "500 62px/1.25 'JetBrains Mono', 'Inter Tight', monospace", color: "var(--ink, #fff)", clipPath: "inset(0 100% 0 0)", paddingBottom: "130px" });
    tl.to(panel, { clipPath: "inset(0 0% 0 0)", duration: 0.4, ease: "power2.inOut" }, at);
    const lab = document.createElement("div"); lab.textContent = o.label || "BRIEF.md"; Object.assign(lab.style, { position: "absolute", top: "14px", left: "44px", font: "800 26px 'Inter Tight'", letterSpacing: ".12em", opacity: 0.7 }); panel.appendChild(lab);
    const body = document.createElement("div"); panel.appendChild(body);
    let t = at + 0.5;
    const caret = document.createElement("span"); caret.textContent = "▌"; caret.style.color = acc;
    for (const [txt, key] of o.text || [["write the brief"]]) {
      const sp = document.createElement("span"); body.appendChild(sp);
      const chars = [...txt].map((ch) => { const c = document.createElement("span"); c.textContent = ch; c.style.opacity = 0; sp.appendChild(c); return c; });
      chars.forEach((c, i) => { tl.set(c, { opacity: 1 }, t + i / cps); if (i % 3 === 0) FX.sfx("typing", t + i / cps, { db: -20 }); });
      t += chars.length / cps;
      if (key) { Object.assign(sp.style, { borderRadius: "8px", padding: "0 6px", display: "inline-block" }); tl.fromTo(sp, { backgroundColor: "rgba(0,0,0,0)", scale: 1 }, { backgroundColor: acc, color: "var(--bg, #111)", scale: 1.12, duration: 0.18, ease: "back.out(3)" }, t); tl.to(sp, { scale: 1, duration: 0.2 }, t + 0.18); }
    }
    body.appendChild(caret);
    FX.onFrame((tt) => { caret.style.opacity = tt > at + 0.5 && Math.floor(tt * 2.5) % 2 ? 0 : 1; });
    const key = document.createElement("div"); key.textContent = "ENTER ⏎"; Object.assign(key.style, { position: "absolute", right: "30px", bottom: "22px", padding: "16px 28px", background: acc, color: "var(--bg, #111)", font: "900 34px 'Inter Tight'", borderRadius: "14px" }); panel.appendChild(key);
    living(cam, (tt) => { const k = 1 + 0.07 * LIFE.seg(tt, at + 0.5, t, "inOut"); return { sx: k, sy: k, y: -12 * LIFE.seg(tt, at + 0.5, t, "inOut") }; }, "50% 40%");   // the camera follows the typing
    const enter = o.enterAt ?? t + 0.6;
    FX.zoomLetter(tl, push, key, enter - 0.45, { zoom: 40, dur: 0.45, sfx: false });   // its own layer: one writer per element
    FX.colorFlood(tl, root, enter - 0.05, acc, { z: 70, dur: 0.12 });
    FX.sfx("click", enter - 0.45);
    return { el: cam, enter };
  };
  FX.picture = (tl, root, at, dur, o = {}) => {
    const W0 = KW(), H0 = KH(), [fx, fy] = o.focus || [0.5, 0.45];
    const frame = box(root, { overflow: "hidden", zIndex: 5, perspective: "1400px", display: "none" });
    const img = document.createElement("img"); img.src = o.src;
    Object.assign(img.style, { position: "absolute", left: 0, top: 0, width: "100%", height: "100%", objectFit: "cover", objectPosition: `${fx * 100}% ${fy * 100}%` });
    frame.appendChild(img);
    if (o.tint) box(frame, { background: `rgba(0,0,0,${o.tint})` });
    tl.set(frame, { display: "block" }, at); tl.set(frame, { display: "none" }, at + dur);
    tl.fromTo(frame, { clipPath: "polygon(0 0, 0 0, 0 100%, 0 100%)" }, { clipPath: "polygon(0 0, 100% 0, 120% 100%, 0 100%)", duration: 0.28, ease: "expo.out" }, at);
    FX.sfx("swish", at);
    const words = o.words || [], cuts = o.cutIns || [];
    living(img, (t) => {   // push fast, pan, a slight 3D tilt, a punch-in on every word, hard cut-ins to details
      const u = (t - at) / dur;
      let k = 1.08 + 0.16 * u, x = -40 * (u - 0.5) * W0 / 1080, rot = 0;
      for (const [wt] of words) { const d = t - wt; if (d > 0 && d < 0.5) k += 0.05 * Math.exp(-d * 8); }
      // a cut-in scales about the detail (cx, cy) instead of the focus: shift by (c - focus)·(1 - scale)
      for (const [ct, sc, [cx, cy], cd = 0.6] of cuts) if (t >= ct && t < ct + cd) return { sx: sc, sy: sc, x: (cx - fx) * W0 * (1 - sc), y: (cy - fy) * H0 * (1 - sc) };
      return { sx: k, sy: k, x, rot: 0.6 * (u - 0.5) + rot };
    }, `${fx * 100}% ${fy * 100}%`);
    for (const [ct] of cuts) FX.sfx("hit", ct, { db: -14 });
    words.forEach(([wt, text, color], i) => FX.kinetic(tl, frame, wt, { style: "cut", text, until: (words[i + 1] || [at + dur])[0], color: color || "#fff", y: o.y ?? H0 * 0.7, width: o.wordWidth || 0.7, fx: "beat" }));
    if (o.weather) FX.weather(frame, { kind: o.weather === "dust" ? "snow" : o.weather, n: o.weather === "dust" ? 60 : undefined, color: o.weather === "dust" ? "rgba(255,240,210,.5)" : undefined, size: o.weather === "dust" ? 0.6 : 1, z: 8 });
    return frame;
  };

  window.FX = FX;
})();
