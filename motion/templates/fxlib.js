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
