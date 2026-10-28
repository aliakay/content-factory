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
  window.FX = FX;
})();
