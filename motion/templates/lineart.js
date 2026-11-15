/* lineart.js — hand-inked line-art animation kit for the explainer scenes (loaded by explainer_shell.html after fxlib.js).
   Exposes FX.ink (alias it: `const LA = FX.ink;`).

   Ported to plain JavaScript and re-engineered for a frame-seeking renderer from "line-art-animation" by JDhruv14
   (https://github.com/JDhruv14/line-art-animation), MIT licence:

     MIT License — Copyright (c) 2026 JDhruv14
     Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
     documentation files (the "Software"), to deal in the Software without restriction, including without limitation
     the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and
     to permit persons to whom the Software is furnished to do so, subject to the following conditions: The above
     copyright notice and this permission notice shall be included in all copies or substantial portions of the
     Software. THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT
     LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT
     SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
     OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
     DEALINGS IN THE SOFTWARE.

   What came from upstream: the open double-stroke limb, the 95-unit figure space and its proportions, the phase-based
   walk / run solver (planted feet, minimum-jerk swing, heel-off, solved hip height), the ink wobble filter and the
   day-to-night palette ramps. What is ours: every state is a PURE FUNCTION OF t (the renderer asks for frames in any
   order and in parallel slices), so the per-frame integrators of the original became closed forms or fixed-step
   simulations cached from t = 0; a mover that derives walk duration from distance; stroke-by-stroke reveals; the
   figure rig with gestures, props, bicycle and rider; scene builders; the stage that plugs into the GSAP timeline,
   the scene's T window and FX.sfx footstep cues.

   Units: the world is measured in FIGURE UNITS (a grown person at scale 1 is ~95 units tall, feet on their y). The
   stage turns units into pixels (default u = 5 px: 1080x1920 is 216x384 units, 1920x1080 is 384x216). All times are
   ABSOLUTE seconds of the film (like every other FX helper), so a scene writes `T.start + 1.2`. No Math.random,
   no Date, no real-time state anywhere. */
(function () {
  "use strict";
  const FX = window.FX;
  if (!FX) throw new Error("lineart.js: load fxlib.js first");
  const LA = (FX.ink = {});
  const NS = "http://www.w3.org/2000/svg";
  const PEN = (LA.PEN = 1.35), INK_DAY = (LA.INK = "#1c1c1c"), PAPER_DAY = (LA.PAPER = "#fdfcf8");

  /* ------------------------------------------------------------------ small maths */
  const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
  const lerp = (a, b, t) => a + (b - a) * t;
  const smooth = (e0, e1, x) => { const t = clamp((x - e0) / (e1 - e0), 0, 1); return t * t * (3 - 2 * t); };
  const minJerk = (s) => s * s * s * (10 - 15 * s + 6 * s * s);
  const f2 = (n) => n.toFixed(2);
  const pt = (p) => f2(p[0]) + " " + f2(p[1]);
  const L2 = (a, b, t) => [lerp(a[0], b[0], t), lerp(a[1], b[1], t)];
  Object.assign(LA, { clamp, lerp, smooth, minJerk, ease: (t) => smooth(0, 1, t), pt });

  const el = (tag, a, parent) => {
    const n = document.createElementNS(NS, tag);
    for (const k in a || {}) n.setAttribute(k, a[k]);
    if (parent) parent.appendChild(n);
    return n;
  };
  LA.el = el;
  const css = document.createElement("style");   // paper is a CSS variable so the whole drawing re-tints (day -> night) in one write
  css.textContent = ".la-pp{fill:var(--la-paper,#fdfcf8)}";
  document.head.appendChild(css);

  /* ------------------------------------------------------------------ drawing primitives (figure units) */
  /** An open pen stroke. */
  const pen = (p, w = PEN) => el("path", { fill: "none", stroke: "currentColor", "stroke-width": w, "stroke-linecap": "round", "stroke-linejoin": "round", pathLength: 1 }, p);
  /** A closed outline filled with paper: it hides what is behind it, like a drawing. */
  const shape = (p, w = PEN) => { const n = el("path", { stroke: "currentColor", "stroke-width": w, "stroke-linejoin": "round", "stroke-linecap": "round", pathLength: 1 }, p); n.setAttribute("class", "la-pp"); return n; };
  /** Solid ink: shoes, hair, small dark parts. */
  const blot = (p) => el("path", { fill: "currentColor", pathLength: 1 }, p);
  /** A closed outline with one flat colour (clothes, props). */
  const paint = (p, colour, w = PEN) => el("path", { fill: colour, stroke: "currentColor", "stroke-width": w, "stroke-linejoin": "round", "stroke-linecap": "round", pathLength: 1 }, p);
  Object.assign(LA, { pen, shape, blot, paint });

  /** A limb: two separate pen lines either side of a soft curve through the joints, open at the far end, paper between.
      This open double stroke is the signature of the style: never draw a limb as a closed tube. */
  LA.limb = (parent, width, w = PEN) => {
    const g = el("g", {}, parent), fill = el("path", { class: "la-pp" }, g), a = pen(g, w), b = pen(g, w), half = (width - w) / 2;
    return {
      g, fill,
      draw(joints, endGap = [0.4, 0.9]) {
        const s = joints[0], e = joints[joints.length - 1];
        let c = [(s[0] + e[0]) / 2, (s[1] + e[1]) / 2];
        if (joints.length === 3) { const m = joints[1]; c = [m[0] + 0.55 * (m[0] - c[0]), m[1] + 0.55 * (m[1] - c[1])]; }
        const P = [];
        for (let i = 0; i <= 16; i++) { const t = i / 16, u = 1 - t; P.push([u * u * s[0] + 2 * u * t * c[0] + t * t * e[0], u * u * s[1] + 2 * u * t * c[1] + t * t * e[1]]); }
        const side = (sg) => P.map((p, i) => {
          const q = P[Math.min(16, i + 1)], o = P[Math.max(0, i - 1)], dx = q[0] - o[0], dy = q[1] - o[1], l = Math.hypot(dx, dy) || 1;
          return [p[0] - (dy / l) * half * sg, p[1] + (dx / l) * half * sg];
        });
        const Lf = side(1), R = side(-1), cut = (arr, gap) => arr.slice(0, arr.length - Math.round(gap * 2));
        fill.setAttribute("d", "M" + Lf.map(pt).join("L") + "L" + R.slice().reverse().map(pt).join("L") + "Z");
        a.setAttribute("d", "M" + cut(Lf, endGap[0]).map(pt).join("L"));
        b.setAttribute("d", "M" + cut(R, endGap[1]).map(pt).join("L"));
      },
    };
  };
  /** A limb with a solid fill (trousers, sleeves). */
  LA.solid = (l, colour = "currentColor") => { l.fill.removeAttribute("class"); l.fill.style.fill = colour; return l; };
  /** Two-bone IK. bend = +1 puts the middle joint toward +x (knees), -1 toward -x. */
  const joint = (a, b, l1, l2, bend = 1) => {
    const dx = b[0] - a[0], dy = b[1] - a[1], d = Math.min(Math.hypot(dx, dy), l1 + l2 - 0.01), th = Math.atan2(dy, dx);
    const al = Math.acos(clamp((l1 * l1 + d * d - l2 * l2) / (2 * l1 * d), -1, 1));
    const c1 = [a[0] + l1 * Math.cos(th - al), a[1] + l1 * Math.sin(th - al)], c2 = [a[0] + l1 * Math.cos(th + al), a[1] + l1 * Math.sin(th + al)];
    return (c1[0] - c2[0]) * bend > 0 ? c1 : c2;
  };
  LA.joint = joint;
  /** The point `len` away at `deg` from straight down (forward positive). */
  LA.hang = (from, len, deg) => { const r = (deg * Math.PI) / 180; return [from[0] + len * Math.sin(r), from[1] + len * Math.cos(r)]; };
  /** A shoe: a fat ink wedge at the ankle pitched toe-down by `toe` degrees. */
  LA.shoe = (node, ankle, toe = 0) => {
    const r = (toe * Math.PI) / 180, c = Math.cos(r), s = Math.sin(r), S = (x, y) => [ankle[0] + x * c - y * s, ankle[1] + x * s + y * c];
    node.setAttribute("d", `M${pt(S(-1.6, -0.6))}L${pt(S(4.6, -0.2))}Q${pt(S(6.6, 0.4))} ${pt(S(5.6, 1.6))}L${pt(S(-1.4, 1.5))}Q${pt(S(-2.2, 0.5))} ${pt(S(-1.6, -0.6))}Z`);
  };
  /** Place a figure-space group: its local (40, 120) lands on world (x, y); flip is the facing (+1 / -1, or between while turning). */
  LA.place = (g, x, y, flip = 1, s = 1) => g.setAttribute("transform", `translate(${f2(x)} ${f2(y)}) scale(${f2(flip * s)} ${f2(s)}) translate(-40 -120)`);

  /* ------------------------------------------------------------------ hand-drawn static lines */
  /** Seeded wobble: points nudged by `amp` units, then a smooth Catmull-Rom curve through them (so nothing is ruler-straight). */
  LA.curvePath = (pts, o = {}) => {
    const R = FX.rand(o.seed ?? 3), a = o.amp ?? 0.25, P = pts.map((p, i) => [p[0] + (R() - 0.5) * 2 * a, p[1] + (R() - 0.5) * 2 * a]);
    const n = P.length, g = (i) => (o.closed ? P[(i + n) % n] : P[clamp(i, 0, n - 1)]);
    let d = "M" + pt(P[0]);
    for (let i = 0; i < (o.closed ? n : n - 1); i++) {
      const p0 = g(i - 1), p1 = g(i), p2 = g(i + 1), p3 = g(i + 2), k = o.tension ?? 6;
      d += `C${pt([p1[0] + (p2[0] - p0[0]) / k, p1[1] + (p2[1] - p0[1]) / k])} ${pt([p2[0] - (p3[0] - p1[0]) / k, p2[1] - (p3[1] - p1[1]) / k])} ${pt(p2)}`;
    }
    return d + (o.closed ? "Z" : "");
  };
  /** A pen line a -> b with a slight bow, so a long wall or a ground line is a drawn line. */
  LA.line = (parent, a, b, o = {}) => {
    const R = FX.rand(o.seed ?? Math.round(a[0] * 7 + a[1] * 13 + b[0] * 3)), len = Math.hypot(b[0] - a[0], b[1] - a[1]), bow = (o.bow ?? 0.012) * len * (R() - 0.5) * 2;
    const nx = -(b[1] - a[1]) / (len || 1), ny = (b[0] - a[0]) / (len || 1), m = [(a[0] + b[0]) / 2 + nx * bow, (a[1] + b[1]) / 2 + ny * bow];
    const n = pen(parent, o.w ?? PEN); n.setAttribute("d", `M${pt(a)}Q${pt(m)} ${pt(b)}`); return n;
  };
  /** A drawn rectangle: corners slightly off, edges bowed; `fill` = paper | ink | a colour | false. */
  LA.rect = (parent, x, y, w, h, o = {}) => {
    const R = FX.rand(o.seed ?? Math.round(x * 5 + y * 11)), j = o.jitter ?? 0.3, e = (v) => v + (R() - 0.5) * 2 * j, bw = Math.min(w, h) * 0.01;
    const A = [e(x), e(y)], B = [e(x + w), e(y)], C = [e(x + w), e(y + h)], D = [e(x), e(y + h)];
    const mid = (p, q, s) => [(p[0] + q[0]) / 2 + (R() - 0.5) * bw * s, (p[1] + q[1]) / 2 + (R() - 0.5) * bw * s];
    const d = `M${pt(A)}Q${pt(mid(A, B, 2))} ${pt(B)}Q${pt(mid(B, C, 2))} ${pt(C)}Q${pt(mid(C, D, 2))} ${pt(D)}Q${pt(mid(D, A, 2))} ${pt(A)}Z`;
    const n = o.fill === false ? pen(parent, o.w ?? PEN) : o.fill === "ink" ? blot(parent) : o.fill && o.fill !== "paper" ? paint(parent, o.fill, o.w ?? PEN) : shape(parent, o.w ?? PEN);
    n.setAttribute("d", d); return n;
  };
  /** An oval (hand-drawn: a slightly uneven ring); returns the path. */
  LA.oval = (parent, cx, cy, rx, ry, o = {}) => {
    const R = FX.rand(o.seed ?? Math.round(cx * 3 + cy * 7)), pts = [];
    for (let i = 0; i < 10; i++) { const a = (i / 10) * Math.PI * 2; pts.push([cx + Math.cos(a) * rx * (1 + (R() - 0.5) * 0.04), cy + Math.sin(a) * ry * (1 + (R() - 0.5) * 0.04)]); }
    const n = o.fill === false ? pen(parent, o.w ?? PEN) : o.fill === "ink" ? blot(parent) : o.fill && o.fill !== "paper" ? paint(parent, o.fill, o.w ?? PEN) : shape(parent, o.w ?? PEN);
    n.setAttribute("d", LA.curvePath(pts, { closed: true, amp: 0, tension: 5.5 })); return n;
  };

  /* ------------------------------------------------------------------ deterministic physics: closed form or fixed step from t = 0, cached */
  /** Fixed-step integration of `step(state, t) -> state` from t = 0; the states are cached, so value(t) is the same whatever
      was asked before (render(5.0) after render(4.9) or on its own). */
  const integrate = (step, s0, dt) => {
    const st = [s0];
    return (t) => {
      const k = Math.max(0, t) / dt, i = Math.floor(k), w = k - i;
      while (st.length <= i + 1) st.push(step(st[st.length - 1], (st.length - 1) * dt));
      const a = st[i], b = st[i + 1];
      return a.map((v, j) => v + (b[j] - v) * w);
    };
  };
  /** A damped spring chasing target(t): sleeves, a lagging arm, anything that follows. -> x(t) */
  LA.spring = (target, o = {}) => {
    const k = o.k ?? 40, d = o.d ?? 6, dt = o.dt ?? 1 / 120, g = integrate(([x, v], t) => { v += (k * (target(t) - x) - d * v) * dt; return [x + v * dt, v]; }, [target(0), 0], dt);
    return (t) => g(t)[0];
  };
  /** A pendulum (angle, radians) pushed by force(t): lanterns, curtains, a briefcase, laundry. -> a(t) */
  LA.pendulum = (force, o = {}) => {
    const k = o.k ?? 10, d = o.d ?? 1.1, dt = o.dt ?? 1 / 120, g = integrate(([a, v], t) => { v += (-k * a - d * v + force(t)) * dt; return [a + v * dt, v]; }, [0, 0], dt);
    return (t) => g(t)[0];
  };
  /** A hanging chain (scarf tail, balloon string, willow strand, flag): verlet from t = 0 with the head pinned to anchor(t) (world
      coordinates). o: {n, seg, g (gravity, negative floats), wind (fn t -> push), windK, drag}. -> nodes(t) = [[x, y], ...] */
  LA.rope = (anchor, o = {}) => {
    const n = o.n ?? 6, seg = o.seg ?? 3, gr = o.g ?? 60, wk = o.windK ?? 40, drag = o.drag ?? 0.06, dt = o.dt ?? 1 / 90, wf = o.wind || (() => 0);
    let g = null;   // built on the first ask: the anchor may belong to a figure that is still being constructed
    const build = () => { const a0 = anchor(0), init = []; for (let i = 0; i < n; i++) init.push(a0[0] - (o.dirX ?? 0) * i * seg, a0[1] + (gr < 0 ? -1 : 1) * i * seg);   // a floating rope starts pointing up
    return integrate((s, t) => {
      const P = s.slice(0, 2 * n), Q = s.slice(2 * n), N = P.slice(), w = wf(t) * wk;
      for (let i = 1; i < n; i++) {
        N[2 * i] = P[2 * i] + (P[2 * i] - Q[2 * i]) * (1 - drag) + w * (i / n) * dt * dt;
        N[2 * i + 1] = P[2 * i + 1] + (P[2 * i + 1] - Q[2 * i + 1]) * (1 - drag) + gr * dt * dt;
      }
      const an = anchor(t + dt); N[0] = an[0]; N[1] = an[1];
      for (let it = 0; it < 4; it++) for (let i = 1; i < n; i++) {
        const dx = N[2 * i] - N[2 * i - 2], dy = N[2 * i + 1] - N[2 * i - 1], l = Math.hypot(dx, dy) || 1e-6, k = (l - seg) / l, m = i === 1 ? 1 : 0.5;
        N[2 * i] -= dx * k * m; N[2 * i + 1] -= dy * k * m;
        if (i > 1) { N[2 * i - 2] += dx * k * 0.5; N[2 * i - 1] += dy * k * 0.5; }
      }
      return N.concat(P);
    }, init.concat(init), dt); };
    return (t) => { if (!g) g = build(); const s = g(t), out = []; for (let i = 0; i < n; i++) out.push([s[2 * i], s[2 * i + 1]]); return out; };
  };
  /** Wind as a function of time: a slow breeze (three incommensurate sines) plus gusts you place: w.gust(at, {dur, amp}). */
  LA.wind = (seed = 1, o = {}) => {
    const R = FX.rand(seed), base = o.base ?? 0.35, amp = o.amp ?? 0.3, ph = [R() * 6.28, R() * 6.28, R() * 6.28], gusts = [];
    const w = (t) => {
      let v = base + amp * (0.5 * Math.sin(t * 0.37 + ph[0]) + 0.3 * Math.sin(t * 0.91 + ph[1]) + 0.2 * Math.sin(t * 2.3 + ph[2]));
      for (const g of gusts) { const p = (t - g.at) / g.dur; if (p > 0 && p < 1) v += g.amp * Math.pow(Math.sin(Math.PI * Math.pow(p, 0.7)), 2); }
      return v;
    };
    w.gust = (at, g = {}) => { gusts.push({ at, dur: g.dur ?? 1.8, amp: g.amp ?? 2 }); return w; };
    return w;
  };

  /* ------------------------------------------------------------------ day to night */
  const toRGB = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
  const rgb = (c) => "rgb(" + c.map((v) => Math.round(v)).join(",") + ")";
  const mix = (a, b, t) => a.map((v, i) => v + (b[i] - v) * t);
  const lum = (c) => (0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]) / 255;
  const ramp = (keys, u) => {
    u = ((u % 1) + 1) % 1;
    const n = keys.length; let i = n - 1;
    for (let j = 0; j < n; j++) if (keys[j][0] <= u) i = j;
    const [p0, c0] = keys[i], [p1, c1] = keys[(i + 1) % n], span = (i + 1 < n ? p1 : p1 + 1) - p0;
    let x = u - p0; if (x < 0) x += 1;
    return mix(toRGB(c0), toRGB(c1), smooth(0, 1, x / span));
  };
  const SKY_TOP = [[0, "#0d1222"], [0.19, "#131a30"], [0.235, "#3d4066"], [0.27, "#cfd8e2"], [0.33, "#f3f2ee"], [0.5, "#f6f5f1"], [0.68, "#f3eee4"], [0.735, "#e3c6a6"], [0.762, "#5a5279"], [0.8, "#1b2140"], [0.86, "#0d1222"]];
  const SKY_BOT = [[0, "#1a2240"], [0.19, "#283050"], [0.235, "#d49884"], [0.27, "#f3d0b3"], [0.33, "#faf6ee"], [0.5, "#fcfbf7"], [0.68, "#f9efdc"], [0.735, "#f0a379"], [0.762, "#d47f68"], [0.8, "#383a60"], [0.86, "#1a2240"]];
  const PAPERS = [[0, "#1a2036"], [0.19, "#1f263e"], [0.235, "#4a4561"], [0.27, "#ede4d8"], [0.33, "#fbf8f1"], [0.5, "#fdfcf8"], [0.68, "#faf4e8"], [0.735, "#f0dbc4"], [0.756, "#5d5571"], [0.8, "#262c48"], [0.86, "#1a2036"]];
  const INK_DARK = toRGB("#1c1c1c"), INK_LIGHT = toRGB("#efe6cf");
  /** palette(tau): tau 0 midnight, 0.25 dawn, 0.5 noon, 0.75 dusk. Day = dark ink on warm paper; night inverts to pale ink on
      indigo with warm lamps. {top, bottom, paper, ink, inkT 0 day..1 night ink, lamp 0 bright..1 dark (lights come on one by one,
      each at its own threshold), night (stars, fireflies), sunset} */
  LA.palette = (tau) => {
    const top = ramp(SKY_TOP, tau), bottom = ramp(SKY_BOT, tau), paper = ramp(PAPERS, tau), L = lum(paper), inkT = smooth(0.56, 0.36, L);
    return {
      tau, top, bottom, paper, inkT, ink: mix(INK_DARK, INK_LIGHT, inkT), lamp: smooth(0.78, 0.4, L), night: smooth(0.42, 0.1, lum(top)),
      sunset: Math.max(smooth(0.67, 0.735, ((tau % 1) + 1) % 1) * smooth(0.79, 0.745, ((tau % 1) + 1) % 1), smooth(0.215, 0.245, ((tau % 1) + 1) % 1) * smooth(0.3, 0.26, ((tau % 1) + 1) % 1)),
    };
  };
  /** A flat colour pushed toward the night palette (clothes, props). */
  LA.nightTint = (colour, P, amount = 0.55) => { const c = toRGB(colour); return rgb(mix(c, mix(c, [12, 16, 30], 0.6), P.inkT * amount)); };
  LA.mix = (a, b, t) => rgb(mix(toRGB(a), toRGB(b), t));
  /** 0..1 light amount for a lamp with its own threshold on P.lamp (and optional lights-out `off` in tau). */
  LA.lit = (P, th = 0.5, off) => smooth(th - 0.04, th + 0.04, P.lamp) * (off === undefined ? 1 : 1 - smooth(off - 0.01, off + 0.01, P.tau) * (1 - smooth(off + 0.25, off + 0.28, P.tau)));

  /* ------------------------------------------------------------------ the mover: position, facing and gait phase as pure functions of t */
  // A walk segment covers `dist` in T seconds with go(t) easing in over r0 and out over r1. G(tau) = integral of go = the distance in
  // "seconds at full speed", so position = lerp(from, to, G / Gtot) and gait phase = G / period: the planted foot stays put at ANY t.
  const Gof = (tau, T, r0, r1) => {
    const Gt = T - (r0 + r1) / 2;
    if (tau <= 0) return 0;
    if (tau >= T) return Gt;
    if (tau < r0) { const q = tau / r0; return r0 * (q * q * q - (q * q * q * q) / 2); }
    if (tau > T - r1) { const s = (T - tau) / r1; return Gt - r1 * (s * s * s - (s * s * s * s) / 2); }
    return r0 / 2 + (tau - r0);
  };
  const goOf = (tau, T, r0, r1) => (r0 > 0 ? smooth(0, r0, tau) : 1) * (r1 > 0 ? smooth(0, r1, T - tau) : 1);
  LA.mover = (o = {}) => {
    const segs = [], face = [[-1e9, o.dir || 1]];
    const m = { segs, x: o.x || 0, y: o.y || 0 };
    const place0 = (t) => { let p = [m.x, m.y]; for (const s of segs) if (t >= s.t1) p = [s.x1, s.y1]; return p; };
    /** walk from where it stands at `at` to `to` (x or [x, y]) at `speed` units/s; -> the time it arrives */
    m.walk = (at, to, w = {}) => {
      const p0 = place0(at), x1 = Array.isArray(to) ? to[0] : to, y1 = Array.isArray(to) ? to[1] : p0[1], dist = Math.hypot(x1 - p0[0], y1 - p0[1]);
      let r0 = w.ramp ? w.ramp[0] : 0.3, r1 = w.ramp ? w.ramp[1] : 0.35;
      const D = dist / w.speed; r0 = Math.min(r0, D); r1 = Math.min(r1, D);
      const T = D + (r0 + r1) / 2, dirv = Math.abs(x1 - p0[0]) > 1e-6 ? Math.sign(x1 - p0[0]) : face[face.length - 1][1];
      const prev = segs.length ? segs[segs.length - 1] : null;
      segs.push({ t0: at, t1: at + T, x0: p0[0], y0: p0[1], x1, y1, dist, T, r0, r1, cum: prev ? prev.cum + prev.dist : 0, speed: w.speed });
      if (dirv !== face[face.length - 1][1]) face.push([at, dirv]);
      return at + T;
    };
    m.face = (at, dir) => { if (dir !== face[face.length - 1][1]) face.push([at, dir]); };
    m.at = (t) => {
      let seg = null;
      for (const s of segs) if (s.t0 <= t) seg = s;
      let x = m.x, y = m.y, G = 0, go = 0, cum = 0;
      if (seg) {
        const tau = t - seg.t0;
        if (tau >= seg.T) { x = seg.x1; y = seg.y1; cum = seg.cum + seg.dist; }
        else {
          const Gt = seg.T - (seg.r0 + seg.r1) / 2, g = Gof(tau, seg.T, seg.r0, seg.r1), k = Gt > 0 ? g / Gt : 1;
          x = lerp(seg.x0, seg.x1, k); y = lerp(seg.y0, seg.y1, k); G = g; go = goOf(tau, seg.T, seg.r0, seg.r1); cum = seg.cum + seg.dist * k;
        }
      }
      let k = 0;
      for (let i = 0; i < face.length; i++) if (face[i][0] <= t) k = i;
      const cur = face[k], prv = k ? face[k - 1][1] : cur[1], flip = prv === cur[1] ? cur[1] : lerp(prv, cur[1], smooth(0, 0.3, t - cur[0]));
      return { x, y, flip, G, go, dist: cum, dir: cur[1], seg };
    };
    /** the times the planted foot lands (every half period of the gait) inside a segment */
    m.footfalls = (seg, period) => {
      const out = [], Gt = seg.T - (seg.r0 + seg.r1) / 2;
      for (let k = 1; k * 0.5 * period < Gt; k++) {
        const target = k * 0.5 * period; let lo = 0, hi = seg.T;
        for (let i = 0; i < 24; i++) { const mid = (lo + hi) / 2; if (Gof(mid, seg.T, seg.r0, seg.r1) < target) lo = mid; else hi = mid; }
        out.push(seg.t0 + lo);
      }
      return out;
    };
    return m;
  };

  /* ------------------------------------------------------------------ the stage */
  let stageN = 0;
  const STROKY = "path,ellipse,circle,line,rect,polyline";
  /** The stage of one scene: an SVG in figure units with layers, a camera, wind, the ink filter and optional day-to-night.
      S = LA.stage(root, T, {u, wob, boil, seed, wind, daynight, camera}).
      Layers back to front: sky, far, back, mid, front (inked) then glow (screen blend) and over. S.layer(name, {par, sortY}) adds one.
      S.frame((t, S) => ..) runs every frame while the scene is on; S.P is the palette (S.daynight(keys)); S.wind(t) the wind. */
  LA.stage = (root, T, o = {}) => {
    const W = FX._W || 1080, H = FX._H || 1920, u = o.u || Math.min(W, H) / 216, id = "la" + stageN++, t0 = T ? T.start : 0, t1 = T ? T.end : 1e9;
    const svg = FX.svg(root, W, H);
    svg.style.overflow = "hidden"; svg.style.color = INK_DAY; svg.style.setProperty("--la-paper", PAPER_DAY);
    const defs = el("defs", {}, svg), wob = o.wob ?? 1, boil = o.boil || 0;
    const flt = el("filter", { id: id + "f", filterUnits: "userSpaceOnUse", x: 0, y: 0, width: W, height: H }, defs);
    const turb = el("feTurbulence", { type: "fractalNoise", baseFrequency: (0.6 / u).toFixed(4), numOctaves: 2, seed: 7, result: "n" }, flt);
    el("feDisplacementMap", { in: "SourceGraphic", in2: "n", scale: (0.45 * u * wob).toFixed(2), xChannelSelector: "R", yChannelSelector: "G", result: "d" }, flt);
    el("feGaussianBlur", { in: "d", stdDeviation: Math.max(0.2, 0.1 * u).toFixed(2) }, flt);
    const hatch = el("pattern", { id: id + "h", width: 3, height: 3, patternUnits: "userSpaceOnUse", patternTransform: "rotate(-35)" }, defs);
    el("line", { x1: 0, y1: 0, x2: 0, y2: 3, stroke: "currentColor", "stroke-width": 0.55 }, hatch);
    const skyGrad = el("linearGradient", { id: id + "s", x1: 0, y1: 0, x2: 0, y2: 1 }, defs);
    const stopTop = el("stop", { offset: 0, "stop-color": "#fdfcf8" }, skyGrad), stopBot = el("stop", { offset: 1, "stop-color": "#fdfcf8" }, skyGrad);
    const S = { svg, defs, W, H, u, w: W / u, h: H / u, pen: PEN, T, id, hatch: `url(#${id}h)`, cbs: [], layers: {}, reveals: [], tints: [], P: LA.palette(0.5), t: 0, _cam: null, _tau: null, _grads: {} };
    S.k = o.figure ?? 1; S.u = 2 * S.k; S.pw = PEN * S.k;   // figure: the scale people will be drawn at; scenery is sized for it (S.u: 1 = a door taller than a 0.5-scale figure) and pens follow (S.pw)
    S.gy = o.ground == null ? Math.round(S.h * 0.7) : o.ground <= 1 ? Math.round(o.ground * S.h) : o.ground;   // the ground line (y of the street / floor); the default sits in the lower quarter
    S.wind = LA.wind(o.seed ?? 1, o.wind);
    el("rect", { x: 0, y: 0, width: W, height: H, class: "la-pp" }, svg);
    S.skyBg = el("rect", { x: 0, y: 0, width: W, height: H, fill: `url(#${id}s)`, opacity: 0 }, svg);
    S.ink = el("g", wob > 0 ? { filter: `url(#${id}f)` } : {}, svg);
    S.over = el("g", {}, svg);
    S.layer = (name, lo = {}) => {
      if (S.layers[name]) return S.layers[name].g;
      const g = el("g", {}, lo.filter === false ? S.over : S.ink);
      if (lo.blend) g.style.mixBlendMode = lo.blend;
      S.layers[name] = { g, par: lo.par ?? 1, sortY: !!lo.sortY }; return g;
    };
    S.layer("sky", { par: 0.12 }); S.layer("far", { par: 0.55 }); S.layer("back", { par: 0.8 }); S.layer("mid", { sortY: true }); S.layer("front", { par: 1.12 });
    S.layer("glow", { filter: false, blend: "screen" }); S.layer("over", { filter: false });
    /** camera: keys [[t, [cx, cy, zoom], ease?], ...] (FX.keys) or a function t -> [cx, cy, zoom]; centre in figure units */
    S.camera = (c) => { S._cam = c; return S; };
    S.daynight = (keys) => {   // keys [[t, tau], ...] linear (tau may run past 1: 0.6 -> 1.3 = afternoon through the night to dawn), or a function t -> tau
      S._tau = typeof keys === "function" ? keys : (t) => {
        if (t <= keys[0][0]) return keys[0][1];
        for (let i = 1; i < keys.length; i++) if (t <= keys[i][0]) return lerp(keys[i - 1][1], keys[i][1], (t - keys[i - 1][0]) / Math.max(1e-6, keys[i][0] - keys[i - 1][0]));
        return keys[keys.length - 1][1];
      };
      S.skyBg.setAttribute("opacity", 1); return S;
    };
    S.frame = (fn) => { S.cbs.push(fn); return fn; };
    /** a flat colour that follows the night palette */
    S.tint = (node, colour, amount) => { node.removeAttribute("class"); node.style.fill = colour; S.tints.push([node, colour, amount]); return node; };   // the paper class would win over an attribute
    /** a warm radial glow (light lives on the screen-blend layer): S.glow(x, y, r, {on: (P, t) => 0..1, colour, flicker}) */
    S.glow = (x, y, r, go = {}) => {
      const col = go.colour || "#ffb454", key = col.replace("#", "g");
      if (!S._grads[key]) {
        const g = el("radialGradient", { id: id + key }, defs);
        el("stop", { offset: 0, "stop-color": col, "stop-opacity": 0.8 }, g); el("stop", { offset: 0.45, "stop-color": col, "stop-opacity": 0.28 }, g); el("stop", { offset: 1, "stop-color": col, "stop-opacity": 0 }, g);
        S._grads[key] = true;
      }
      const c = el("circle", { cx: x, cy: y, r, fill: `url(#${id}${key})`, opacity: 0 }, S.layer("glow")), ph = go.phase ?? (x * 0.37 + y * 0.11);
      S.frame((t) => { const k = (go.on ? go.on(S.P, t) : 1) * (go.flicker ? 1 - go.flicker * 0.5 * (1 + Math.sin(t * 9 + ph) * Math.sin(t * 5.3 + ph * 2)) : 1); c.setAttribute("opacity", f2(clamp(k, 0, 1))); });
      return c;
    };
    if (o.daynight) S.daynight(o.daynight);
    if (o.camera) S.camera(o.camera);

    const prepare = (job) => {   // first visible frame: stroke lengths and centres (geometry needs the scene to be displayed)
      job.items = job.nodes.map((n, i) => {
        let len = 20, cx = 0, cy = 0;
        try { len = n.getTotalLength ? n.getTotalLength() : 20; } catch (e) { /* no geometry */ }
        try { const b = n.getBBox(); cx = b.x + b.width / 2; cy = b.y + b.height / 2; if (!len) len = (b.width + b.height) * 2; } catch (e) { /* hidden */ }
        return { n, i, len: Math.max(len, 1), cx, cy, fillOnly: !n.getAttribute("stroke") && !n.style.stroke };
      });
      const ord = job.order, key = { lr: (a) => a.cx, tb: (a) => a.cy, bt: (a) => -a.cy, out: (a) => Math.abs(a.cx - job.cx0) }[ord];
      if (ord === "out") job.cx0 = job.items.reduce((s, a) => s + a.cx, 0) / (job.items.length || 1);
      if (key) job.items.sort((a, b) => key(a) - key(b));
      const n = job.items.length || 1, w = job.items.map((a) => Math.pow(clamp(a.len, 4, 300), 0.6)), tot = w.reduce((a, b) => a + b, 0) || 1, avg = tot / n;
      const conc = job.overlap ?? clamp(n / 10, 1, 8), mean = (job.dur * conc) / n;
      let cum = 0, maxd = 0;
      job.items.forEach((a, k) => { a.d = clamp(mean * (w[k] / avg), 0.14, job.dur * 0.7); maxd = Math.max(maxd, a.d); a.c = cum; cum += w[k]; });
      job.items.forEach((a) => { a.s = job.at + (job.dur - maxd) * (a.c / tot); });
      job.state = null;
    };
    const runReveal = (job, t) => {
      if (!job.items) prepare(job);
      const st = t < job.at ? "pre" : t >= job.at + job.dur + 0.001 ? "done" : "live";
      if (st === job.state && st !== "live") return;
      job.state = st;
      for (const a of job.items) {
        const n = a.n;
        if (st === "pre") { n.style.visibility = "hidden"; continue; }
        if (st === "done") { n.style.visibility = ""; n.style.strokeDasharray = ""; n.style.fillOpacity = ""; n.style.opacity = ""; continue; }
        const p = smooth(0, 1, (t - a.s) / a.d);
        if (p <= 0) { n.style.visibility = "hidden"; continue; }
        n.style.visibility = "";
        if (a.fillOnly) { n.style.fillOpacity = f2(smooth(0.35, 1, p)); }
        else { n.style.strokeDasharray = p >= 1 ? "" : `${p.toFixed(4)} 2`; n.style.fillOpacity = f2(smooth(0.6, 1, p)); }
      }
      for (const x of job.texts) x.style.opacity = f2(smooth(0.72, 1, (t - job.at) / job.dur));
    };
    FX.onFrame((t) => {
      if (t < t0 - 1e-6 || t > t1 + 1e-6) return;
      S.t = t;
      if (S._tau) {
        const P = (S.P = LA.palette(S._tau(t)));
        svg.style.color = rgb(P.ink); svg.style.setProperty("--la-paper", rgb(P.paper));
        stopTop.setAttribute("stop-color", rgb(P.top)); stopBot.setAttribute("stop-color", rgb(P.bottom));
        for (const [n, c, a] of S.tints) n.style.fill = LA.nightTint(c, P, a);
      }
      const cam = S._cam ? (typeof S._cam === "function" ? S._cam(t) : FX.keys(t, S._cam)) : [S.w / 2, S.h / 2, 1], c0 = [S.w / 2, S.h / 2];
      for (const k in S.layers) {
        const L = S.layers[k], cx = lerp(c0[0], cam[0], L.par), cy = lerp(c0[1], cam[1], L.par), z = 1 + (cam[2] - 1) * L.par;
        L.g.setAttribute("transform", `translate(${W / 2} ${H / 2}) scale(${f2(u * z)}) translate(${f2(-cx)} ${f2(-cy)})`);
      }
      if (boil) turb.setAttribute("seed", [7, 19, 31][Math.floor(t * boil) % 3]);
      for (const fn of S.cbs) fn(t, S);
      for (const job of S.reveals) runReveal(job, t);
      for (const k in S.layers) if (S.layers[k].sortY) {   // people in front of people: lower on the page = nearer
        const g = S.layers[k].g, kids = [...g.children], sorted = kids.slice().sort((a, b) => (a.__y || 0) - (b.__y || 0));
        if (kids.some((c, i) => c !== sorted[i])) sorted.forEach((c) => g.appendChild(c));
      }
    });
    return S;
  };

  /** Draw a group in stroke by stroke, like a pen (every stroke is a dash of pathLength 1, so animated paths work too): fills fade in as
      their outline closes, text fades at the end. o: {at, dur, order: seq|lr|tb|bt|out, overlap (strokes in flight at once)}; -> the end time */
  LA.drawIn = (S, target, o = {}) => {
    const list = target instanceof Element ? [...target.querySelectorAll(STROKY)].concat(target.matches(STROKY) ? [target] : []) : target;
    const nodes = list.filter((n) => !n.closest("defs") && !n.closest("text"));
    nodes.forEach((n) => n.setAttribute("pathLength", 1));
    const job = { nodes, texts: target instanceof Element ? [...target.querySelectorAll("text")] : [], at: o.at ?? 0, dur: o.dur ?? 2, order: o.order || "seq", overlap: o.overlap, items: null, state: null };
    S.reveals.push(job); job.texts.forEach((x) => (x.style.opacity = 0));
    if (o.sfx) FX.sfx("swish", job.at, { db: -20 });
    return job.at + job.dur;
  };

  /* ------------------------------------------------------------------ the sky */
  /** Sun and moon on their arcs, stars, drifting clouds, far hills: LA.sky(S, {sun, moon, stars, clouds, hills, horizon}). Follows S.daynight. */
  LA.sky = (S, o = {}) => {
    const g = S.layer("sky"), hz = o.horizon ?? S.gy - 6, R = FX.rand(o.seed ?? 5), W = S.w, H = S.h;
    const arc = (tau, a, b) => { const k = clamp((((tau % 1) + 1) % 1 - a) / (b - a), 0, 1); return [lerp(W * 0.12, W * 0.88, k), hz - Math.sin(Math.PI * k) * (hz - H * 0.1) * 0.92, k]; };
    const out = {};
    if (o.hills) {
      const far = S.layer("far"), pts = []; for (let i = 0; i <= 9; i++) pts.push([(W * i) / 9, hz - 6 - 12 * Math.abs(Math.sin(i * 1.7 + 1)) - R() * 8]);
      const hl = pen(far, 0.8); hl.setAttribute("d", LA.curvePath(pts, { amp: 0 })); hl.setAttribute("opacity", 0.45);
    }
    if (o.sun !== false) {
      const sun = LA.oval(g, 0, 0, 7, 7, { fill: false, w: 1.1 }), rays = pen(g, 0.8); let d = "";
      for (let i = 0; i < 12; i++) { const a = (i / 12) * 6.283; d += `M${f2(Math.cos(a) * 10)} ${f2(Math.sin(a) * 10)}L${f2(Math.cos(a) * (i % 2 ? 12.4 : 14))} ${f2(Math.sin(a) * (i % 2 ? 12.4 : 14))}`; }
      rays.setAttribute("d", d);
      const sg = el("g", {}, g); sg.appendChild(sun); sg.appendChild(rays);
      S.frame((t) => { const [x, y, k] = arc(S.P.tau, 0.26, 0.74); sg.setAttribute("transform", `translate(${f2(x)} ${f2(y)}) rotate(${f2(S.P.tau * 360 * 2)})`); sg.setAttribute("opacity", k > 0 && k < 1 ? 1 : 0); });
      out.sun = sg;
    }
    if (o.moon !== false) {
      const mg = el("g", {}, g), m = blot(mg); m.setAttribute("d", "M0 -8A8 8 0 1 0 6.5 4.6A6.4 6.4 0 1 1 0 -8Z");
      S.frame((t) => { const tau = ((S.P.tau % 1) + 1) % 1, k = tau >= 0.7 ? (tau - 0.7) / 0.6 : (tau + 0.3) / 0.6, x = lerp(W * 0.15, W * 0.85, clamp(k, 0, 1)), y = hz - Math.sin(Math.PI * clamp(k, 0, 1)) * (hz - H * 0.12) * 0.9;
        mg.setAttribute("transform", `translate(${f2(x)} ${f2(y)})`); mg.setAttribute("opacity", f2(S.P.night)); });
      out.moon = mg;
    }
    if (o.stars) {
      const sg = el("g", {}, g), st = [];
      for (let i = 0; i < o.stars; i++) { const x = R() * W, y = R() * (hz - 30), r = 0.8 + R() * 1.1, p = pen(sg, 0.45); p.setAttribute("d", `M${f2(x - r)} ${f2(y)}H${f2(x + r)}M${f2(x)} ${f2(y - r)}V${f2(y + r)}`); st.push([p, R() * 6.28, 0.8 + R() * 1.8]); }
      S.frame((t) => { sg.setAttribute("opacity", f2(S.P.night)); if (S.P.night > 0.02) for (const [p, ph, sp] of st) p.setAttribute("opacity", f2(0.55 + 0.45 * Math.sin(t * sp + ph))); });
    }
    if (o.clouds) {
      const cg = el("g", {}, g), cl = [];
      for (let i = 0; i < o.clouds; i++) {
        const w = 22 + R() * 18, y = H * 0.1 + R() * (hz - H * 0.4) * 0.6, p = shape(cg, 0.9), x0 = R() * (W + 80) - 40;
        p.setAttribute("d", LA.curvePath([[0, 0], [w * 0.15, -5], [w * 0.4, -7], [w * 0.65, -4], [w * 0.9, -5.5], [w, 0], [w * 0.5, 2.4]], { closed: true, amp: 0.3, seed: i + 3, tension: 5 }));
        cl.push([p, x0, y, 1.2 + R() * 1.4]);
      }
      S.frame((t) => { for (const [p, x0, y, v] of cl) { const x = ((x0 + t * v) % (W + 80) + (W + 80)) % (W + 80) - 50; p.setAttribute("transform", `translate(${f2(x)} ${f2(y)})`); p.setAttribute("opacity", f2(1 - S.P.night * 0.55)); } });
    }
    return out;
  };

  /* ------------------------------------------------------------------ gait (ported from upstream: planted foot, minimum-jerk swing, heel-off, solved hip) */
  const GAITS = {   // one standing height for all of them (ankleY 118.4), so a stop between two segments never pops
    walk: { period: 1.0, duty: 0.62, stride: 24, lift: 3.4, heelOff: 15, heelKick: 0, thigh: 23, shin: 23, ankleY: 118.4, ground: 120, toe: 4.2 },
    shuffle: { period: 0.9, duty: 0.64, stride: 18, lift: 2.4, heelOff: 12, heelKick: 0, thigh: 23, shin: 23, ankleY: 118.4, ground: 120, toe: 4.2 },
    run: { period: 0.62, duty: 0.38, stride: 30, lift: 11, heelOff: 10, heelKick: 4, thigh: 23, shin: 23, ankleY: 118.4, ground: 120, toe: 3.4 },
  };
  const kneeOf = (hip, ankle, l1, l2) => joint(hip, ankle, l1, l2, 1);
  LA.gait = (kind = "walk", over = {}) => {
    const o = { ...GAITS[kind], ...over }, { period, duty, stride: S, lift, heelOff, heelKick, thigh, shin, ankleY, ground, toe } = o;
    const reach = (thigh + shin) * 0.983, restHip = ankleY - reach, speed = S / (duty * period);
    const foot = (u) => {
      u = ((u % 1) + 1) % 1;
      if (u < duty) {
        const x = 40 + S / 2 - (S * u) / duty, peel = smooth(duty - 0.14, duty, u), th = (heelOff * peel * Math.PI) / 180, px = x + toe, ox = -toe, oy = ankleY - ground;
        return { ankle: [px + ox * Math.cos(th) - oy * Math.sin(th), ground + ox * Math.sin(th) + oy * Math.cos(th)], pitch: heelOff * peel, stance: true };
      }
      const s = (u - duty) / (1 - duty), x = 40 - S / 2 + S * minJerk(s) - heelKick * Math.sin(Math.PI * Math.min(1, s * 1.6)), y = ankleY - lift * Math.pow(Math.sin(Math.PI * Math.pow(s, heelKick ? 0.7 : 1)), 1.2);
      return { ankle: [x, y], pitch: heelOff * Math.pow(1 - smooth(0, 0.55, s), 1.4), stance: false };
    };
    return {
      ...o, kind, speed, restHip,
      pose(phase, go = 1) {
        const raw = [foot(phase), foot(phase + 0.5)];
        if (go < 1) raw.forEach((fo, i) => { const rest = 40 + (i ? -2 : 2); fo.ankle = [rest + (fo.ankle[0] - rest) * go, ankleY + (fo.ankle[1] - ankleY) * go]; fo.pitch *= go; fo.stance = true; });
        let hipY = restHip;
        const half = (((phase % 0.5) + 0.5) % 0.5);
        if (heelKick && go >= 1) hipY = half < duty ? restHip + 1.4 * Math.sin((Math.PI * half) / duty) : restHip - 2.6 * Math.sin((Math.PI * (half - duty)) / (0.5 - duty));   // runner: compressed over the planted foot, highest in flight
        else for (const fo of raw) if (fo.stance) { const dx = fo.ankle[0] - 40; hipY = Math.max(hipY, fo.ankle[1] - Math.sqrt(Math.max(1, reach * reach - dx * dx))); }   // walker: highest as the legs pass
        if (heelKick && go < 1) hipY = restHip;
        const hip = [40, hipY], feet = raw.map((fo) => ({ ...fo, knee: kneeOf(hip, fo.ankle, thigh, shin) }));
        return { hip, feet, front: feet[0].ankle[0] >= feet[1].ankle[0] ? 0 : 1, bob: hipY - restHip };
      },
    };
  };

  /* ------------------------------------------------------------------ the figure */
  const DUR = { wave: 2.4, tipHat: 1.8, point: 1.8, bow: 2.6, cheer: 1.8, shrug: 1.5, think: 2.4, look: 2, present: 2.2, lookUp: 2 };
  const armIK = (a, b, l1 = 17, l2 = 16) => { const c1 = joint(a, b, l1, l2, 1), c2 = joint(a, b, l1, l2, -1); return c1[1] + 0.3 * c1[0] > c2[1] + 0.3 * c2[0] ? c1 : c2; };   // the elbow hangs down
  const env = (t, at, dur, ri = 0.35, ro = 0.4) => (t < at || t > at + dur ? 0 : smooth(0, ri, t - at) * smooth(0, ro, at + dur - t));
  /** A person (or a rig you pose): LA.figure(S, {who: man|woman|child, x, y (feet), dir, scale, coat, hat: bowler|cap|straw|beret|false, hair, scarf, prop: briefcase|bag|umbrella|balloon|backpack|lantern, accent, gait, layer}).
      fig.walk(at, x | [x, y], {gait: walk|shuffle|run, ramp, steps}) -> arrival time (the duration comes from the distance: the feet never slide)
      fig.face(at, dir) · fig.act(at, "wave|tipHat|point|bow|cheer|shrug|think|look|present|lookUp", {dur, arm, deg}) -> end · fig.sit(at) / fig.stand(at) */
  LA.figure = (S, o = {}) => {
    const who = o.who || "man", s = (o.scale ?? 1) * S.k * (who === "child" ? 0.7 : 1), PAL = { coat: o.coat ?? false, accent: o.accent || "#b3412d", hair: o.hair || "currentColor" };
    const hat = o.hat === undefined ? (who === "man" ? "bowler" : false) : o.hat, prop = o.prop || false;
    const layer = S.layer(o.layer || "mid"), g = el("g", {}, layer);
    const m = LA.mover({ x: o.x ?? S.w / 2, y: o.y ?? S.gy, dir: o.dir || 1 }), gaits = {}, gaitOf = (k) => gaits[k] || (gaits[k] = LA.gait(k, o.gaitOver));
    const acts = [], posture = [[-1e9, 0]], fig = { g, mv: m, s, who, S, acts, rig: null };
    const headRx = who === "child" ? 4.4 : 3.6, headRy = who === "child" ? 5.4 : 4.6;
    // ---- nodes, back to front
    const back = el("g", {}, g), farArm = LA.limb(back, 3.6);
    const legs = el("g", {}, g), L = [LA.limb(legs, 4.2), LA.limb(legs, 4.2)], shoes = [blot(legs), blot(legs)];
    if (who !== "woman") L.forEach((l) => LA.solid(l, o.trousers || "currentColor"));
    const up = el("g", {}, g), body = who === "woman" || PAL.coat ? paint(up, PAL.coat || "#d9cdb8", PEN) : shape(up);
    if (PAL.coat) S.tint(body, PAL.coat); else if (who === "woman") body.setAttribute("class", "la-pp");
    if (who === "child") body.setAttribute("fill", `url(#${S.id}h)`), body.removeAttribute("class");
    const seam = pen(up, PEN * 0.6), tailNode = scarfOn() ? paint(up, PAL.accent, PEN * 0.8) : null;
    function scarfOn() { return !!o.scarf; }
    const headG = el("g", {}, up), head = el("ellipse", { rx: headRx, ry: headRy, stroke: "currentColor", "stroke-width": PEN, "stroke-linejoin": "round", class: "la-pp", pathLength: 1 }, headG);
    const hair = blot(headG), hatN = hat ? (hat === "straw" ? shape(headG, PEN * 0.9) : blot(headG)) : null, brim = hat === "bowler" || hat === "cap" ? pen(headG, PEN * 0.7) : null;
    if (hatN && hat === "straw") S.tint(hatN, "#d8b868");
    const neckScarf = o.scarf ? paint(up, PAL.accent, PEN * 0.8) : null;
    if (o.scarf) { S.tint(neckScarf, o.scarf === true ? PAL.accent : o.scarf); S.tint(tailNode, o.scarf === true ? PAL.accent : o.scarf); }
    const near = LA.limb(up, 3.6), pg = el("g", {}, up);   // the prop sits on the near hand
    const P = {};   // prop nodes
    if (prop === "briefcase") { P.body = paint(pg, "#6b4a32", PEN * 0.8); P.handle = pen(pg, PEN * 0.7); S.tint(P.body, "#6b4a32"); }
    if (prop === "bag") { P.body = paint(pg, o.propColour || "#c9a96a", PEN * 0.8); P.handle = pen(pg, PEN * 0.7); P.loaf = shape(pg, PEN * 0.6); S.tint(P.body, o.propColour || "#c9a96a"); }
    if (prop === "umbrella") { P.dome = paint(pg, o.propColour || "#b3412d", PEN * 0.8); P.shaft = pen(pg, PEN * 0.9); P.ribs = pen(pg, PEN * 0.4); S.tint(P.dome, o.propColour || "#b3412d"); }
    if (prop === "balloon") { P.string = pen(layer, PEN * 0.5); P.ball = paint(layer, o.propColour || "#c8473c", PEN * 0.8); P.shine = pen(layer, PEN * 0.5); S.tint(P.ball, o.propColour || "#c8473c"); g.__extra = [P.string, P.ball, P.shine]; }
    if (prop === "backpack") { P.pack = paint(back, o.propColour || "#4a6a8a", PEN * 0.8); S.tint(P.pack, o.propColour || "#4a6a8a"); P.strap = pen(up, PEN * 0.7); }
    if (prop === "lantern") { P.cord = pen(pg, PEN * 0.6); P.box = paint(pg, "#e8a64a", PEN * 0.8); P.ribs = pen(pg, PEN * 0.5); P.glow = S.glow(0, 0, 26 * s, { on: (Pl) => 0.35 + 0.65 * Pl.night }); }
    // ---- wind-driven secondary motion (pure functions of t)
    const phaseOf = (t) => { const a = m.at(t), kind = a.seg ? a.seg.kind : "walk"; return { a, kind, gt: gaitOf(kind), phase: (a.G * (a.seg && a.seg.pace || 1)) / gaitOf(kind).period }; };   // pace = steps per second relative to the gait: the planted foot still moves at the travel speed
    const accel = (t) => { const { a, phase } = phaseOf(t); return Math.cos(4 * Math.PI * phase) * 1.6 * a.go; };
    const swing = prop === "briefcase" || prop === "bag" || prop === "lantern" ? LA.pendulum((t) => -accel(t) - S.wind(t) * 0.3, { k: prop === "lantern" ? 9 : 14, d: prop === "lantern" ? 0.9 : 1.8 }) : null;
    const umbTilt = prop === "umbrella" ? LA.spring((t) => -0.1 - S.wind(t) * 0.12 + 0.02 * Math.sin(phaseOf(t).phase * 6.283) * phaseOf(t).a.go, { k: 30, d: 5 }) : null;
    const hcOf = (b) => [42.6, 31.6 + b], toWorld = (t, l) => { const a = m.at(t); return [a.x + a.flip * s * (l[0] - 40), a.y + s * (l[1] - 120)]; };
    const hipRef = (t) => { const p = fig.pose(t); return p; };
    const scarfRope = o.scarf ? LA.rope((t) => { const p = fig.pose(t), hc = hcOf(p.b); return toWorld(t, [hc[0] - 3.6, hc[1] + 6]); }, { n: 6, seg: 2.6 * s, g: 20 * s, wind: (t) => S.wind(t) * 1.4 * (m.at(t).dir || 1) + 0.0, windK: 55 * s, dirX: 0.5 * s * (o.dir || 1), drag: 0.1 }) : null;
    const balloonRope = prop === "balloon" ? LA.rope((t) => { const p = fig.pose(t); return toWorld(t, p.hand); }, { n: 6, seg: 5.2 * s, g: -380 * s, wind: (t) => S.wind(t) * 0.8 * (m.at(t).dir || 1), windK: 50 * s, drag: 0.08 }) : null;
    fig.ropes = { scarf: scarfRope, balloon: balloonRope };
    // ---- the plan
    fig.walk = (at, to, w = {}) => {
      const gt = gaitOf(w.gait || o.gait || "walk"), end = m.walk(at, to, { speed: gt.speed * s * (w.pace ?? 1), ramp: w.ramp });
      const sg = m.segs[m.segs.length - 1]; sg.kind = gt.kind; sg.pace = w.pace ?? 1;
      if (w.steps !== false) m.footfalls(sg, gt.period / sg.pace).slice(0, w.maxSteps ?? 30).forEach((ft) => FX.sfx("tick", ft, { db: -27 }));
      return end;
    };
    fig.face = (at, dir) => m.face(at, dir);
    fig.act = (at, name, ao = {}) => { const dur = ao.dur ?? DUR[name] ?? 2; acts.push({ at, dur, name, o: ao }); return at + dur; };
    fig.sit = (at, so = {}) => { posture.push([at, 1, so.dur ?? 0.9]); return at + (so.dur ?? 0.9); };
    fig.stand = (at, so = {}) => { posture.push([at, 0, so.dur ?? 0.8]); return at + (so.dur ?? 0.8); };
    fig.pos = (t) => m.at(t);
    fig.hand = (t) => toWorld(t, fig.pose(t).hand);   // world position of the near hand (hang something there)
    fig.head = (t) => toWorld(t, hcOf(fig.pose(t).b));
    // ---- the pose at t (memoised for the frame: rope sims and the draw both ask for it)
    let memoT = null, memo = null;
    fig.pose = (t) => {
      if (memoT === t) return memo;
      const { a, gt, phase } = phaseOf(t);
      let sit = 0;
      for (let i = 1; i < posture.length; i++) { const [pt0, v, d] = posture[i]; if (t >= pt0) sit = lerp(posture[i - 1][1], v, smooth(0, d, t - pt0)); }
      let pose = gt.pose(phase, a.go);
      if (fig.rig) { const r = fig.rig(t); pose = { ...pose, hip: r.hip, feet: r.ankles.map((an, i) => ({ ankle: an, pitch: r.pitch ? r.pitch[i] : 0, knee: kneeOf(r.hip, an, 23, 23) })), front: 0, bob: r.hip[1] - 73.2, rider: r }; }
      else if (sit > 0.001) {
        const hip = L2(pose.hip, [36, 95.4], sit), ank = [[lerp(pose.feet[0].ankle[0], 62, sit), lerp(pose.feet[0].ankle[1], 118.4, sit)], [lerp(pose.feet[1].ankle[0], 57, sit), lerp(pose.feet[1].ankle[1], 118.4, sit)]];
        pose = { ...pose, hip, feet: ank.map((an, i) => ({ ankle: an, pitch: pose.feet[i].pitch * (1 - sit), knee: kneeOf(hip, an, 23, 23) })), front: 0, bob: hip[1] - 73.2 };
      }
      const breathe = Math.sin(t * 1.9 + (o.x ?? 0)) * 0.3 * (1 - a.go), b = pose.bob + breathe, hc = hcOf(b), sh0 = [pose.hip[0] + 1, pose.hip[1] - 32.2 + breathe];
      let lean = (pose.rider ? pose.rider.lean : 0) + sit * -3 + (who === "man" && o.stoop ? o.stoop : 0), tilt = 0, hatLift = 0;
      const legSwing = Math.cos(2 * Math.PI * (phase - 0.06)) * (gt.heelKick ? 1.25 : 1) * a.go;
      const aF = -legSwing * 16 * (gt.heelKick ? 1.4 : 1) * Math.PI / 180, aN = legSwing * 14 * (gt.heelKick ? 1.4 : 1) * Math.PI / 180, bendRun = gt.heelKick ? 0.5 : 0.25;
      const shF = [sh0[0] - 1, sh0[1] + 2], shN = [sh0[0] + 1.6, sh0[1] + 2.4];
      const swingArm = (sh, ang) => { const e = [sh[0] + 17 * Math.sin(ang), sh[1] + 17 * Math.cos(ang)], h = [e[0] + 16 * Math.sin(ang + bendRun), e[1] + 16 * Math.cos(ang + bendRun)]; return { e, h }; };
      let far = swingArm(shF, aF), nr = swingArm(shN, aN);
      if (sit > 0.001) { const rest = (sh, kx) => armIK(sh, [kx, 91]); const sf = rest(shF, 58), sn = rest(shN, 62); far = { e: L2(far.e, sf, sit), h: L2(far.h, [58, 91], sit) }; nr = { e: L2(nr.e, sn, sit), h: L2(nr.h, [62, 91], sit) }; }
      let nearW = 0;   // how much a gesture has taken the near hand away from the prop
      const useArm = (arm, tgt, e, elbowHint) => {
        const sh = arm === "near" ? shN : shF, H = arm === "near" ? nr : far, el2 = elbowHint || armIK(sh, tgt);
        H.e = L2(H.e, el2, e); H.h = L2(H.h, tgt, e); if (arm === "near") nearW = Math.max(nearW, e);
      };
      if (pose.rider) {   // hands on the bars: the torso is rotated by `lean` about the hip, so aim at the point that lands on the bar after it
        const q = (-lean * Math.PI) / 180, c = Math.cos(q), sn = Math.sin(q), dx = pose.rider.bar[0] - pose.hip[0], dy = pose.rider.bar[1] - pose.hip[1], tg = [pose.hip[0] + dx * c - dy * sn, pose.hip[1] + dx * sn + dy * c];
        useArm("near", tg, 1); useArm("far", [tg[0] - 1, tg[1]], 1);
      }
      for (const A of acts) {
        const e = env(t, A.at, A.dur, A.o.ramp ?? 0.35, A.o.ramp ?? 0.4);
        if (e <= 0) continue;
        const arm = A.o.arm || (prop && prop !== "balloon" || fig.rig ? "far" : "near"), sh = arm === "near" ? shN : shF, u = t - A.at;
        if (A.name === "wave") useArm(arm, [sh[0] + 13 + 5 * Math.sin(u * 15), sh[1] - 25 + Math.sin(u * 15 + 1.2) * 1.2], e);
        else if (A.name === "tipHat") { useArm(arm, [hc[0] + 4, hc[1] - 4.5 - 5 * smooth(0.3, 0.55, u / A.dur * 1.0 - 0.1 + 0.1) * (1 - smooth(0.62, 0.85, u / A.dur))], e); hatLift = 5 * smooth(0.28, 0.45, u / A.dur) * (1 - smooth(0.58, 0.75, u / A.dur)) * e; tilt += 3 * e; }
        else if (A.name === "point") { const dg = ((A.o.deg ?? 8) * Math.PI) / 180; useArm(arm, [sh[0] + 32 * Math.cos(dg), sh[1] - 32 * Math.sin(dg)], e); }
        else if (A.name === "cheer") { const w = Math.sin(u * 12) * 1.5; useArm("near", [sh0[0] + 11 + w, sh0[1] - 27], e); useArm("far", [sh0[0] - 3 - w, sh0[1] - 27], e); lean -= 4 * e; }
        else if (A.name === "shrug") { useArm("near", [shN[0] + 18, shN[1] + 13], e); useArm("far", [shF[0] + 11, shF[1] + 14], e); sh0[1] -= 1.4 * e; tilt -= 5 * e; }
        else if (A.name === "think") { useArm(arm, [hc[0] + 3.6, hc[1] + 6.4], e); tilt += 7 * e; }
        else if (A.name === "present") { useArm(arm, [sh[0] + 26 + 2 * Math.sin(u * 3), sh[1] + 9 - 3 * Math.sin(u * 3)], e); lean += 3 * e; }
        else if (A.name === "bow") lean += (A.o.deg ?? 32) * e * (1 - 0.2 * smooth(0.5, 1, u / A.dur));
        else if (A.name === "look") tilt += 9 * Math.sin(u * 3.2) * e;
        else if (A.name === "lookUp") { tilt -= 12 * e; hatLift += 1.2 * e; }
      }
      const feetN = pose.feet, front = pose.front;
      return (memo = { ...pose, t, a, b, hc, sh: sh0, shF, shN, far, nr, nearW, lean, tilt, hatLift, sit, phase, go: a.go, hand: L2(nr.h, [shN[0] + 6, shN[1] + 34], nearW * (prop ? 1 : 0)), feetN, front }, memoT = t, memo);
    };
    // ---- drawing
    const bodyPath = (p) => {
      const { b, sh, feetN, front } = p, sit = Math.max(p.sit, p.rider ? 1 : 0), kF = feetN[front].knee, aFt = p.rider ? [kF[0] - 1, 0] : feetN[front].ankle;   // a rider's skirt rides up like a seated one's const sh0 = sh[0], sh1 = sh[1], hipY = p.hip[1], waist = hipY - 3.2;
      const sh0 = sh[0], sh1 = sh[1], hipY = p.hip[1], waist = hipY - 3.2;
      const hemY = hipY + (who === "woman" ? 27.8 : 18.8) - sit * (who === "woman" ? 12 : 10), fx = Math.max(kF[0] + 2.4, 46.4), back0 = who === "woman" ? 28.6 : 30.6;
      const wA = who === "woman" ? 1 : 0;
      return `M${f2(sh0 - 6)} ${f2(sh1 + 1)}Q${f2(sh0 - 1)} ${f2(sh1 - 2.4)} ${f2(sh0 + 5)} ${f2(sh1 + 1)}L${f2(fx - 0.6 + wA * 1.5)} ${f2(waist)}Q${f2(fx + wA * 2)} ${f2(lerp(waist, hemY, 0.6) + b * 0.4)} ${f2(Math.max(fx + wA * 3, aFt[0] - 4 + wA * 4))} ${f2(hemY)}L${f2(back0)} ${f2(hemY + 1)}L${f2(33.2 - wA * 1)} ${f2(waist)}Z`;
    };
    const hatPath = (hc, lift) => {
      const x = hc[0], y = hc[1] - lift;
      if (hat === "bowler") return `M${f2(x - 6.4)} ${f2(y - 3.6)}L${f2(x + 6.6)} ${f2(y - 3.6)}Q${f2(x + 4.4)} ${f2(y - 5)} ${f2(x + 4)} ${f2(y - 8)}Q${f2(x)} ${f2(y - 11)} ${f2(x - 3.8)} ${f2(y - 8)}Q${f2(x - 4.2)} ${f2(y - 5)} ${f2(x - 6.4)} ${f2(y - 3.6)}Z`;
      if (hat === "cap") return `M${f2(x - 4.4)} ${f2(y - 3.2)}Q${f2(x - 4.8)} ${f2(y - 8.6)} ${f2(x + 0.4)} ${f2(y - 8.6)}Q${f2(x + 4.8)} ${f2(y - 8.4)} ${f2(x + 4.6)} ${f2(y - 3.4)}L${f2(x + 8.4)} ${f2(y - 2.6)}L${f2(x + 4.4)} ${f2(y - 2.4)}Z`;
      if (hat === "straw") return `M${f2(x - 9.5)} ${f2(y - 3.2)}Q${f2(x)} ${f2(y - 1.6)} ${f2(x + 9.5)} ${f2(y - 3.2)}Q${f2(x + 5)} ${f2(y - 5.2)} ${f2(x + 4.4)} ${f2(y - 8)}Q${f2(x)} ${f2(y - 9.6)} ${f2(x - 4.4)} ${f2(y - 8)}Q${f2(x - 5)} ${f2(y - 5.2)} ${f2(x - 9.5)} ${f2(y - 3.2)}Z`;
      return `M${f2(x - 5.6)} ${f2(y - 3.8)}Q${f2(x - 6.4)} ${f2(y - 8)} ${f2(x)} ${f2(y - 8.2)}Q${f2(x + 6.8)} ${f2(y - 8)} ${f2(x + 5.6)} ${f2(y - 4)}Q${f2(x)} ${f2(y - 2.6)} ${f2(x - 5.6)} ${f2(y - 3.8)}Z`;   // beret
    };
    const draw = (t) => {
      const a = m.at(t);
      if (t < 0) return;
      const p = fig.pose(t), { b, hc, feetN, front } = p;
      LA.place(g, a.x, a.y, a.flip || 0.001, s); g.__y = a.y;
      const rot = `rotate(${f2(p.lean)} ${f2(p.hip[0])} ${f2(p.hip[1])})`;
      back.setAttribute("transform", rot); up.setAttribute("transform", rot);
      feetN.forEach((fo, i) => { L[i].draw([p.hip, fo.knee, fo.ankle], [0.3, 0.8]); LA.shoe(shoes[i], fo.ankle, fo.pitch); });
      legs.appendChild(L[front].g); legs.appendChild(shoes[front]);
      body.setAttribute("d", bodyPath(p));
      seam.setAttribute("d", who === "woman" ? "" : `M${f2(p.sh[0] + 2.6)} ${f2(p.sh[1] + 4)}L${f2(p.sh[0] + 3.8)} ${f2(p.hip[1] - 7)}`);
      // head, hair, hat
      head.setAttribute("cx", f2(hc[0])); head.setAttribute("cy", f2(hc[1]));
      headG.setAttribute("transform", `rotate(${f2(p.tilt)} ${f2(hc[0] - 1)} ${f2(hc[1] + 5)})`);
      hair.setAttribute("d", who === "woman" ? `M${f2(hc[0] - 3.8)} ${f2(hc[1] - 1)}Q${f2(hc[0] - 4.6)} ${f2(hc[1] - 5.6)} ${f2(hc[0] + 0.4)} ${f2(hc[1] - 5.2)}Q${f2(hc[0] - 1.6)} ${f2(hc[1] - 2.2)} ${f2(hc[0] - 3.4)} ${f2(hc[1] + 2.4)}Z M${f2(hc[0] - 4.4)} ${f2(hc[1] - 4.6)}m-3 0a3 3 0 1 0 6 0a3 3 0 1 0-6 0`
        : `M${f2(hc[0] - headRx + 0.3)} ${f2(hc[1] - 0.6)}Q${f2(hc[0] - headRx - 0.4)} ${f2(hc[1] - headRy - 0.6)} ${f2(hc[0] + 0.8)} ${f2(hc[1] - headRy - 0.2)}Q${f2(hc[0] - 1)} ${f2(hc[1] - 2)} ${f2(hc[0] - headRx + 0.3)} ${f2(hc[1] + 2.2)}Z`);
      if (hair.style) hair.style.fill = PAL.hair === "currentColor" ? "" : PAL.hair;
      if (hatN) { hatN.setAttribute("d", hatPath(hc, p.hatLift)); if (brim) brim.setAttribute("d", hat === "bowler" ? `M${f2(hc[0] - 6.4)} ${f2(hc[1] - 3.6 - p.hatLift)}L${f2(hc[0] + 6.6)} ${f2(hc[1] - 3.6 - p.hatLift)}` : ""); if (hat !== "straw" && hat !== "beret" && hat !== "cap") hatN.style.fill = ""; if (o.hatColour) S.tint(hatN, o.hatColour); }
      if (o.scarf) {
        neckScarf.setAttribute("d", `M${f2(hc[0] - 4.6)} ${f2(hc[1] + 4.6)}Q${f2(hc[0])} ${f2(hc[1] + 8.4)} ${f2(hc[0] + 4)} ${f2(hc[1] + 4.8)}L${f2(hc[0] + 4.4)} ${f2(hc[1] + 7.6)}Q${f2(hc[0])} ${f2(hc[1] + 11)} ${f2(hc[0] - 4.8)} ${f2(hc[1] + 7.4)}Z`);
        const fl = Math.abs(a.flip) < 0.15 ? 0.15 * Math.sign(a.flip || 1) : a.flip, nodes = scarfRope(t).map((w) => [40 + (w[0] - a.x) / (fl * s), 120 + (w[1] - a.y) / s]);
        const nrm = nodes.map((q, i) => { const A = nodes[Math.max(0, i - 1)], B = nodes[Math.min(nodes.length - 1, i + 1)], dx = B[0] - A[0], dy = B[1] - A[1], l = Math.hypot(dx, dy) || 1; return [-dy / l, dx / l]; });
        const left = nodes.map((q, i) => [q[0] + nrm[i][0] * (1.5 - i * 0.12), q[1] + nrm[i][1] * (1.5 - i * 0.12)]), right = nodes.map((q, i) => [q[0] - nrm[i][0] * (1.5 - i * 0.12), q[1] - nrm[i][1] * (1.5 - i * 0.12)]);
        tailNode.setAttribute("d", "M" + left.map(pt).join("L") + "L" + right.reverse().map(pt).join("L") + "Z");
      }
      // arms: the far arm sits behind the body, the near one in front
      farArm.draw([p.shF, p.far.e, p.far.h], [0.2, 0.5]);
      near.draw([p.shN, p.nr.e, p.nr.h], [0.2, 0.4]);
      // props
      const hand = p.hand;
      if (prop === "briefcase" || prop === "bag") {
        const ca = swing(t), ch = hand;
        pg.setAttribute("transform", `rotate(${f2(ca * 57.3)} ${pt(ch)})`);
        P.handle.setAttribute("d", `M${f2(ch[0] - 2.4)} ${f2(ch[1] + 2.4)}Q${pt(ch)} ${f2(ch[0] + 2.4)} ${f2(ch[1] + 2.4)}`);
        if (prop === "briefcase") P.body.setAttribute("d", `M${f2(ch[0] - 8)} ${f2(ch[1] + 2.4)}L${f2(ch[0] + 8)} ${f2(ch[1] + 2.4)}L${f2(ch[0] + 8)} ${f2(ch[1] + 13)}L${f2(ch[0] - 8)} ${f2(ch[1] + 13)}Z`);
        else { P.body.setAttribute("d", `M${f2(ch[0] - 6)} ${f2(ch[1] + 2.4)}L${f2(ch[0] + 6)} ${f2(ch[1] + 2.4)}L${f2(ch[0] + 7.4)} ${f2(ch[1] + 15)}L${f2(ch[0] - 7.4)} ${f2(ch[1] + 15)}Z`); P.loaf.setAttribute("d", `M${f2(ch[0] - 1)} ${f2(ch[1] + 3)}L${f2(ch[0] + 2.4)} ${f2(ch[1] - 8)}L${f2(ch[0] + 4.6)} ${f2(ch[1] - 7.6)}L${f2(ch[0] + 3)} ${f2(ch[1] + 3)}Z`); }
      } else if (prop === "umbrella") {
        const ang = umbTilt(t) + 0.12, hnd = hand;
        pg.setAttribute("transform", `rotate(${f2(ang * 57.3)} ${pt(hnd)})`);
        P.shaft.setAttribute("d", `M${f2(hnd[0])} ${f2(hnd[1] + 3)}L${f2(hnd[0])} ${f2(hnd[1] - 38)}`);
        const ty = hnd[1] - 38;
        P.dome.setAttribute("d", `M${f2(hnd[0] - 21)} ${f2(ty + 8)}Q${f2(hnd[0] - 20)} ${f2(ty - 12)} ${f2(hnd[0])} ${f2(ty - 12)}Q${f2(hnd[0] + 20)} ${f2(ty - 12)} ${f2(hnd[0] + 21)} ${f2(ty + 8)}Q${f2(hnd[0] + 14)} ${f2(ty + 4)} ${f2(hnd[0] + 7)} ${f2(ty + 8)}Q${f2(hnd[0])} ${f2(ty + 4)} ${f2(hnd[0] - 7)} ${f2(ty + 8)}Q${f2(hnd[0] - 14)} ${f2(ty + 4)} ${f2(hnd[0] - 21)} ${f2(ty + 8)}Z`);
        P.ribs.setAttribute("d", `M${f2(hnd[0])} ${f2(ty - 12)}L${f2(hnd[0] - 12)} ${f2(ty + 5)}M${f2(hnd[0])} ${f2(ty - 12)}L${f2(hnd[0] + 12)} ${f2(ty + 5)}M${f2(hnd[0])} ${f2(ty - 12)}L${f2(hnd[0])} ${f2(ty + 4)}`);
      } else if (prop === "lantern") {
        const ca = swing(t) * 1.4, ch = hand;
        pg.setAttribute("transform", `rotate(${f2(ca * 57.3)} ${pt(ch)})`);
        P.cord.setAttribute("d", `M${pt(ch)}L${f2(ch[0])} ${f2(ch[1] + 7)}`);
        P.box.setAttribute("d", `M${f2(ch[0] - 4)} ${f2(ch[1] + 7)}L${f2(ch[0] + 4)} ${f2(ch[1] + 7)}L${f2(ch[0] + 5)} ${f2(ch[1] + 16)}L${f2(ch[0] - 5)} ${f2(ch[1] + 16)}Z`);
        P.ribs.setAttribute("d", `M${f2(ch[0] - 4.6)} ${f2(ch[1] + 10)}H${f2(ch[0] + 4.6)}M${f2(ch[0] - 4.8)} ${f2(ch[1] + 13)}H${f2(ch[0] + 4.8)}`);
        const gp = toWorld(t, [ch[0] + Math.sin(ca) * 10 * 0, ch[1] + 12]); P.glow.setAttribute("cx", f2(gp[0])); P.glow.setAttribute("cy", f2(gp[1]));
      } else if (prop === "backpack") {
        P.pack.setAttribute("d", `M${f2(p.sh[0] - 11)} ${f2(p.sh[1] + 1)}Q${f2(p.sh[0] - 14)} ${f2(p.sh[1] + 12)} ${f2(p.sh[0] - 11)} ${f2(p.sh[1] + 24)}L${f2(p.sh[0] - 3)} ${f2(p.sh[1] + 23)}L${f2(p.sh[0] - 2)} ${f2(p.sh[1] + 2)}Z`);
        P.strap.setAttribute("d", `M${f2(p.sh[0] + 0.4)} ${f2(p.sh[1] + 1)}Q${f2(p.sh[0] + 3.4)} ${f2(p.sh[1] + 9)} ${f2(p.sh[0] - 2.4)} ${f2(p.sh[1] + 20)}`);
      } else if (prop === "balloon") {
        const nodes = balloonRope(t), fl = Math.abs(a.flip) < 0.15 ? 0.15 : a.flip, last = nodes[nodes.length - 1], prev = nodes[nodes.length - 2];
        const dx = last[0] - prev[0], dy = last[1] - prev[1], l = Math.hypot(dx, dy) || 1, cx = last[0] + (dx / l) * 8.5 * s, cy = last[1] + (dy / l) * 8.5 * s, loc = (w) => [40 + (w[0] - a.x) / (fl * s), 120 + (w[1] - a.y) / s], c = loc([cx, cy]), r = 7.2;
        P.string.setAttribute("d", "M" + nodes.map((w) => pt(loc(w))).join("L"));
        P.ball.setAttribute("d", `M${f2(c[0])} ${f2(c[1] + r * 1.18)}C${f2(c[0] - r * 1.3)} ${f2(c[1] + r * 0.6)} ${f2(c[0] - r * 1.1)} ${f2(c[1] - r * 1.2)} ${f2(c[0])} ${f2(c[1] - r * 1.2)}C${f2(c[0] + r * 1.1)} ${f2(c[1] - r * 1.2)} ${f2(c[0] + r * 1.3)} ${f2(c[1] + r * 0.6)} ${f2(c[0])} ${f2(c[1] + r * 1.18)}Z`);
        P.shine.setAttribute("d", `M${f2(c[0] - r * 0.55)} ${f2(c[1] - r * 0.1)}Q${f2(c[0] - r * 0.5)} ${f2(c[1] - r * 0.7)} ${f2(c[0] - r * 0.1)} ${f2(c[1] - r * 0.85)}`);
        for (const n of [P.string, P.ball, P.shine]) { n.setAttribute("transform", `translate(${f2(a.x)} ${f2(a.y)}) scale(${f2(fl * s)} ${f2(s)}) translate(-40 -120) scale(1 1)`); n.setAttribute("transform", ""); }
      }
    };
    S.frame(draw);
    // the balloon lives outside the flipped figure group: its nodes are written in the figure's local space, so give them the same transform
    if (prop === "balloon") { const base = draw; S.cbs[S.cbs.length - 1] = (t) => { base(t); const a = m.at(t), tr = g.getAttribute("transform"); for (const n of [P.string, P.ball, P.shine]) n.setAttribute("transform", tr); }; }
    // when a prop is dropped later or removed: not needed here; props are part of the character
    return fig;
  };

  /* ------------------------------------------------------------------ scenery (every builder: static ink drawn once, per-frame closed forms for what moves) */
  const wk = (S, k) => (t) => S.wind(t) * k;
  const rgbm = (c, hex, k) => rgb(mix(c, toRGB(hex), k));   // a palette array pushed toward a warm hex by k
  const WARM = "#f6c25b";
  /** Lights out late at night: `off` is a tau (1.0 midnight .. 1.2 just before dawn); lamps come on at their own threshold th on P.lamp. */
  LA.lit = (P, th = 0.5, off) => smooth(th - 0.04, th + 0.04, P.lamp) * (off == null ? 1 : 1 - smooth(off, off + 0.012, ((P.tau - 0.5) % 1 + 1) % 1 + 0.5));
  /** A tree: LA.tree(S, x, ground, {h, kind: round|pine|willow, seed, layer}). Sways with the wind (a pendulum per tree, so no two move alike). */
  LA.tree = (S, x, y, o = {}) => {
    const PEN = S.pw, h = o.h ?? 60 * S.u, R = FX.rand(o.seed ?? Math.round(x * 3 + 1)), kind = o.kind || "round", g = el("g", {}, S.layer(o.layer || "back")), kd = o.trunk ?? h * 0.07;
    const sway = LA.pendulum((t) => S.wind(t) * 0.0016 + 0.0009 * Math.sin(t * 1.3 + x), { k: 5 + R() * 2, d: 0.7 });
    const tk = el("g", {}, g), a = pen(tk), b = pen(tk), th = h * (kind === "pine" ? 0.25 : 0.5);
    a.setAttribute("d", `M${f2(x - kd)} ${y}Q${f2(x - kd * 0.5)} ${f2(y - th * 0.5)} ${f2(x - kd * 0.3)} ${f2(y - th)}`); b.setAttribute("d", `M${f2(x + kd)} ${y}Q${f2(x + kd * 0.5)} ${f2(y - th * 0.5)} ${f2(x + kd * 0.3)} ${f2(y - th)}`);
    const cr = el("g", {}, g), cy = y - th - h * 0.3;
    if (kind === "pine") {
      for (let i = 0; i < 3; i++) { const k = i / 3, w = h * (0.3 - k * 0.07), yy = y - th * (0.8) - k * h * 0.28, n = shape(cr, PEN * 0.9); n.setAttribute("d", LA.curvePath([[x - w, yy], [x - w * 0.4, yy - h * 0.1], [x, yy - h * 0.3], [x + w * 0.4, yy - h * 0.1], [x + w, yy], [x + w * 0.3, yy + 1.6], [x - w * 0.3, yy + 1.6]], { closed: true, amp: 0.4, seed: i + 1, tension: 9 })); }
    } else {
      const rx = h * 0.27 * (o.wide ?? 1), ry = h * 0.26, pts = [], n = 11;
      for (let i = 0; i < n; i++) { const an = (i / n) * 6.283, k = 1 + (R() - 0.5) * 0.26 + (i % 2 ? 0.1 : -0.04); pts.push([x + Math.cos(an) * rx * k, cy + Math.sin(an) * ry * k]); }
      const c = shape(cr, PEN * 0.9); c.setAttribute("d", LA.curvePath(pts, { closed: true, amp: 0, tension: 5 }));
      const lv = pen(cr, PEN * 0.45); let d = "";   // a few leaf arcs, the density of a quick pen
      for (let i = 0; i < 9; i++) { const lx = x + (R() - 0.5) * rx * 1.4, ly = cy + (R() - 0.5) * ry * 1.3; d += `M${f2(lx)} ${f2(ly)}q${f2(1.6)} ${f2(-1.8)} ${f2(3.2)} 0`; }
      lv.setAttribute("d", d);
      if (kind === "willow") for (let i = 0; i < 7; i++) {
        const sx = x - rx * 0.9 + (i / 6) * rx * 1.8, sy = cy + ry * 0.55, len = h * (0.34 + R() * 0.16), s2 = pen(cr, PEN * 0.5), ph = R() * 6.28, dd = LA.pendulum((t) => S.wind(t) * 0.01 + 0.004 * Math.sin(t * 0.9 + ph), { k: 3, d: 0.5 });
        S.frame((t) => { const bx = dd(t) * len * 18; s2.setAttribute("d", `M${f2(sx)} ${f2(sy)}Q${f2(sx + bx * 0.3)} ${f2(sy + len * 0.5)} ${f2(sx + bx)} ${f2(sy + len)}`); });
      }
    }
    S.frame((t) => { g.setAttribute("transform", `rotate(${f2(sway(t) * 57.3)} ${f2(x)} ${f2(y)})`); });
    return g;
  };
  /** A street lamp: post, lantern, a warm glow that comes on with the dusk. */
  LA.lamp = (S, x, y, o = {}) => {
    const PEN = S.pw / S.u, h = o.h ?? 52, g = el("g", { transform: `translate(${x} ${y}) scale(${S.u}) translate(${-x} ${-y})` }, S.layer(o.layer || "back")), p = pen(g, PEN), arm = pen(g, PEN), box = paint(g, "#f2d98c", PEN * 0.8), th = o.th ?? 0.4;
    p.setAttribute("d", `M${x} ${y}L${x} ${y - h}`); arm.setAttribute("d", `M${x} ${y - h}q0 -4 5 -4`);
    box.setAttribute("d", `M${x + 2.6} ${y - h - 4}L${x + 7.4} ${y - h - 4}L${x + 6.6} ${y - h + 2.5}L${x + 3.4} ${y - h + 2.5}Z`);
    const base = shape(g, PEN * 0.8); base.setAttribute("d", `M${x - 2.4} ${y}L${x - 1.4} ${y - 5}L${x + 1.4} ${y - 5}L${x + 2.4} ${y}Z`);
    S.frame(() => { const k = LA.lit(S.P, th); box.style.fill = rgbm(S.P.paper, WARM, k * 0.9 + 0.08); });
    S.glow(x + 5 * S.u, y - (h + 1) * S.u, h * 0.8 * S.u, { on: (P) => LA.lit(P, th), flicker: 0.06 });
    return g;
  };
  /** A building seen straight on: LA.building(S, x, ground, w, h, {roof: flat|gable|tiles, cols, rows, door, sign, accent, seed, chimney}).
      Doors and windows are sized for the stage's figure scale (S.u), so a person fits the door. Windows light up one by one at dusk
      (each its own threshold) and some go dark again after midnight. */
  LA.building = (S, x, y, w, h, o = {}) => {
    const PEN = S.pw, u = S.u, R = FX.rand(o.seed ?? Math.round(x * 7 + w)), g = el("g", {}, S.layer(o.layer || "back")), top = y - h, roof = o.roof || "gable", wins = [];
    let rh = 0;
    if (roof === "gable" || roof === "tiles") rh = Math.min(h * 0.3, w * 0.32);
    if (o.chimney) { const c = shape(g, PEN), cx = x + w * 0.7; c.setAttribute("d", `M${f2(cx)} ${f2(top - rh * 0.3)}L${f2(cx)} ${f2(top - rh * 0.95 - 8 * u)}L${f2(cx + 6 * u)} ${f2(top - rh * 0.95 - 8 * u)}L${f2(cx + 6 * u)} ${f2(top - rh * 0.3)}Z`); g.chimney = [cx + 3 * u, top - rh * 0.95 - 8 * u]; }
    const body = LA.rect(g, x, top, w, h, { seed: o.seed ?? 3, jitter: 0.25 * u, w: PEN });
    if (o.accent) S.tint(body, o.accent);
    if (rh) {
      const rp = shape(g, PEN), e = 2.4 * u; rp.setAttribute("d", `M${f2(x - e)} ${f2(top + 0.4)}L${f2(x + w / 2)} ${f2(top - rh)}L${f2(x + w + e)} ${f2(top + 0.4)}Z`);
      const ln = pen(g, PEN * 0.45); let d = ""; const n = Math.max(3, Math.round(w / ((roof === "tiles" ? 4 : 8) * u)));
      for (let i = 1; i < n; i++) { const k = i / n; d += roof === "tiles" ? `M${f2(lerp(x, x + w / 2, k))} ${f2(lerp(top, top - rh, k))}L${f2(lerp(x - e, x + w + e, k))} ${f2(top + 0.2)}` : `M${f2(x + w * k)} ${f2(top + 0.2)}L${f2(x + w * k)} ${f2(top + 0.2 - rh * (1 - Math.abs(2 * k - 1)))}`; }
      ln.setAttribute("d", d);
    } else { const ps = pen(g, PEN * 0.8); ps.setAttribute("d", `M${f2(x - 1.6 * u)} ${f2(top - 2.4 * u)}L${f2(x + w + 1.6 * u)} ${f2(top - 2.4 * u)}`); }
    const cols = o.cols ?? Math.max(1, Math.round(w / (17 * u))), ww = Math.min(10 * u, (w / cols) * 0.5), wh = ww * 1.4, floor = 24 * u, rows = o.rows ?? Math.max(1, Math.floor((h - 52 * u) / floor + 0.5));
    for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
      const cx = x + (w / cols) * (c + 0.5), cy = top + 14 * u + wh / 2 + r * floor, th = 0.3 + R() * 0.45, off = R() < 0.55 ? 1.02 + R() * 0.22 : null;
      if (cy + wh / 2 > y - 52 * u) continue;   // keep the ground floor for the door
      const pane = shape(g, PEN * 0.8); pane.setAttribute("d", `M${f2(cx - ww / 2)} ${f2(cy - wh / 2)}h${f2(ww)}v${f2(wh)}h${f2(-ww)}Z`);
      const bars = pen(g, PEN * 0.45); bars.setAttribute("d", `M${f2(cx)} ${f2(cy - wh / 2)}v${f2(wh)}M${f2(cx - ww / 2)} ${f2(cy)}h${f2(ww)}`);
      const sl = pen(g, PEN * 0.7); sl.setAttribute("d", `M${f2(cx - ww / 2 - 1.2 * u)} ${f2(cy + wh / 2 + 0.8 * u)}h${f2(ww + 2.4 * u)}`);
      wins.push({ cx, cy, th, off, pane }); S.glow(cx, cy, 9 * u, { on: (P) => LA.lit(P, th, off) * 0.85, phase: cx });
    }
    if (o.door !== false) {
      const dw = 11 * u, dh = 50 * u, dx = x + (w - dw) * (o.doorAt ?? 0.5), door = paint(g, o.doorColour || "#8a5a3c", PEN * 0.9); S.tint(door, o.doorColour || "#8a5a3c", 0.5);
      door.setAttribute("d", `M${f2(dx)} ${y}L${f2(dx)} ${f2(y - dh + 4 * u)}Q${f2(dx + dw / 2)} ${f2(y - dh - 1 * u)} ${f2(dx + dw)} ${f2(y - dh + 4 * u)}L${f2(dx + dw)} ${y}Z`);
      const kn = blot(g); kn.setAttribute("d", `M${f2(dx + dw * 0.78)} ${f2(y - dh * 0.45)}a${f2(0.9 * u)} ${f2(0.9 * u)} 0 1 0 0.01 0Z`);
      if (o.sign) LA.label(S, dx + dw / 2, y - dh - 5 * u, o.sign, { size: 4.2 * u, anchor: "middle", layer: o.layer || "back" });
    }
    S.frame(() => { for (const wn of wins) wn.pane.style.fill = rgbm(S.P.paper, WARM, LA.lit(S.P, wn.th, wn.off) * 0.85); });
    g.wins = wins; return g;
  };
  /** A row of far buildings in thin diluted ink: LA.skyline(S, {y, n, minH, maxH, seed}). Their windows are dots. */
  LA.skyline = (S, o = {}) => {
    const PEN = S.pw, u = S.u, R = FX.rand(o.seed ?? 11), g = el("g", {}, S.layer(o.layer || "far")), y = o.y ?? S.gy - 2 * u; let x = -4;
    g.setAttribute("opacity", o.opacity ?? 0.6);
    for (let i = 0; i < 40 && x < S.w + 4; i++) {
      const w = (12 + R() * 14) * u, h = (o.minH ?? 22 * u) + R() * ((o.maxH ?? 70 * u) - (o.minH ?? 22 * u)); LA.rect(g, x, y - h, w, h, { seed: i + 5, w: PEN * 0.7, jitter: 0.2 * u });
      const win = pen(g, PEN * 0.5); let d = ""; for (let yy = y - h + 5 * u; yy < y - 5 * u; yy += 6 * u) for (let xx = x + 3 * u; xx < x + w - 2 * u; xx += 4.4 * u) if (R() < 0.55) d += `M${f2(xx)} ${f2(yy)}h${f2(1.4 * u)}`;
      win.setAttribute("d", d); x += w + R() * 3 * u;
    }
    return g;
  };
  /** The standard street: ground line, kerb, a row of buildings (with smoke from a chimney), trees and lamps. S.gy is the ground; o: {seed, trees, lamps, smoke, accents[]}. -> {buildings, lamps} */
  LA.street = (S, o = {}) => {
    const PEN = S.pw, u = S.u, R = FX.rand(o.seed ?? 4), out = { buildings: [], lamps: [] }, acc = o.accents || ["#d9cdb8", "#e8d9c4", "#cfd6cf", "#e6d0c8"], bw = 46 * u;
    LA.line(S.layer("back"), [-4, S.gy], [S.w + 4, S.gy], { w: PEN, bow: 0.006 });
    const kerb = pen(S.layer("back"), PEN * 0.5); kerb.setAttribute("d", `M-4 ${f2(S.gy + 3.4 * u)}L${S.w + 4} ${f2(S.gy + 3.4 * u)}`);
    let x = -8 * u, i = 0;
    while (x < S.w) {
      const w = bw * (0.85 + R() * 0.4), h = (o.minH ?? 66 * u) + R() * ((o.maxH ?? 104 * u) - (o.minH ?? 66 * u));
      const b = LA.building(S, x, S.gy, w, h, { roof: ["gable", "flat", "tiles"][i % 3], accent: acc[i % acc.length], seed: 20 + i, chimney: i % 3 === 0, doorAt: 0.2 + R() * 0.6 });
      out.buildings.push(b); if (b.chimney && o.smoke !== false && !out.smoked) { LA.smoke(S, b.chimney[0], b.chimney[1], {}); out.smoked = true; }
      x += w + (1.2 + R() * 3) * u; i++;
    }
    const nt = Math.max(1, Math.round(S.w / (70 * u)));
    if (o.trees !== false) for (let k = 0; k < nt; k++) LA.tree(S, S.w * ((k + 0.5) / nt) + (R() - 0.5) * 12 * u, S.gy + 5 * u, { h: (46 + R() * 14) * u, seed: 30 + k, layer: "mid" });
    const nl = Math.max(1, Math.round(S.w / (90 * u)));
    if (o.lamps !== false) for (let k = 0; k < nl; k++) out.lamps.push(LA.lamp(S, S.w * ((k + 0.25) / nl) + 8 * u, S.gy + 3 * u, { th: 0.34 + 0.06 * k }));
    return out;
  };
  /** Birds: a loose flock crossing and looping (closed form: x = start + speed * t wrapped, so any t is independent). {n, y, speed, seed, scale, dir, flap} */
  LA.birds = (S, o = {}) => {
    const R = FX.rand(o.seed ?? 9), n = o.n ?? 5, g = el("g", {}, S.layer(o.layer || "far")), v = (o.speed ?? 14) * (o.dir || 1), sc = (o.scale ?? 1) * S.k * 1.3, span = S.w + 80, bs = [];
    const x0 = o.x ?? R() * S.w, y0 = o.y ?? S.h * 0.22;
    for (let i = 0; i < n; i++) bs.push({ p: pen(g, S.pw * 0.75), dx: -Math.abs(i - (n - 1) / 2) * (6 + R() * 3) * sc * (o.dir || 1), dy: Math.abs(i - (n - 1) / 2) * 3.4 * sc * (i % 2 ? 1 : 0.7) + (R() - 0.5) * 3, ph: R() * 6.28, fr: 3.4 + R() * 1.2 });
    S.frame((t) => {
      for (const b of bs) {
        const x = ((((x0 + b.dx + v * t) % span) + span) % span) - 40, y = y0 + b.dy + 2.6 * Math.sin(t * 0.7 + b.ph), f = Math.sin(t * b.fr * 6.283 + b.ph), w = 3.6 * sc;
        b.p.setAttribute("d", `M${f2(x - w)} ${f2(y - 1.2 * f * sc)}Q${f2(x - w * 0.45)} ${f2(y - 2.8 * sc - 1.6 * f * sc)} ${f2(x)} ${f2(y)}Q${f2(x + w * 0.45)} ${f2(y - 2.8 * sc - 1.6 * f * sc)} ${f2(x + w)} ${f2(y - 1.2 * f * sc)}`);
      }
      g.setAttribute("opacity", f2(1 - S.P.night * 0.9));   // they roost at dusk
    });
    return g;
  };
  /** A seated cat (closed paper shape, a flicking tail, blinks, breathes): LA.cat(S, x, ground, {dir, patch, scale, layer}). Closed forms in t. */
  LA.cat = (S, x, y, o = {}) => {
    const s = (o.scale ?? 1) * S.k * 0.65, PEN = S.pw / s, g = el("g", {}, S.layer(o.layer || "mid")), dir = o.dir || 1, ph = x * 0.13;
    g.__y = y;
    const body = shape(g, PEN * 0.9), head = el("g", {}, g), hd = shape(head, PEN * 0.9), ears = shape(head, PEN * 0.8), eyes = pen(head, PEN * 0.6), nose = blot(head), tail = pen(g, PEN * 1.5);
    body.setAttribute("d", LA.curvePath([[4, 0], [5, -6], [3.4, -11], [1.4, -14], [-3, -14], [-7, -10], [-9, -4], [-8, 0]], { closed: true, amp: 0, tension: 5 }));
    hd.setAttribute("d", LA.curvePath([[0.2, -17.6], [1.6, -20.4], [4.4, -21], [7, -19.4], [7.2, -17], [5.6, -14.8], [2.4, -14.8]], { closed: true, amp: 0, tension: 5 }));
    ears.setAttribute("d", "M1.4 -20L1.2 -24.4L3.8 -21Z M5.2 -21L7.4 -24.6L7.6 -19.6Z"); nose.setAttribute("d", "M7 -17.6l1.2 0.3l-0.8 0.9Z");
    if (o.patch) { const p = blot(g); p.setAttribute("d", "M-6 -10Q-4 -13 -1 -12Q-3 -8 -6.4 -7Z"); S.tint(p, o.patch); p.setAttribute("fill", o.patch); }
    S.frame((t) => {
      const u = ((t / 5.7 + ph) % 1 + 1) % 1, burst = smooth(0.55, 0.62, u) * (1 - smooth(0.88, 0.95, u)), fl = Math.sin(t * 9 + ph) * burst, slow = Math.sin(t * 0.8 + ph) * 0.6;
      tail.setAttribute("d", `M-8 -1.2Q${f2(-14 + slow)} ${f2(-0.4)} ${f2(-15 + slow + fl * 2)} ${f2(-6.6 - burst * 1.4)}Q${f2(-15.4 + slow + fl * 3.6)} ${f2(-10 - burst * 2)} ${f2(-12.4 + fl * 4.4)} ${f2(-11.4 - burst * 2.4)}`);
      const bl = ((t / 4.1 + ph * 3) % 1 + 1) % 1, closed = bl > 0.94 ? 1 : 0, eh = 0.8 * (1 - closed);
      eyes.setAttribute("d", closed ? "M4.4 -17.8h1M6.2 -17.8h1" : `M4.4 ${f2(-18.2)}q0.5 ${f2(-1 * eh)} 1 0M6.2 ${f2(-18.2)}q0.5 ${f2(-1 * eh)} 1 0`);
      const br = Math.sin(t * 1.7 + ph) * 0.25; head.setAttribute("transform", `translate(0 ${f2(br * 0.4)}) rotate(${f2(Math.sin(t * 0.5 + ph) * 2)} 3 -14.8)`);
      g.setAttribute("transform", `translate(${f2(x)} ${f2(y)}) scale(${f2(dir * s)} ${f2(s * (1 + br * 0.01))})`);
    });
    return g;
  };
  /** Washing on a line between two points; every piece hangs from a pendulum pushed by the wind. {items: [colour...]} */
  LA.laundry = (S, a, b, o = {}) => {
    const PEN = S.pw, g = el("g", {}, S.layer(o.layer || "mid")), sag = (o.sag ?? 3) * S.k, line = pen(g, PEN * 0.6), items = o.items || ["#c9553f", "#e8dfc9", "#4a6a8a", "#e8dfc9", "#d4a548"];
    line.setAttribute("d", `M${pt(a)}Q${f2((a[0] + b[0]) / 2)} ${f2((a[1] + b[1]) / 2 + sag * 2)} ${pt(b)}`);
    items.forEach((c, i) => {
      const k = (i + 0.7) / (items.length + 0.4), x = lerp(a[0], b[0], k), y = lerp(a[1], b[1], k) + sag * 2 * 2 * k * (1 - k), w = (o.w ?? 7) * S.u * 0.7, h = (o.h ?? 11) * S.u * 0.7 * (i % 2 ? 0.8 : 1);
      const cl = paint(g, c, PEN * 0.7); S.tint(cl, c, 0.5); const ph = i * 1.7, pdl = LA.pendulum((t) => S.wind(t) * 0.12 + 0.02 * Math.sin(t * 1.9 + ph), { k: 14, d: 0.9 });
      S.frame((t) => { const an = pdl(t) * 57.3, wave = pdl(t) * 6; cl.setAttribute("d", `M${f2(-w / 2)} 0L${f2(w / 2)} 0L${f2(w / 2 + wave)} ${f2(h)}Q${f2(wave)} ${f2(h + 1)} ${f2(-w / 2 + wave)} ${f2(h)}Z`); cl.setAttribute("transform", `translate(${f2(x)} ${f2(y)}) rotate(${f2(an)})`); });
    });
    return g;
  };
  /** Smoke from a chimney: puffs rise on a fixed loop and bend with the wind (closed form). */
  LA.smoke = (S, x, y, o = {}) => {
    const PEN = S.pw, k = S.u * 0.7, g = el("g", {}, S.layer(o.layer || "back")), n = o.n ?? 5, per = o.period ?? 5, ps = [];
    for (let i = 0; i < n; i++) ps.push(LA.oval(g, 0, 0, 2.4, 2.4, { fill: false, w: PEN * 0.6, seed: i + 2 }));
    S.frame((t) => ps.forEach((p, i) => { const u = (((t / per + i / n) % 1) + 1) % 1, wd = S.wind(t); p.setAttribute("transform", `translate(${f2(x + (u * u * 16 * (0.4 + wd * 0.9) + Math.sin(u * 6 + i) * 1.4) * k)} ${f2(y - u * 26 * k)}) scale(${f2(k * (0.5 + u * 1.7))})`); p.setAttribute("opacity", f2((1 - u) * smooth(0, 0.12, u) * (1 - S.P.night * 0.4))); }));
    return g;
  };
  /** A room: floor line, skirting, a window that shows the sky, curtains on pendulums, a framed picture, a table with a lamp. o: {x0, x1, floor} -> {win: [x, y, w, h], table: [x, y]} */
  LA.room = (S, o = {}) => {
    const PEN = S.pw, kk = S.k, g = el("g", {}, S.layer(o.layer || "back")), fy = o.floor ?? S.gy, wx = o.winX ?? S.w * 0.3, ww = o.winW ?? Math.min(S.w * 0.32, 70), wh = ww * 1.3, wy = fy - wh - (o.winLift ?? 34);
    LA.line(g, [-4, fy], [S.w + 4, fy], { w: PEN }); const sk = pen(g, PEN * 0.5); sk.setAttribute("d", `M-4 ${fy - 7}L${S.w + 4} ${fy - 7}`);
    const pane = shape(g, PEN), fr = LA.rect(g, wx, wy, ww, wh, { fill: false, w: PEN * 1.2, seed: 8 }), bars = pen(g, PEN * 0.7);
    pane.setAttribute("d", `M${wx} ${wy}h${ww}v${wh}h${-ww}Z`); bars.setAttribute("d", `M${f2(wx + ww / 2)} ${wy}v${wh}M${wx} ${f2(wy + wh * 0.4)}h${ww}`);
    const sill = pen(g, PEN * 1.1); sill.setAttribute("d", `M${f2(wx - 3)} ${f2(wy + wh + 1.6)}h${f2(ww + 6)}`);
    for (const sd of [-1, 1]) {
      const c = paint(g, o.curtain || "#b3412d", PEN * 0.8); S.tint(c, o.curtain || "#b3412d", 0.5);
      const pd = LA.pendulum((t) => S.wind(t) * 0.05 * sd, { k: 6, d: 0.8 }), cx = sd < 0 ? wx - 1 : wx + ww + 1;
      S.frame((t) => { const b = pd(t) * 14, w = ww * 0.28; c.setAttribute("d", `M${f2(cx)} ${f2(wy - 3)}L${f2(cx + sd * w)} ${f2(wy - 3)}Q${f2(cx + sd * w * 0.6 + b)} ${f2(wy + wh * 0.5)} ${f2(cx + sd * w * 0.9 + b * 1.5)} ${f2(wy + wh + 7)}L${f2(cx + sd * w * 0.1 + b * 1.4)} ${f2(wy + wh + 7)}Q${f2(cx + b * 0.4)} ${f2(wy + wh * 0.5)} ${f2(cx)} ${f2(wy - 3)}Z`); });
    }
    const tx = o.tableX ?? S.w * 0.74, tw = o.tableW ?? 44, ty = fy - 30, PEN0 = PEN, tg = el("g", { transform: `translate(${tx} ${fy}) scale(${kk}) translate(${-tx} ${-fy})` }, g);
    { const PEN = PEN0 / kk, g = tg;
    const top = shape(g, PEN), l1 = pen(g, PEN), l2 = pen(g, PEN); top.setAttribute("d", `M${tx - tw / 2} ${ty}h${tw}v3h${-tw}Z`); l1.setAttribute("d", `M${tx - tw / 2 + 3} ${ty + 3}V${fy}`); l2.setAttribute("d", `M${tx + tw / 2 - 3} ${ty + 3}V${fy}`);
    const lb = paint(g, "#f2d98c", PEN * 0.8), st = pen(g, PEN); st.setAttribute("d", `M${tx - tw * 0.2} ${ty}v-10`); lb.setAttribute("d", `M${f2(tx - tw * 0.2 - 5)} ${ty - 9}L${f2(tx - tw * 0.2 - 2.4)} ${ty - 18}L${f2(tx - tw * 0.2 + 2.4)} ${ty - 18}L${f2(tx - tw * 0.2 + 5)} ${ty - 9}Z`);
    S.frame(() => { lb.style.fill = rgbm(S.P.paper, WARM, LA.lit(S.P, 0.45) * 0.9 + 0.1); }); }
    S.frame(() => { pane.style.fill = rgb(S.P.bottom); });
    S.glow(tx - tw * 0.2 * kk, fy - (fy - ty + 14) * kk, 34 * kk, { on: (P) => LA.lit(P, 0.45), flicker: 0.04 });
    const pic = LA.rect(g, S.w * 0.58, wy + 6, 26, 20, { seed: 2, w: PEN * 0.9 }), hl = pen(g, PEN * 0.6); hl.setAttribute("d", `M${f2(S.w * 0.58 + 3)} ${f2(wy + 22)}l6 -8l5 6l4 -4l5 6`);
    return { win: [wx, wy, ww, wh], table: [tx, ty], floor: fy };
  };
  /** A bench (a person sits on it with fig.sit): seat top is 22 units above the ground, centred on x. */
  LA.bench = (S, x, y, o = {}) => {
    const w = o.w ?? 34, g = el("g", { transform: `translate(${x} ${y}) scale(${S.k}) translate(${-x} ${-y})` }, S.layer(o.layer || "mid")), seat = shape(g, PEN), l1 = pen(g, PEN), l2 = pen(g, PEN), bk = pen(g, PEN);
    seat.setAttribute("d", `M${x - w / 2} ${y - 22}h${w}v2.6h${-w}Z`); l1.setAttribute("d", `M${x - w / 2 + 3} ${y - 19.4}V${y}`); l2.setAttribute("d", `M${x + w / 2 - 3} ${y - 19.4}V${y}`);
    if (o.back !== false) bk.setAttribute("d", `M${x - w / 2 + 1} ${y - 22}V${y - 36}M${x + w / 2 - 1} ${y - 22}V${y - 36}M${x - w / 2 + 1} ${y - 33}H${x + w / 2 - 1}M${x - w / 2 + 1} ${y - 29}H${x + w / 2 - 1}`);
    g.__y = y - 0.5; return g;
  };
  /** A cheerful gear (teeth + hub + spokes), centred on its own group origin; rotate the returned group. */
  LA.gear = (parent, R, teeth, o = {}) => {
    const g = el("g", {}, parent), th = o.tooth ?? R * 0.16, pts = [];
    for (let i = 0; i < teeth; i++) { const a = (i / teeth) * 6.2832, w = 6.2832 / teeth; for (const [k, r] of [[0.02, R - th * 0.3], [0.22, R + th * 0.55], [0.5, R + th * 0.55], [0.7, R - th * 0.3]]) { pts.push([Math.cos(a + k * w) * r, Math.sin(a + k * w) * r]); } }
    const body = shape(g, PEN); body.setAttribute("d", "M" + pts.map(pt).join("L") + "Z");
    const ring = LA.oval(g, 0, 0, R * 0.55, R * 0.55, { fill: false, w: PEN * 0.7, seed: 3 }), hub = LA.oval(g, 0, 0, R * 0.14, R * 0.14, { fill: "ink", seed: 4 }), sp = pen(g, PEN * 0.7); let d = "";
    for (let i = 0; i < (o.spokes ?? 5); i++) { const a = (i / (o.spokes ?? 5)) * 6.2832 + 0.3; d += `M${f2(Math.cos(a) * R * 0.14)} ${f2(Math.sin(a) * R * 0.14)}L${f2(Math.cos(a) * R * 0.55)} ${f2(Math.sin(a) * R * 0.55)}`; }
    sp.setAttribute("d", d); return g;
  };
  /** The bicycle's chain drive as an explanation: a chainring and a cog joined by a moving chain. LA.drivetrain(S, cx, cy, {R1, n1, R2, n2, rate (chainring rad/s), at})
      -> {ang1(t), ang2(t), ratio, g, p1, p2 (the centres), crank}. The smaller cog turns n1/n2 times faster: that is the whole idea of a gear. */
  LA.drivetrain = (S, cx, cy, o = {}) => {
    const R1 = o.R1 ?? 24, n1 = o.n1 ?? 24, R2 = o.R2 ?? 10, n2 = o.n2 ?? 10, d = o.d ?? R1 * 2.9, rate = o.rate ?? 2.2, at = o.at ?? 0, g = el("g", {}, S.layer(o.layer || "front"));
    const nx = (R1 - R2) / d, ny = Math.sqrt(1 - nx * nx), chain = el("path", { fill: "none", stroke: "currentColor", "stroke-width": PEN * 1.5, "stroke-linecap": "butt" }, g), inner = pen(g, PEN * 0.5);
    const T1 = [cx + R1 * nx, cy - R1 * ny], T2 = [cx + d + R2 * nx, cy - R2 * ny], B2 = [cx + d + R2 * nx, cy + R2 * ny], B1 = [cx + R1 * nx, cy + R1 * ny], dp = `M${pt(T1)}L${pt(T2)}A${R2} ${R2} 0 1 1 ${pt(B2)}L${pt(B1)}A${R1} ${R1} 0 1 1 ${pt(T1)}Z`;
    chain.setAttribute("d", dp); chain.removeAttribute("pathLength"); chain.setAttribute("stroke-dasharray", "1.5 1.2"); inner.setAttribute("d", dp); inner.setAttribute("stroke-dasharray", "0"); inner.setAttribute("opacity", 0);
    const gA = LA.gear(g, R1, n1, { spokes: 5 }), gB = LA.gear(g, R2, n2, { spokes: 4 });
    const crank = pen(g, PEN * 2), pedal = paint(g, "#555", PEN * 0.8); const sprocketLen = 2 * (Math.hypot(d, R1 - R2)) + R1 * (3.1416 + 2 * Math.asin(nx)) + R2 * (3.1416 - 2 * Math.asin(nx));
    const go = (t) => minJerk(clamp((t - at) / 1.2, 0, 1)), ang1 = (t) => (t < at ? 0 : rate * ((t - at) - 0.6 * (1 - go(t)) * 0 - 0)), ang2 = (t) => (ang1(t) * n1) / n2;
    S.frame((t) => {
      const a1 = ang1(t), a2 = ang2(t);
      gA.setAttribute("transform", `translate(${f2(cx)} ${f2(cy)}) rotate(${f2(a1 * 57.2958)})`); gB.setAttribute("transform", `translate(${f2(cx + d)} ${f2(cy)}) rotate(${f2(a2 * 57.2958)})`);
      chain.setAttribute("stroke-dashoffset", f2(-(a1 * R1) % 2.7));
      const px = cx + Math.cos(a1 + 0.5) * R1 * 0.95, py = cy + Math.sin(a1 + 0.5) * R1 * 0.95; crank.setAttribute("d", `M${f2(cx)} ${f2(cy)}L${f2(px)} ${f2(py)}`);
      pedal.setAttribute("d", `M${f2(px - 4)} ${f2(py - 1.4)}h8v2.8h-8Z`);
    });
    return { g, gears: [gA, gB], ang1, ang2, ratio: n1 / n2, p1: [cx, cy], p2: [cx + d, cy], R1, R2 };
  };
  /** The bicycle with a rider: LA.bike(S, fig, {colour, lamp}) turns the figure into a cyclist (pedals drive the feet, hands on the bars, wheels roll
      without slipping: angle = distance / radius) and adds fig.ride(at, to, {speed}) -> arrival time. */
  LA.bike = (S, fig, o = {}) => {
    const g = fig.g, bg = el("g", {}, g), r = 17, RW = [19, 103], FW = [61, 103], BB = [38, 105], SD = [34.5, 72], HT = [54, 78], BAR = [56.5, 68];
    g.insertBefore(bg, g.firstChild);
    const wheel = () => { const w = el("g", {}, bg), tire = pen(w, PEN), rim = pen(w, PEN * 0.5), sp = pen(w, PEN * 0.4), hub = blot(w); const arc = (R) => `M${-R} 0a${R} ${R} 0 1 0 ${2 * R} 0a${R} ${R} 0 1 0 ${-2 * R} 0`; tire.setAttribute("d", arc(r)); rim.setAttribute("d", arc(r - 2.4)); let d = ""; for (let i = 0; i < 6; i++) { const a = (i / 6) * 3.1416; d += `M${f2(Math.cos(a) * (r - 2.4))} ${f2(Math.sin(a) * (r - 2.4))}L${f2(-Math.cos(a) * (r - 2.4))} ${f2(-Math.sin(a) * (r - 2.4))}`; } sp.setAttribute("d", d); hub.setAttribute("d", "M-1.2 0a1.2 1.2 0 1 0 2.4 0a1.2 1.2 0 1 0 -2.4 0"); return w; };
    const wR = wheel(), wF = wheel(), fr = paint(bg, "none", PEN * 1.3), seat = blot(bg), bars = pen(bg, PEN * 1.1), fork = pen(bg, PEN * 1.1), chainring = pen(bg, PEN * 0.6), lamp = o.lamp ? paint(bg, "#f2d98c", PEN * 0.7) : null;
    fr.setAttribute("fill", "none"); fr.setAttribute("d", `M${pt(RW)}L${pt(BB)}L${pt(SD)}ZM${pt(BB)}L${f2(HT[0] - 1)} ${f2(HT[1] + 5)}L${pt(HT)}L${pt(SD)}`); fork.setAttribute("d", `M${pt(HT)}L${pt(FW)}`);
    if (o.colour) { fr.setAttribute("stroke", o.colour); } seat.setAttribute("d", `M${SD[0] - 5} ${SD[1] - 0.6}Q${SD[0]} ${SD[1] - 3.4} ${SD[0] + 4} ${SD[1] - 1.4}L${SD[0] + 3.6} ${SD[1] + 0.4}L${SD[0] - 5} ${SD[1] + 0.6}Z`);
    bars.setAttribute("d", `M${f2(HT[0] + 0.6)} ${f2(HT[1] - 1)}L${pt(BAR)}L${f2(BAR[0] + 4.2)} ${f2(BAR[1] + 1.2)}`); chainring.setAttribute("d", `M${f2(BB[0] - 5)} ${f2(BB[1])}a5 5 0 1 0 10 0a5 5 0 1 0 -10 0`);
    if (lamp) lamp.setAttribute("d", `M${f2(HT[0] + 3)} ${f2(HT[1] - 3)}h4v3h-4Z`);
    const crank = [pen(bg, PEN * 1.4), pen(bg, PEN * 1.4)], pedals = [blot(bg), blot(bg)];
    const rig = (t) => {
      const a = fig.mv.at(t), th = (a.dist / fig.s / r) * 0.42 * (a.go > 0.02 || a.dist > 0 ? 1 : 0), cr = 6.4, pd = [0, 1].map((i) => [BB[0] + Math.cos(th + i * Math.PI) * cr, BB[1] + Math.sin(th + i * Math.PI) * cr]);
      return { hip: [SD[0] + 1.6, SD[1] - 6 + 0.5 * Math.sin(th * 2)], ankles: pd.map((p) => [p[0] - 1.6, p[1] - 1.2]), pitch: [0, 0], lean: 11, bar: BAR, th, wheel: (a.dist / fig.s) / r, pd };
    };
    fig.rig = rig;
    S.frame((t) => {
      const q = rig(t), w = q.wheel * 57.2958;
      wR.setAttribute("transform", `translate(${pt(RW)}) rotate(${f2(w)})`); wF.setAttribute("transform", `translate(${pt(FW)}) rotate(${f2(w)})`);
      q.pd.forEach((p, i) => { crank[i].setAttribute("d", `M${pt(BB)}L${pt(p)}`); pedals[i].setAttribute("d", `M${f2(p[0] - 2.6)} ${f2(p[1] - 0.6)}h5.2v1.4h-5.2Z`); });
      if (lamp) lamp.style.fill = rgbm(S.P.paper, WARM, S.P.night);
    });
    if (o.lamp) { const gl = S.glow(0, 0, 30, { on: (P) => P.night }); S.frame((t) => { const a = fig.mv.at(t); gl.setAttribute("cx", f2(a.x + a.flip * fig.s * (HT[0] + 7 - 40))); gl.setAttribute("cy", f2(a.y + fig.s * (HT[1] - 1.5 - 120))); }); }
    fig.ride = (at, to, w = {}) => { const end = fig.mv.walk(at, to, { speed: (w.speed ?? 52) * fig.s, ramp: w.ramp ?? [0.8, 0.9] }); fig.mv.segs[fig.mv.segs.length - 1].kind = "walk"; return end; };
    return fig;
  };

  /* ------------------------------------------------------------------ annotation in the ink look */
  /** Hand lettering: LA.label(S, x, y, "text", {size, anchor: start|middle|end, layer, italic}) -> the <text>. Instrument Serif italic reads as pen lettering. */
  LA.label = (S, x, y, str, o = {}) => {
    const t = el("text", { x, y, "font-size": o.size ?? 6, "text-anchor": o.anchor || "start", fill: "currentColor", "font-family": o.font || "'Instrument Serif', Georgia, serif", "font-style": o.italic === false ? "normal" : "italic" }, S.layer(o.layer || "front"));
    t.textContent = str; if (o.rotate) t.setAttribute("transform", `rotate(${o.rotate} ${x} ${y})`); return t;
  };
  /** A curved hand-drawn arrow from a to b with an open arrowhead -> a group (LA.drawIn it for the pen-stroke reveal). */
  LA.arrow = (S, a, b, o = {}) => {
    const g = el("g", {}, S.layer(o.layer || "front")), R = FX.rand(o.seed ?? Math.round(a[0] + b[1])), l = pen(g, o.w ?? PEN * 0.9), hd = pen(g, o.w ?? PEN * 0.9);
    const dx = b[0] - a[0], dy = b[1] - a[1], len = Math.hypot(dx, dy) || 1, bend = (o.bend ?? 0.22) * len, m = [(a[0] + b[0]) / 2 - (dy / len) * bend, (a[1] + b[1]) / 2 + (dx / len) * bend];
    l.setAttribute("d", `M${pt(a)}Q${pt(m)} ${pt(b)}`);
    const an = Math.atan2(b[1] - m[1], b[0] - m[0]), hs = o.head ?? 3, p1 = [b[0] - Math.cos(an - 0.5) * hs, b[1] - Math.sin(an - 0.5) * hs], p2 = [b[0] - Math.cos(an + 0.5) * hs, b[1] - Math.sin(an + 0.5) * hs];
    hd.setAttribute("d", `M${pt(p1)}L${pt(b)}L${pt(p2)}`); return g;
  };
  /** A scribbled ring around something (to point at it): LA.circleAround(S, cx, cy, rx, ry) -> group. */
  LA.circleAround = (S, cx, cy, rx, ry, o = {}) => {
    const g = el("g", {}, S.layer(o.layer || "front")), p = pen(g, o.w ?? PEN * 1.1), R = FX.rand(o.seed ?? 6), pts = [];
    for (let i = 0; i <= 12; i++) { const a = -0.5 + (i / 12) * 6.9; pts.push([cx + Math.cos(a) * rx * (1 + i * 0.006) + (R() - 0.5) * 0.5, cy + Math.sin(a) * ry * (1 + i * 0.006) + (R() - 0.5) * 0.5]); }
    p.setAttribute("d", LA.curvePath(pts, { amp: 0, tension: 6 })); if (o.colour) p.setAttribute("stroke", o.colour); return g;
  };
  /** A hand-drawn bar chart that grows: LA.bars(S, x, y (baseline), w, h, [{label, v, colour}], {at, max, unit, stagger}) -> group. Bars are paper with hatching. */
  LA.bars = (S, x, y, w, h, data, o = {}) => {
    const g = el("g", {}, S.layer(o.layer || "front")), mx = o.max ?? Math.max(...data.map((d) => d.v)) * 1.1, n = data.length, bw = (w / n) * 0.62, R = FX.rand(o.seed ?? 5), at = o.at ?? 0;
    LA.line(g, [x - 3, y], [x + w + 3, y], { w: PEN }); LA.line(g, [x - 3, y], [x - 3, y - h - 4], { w: PEN });
    data.forEach((d, i) => {
      const bx = x + (w / n) * (i + 0.5) - bw / 2, j = [R() - 0.5, R() - 0.5, R() - 0.5], body = shape(g, PEN), hat = el("path", { fill: S.hatch, stroke: "none", opacity: 0.55 }, g), lab = LA.label(S, bx + bw / 2, y + 7.4, d.label, { size: o.size ?? 5.4, anchor: "middle", layer: o.layer || "front" }), val = LA.label(S, bx + bw / 2, y - 2, (d.text ?? d.v) + (o.unit || ""), { size: (o.size ?? 5.4) * 1.1, anchor: "middle", layer: o.layer || "front" });
      if (d.colour) { body.setAttribute("class", ""); body.setAttribute("fill", d.colour); S.tint(body, d.colour, 0.4); }
      S.frame((t) => { const p = minJerk(clamp((t - at - i * (o.stagger ?? 0.18)) / 0.9, 0, 1)), hh = (d.v / mx) * h * p, yy = y - hh;
        const dd = `M${f2(bx + j[0])} ${f2(y)}L${f2(bx + j[1] * 0.6)} ${f2(yy)}Q${f2(bx + bw / 2)} ${f2(yy - 0.8 + j[2])} ${f2(bx + bw + j[0])} ${f2(yy)}L${f2(bx + bw)} ${f2(y)}Z`;
        body.setAttribute("d", dd); hat.setAttribute("d", dd); body.style.visibility = hat.style.visibility = p > 0 ? "" : "hidden"; val.setAttribute("y", f2(yy - 2)); val.style.opacity = f2(smooth(0.8, 1, p)); lab.style.opacity = f2(smooth(0, 0.3, p)); });
    });
    return g;
  };
})();
