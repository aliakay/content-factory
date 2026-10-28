/* FX — the motion designer's recipe library for explainer scenes (loaded by explainer_shell.html).
   Everything is deterministic: tweens go on the master timeline `tl` at absolute times; per-frame drawing (canvas,
   Three.js) registers with FX.onFrame and is driven by window.render(t). No timers, no real-time loops, no randomness
   except the seeded FX.rand. Written for this factory (ideas from public motion vocabularies: split/blur/scramble
   text, shine, spotlight, glass, draw-on paths, count-ups, seeded particles, aurora fields, deterministic 3D). */
(function () {
  const FX = {};
  const frameHooks = [];
  FX._hooks = frameHooks;
  FX.onFrame = (fn) => frameHooks.push(fn);
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
    const [W] = dims(root), w = o.w || 520, h = w * 2.05, x = o.x ?? (W - w) / 2, y = o.y ?? 300;
    const el = div(root, { position: "absolute", left: x + "px", top: y + "px", width: w + "px", height: h + "px", borderRadius: w * 0.16 + "px", boxSizing: "border-box",
                           padding: w * 0.035 + "px", background: o.frame || "linear-gradient(145deg,#3a3d45,#0d0e11 60%)",
                           boxShadow: "0 60px 120px -30px rgba(0,0,0,.65), inset 0 0 0 3px rgba(255,255,255,.14)" });
    const screen = div(el, { position: "relative", width: "100%", height: "100%", borderRadius: w * 0.13 + "px", overflow: "hidden", background: o.bg || "#fff" }, o.html ?? media(o.img));
    div(screen, { position: "absolute", top: w * 0.03 + "px", left: "50%", width: w * 0.3 + "px", height: w * 0.085 + "px", marginLeft: -w * 0.15 + "px", borderRadius: "999px", background: "#000", zIndex: 5 });
    div(el, { position: "absolute", right: "-5px", top: h * 0.22 + "px", width: "6px", height: h * 0.1 + "px", background: "#1b1d22", borderRadius: "3px" });
    div(el, { position: "absolute", left: "-5px", top: h * 0.18 + "px", width: "6px", height: h * 0.06 + "px", background: "#1b1d22", borderRadius: "3px" });
    div(el, { position: "absolute", inset: 0, borderRadius: "inherit", pointerEvents: "none", background: "linear-gradient(120deg, rgba(255,255,255,.16), transparent 32%)" });
    return { el, screen };
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
  FX.boil = (el, T, o = {}) => {
    const id = "fxboil" + uid++, svg = document.createElementNS(NS, "svg");
    Object.assign(svg.style, { position: "absolute", width: 0, height: 0 });
    svg.innerHTML = `<filter id="${id}" x="-10%" y="-10%" width="120%" height="120%"><feTurbulence type="turbulence" baseFrequency="${o.freq || 0.025}" numOctaves="2" seed="1"/>` +
                    `<feDisplacementMap in="SourceGraphic" scale="${o.amount || 7}" xChannelSelector="R" yChannelSelector="G"/></filter>`;
    document.body.appendChild(svg);
    el.style.filter = `url(#${id})`;
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
  window.FX = FX;
})();
