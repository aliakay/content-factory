/* FX 3D figures — real 3D characters built in code (three.js primitives, free render) for the 3D kit (fx3d.js).
   Loaded by FX.load3d() right after fx3d.js; registers k.figure / k.prop on every FX.stage3 stage (X.kit).

   fig = k.figure({build: "average", skin: "#e8b48a", hair: {style: "short", color: "#3a2a20"}, beard: "none", glasses: false,
                   top: {kind: "shirt", color: "accent"}, bottom: {kind: "trousers", color: "#2f3b52"}, shoes: "#f4f1ea",
                   finish: "auto"}, {x, z, size, y, facing})
     build   slim | average | heavy | child            hair.style  short | long | bun | bald | curly (+ buzz, ponytail, side)
     top     shirt | jacket | coat | dress | lab       bottom      trousers | shorts | skirt          beard  none | stubble | short | full
     finish  auto (follows the stage look: clay -> clay, studio -> glossy, paper -> lowpoly, blueprint / neon -> outlined)
             | matte | clay | glossy | lowpoly        colours: "#rrggbb" or a palette name (accent, accent2, hot, ink, muted, paper)
   Animation, all (tl, at) on the film's absolute seconds and all pure functions of t (frames render in any order):
     fig.pose(tl, at, "explain", {dur})      idle point_left point_right explain think shrug wave cheer hold sit look_at (+ present, hips, surprised, ...)
     fig.gesture(tl, at, "nod", {dur})       short beats over the current pose: nod shake wave beat point_beat shrug cheer
     fig.walk(tl, at, {to: [x, z], dur})     turns to profile in the walking direction, legs and arms swing, turns back
     fig.talk(tl, at, dur, {words: [{start, end, text?}]})   mouth flaps (visemes from the letters when `text` is given)
     fig.lookAt(target) | fig.lookAt(tl, at, target, {dur})  target: [x, y, z] | Object3D | another figure | "camera"
     fig.face(tl, at, yawDeg | target)       turn the whole body; fig.express(tl, at, "happy" | "worried" | ..., {dur})
     fig.hold(object3D, {hand: "R" | "L", at})  and fig.release(at)    k.prop("book" | "tablet" | "phone" | "cup" | "bulb" | "magnifier" | "clipboard")
   A figure is never frozen: breathing, a slow weight shift, a drifting gaze and blinks run whenever nothing else does.
   L / R are the viewer's screen sides (L = x < 0). */
(function () {
  "use strict";
  const FX = window.FX, X = FX.x3 || (FX.x3 = {});
  X.figureKit = true;
  const D2R = Math.PI / 180, TAU = Math.PI * 2;
  const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
  const lerp = (a, b, p) => a + (b - a) * p;
  const smooth = (p) => p * p * (3 - 2 * p);
  const rng = (seed) => { let a = (seed >>> 0) || 1; return () => { a = (a + 0x6d2b79f5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; };
  const easeFn = (name) => { if (typeof gsap !== "undefined" && name) { try { return gsap.parseEase(name); } catch (e) { /* fall through */ } } return smooth; };

  /* =========================== spec ===========================
     A figure is a spec, never geometry: validated here (errors list every problem), defaults filled. */
  const ENUM = {
    build: ["slim", "average", "heavy", "child"], hair: ["short", "long", "bun", "bald", "curly", "buzz", "ponytail", "side"], beard: ["none", "stubble", "short", "full"],
    top: ["shirt", "jacket", "coat", "dress", "lab"], bottom: ["trousers", "shorts", "skirt"], finish: ["auto", "matte", "clay", "glossy", "lowpoly"],
  };
  const ALIAS = {   // the older vocabulary of the 2D puppet specs maps onto ours
    build: { broad: "heavy", kid: "child" }, finish: { faceted: "lowpoly", "low-poly": "lowpoly", lowpoly: "lowpoly" },
    top: { tshirt: "shirt", "t-shirt": "shirt", sweater: "shirt", hoodie: "shirt", vest: "jacket" }, hair: { "side-part": "side" },
  };
  const TOKENS = ["accent", "accent2", "hot", "ink", "muted", "paper", "bg"];
  const isColor = (c) => typeof c === "string" && (/^#[0-9a-fA-F]{6}$/.test(c) || /^#[0-9a-fA-F]{3}$/.test(c) || TOKENS.includes(c));
  const SPEC_DEFAULT = {
    build: "average", skin: "#e8b48a", hair: { style: "short", color: "#3a2a20" }, beard: "none", glasses: false,
    top: { kind: "shirt", color: "accent" }, bottom: { kind: "trousers", color: "#2f3b52" }, shoes: "#f4f1ea", finish: "auto",
  };
  X.figureSpec = (input = {}) => {
    const errs = [], sp = input && typeof input === "object" ? input : {};
    const pick = (field, v, dflt) => { if (v === undefined || v === null) return dflt; v = String(ALIAS[field] && ALIAS[field][v] || v); if (!ENUM[field].includes(v)) { errs.push(`${field} '${v}' (use ${ENUM[field].join(" | ")})`); return dflt; } return v; };
    const col = (field, v, dflt) => { if (v === undefined || v === null) return dflt; if (!isColor(v)) { errs.push(`${field} colour '${v}' (use #rrggbb or ${TOKENS.join(" | ")})`); return dflt; } return v; };
    const obj = (v, key) => (typeof v === "string" ? { [key]: v } : v && typeof v === "object" ? v : {});
    for (const k of Object.keys(sp)) if (!["build", "skin", "hair", "beard", "glasses", "top", "bottom", "shoes", "finish", "seed", "name"].includes(k)) errs.push(`unknown field '${k}'`);
    const hair = obj(sp.hair, "style"), top = obj(sp.top, "kind"), bottom = obj(sp.bottom, "kind"), D = SPEC_DEFAULT;
    if (typeof sp.bottom === "string" && isColor(sp.bottom)) { bottom.kind = undefined; bottom.color = sp.bottom; }   // "bottom: '#223'" = trousers of that colour
    if (typeof sp.top === "string" && isColor(sp.top)) { top.kind = undefined; top.color = sp.top; }
    const out = {
      build: pick("build", sp.build, D.build), skin: col("skin", sp.skin, D.skin),
      hair: { style: pick("hair", hair.style, D.hair.style), color: col("hair.color", hair.color, D.hair.color) },
      beard: sp.beard === true ? "short" : sp.beard === false ? "none" : pick("beard", sp.beard, D.beard),
      glasses: sp.glasses && typeof sp.glasses === "object" ? { color: col("glasses.color", sp.glasses.color, "#26252c") } : sp.glasses ? { color: "#26252c" } : false,
      top: { kind: pick("top", top.kind ?? top.style, D.top.kind), color: col("top.color", top.color, D.top.color), inner: col("top.inner", top.inner, undefined) },
      bottom: { kind: pick("bottom", bottom.kind ?? bottom.style, D.bottom.kind), color: col("bottom.color", bottom.color, D.bottom.color) },
      shoes: col("shoes", sp.shoes && typeof sp.shoes === "object" ? sp.shoes.color : sp.shoes, D.shoes), finish: pick("finish", sp.finish, D.finish),
      seed: Number.isFinite(sp.seed) ? sp.seed : 1, name: sp.name || "",
    };
    if (errs.length) throw new Error("figure spec: " + errs.join("; "));
    return out;
  };
  /* a colour a little lighter (f > 0) or darker (f < 0); pure string maths (no THREE) so the tests can run it in node */
  const hex3 = (h) => (h.length === 4 ? "#" + h[1] + h[1] + h[2] + h[2] + h[3] + h[3] : h);
  const shade = (hex, f) => { const h = hex3(hex), c = [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16)), t = f > 0 ? 255 : 0, a = Math.abs(f); return "#" + c.map((v) => Math.round(lerp(v, t, a)).toString(16).padStart(2, "0")).join(""); };
  X.shade = shade;

  /* =========================== proportions ===========================
     Vinyl-toy proportions in figure units (average build stands ~2.2 tall; the head is a third of it). Feet at y = 0,
     the figure faces +z (towards the camera). Every joint is a Group pivot, limbs are capsules centred on the bone. */
  const DIM = { ankle: 0.13, shin: 0.34, thigh: 0.37, hip: 0.84, hipX: 0.15, spineY: 0.05, shX: 0.35, shY: 0.43, upper: 0.34, fore: 0.3, hand: 0.085, neckY: 0.58, headC: 0.3, headR: 0.36 };
  DIM.height = DIM.hip + DIM.spineY + DIM.neckY + 0.06 + DIM.headC + DIM.headR;   // 2.19
  const BUILD = {
    slim: { w: 0.88, lw: 0.86, belly: 0.92, sc: 1, head: 1 }, average: { w: 1, lw: 1, belly: 1, sc: 1, head: 1 },
    heavy: { w: 1.2, lw: 1.18, belly: 1.34, sc: 1, head: 1 }, child: { w: 0.92, lw: 0.94, belly: 1.1, sc: 0.74, head: 1.2 },
  };
  X.BUILD = BUILD; X.DIM = DIM;
  X.figureHeight = (spec) => (DIM.height + (BUILD[spec.build].head - 1) * (DIM.headC * 0.8 + DIM.headR)) * BUILD[spec.build].sc;

  /* =========================== two-bone arm IK ===========================
     Poses with a hand at a place (chin, a held book) are written as targets and solved once into the shoulder / elbow
     angles the rig uses: shoulder f (swing forward), a (out to the side), t (twist, turns the elbow's bend plane), elbow b. */
  const v3 = { sub: (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]], add: (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]], mul: (a, s) => [a[0] * s, a[1] * s, a[2] * s], dot: (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2], len: (a) => Math.hypot(a[0], a[1], a[2]) };
  const ik = (side, T, pole) => {
    const S = [side * DIM.shX, DIM.shY, 0], L1 = DIM.upper, L2 = DIM.fore + DIM.hand;
    let d = v3.sub(T, S), len = clamp(v3.len(d), 0.14, L1 + L2 - 0.01); const u = v3.mul(d, 1 / (v3.len(d) || 1));
    pole = pole || [side * 0.5, -1, -0.25];
    const a = (L1 * L1 - L2 * L2 + len * len) / (2 * len), h = Math.sqrt(Math.max(0, L1 * L1 - a * a));
    let p = v3.sub(pole, v3.mul(u, v3.dot(pole, u))); p = v3.mul(p, 1 / (v3.len(p) || 1));
    const E = v3.add(v3.mul(u, a), v3.mul(p, h)), v1 = v3.mul(E, 1 / L1), v2 = v3.mul(v3.sub(v3.mul(u, len), E), 1 / L2);
    const f = Math.asin(clamp(v1[2], -1, 1)), th = Math.atan2(v1[0], -v1[1]);
    const x1 = v2[0] * Math.cos(th) + v2[1] * Math.sin(th), y1 = -v2[0] * Math.sin(th) + v2[1] * Math.cos(th), z1 = v2[2];   // Rz(-th) v2
    const wx = x1, wy = y1 * Math.cos(f) - z1 * Math.sin(f), wz = y1 * Math.sin(f) + z1 * Math.cos(f);                       // Rx(f) of that
    const psi = Math.atan2(wx, wz), b = Math.acos(clamp(-wy, -1, 1)), S2 = side > 0 ? "R" : "L";
    return { ["sh" + S2 + ".f"]: f / D2R, ["sh" + S2 + ".a"]: (side * th) / D2R, ["sh" + S2 + ".t"]: psi / D2R, ["el" + S2 + ".b"]: b / D2R };
  };
  X.armIK = ik;

  /* =========================== poses ===========================
     A pose is a full set of joint values in degrees (everything not named falls back to the relaxed stand). Keys:
       hips.dy (height) hips.rx hips.ry hips.rz   spine.x y z   neck.x y z   head.x y z
       shL/R .f .a .t  elL/R .b  wrL/R .x .z .t   hipL/R .f .a  knL/R .b  anL/R .x
       ex.brow ex.tilt ex.lid ex.smile  ptL ptR (pointing finger)  swing (arm swing while walking)  seat (stool)
     osc: [key, amplitude, hertz, phase] added while the pose is held (a waving hand, a talking hand). */
  const KEYS = ["hips.dy", "hips.rx", "hips.ry", "hips.rz", "spine.x", "spine.y", "spine.z", "neck.x", "neck.y", "neck.z", "head.x", "head.y", "head.z"];
  for (const S of ["L", "R"]) KEYS.push("sh" + S + ".f", "sh" + S + ".a", "sh" + S + ".t", "el" + S + ".b", "wr" + S + ".x", "wr" + S + ".z", "wr" + S + ".t", "hip" + S + ".f", "hip" + S + ".a", "kn" + S + ".b", "an" + S + ".x", "pt" + S);
  KEYS.push("ex.brow", "ex.tilt", "ex.lid", "ex.smile", "swing", "seat");
  const ZERO = Object.fromEntries(KEYS.map((k) => [k, 0])); ZERO.swing = 1;
  const RELAX = { "shL.a": 9, "shR.a": 9, "elL.b": 14, "elR.b": 14, "hipL.a": 2, "hipR.a": 2, "ex.smile": 0.3 };
  const MIRROR_NEG = new Set(["head.y", "head.z", "neck.y", "neck.z", "spine.y", "spine.z", "hips.ry", "hips.rz", "shL.t", "shR.t", "wrL.z", "wrR.z", "wrL.t", "wrR.t"]);
  const mirrorKey = (k) => (k[0] === "p" && k[1] === "t" ? (k[2] === "L" ? "ptR" : "ptL") : /^(sh|el|wr|hip|kn|an)[LR]/.test(k) ? k.replace(/([a-z]+)([LR])/, (m, a, s) => a + (s === "L" ? "R" : "L")) : k);
  const mirror = (p) => ({ j: Object.fromEntries(Object.entries(p.j).map(([k, v]) => [mirrorKey(k), MIRROR_NEG.has(k) ? -v : v])), osc: (p.osc || []).map(([k, a, h, ph]) => [mirrorKey(k), MIRROR_NEG.has(k) ? -a : a, h, ph + 0.9]) });
  const P = (j, osc) => ({ j: { ...ZERO, ...RELAX, ...j }, osc: osc || [] });
  const POSES = {};
  POSES.idle = P({});
  POSES.point_right = P({ "shR.f": 16, "shR.a": 84, "elR.b": 3, ptR: 1, "wrR.x": 0, "head.y": 18, "neck.y": 6, "spine.y": 9, "shL.a": 6, "ex.smile": 0.55, "ex.brow": 0.2 });
  POSES.point_left = mirror(POSES.point_right);
  // both hands open in front of the chest, a little apart: "so here is the thing"
  POSES.explain = P({ ...ik(-1, [-0.34, 0.2, 0.44], [-0.4, -1, 0]), ...ik(1, [0.34, 0.2, 0.44], [0.4, -1, 0]), "head.z": 3, "neck.x": -2, "spine.x": -2, "ex.smile": 0.55, "ex.brow": 0.25, "wrL.x": 25, "wrR.x": 25, swing: 0.3 },
    [["elL.b", 5, 0.5, 0], ["elR.b", 5, 0.43, 1.7], ["shL.f", 3, 0.6, 0.5], ["shR.f", 3, 0.52, 2.2], ["head.z", 1.6, 0.33, 0.7]]);
  // right hand to the chin, left arm across the belly under the elbow, head tilted, eyes up
  POSES.think = P({ ...ik(1, [0.12, 0.64, 0.3], [0.5, -1, 0.2]), ...ik(-1, [0.08, 0.22, 0.36], [-0.2, -1, 0.1]), "head.z": -8, "head.x": -4, "neck.x": -3, "head.y": 6, "spine.x": 2, "ex.brow": 0.45, "ex.tilt": -0.25, "ex.smile": 0.05, swing: 0.1 },
    [["head.z", 1.2, 0.2, 0], ["elR.b", 1.5, 0.3, 1]]);
  POSES.shrug = P({ ...ik(-1, [-0.46, 0.3, 0.28], [-0.5, -1, -0.1]), ...ik(1, [0.46, 0.3, 0.28], [0.5, -1, -0.1]), "head.z": 7, "neck.z": 3, "spine.x": -1, "hips.rz": 0, "ex.brow": 0.7, "ex.tilt": -0.5, "ex.smile": -0.25, "wrL.x": 20, "wrR.x": 20, swing: 0.3 },
    [["spine.x", 1, 0.4, 0]]);
  POSES.wave = P({ ...ik(1, [0.5, 1.0, 0.12], [0.8, -0.6, -0.3]), "head.z": -4, "head.y": -6, "spine.y": -3, "ex.smile": 0.9, "ex.brow": 0.25, swing: 0.1 },
    [["elR.b", 22, 1.6, 0], ["wrR.z", 14, 1.6, 0.8], ["shR.a", 5, 1.6, 0.3]]);
  POSES.cheer = P({ ...ik(-1, [-0.6, 1.06, 0.04], [-0.4, -0.3, 1]), ...ik(1, [0.6, 1.06, 0.04], [0.4, -0.3, 1]), "head.x": -10, "spine.x": -4, "ex.smile": 1, "ex.brow": 0.5, "hipL.a": 5, "hipR.a": 5, swing: 0 },
    [["hips.dy", 0.035, 2.2, 0], ["shL.a", 5, 2.2, 0.4], ["shR.a", 5, 2.2, 0.4], ["spine.z", 2, 1.1, 0]]);
  // an object held in front of the belly, close to the body: reading, showing, carrying
  POSES.hold = P({ ...ik(-1, [-0.19, 0.3, 0.4], [-0.5, -1, 0]), ...ik(1, [0.19, 0.3, 0.4], [0.5, -1, 0]), "head.x": 8, "neck.x": 3, "ex.smile": 0.3, swing: 0.15 });
  // sitting on the stool the pose brings: thighs level, shins down, the hands rest on the knees
  POSES.sit = P({ "hips.dy": -(DIM.hip - DIM.ankle - DIM.shin) - 0.02, "hipL.f": 88, "hipR.f": 88, "knL.b": 88, "knR.b": 88, "hipL.a": 5, "hipR.a": 5, ...ik(-1, [-0.2, -0.14, 0.4], [-0.6, -1, 0]), ...ik(1, [0.2, -0.14, 0.4], [0.6, -1, 0]), "spine.x": 3, seat: 1, swing: 0 });
  POSES.look_at = P({ "head.z": 3, "ex.brow": 0.3, "ex.smile": 0.35 });
  // one open hand sweeping out to the side: "over here" / presenting
  POSES.present = P({ ...ik(1, [0.62, 0.38, 0.4], [0.5, -1, -0.2]), "wrR.x": 20, "head.y": 10, "spine.y": 6, "ex.smile": 0.7, "ex.brow": 0.2, "shL.a": 7, swing: 0.2 },
    [["shR.f", 4, 0.45, 0], ["head.z", 1.5, 0.3, 0.4]]);
  POSES.hips = P({ ...ik(-1, [-0.36, 0.12, 0.05], [-1, 0, -0.3]), ...ik(1, [0.36, 0.12, 0.05], [1, 0, -0.3]), "head.x": -3, "hips.rz": 0, "ex.smile": 0.6, "ex.brow": 0.15, swing: 0.2, "hipL.a": 4, "hipR.a": 4 });
  POSES.surprised = P({ "shL.a": 28, "shR.a": 28, "shL.f": 12, "shR.f": 12, "elL.b": 55, "elR.b": 55, "spine.x": -5, "head.x": -6, "ex.brow": 1, "ex.lid": -0.6, "ex.smile": 0.1, swing: 0.2 });
  POSES.arms_crossed = P({ ...ik(-1, [0.17, 0.26, 0.42], [-0.3, -1, 0]), ...ik(1, [-0.17, 0.3, 0.45], [0.3, -1, 0]), "head.z": 2, "ex.tilt": 0.2, "ex.smile": 0.15, swing: 0.2 });
  X.POSES = POSES;
  // gestures: partial poses laid over whatever the base pose is, ramped in and out (w = envelope)
  const GESTURES = {
    nod: { j: { "head.x": 11, "neck.x": 4 }, osc: [["head.x", 6, 2.1, 0]], dur: 1.0 },
    shake: { j: {}, osc: [["head.y", 14, 2.2, 0], ["neck.y", 5, 2.2, 0.3]], dur: 1.1 },
    wave: { j: { ...ik(1, [0.5, 1.0, 0.12], [0.8, -0.6, -0.3]), "head.y": -5, "ex.smile": 0.9 }, osc: [["elR.b", 22, 1.6, 0], ["wrR.z", 14, 1.6, 0.8]], dur: 1.8 },
    beat: { j: {}, osc: [["shL.f", 14, 1.7, 0], ["elL.b", 14, 1.7, 0], ["shR.f", 14, 1.7, 1.8], ["elR.b", 14, 1.7, 1.8], ["head.x", 3, 1.7, 0.2]], dur: 1.2 },
    point_beat: { j: { "shR.f": 24, "shR.a": 60, "elR.b": 10, ptR: 1, "head.y": 10 }, osc: [["shR.f", 6, 2, 0]], dur: 1.2 },
    shrug: { j: { ...ik(-1, [-0.46, 0.3, 0.28], [-0.5, -1, -0.1]), ...ik(1, [0.46, 0.3, 0.28], [0.5, -1, -0.1]), "head.z": 7, "ex.brow": 0.7, "ex.smile": -0.2 }, osc: [], dur: 1.2 },
    cheer: { j: { ...ik(-1, [-0.6, 1.06, 0.04], [-0.4, -0.3, 1]), ...ik(1, [0.6, 1.06, 0.04], [0.4, -0.3, 1]), "ex.smile": 1, "ex.brow": 0.5 }, osc: [["hips.dy", 0.04, 2.4, 0]], dur: 1.4 },
    clap: { j: { ...ik(-1, [-0.06, 0.4, 0.45], [-0.5, -1, 0]), ...ik(1, [0.06, 0.4, 0.45], [0.5, -1, 0]), "ex.smile": 0.9 }, osc: [["shL.a", -7, 3, 0], ["shR.a", -7, 3, 0]], dur: 1.4 },
  };
  X.GESTURES = GESTURES;
  const EXPRESSIONS = {   // face only: brow raise, brow tilt (+ angry, - sad), lid (+ closed, - wide), smile
    neutral: { "ex.brow": 0, "ex.tilt": 0, "ex.lid": 0, "ex.smile": 0.1 }, happy: { "ex.brow": 0.3, "ex.tilt": 0, "ex.lid": 0.1, "ex.smile": 1 },
    worried: { "ex.brow": 0.5, "ex.tilt": -0.7, "ex.lid": 0, "ex.smile": -0.4 }, angry: { "ex.brow": -0.2, "ex.tilt": 0.9, "ex.lid": 0.2, "ex.smile": -0.5 },
    surprised: { "ex.brow": 1, "ex.tilt": 0, "ex.lid": -0.6, "ex.smile": 0.1 }, sad: { "ex.brow": 0.2, "ex.tilt": -0.9, "ex.lid": 0.25, "ex.smile": -0.8 },
  };
  X.EXPRESSIONS = EXPRESSIONS;

  /* =========================== visemes ===========================
     Mouth shapes [open 0..1, width 0.5..1.25]. Letters -> shape, vowels last 1.6x, a 40 ms lead (the mouth moves first). */
  const VIS = { A: [0.92, 1.0], E: [0.55, 1.2], I: [0.3, 1.25], O: [0.8, 0.62], U: [0.45, 0.5], M: [0, 0.9], F: [0.12, 1.0], L: [0.4, 0.95], S: [0.2, 1.12], T: [0.26, 1.0] };
  const LETTER = (c) => {
    c = c.toLowerCase();
    if ("aâ".includes(c)) return "A"; if ("eé".includes(c)) return "E"; if ("iıîy".includes(c)) return "I"; if ("oö".includes(c)) return "O"; if ("uüû".includes(c)) return "U";
    if ("mbp".includes(c)) return "M"; if ("fvw".includes(c)) return "F"; if ("lnrdh".includes(c)) return "L"; if ("szcçşjx".includes(c)) return "S"; if (/\p{L}/u.test(c)) return "T"; return null;
  };
  const isVowel = (s) => "AEIOU".includes(s);
  /* keys [t, open, wide] for the words of a line. words: [{start, end, text?}] in the same seconds as `at`. */
  X.visemeTrack = (words, seed = 1, lead = 0.04) => {
    const r = rng(seed * 7919 + 13), keys = [], pat = ["A", "E", "O", "I", "A", "U", "E"];
    let k0 = Math.floor(r() * pat.length), prevEnd = null;
    const REST = [0, 1];
    for (const w of words) {
      const a = w.start, b = Math.max(w.end, w.start + 0.06);
      if (prevEnd !== null && a - prevEnd > 0.14) { keys.push([prevEnd + 0.03, ...REST]); if (a - 0.12 > prevEnd + 0.06) keys.push([a - 0.1, ...REST]); }   // closed through a pause, opening only for the next word
      let shapes = [];
      const text = w.text ?? w.word;
      if (text) { for (const ch of String(text)) { const s = LETTER(ch); if (s) shapes.push([s, isVowel(s) ? 1.6 : 1]); } }
      if (!shapes.length) { const n = Math.max(1, Math.round((b - a) / 0.2)); for (let i = 0; i < n; i++) { shapes.push([pat[(k0++) % pat.length], 1.6]); if (i < n - 1) shapes.push(["T", 0.7]); } }
      // consecutive duplicates blur into one shape; keep them (the flap needs the dip) but never below 35 ms
      const total = shapes.reduce((s, x) => s + x[1], 0);
      let t = a; const minD = 0.035;
      for (const [s, wt] of shapes) { const d = Math.max(minD, ((b - a) * wt) / total), v = VIS[s]; keys.push([Math.max(0, t + d / 2 - lead), v[0] * (0.85 + 0.15 * r()), v[1]]); t += d; }
      prevEnd = b;
    }
    if (prevEnd !== null) keys.push([prevEnd + 0.04, ...REST]);
    keys.sort((p, q) => p[0] - q[0]);
    return keys;
  };
  /* with no words: a seeded syllable rhythm over [at, at + dur] */
  X.talkTrack = (at, dur, seed = 1) => {
    const r = rng(seed * 104729 + 7), keys = [], pat = [VIS.A, VIS.E, VIS.O, VIS.I, VIS.U];
    let t = at + 0.05, i = Math.floor(r() * 5);
    while (t < at + dur - 0.1) { const syl = 0.13 + r() * 0.1, v = pat[(i++) % 5]; keys.push([t, v[0] * (0.7 + 0.3 * r()), v[1]]); keys.push([t + syl * 0.62, 0.08 + r() * 0.08, 1]); t += syl; if (r() < 0.16) { keys.push([t + 0.04, 0, 1]); t += 0.12 + r() * 0.12; } }
    keys.push([at + dur, 0, 1]);
    return keys;
  };
  const mouthAt = (keys, t) => {
    if (!keys.length || t <= keys[0][0] - 0.08) return [0, 1];
    let lo = 0, hi = keys.length - 1;
    if (t >= keys[hi][0]) return [keys[hi][1], keys[hi][2]];
    while (hi - lo > 1) { const m = (lo + hi) >> 1; if (keys[m][0] <= t) lo = m; else hi = m; }
    const a = keys[lo], b = keys[hi], p = clamp((t - a[0]) / Math.max(1e-6, b[0] - a[0]));
    if (t < keys[0][0]) return [lerp(0, keys[0][1], clamp((t - keys[0][0] + 0.08) / 0.08)), 1];   // the first shape opens from rest
    return [lerp(a[1], b[1], smooth(p)), lerp(a[2], b[2], smooth(p))];
  };
  X.mouthAt = mouthAt;
  /* blinks: seeded gaps of 2.2-5.4 s (sometimes a double blink), each 0.17 s: closed fraction 0..1 as a function of t */
  X.blinkTimes = (seed, until) => { const r = rng(seed * 6007 + 3), out = []; let t = 0.8 + r() * 1.6; while (t < until + 6) { out.push(t); if (r() < 0.18) out.push(t + 0.32); t += 2.2 + r() * 3.2; } return out; };
  X.blinkAt = (times, t) => { let c = 0; for (const b of times) { const d = Math.abs(t - b); if (d < 0.085) c = Math.max(c, 1 - d / 0.085); if (b > t + 0.2) break; } return c; };

  /* =========================== evaluation (pure) =========================== */
  const SEG = { J: Object.keys(ZERO) };
  // keyed track of poses (full joint dicts): every key eases from wherever the previous one was when it started
  const prepTrack = (tr) => {
    if (!tr.dirty) return;
    tr.keys.sort((a, b) => a.t - b.t || a.n - b.n);
    let prev = null;
    tr.keys.forEach((kk, i) => { kk.from = prev ? valueAt(tr, i - 1, kk.t) : { ...POSES.idle.j }; prev = kk; });
    tr.dirty = false;
  };
  const progress = (kk, t) => kk.ez(clamp((t - kk.t) / Math.max(1e-6, kk.dur)));
  const valueAt = (tr, i, t) => { const kk = tr.keys[i], p = progress(kk, t), out = {}; for (const k of KEYS) out[k] = lerp(kk.from[k], kk.pose.j[k], p); return out; };
  const sampleBase = (tr, t) => {
    prepTrack(tr);
    let i = -1; for (let n = 0; n < tr.keys.length; n++) if (tr.keys[n].t <= t) i = n; else break;
    if (i < 0) return { j: { ...POSES.idle.j }, osc: [] };
    const j = valueAt(tr, i, t), oscs = [];
    for (let n = Math.max(0, i - 1); n <= i; n++) {   // the oscillation of a pose fades in with it and out as the next arrives
      const kk = tr.keys[n]; if (!kk.pose.osc.length) continue;
      const w = progress(kk, t) * (n < i ? 1 - progress(tr.keys[n + 1], t) : 1);
      if (w > 0) oscs.push([kk, w]);
    }
    for (const [kk, w] of oscs) for (const [key, amp, hz, ph] of kk.pose.osc) j[key] += amp * w * Math.sin(TAU * hz * (t - kk.t) + ph);
    return { j };
  };
  const gestureW = (g, t) => { const a = t - g.t; if (a < 0 || a > g.dur) return 0; return smooth(clamp(a / g.inT)) * smooth(clamp((g.dur - a) / g.outT)); };
  // trapezoid distance profile of a walk: accelerate over r, cruise, decelerate over r. s in 0..1 and its slope
  const WALK_R = 0.2, trap = (p) => { const r = WALK_R, v = 1 / (1 - r); return p <= 0 ? 0 : p >= 1 ? 1 : p < r ? (v * p * p) / (2 * r) : p < 1 - r ? v * (p - r / 2) : 1 - (v * (1 - p) * (1 - p)) / (2 * r); };
  const trapV = (p) => { const r = WALK_R, v = 1 / (1 - r); return p <= 0 || p >= 1 ? 0 : p < r ? (v * p) / r : p < 1 - r ? v : (v * (1 - p)) / r; };
  X.trap = trap;
  const angDiff = (a, b) => { let d = (b - a) % TAU; if (d > Math.PI) d -= TAU; if (d < -Math.PI) d += TAU; return d; };
  // keyed scalar track with angle wrapping (yaw): same "ease from wherever it was" rule
  const scalarAt = (keys, t, base, wrap) => {
    let v = base;
    for (const kk of keys) {
      if (kk.t > t) break;
      const p = kk.ez(clamp((t - kk.t) / Math.max(1e-6, kk.dur)));
      v = wrap ? v + angDiff(v, kk.v) * p : lerp(v, kk.v, p);
      if (p >= 1) v = kk.v;
    }
    return v;
  };
  // the walk layer at time t: position, leg phase and weight (pure; walks sorted by start)
  const walkState = (walks, t, start) => {
    let x = start[0], z = start[1], phase = 0, wk = 0, speedN = 0;
    for (const w of walks) {
      if (t >= w.t1) { x = w.to[0]; z = w.to[1]; continue; }
      if (t < w.t0) break;
      const p = (t - w.t0) / (w.t1 - w.t0), s = trap(p);
      x = lerp(w.from[0], w.to[0], s); z = lerp(w.from[1], w.to[1], s);
      phase = Math.PI * w.steps * s; wk = clamp(trapV(p) * (1 - WALK_R) * 1.15); speedN = Math.min(1.2, w.speed / w.nominal); break;
    }
    return { x, z, phase, wk, speedN };
  };
  X.walkState = walkState;

  // human ranges in degrees (AAOS-like, a little generous for a toy): elbow and knee only flex, shoulders go forward 185 / back 60, hips 125 / 30
  const LIMITS = [["el#.b", 0, 150], ["kn#.b", 0, 140], ["sh#.f", -60, 185], ["sh#.a", -62, 185], ["hip#.f", -30, 125], ["hip#.a", -18, 50], ["an#.x", -30, 40], ["wr#.x", -60, 70], ["wr#.z", -30, 30], ["pt#", 0, 1]];
  const LIMITS_FLAT = [["head.x", -40, 40], ["head.y", -60, 60], ["head.z", -30, 30], ["neck.x", -30, 30], ["neck.y", -45, 45], ["spine.x", -25, 30], ["spine.y", -45, 45], ["spine.z", -20, 20], ["hips.rz", -10, 10], ["ex.smile", -1, 1], ["ex.brow", -1, 1.2], ["ex.tilt", -1, 1], ["ex.lid", -1, 1]];
  /* joint dict + root state + face of a figure at absolute time t: the whole animation is this function */
  const sampleFigure = (F, t) => {
    const base = sampleBase(F.track, t), j = base.j;
    for (const g of F.gestures) {
      const w = gestureW(g, t); if (w <= 0) continue;
      for (const k of Object.keys(g.j)) j[k] = lerp(j[k], g.j[k], w);
      for (const [key, amp, hz, ph] of g.osc) j[key] += amp * w * Math.sin(TAU * hz * (t - g.t) + ph);
    }
    for (const e of F.faceKeys) { const p = progress(e, t); if (p > 0) for (const k of Object.keys(e.to)) j[k] = lerp(j[k], e.to[k], p); }
    // idle layer: always on, small, deterministic. A figure that stands still still breathes, shifts weight and looks around.
    const W = walkState(F.walks, t, F.pos0), moving = W.wk, idle = F.idle ? 1 - 0.75 * moving : 0, I = { x: 0, y: 0 };
    const ph = TAU * t, breath = Math.sin(ph / 3.8 + F.seed);
    j["spine.x"] += idle * 0.9 * breath; j["head.x"] += idle * (0.8 * Math.sin(ph / 5.3 + 1.7)); j["neck.y"] += idle * 2.4 * Math.sin(ph / 7.9 + 0.4 * F.seed); j["head.z"] += idle * 1.1 * Math.sin(ph / 6.1 + 2.2);
    j["hips.rz"] += idle * 1.3 * Math.sin(ph / 6.7 + 0.5); j["hipL.a"] += idle * 1.4 * Math.sin(ph / 6.7 + 0.5); j["hipR.a"] -= idle * 1.4 * Math.sin(ph / 6.7 + 0.5);
    j["hips.ry"] += idle * 2.2 * Math.sin(ph / 9.3 + 1.1); j["spine.z"] -= idle * 0.9 * Math.sin(ph / 6.7 + 0.5);
    j["shL.f"] += idle * 1.8 * Math.sin(ph / 4.7 + 0.2); j["shR.f"] += idle * 1.8 * Math.sin(ph / 4.7 + 2.9); j["elL.b"] += idle * 1.5 * (0.5 + 0.5 * breath); j["elR.b"] += idle * 1.5 * (0.5 + 0.5 * Math.sin(ph / 4.1));
    // the walk: legs and arms swing in opposition, the knee lifts through the swing, the body bobs twice a stride and leans in
    if (W.wk > 0) {
      const A = 27 * W.wk * Math.max(0.55, W.speedN), s1 = Math.sin(W.phase), c1 = Math.cos(W.phase), s2 = Math.sin(W.phase + Math.PI), c2 = Math.cos(W.phase + Math.PI), sw = (j.swing ?? 1) * 0.8 + 0.2;
      j["hipL.f"] += A * s1; j["hipR.f"] += A * s2;
      j["knL.b"] += W.wk * (6 + 38 * Math.max(0, c1) ** 1.3); j["knR.b"] += W.wk * (6 + 38 * Math.max(0, c2) ** 1.3);
      
      j["shL.f"] += -0.85 * A * s1 * sw; j["shR.f"] += -0.85 * A * s2 * sw; j["elL.b"] += W.wk * sw * (10 + 22 * Math.max(0, -s1)); j["elR.b"] += W.wk * sw * (10 + 22 * Math.max(0, -s2));
      j["anL.x"] += 0.85 * W.wk * (j["knL.b"] - j["hipL.f"]); j["anR.x"] += 0.85 * W.wk * (j["knR.b"] - j["hipR.f"]);   // the foot stays flat to the floor whatever the leg does
      j["hips.dy"] -= (DIM.thigh + DIM.shin) * (1 - Math.cos(A * Math.abs(s1) * D2R));   // the hips sink as the straight planted leg spreads: the foot stays on the floor j["spine.x"] += W.wk * 4.5; j["hips.ry"] += W.wk * 3.5 * s1; j["spine.y"] -= W.wk * 4 * s1; j["head.x"] -= W.wk * 2.5;
      j["hips.rz"] += W.wk * 2.2 * Math.cos(W.phase);
    }
    // yaw of the whole figure: keyed turns (explicit + the walk's turn to profile and back)
    const yaw = scalarAt(F.yawKeys, t, F.yaw0, true);
    // talk: mouth + a little head and brow life while it speaks
    const m = mouthAt(F.mouth, t), talking = clamp(m[0] * 4) ;
    const talkW = F.mouth.length ? clamp(F.mouthSpan.reduce((a, [a0, a1]) => Math.max(a, smooth(clamp((t - a0 + 0.15) / 0.2)) * smooth(clamp((a1 + 0.25 - t) / 0.3))), 0)) : 0;
    j["head.x"] += talkW * (1.6 * Math.sin(TAU * 1.9 * t) + 1.2 * Math.sin(TAU * 3.1 * t + 1)); j["neck.y"] += talkW * 1.8 * Math.sin(TAU * 0.8 * t + 2); j["ex.brow"] += talkW * 0.16 * Math.max(0, Math.sin(TAU * 1.3 * t + F.seed));
    // hands talk along with the voice (small, over any pose; the pose's own oscillation adds to it)
    j["shL.f"] += talkW * 6 * Math.sin(TAU * 0.9 * t + 0.4); j["shR.f"] += talkW * 6 * Math.sin(TAU * 0.8 * t + 2.6); j["elL.b"] += talkW * 7 * (0.5 + 0.5 * Math.sin(TAU * 1.1 * t + 1)); j["elR.b"] += talkW * 7 * (0.5 + 0.5 * Math.sin(TAU * 0.95 * t + 3.3));
    j["wrL.x"] += talkW * 8 * Math.sin(TAU * 1.3 * t); j["wrR.x"] += talkW * 8 * Math.sin(TAU * 1.2 * t + 1.5); j["spine.y"] += talkW * 2 * Math.sin(TAU * 0.4 * t);
    // gaze toward the current target
    const g = F.gaze(t, { x: W.x, z: W.z, yaw });
    j["head.y"] += g.hy; j["head.x"] += g.hx; j["neck.y"] += g.hy * 0.35; j["spine.y"] += g.hy * 0.12;
    for (const S of ["L", "R"]) for (const [key, lo, hi] of LIMITS) { const kk = key.replace("#", S); j[kk] = clamp(j[kk], lo, hi); }   // anatomy: nothing bends past a human range
    for (const [kk, lo, hi] of LIMITS_FLAT) j[kk] = clamp(j[kk], lo, hi);
    return { j, W, yaw, mouth: m, talking, talkW, eye: g, blink: Math.max(F.blink ? X.blinkAt(F.blinks, t) : 0, 0) };
  };
  X.sampleFigure = sampleFigure;

  /* a bare animation state without any three.js object: what the tests (and the builder) drive */
  X.figureState = (spec, o = {}) => {
    const F = {
      spec: X.figureSpec(spec), seed: (spec && spec.seed) || o.seed || 1, track: { keys: [], dirty: false }, gestures: [], faceKeys: [], walks: [], yawKeys: [], mouth: [], mouthSpan: [], blinks: [], idle: o.idle !== false, blink: true,
      pos0: o.pos || [0, 0], yaw0: o.yaw || 0, gazeKeys: [], gazeDefault: null, height: o.height || 1, floorY: o.floorY || 0, holds: [], seq: 0,
    };
    F.blinks = X.blinkTimes(F.seed, o.until || 60);
    F.gaze = (t, root) => gazeAt(F, t, root);
    return F;
  };
  const gazeAt = (F, t, root) => {
    const none = { hy: 0, hx: 0, ey: 0, ex: 0 };
    if (!F.gazeKeys.length && !F.gazeDefault) return none;
    let tgt = F.gazeDefault ? resolve(F.gazeDefault, t, F) : null;
    for (const kk of F.gazeKeys) { if (kk.t > t) break; const p = kk.ez(clamp((t - kk.t) / Math.max(1e-6, kk.dur))), q = resolve(kk.tgt, t, F); tgt = tgt ? [lerp(tgt[0], q[0], p), lerp(tgt[1], q[1], p), lerp(tgt[2], q[2], p)] : q; }
    if (!tgt) return none;
    const hp = [root.x, F.floorY + F.height * 0.82, root.z], d = v3.sub(tgt, hp), c = Math.cos(-root.yaw), s = Math.sin(-root.yaw), dx = d[0] * c + d[2] * s, dz = -d[0] * s + d[2] * c;
    const yy = clamp(Math.atan2(dx, dz) / D2R, -120, 120), pitch = Math.atan2(d[1], Math.hypot(dx, dz)) / D2R, hy = clamp(yy * 0.45, -40, 40);
    return { hy, hx: clamp(-pitch * 0.5, -22, 22), ey: clamp(yy - hy, -30, 30), ex: clamp(pitch * 0.5, -20, 20) };
  };
  const resolve = (tg, t, F) => {
    if (typeof tg === "function") return tg(t);
    if (Array.isArray(tg)) return tg;
    if (tg === "camera") return [0, F ? F.floorY + F.height * 0.82 : 1.2, 40];
    if (tg && tg.isObject3D) { tg.updateWorldMatrix(true, false); const e = tg.matrixWorld.elements; return [e[12], e[13], e[14]]; }
    if (tg && tg.headPos) return tg.headPos(t);
    return [0, 1, 40];
  };

  /* the timeline API on a state (the builder wires these onto the figure and adds the rig); kept separate so it is testable in node */
  X.figureAPI = (F, k) => {
    const A = {};
    const nextN = () => ++F.seq;
    const extend = (tl, t) => { if (tl && tl.set) tl.set({}, {}, t); };   // the timeline lasts at least to the end of this action
    A.pose = (tl, at, name, o = {}) => {
      let p = typeof name === "string" ? POSES[name] : name;
      if (!p) throw new Error("figure.pose: unknown pose '" + name + "' (" + Object.keys(POSES).join(", ") + ")");
      if (o.mirror) p = mirror(p);
      if (p.j === undefined) p = P(p);
      F.track.keys.push({ t: at, dur: o.dur ?? 0.55, ez: easeFn(o.ease || "power2.inOut"), pose: { j: { ...ZERO, ...RELAX, ...p.j }, osc: p.osc || [] }, n: nextN(), name: typeof name === "string" ? name : "custom" }); F.track.dirty = true;
      if (name === "look_at" && o.target) A.lookAt(tl, at, o.target, { dur: o.dur });
      extend(tl, at + (o.dur ?? 0.55)); return A;
    };
    A.gesture = (tl, at, name, o = {}) => {
      const g0 = GESTURES[name]; if (!g0) throw new Error("figure.gesture: unknown '" + name + "' (" + Object.keys(GESTURES).join(", ") + ")");
      const dur = o.dur ?? g0.dur, amt = o.amount ?? 1, osc = g0.osc.map(([a, b, c, d]) => [a, b * amt, c, d]);
      F.gestures.push({ t: at, dur, j: o.mirror ? mirror({ j: g0.j, osc: [] }).j : g0.j, osc: o.mirror ? mirror({ j: {}, osc }).osc : osc, inT: Math.min(0.28, dur * 0.35), outT: Math.min(0.35, dur * 0.4) });
      extend(tl, at + dur); return A;
    };
    A.express = (tl, at, name, o = {}) => {
      const e = EXPRESSIONS[name]; if (!e) throw new Error("figure.express: unknown '" + name + "'");       F.faceKeys.push({ t: at, dur: o.dur ?? 0.3, ez: easeFn("power2.out"), to: e, n: nextN() }); F.faceKeys.sort((a, b) => a.t - b.t || a.n - b.n);   // expressions blend over the pose's own face
      extend(tl, at + (o.dur ?? 0.3)); return A;
    };
    A.face = (tl, at, to, o = {}) => {
      let yaw = typeof to === "number" ? to * D2R : 0;
      if (typeof to !== "number") { const r = resolve(to, at, F), p = walkState(F.walks, at, F.pos0); yaw = Math.atan2(r[0] - p.x, r[2] - p.z); }
      F.yawKeys.push({ t: at, dur: o.dur ?? 0.5, ez: easeFn("power2.inOut"), v: yaw, n: nextN() }); F.yawKeys.sort((a, b) => a.t - b.t || a.n - b.n); extend(tl, at + (o.dur ?? 0.5)); return A;
    };
    A.walk = (tl, at, o = {}) => {
      const last = F.walks.length ? F.walks[F.walks.length - 1] : null, from = o.from || (last ? last.to : F.pos0), to = o.to;
      if (!to) throw new Error("figure.walk: {to: [x, z]} is required");
      const dist = Math.hypot(to[0] - from[0], to[1] - from[1]), H = F.height, nominal = 0.62 * H;   // world units per second of an easy walk
      const dur = o.dur ?? Math.max(0.9, dist / nominal), stepLen = 0.34 * H, steps = Math.max(1, Math.round(dist / stepLen));
      F.walks.push({ t0: at, t1: at + dur, from, to, steps, speed: dist / dur, nominal });
      const head = Math.atan2(to[0] - from[0], to[1] - from[1]) * (o.profile ?? 0.94);
      const keepYaw = scalarAt(F.yawKeys, at - 1e-4, F.yaw0, true);
      if (dist > 1e-3) F.yawKeys.push({ t: at - 0.02, dur: 0.34, ez: easeFn("power2.inOut"), v: head + 0 * keepYaw, n: nextN() });
      if (o.face !== false) F.yawKeys.push({ t: at + dur - 0.12, dur: 0.45, ez: easeFn("power2.inOut"), v: typeof o.face === "number" ? o.face * D2R : F.yaw0, n: nextN() });
      F.yawKeys.sort((a, b) => a.t - b.t || a.n - b.n); extend(tl, at + dur + 0.35); return A;
    };
    A.talk = (tl, at, dur, o = {}) => {
      if (typeof dur === "object") { o = dur; dur = o.dur; }
      let words = o.words && o.words.length ? o.words.map((w) => (o.relative ? { ...w, start: w.start + at, end: w.end + at } : w)) : null, keys;
      if (words) { keys = X.visemeTrack(words, F.seed + F.mouthSpan.length); dur = dur ?? Math.max(...words.map((w) => w.end)) - at; }
      else keys = X.talkTrack(at, dur, F.seed + F.mouthSpan.length);
      F.mouth = F.mouth.concat(keys).sort((a, b) => a[0] - b[0]); F.mouthSpan.push([words ? words[0].start : at, words ? words[words.length - 1].end : at + dur]);
      extend(tl, at + dur); return A;
    };
    A.lookAt = (a, b, c, d) => {
      if (a && a.to && typeof b === "number") { const at = b, tgt = c, o = d || {}; F.gazeKeys.push({ t: at, dur: o.dur ?? 0.45, ez: easeFn("power2.inOut"), tgt, n: nextN() }); F.gazeKeys.sort((p, q) => p.t - q.t || p.n - q.n); extend(a, at + (o.dur ?? 0.45)); }
      else F.gazeDefault = a;
      return A;
    };
    A.headPos = (t) => { const W = walkState(F.walks, t, F.pos0); return [W.x, F.floorY + F.height * 0.82, W.z]; };
    A.state = (t) => sampleFigure(F, t);
    return A;
  };

  /* =========================== the builder =========================== */
  X.kit.push((k) => {
    const THREE = k.THREE, { pal } = k, EX = X.EX;
    const V3 = (x = 0, y = 0, z = 0) => new THREE.Vector3(x, y, z);
    const tokens = { ...pal };
    const hexOf = (c) => { if (!c) return "#888888"; if (TOKENS.includes(c)) { const v = tokens[c] || "#888888"; return new THREE.Color(v).getStyle().startsWith("rgb") ? "#" + new THREE.Color(v).getHexString() : v; } return hex3(c); };
    const GEO = new Map();   // geometry is shared between figures (same parameters, same buffers)
    const geo = (key, make) => { let g = GEO.get(key); if (!g) { g = make(); GEO.set(key, g); } return g; };

    k.figure = (input, fo = {}) => {
      const spec = X.figureSpec(input), B = BUILD[spec.build], lk = k.lookName;
      const mode = lk === "blueprint" ? "blueprint" : lk === "neon" ? "neon" : "solid";
      const finish = spec.finish !== "auto" ? spec.finish : { clay: "clay", studio: "glossy", paper: "lowpoly" }[lk] || "matte";
      const FIN = { matte: { r: 0.62 }, clay: { r: 0.92 }, glossy: { r: 0.3, cc: 1 }, lowpoly: { r: 0.8, flat: true } }[finish];
      const low = finish === "lowpoly", S = (n) => (low ? Math.max(5, Math.round(n / 4)) : Math.max(6, Math.round(n * 0.62)));   // segment counts: software WebGL pays per vertex
      const mats = new Map();
      const C = (c) => hexOf(c);
      const skin = C(spec.skin), hairC = C(spec.hair.color);
      const mat = (color, mo = {}) => {
        const key = color + "|" + (mo.rough ?? "") + "|" + (mo.glossy ? 1 : 0) + "|" + (mo.double ? 1 : 0), hit = mats.get(key); if (hit) return hit;
        const c = new THREE.Color(color); if (lk === "studio") c.multiplyScalar(0.8); let m;
        if (mode === "blueprint") m = new THREE.MeshBasicMaterial({ color: new THREE.Color(pal.bg).lerp(c, 0.34), side: mo.double ? THREE.DoubleSide : THREE.FrontSide });   // a dark tinted fill: the outline hull then reads as lines
        else if (mode === "neon") m = new THREE.MeshStandardMaterial({ color: c.clone().multiplyScalar(0.18), roughness: 0.45, metalness: 0.35, emissive: c, emissiveIntensity: 0.28, side: mo.double ? THREE.DoubleSide : THREE.FrontSide });
        else if (FIN.cc || mo.glossy) m = new THREE.MeshPhysicalMaterial({ color: c, roughness: mo.glossy ? 0.22 : FIN.r, metalness: 0, clearcoat: 0.7, clearcoatRoughness: 0.22, flatShading: !!FIN.flat, side: mo.double ? THREE.DoubleSide : THREE.FrontSide, envMapIntensity: (k.look.env || 1) * 0.5 });
        else m = new THREE.MeshStandardMaterial({ color: c, roughness: mo.rough ?? FIN.r, metalness: 0, flatShading: !!FIN.flat, side: mo.double ? THREE.DoubleSide : THREE.FrontSide, envMapIntensity: (k.look.env || 1) * 0.5 });
        mats.set(key, m); return m;
      };
      const hullMats = {};
      const hullMat = (add) => hullMats[add ? "a" : "s"] || (hullMats[add ? "a" : "s"] = new THREE.MeshBasicMaterial(add ? { color: new THREE.Color(pal.accent), side: THREE.BackSide, transparent: true, opacity: 0.95, blending: THREE.AdditiveBlending, depthWrite: false } : { color: new THREE.Color(mix(pal.ink, pal.bg, 0.15)), side: THREE.BackSide }));
      const mix = (a, b, p) => new THREE.Color(a).lerp(new THREE.Color(b), p).getStyle();
      /* a mesh dressed for the look: shadows on, and an inverted-hull outline in blueprint / neon */
      const part = (g, color, o = {}) => {
        const m = new THREE.Mesh(g, mat(color, o)); if (o.pos) m.position.set(...o.pos); if (o.scale) m.scale.set(...o.scale); if (o.rot) m.rotation.set(...o.rot);
        m.castShadow = !o.tiny && k.look.shadow > 0; m.receiveShadow = !o.tiny && k.look.shadow > 0;
        if (mode !== "solid" && !o.tiny && !o.noHull) {
          if (!g.boundingSphere) g.computeBoundingSphere(); const bs = g.boundingSphere, sc = mode === "neon" ? 1.05 : 1.045, h = new THREE.Mesh(g, hullMat(mode === "neon"));
          h.scale.setScalar(sc); h.position.copy(bs.center).multiplyScalar(1 - sc); m.add(h);
        }
        return m;
      };
      const grp = (x = 0, y = 0, z = 0) => { const g = new THREE.Group(); g.position.set(x, y, z); return g; };
      const sph = (r, a = 24, b = 16) => geo(`s${r}|${S(a)}|${S(b)}`, () => new THREE.SphereGeometry(r, S(a), S(b)));
      const cap = (r, len, a = 6, b = 14) => geo(`c${r}|${len}|${S(a)}|${S(b)}`, () => new THREE.CapsuleGeometry(r, len, S(a), S(b)));

      const dimK = { shin: DIM.shin, thigh: DIM.thigh };
      const root = new THREE.Group(), body = grp(0, DIM.hip, 0);   // body = the hips joint
      root.add(body);
      const topKind = spec.top.kind, topC = C(spec.top.color), innerC = spec.top.inner ? C(spec.top.inner) : shade(topKind === "lab" ? "#6a7fa0" : "#f4efe6", 0);
      const longSleeve = topKind !== "dress", sleeveC = topC, forearmC = longSleeve ? topC : skin;
      const botKind = spec.bottom.kind, botC = C(spec.bottom.color), shinC = botKind === "trousers" ? botC : skin, thighC = botKind === "skirt" || topKind === "dress" ? skin : botC;
      const lw = B.lw, W = B.w;

      // ---- pelvis + legs (hip -> knee -> ankle -> foot)
      body.add(part(sph(0.2, 28, 18), topKind === "dress" ? topC : botKind === "skirt" ? botC : botC, { pos: [0, -0.01, 0], scale: [1.2 * W, 0.78, 0.9] }));
      const joints = {};
      const leg = (side) => {
        const S2 = side < 0 ? "L" : "R", hip = grp(side * DIM.hipX * W, 0, 0), knee = grp(0, -DIM.thigh, 0), ankle = grp(0, -DIM.shin, 0);
        hip.add(part(cap(0.105 * lw, DIM.thigh, 6, 16), thighC, { pos: [0, -DIM.thigh / 2, 0] }));
        knee.add(part(sph(0.097 * lw, 16, 12), shinC, { noHull: true }));
        knee.add(part(cap(0.088 * lw, DIM.shin, 6, 16), shinC, { pos: [0, -DIM.shin / 2, 0] }));
        // the shoe: a rounded upper over a pale sole, the toe forward; ankle y = 0.13 above the floor
        ankle.add(part(sph(1, 24, 16), C(spec.shoes), { pos: [0, -0.05, 0.075], scale: [0.115 * lw, 0.082, 0.215] }));
        ankle.add(part(sph(1, 20, 10), shade(C(spec.shoes), 0.55), { pos: [0, -0.108, 0.082], scale: [0.122 * lw, 0.026, 0.225], noHull: true }));
        hip.add(knee); knee.add(ankle); body.add(hip); joints["hip" + S2] = hip; joints["kn" + S2] = knee; joints["an" + S2] = ankle;
      };
      leg(-1); leg(1);

      // ---- torso (lathe, pear shaped), clothes, arms, head
      const spine = grp(0, DIM.spineY, 0); body.add(spine);
      const TP = [[0, -0.14], [0.17, -0.13], [0.255, -0.07], [0.295, 0.05], [0.305 * B.belly, 0.17], [0.29, 0.31], [0.285, 0.41], [0.255, 0.5], [0.16, 0.555], [0.075, 0.578], [0, 0.585]];
      const torsoG = geo("torso" + B.w + "|" + B.belly + "|" + S(48), () => new THREE.LatheGeometry(new THREE.SplineCurve(TP.map(([r, y]) => new THREE.Vector2(r * W, y))).getPoints(S(34)), S(48)));
      const torso = part(torsoG, topC, { scale: [1, 1, 0.78] }); spine.add(torso);
      const frontZ = (y) => { for (let i = 1; i < TP.length; i++) if (y <= TP[i][1]) { const a = TP[i - 1], b = TP[i], p = (y - a[1]) / (b[1] - a[1]); return lerp(a[0], b[0], p) * W * 0.78; } return 0.1; };
      // skirt-like lower garments hang from the hips (legs swing inside them)
      const skirts = [], skirtOf = (pts, color) => { const g = geo("skirt" + pts.join(","), () => new THREE.LatheGeometry(new THREE.SplineCurve(pts.map(([r, y]) => new THREE.Vector2(r, y))).getPoints(S(14)), S(40))); const m = part(g, color, { double: true, noHull: true, scale: [W, 1, 0.84] }); m.position.y = -0.02; m.castShadow = false; skirts.push(m); return m; };
      if (topKind === "dress") body.add(skirtOf([[0.26, 0.1], [0.3, -0.05], [0.36, -0.22], [0.43, -0.42]], topC));
      else if (topKind === "coat" || topKind === "lab") body.add(skirtOf([[0.27, 0.1], [0.3, -0.08], [0.345, -0.3], [0.38, -0.52]], topC));
      else if (botKind === "skirt") body.add(skirtOf([[0.26, 0.04], [0.3, -0.04], [0.35, -0.16], [0.4, -0.3]], botC));
      const collarR = 0.125;
      if (topKind !== "dress") { const col = part(geo(`col|${S(10)}|${S(28)}`, () => new THREE.TorusGeometry(collarR, 0.034, S(10), S(28))), topKind === "shirt" ? shade(topC, 0.18) : innerC, { pos: [0, 0.57, 0.015], rot: [Math.PI / 2 - 0.25, 0, 0], scale: [1, 1, 0.8], noHull: true }); spine.add(col); }
      if (topKind === "jacket" || topKind === "coat" || topKind === "lab") {
        const zf = frontZ(0.36) - 0.005;
        spine.add(part(k.rbox(0.19, 0.34, 0.03, 0.012), innerC, { pos: [0, 0.37, zf], noHull: true, tiny: true }));   // the shirt showing between the lapels
        for (const s of [-1, 1]) spine.add(part(k.rbox(0.085, 0.36, 0.035, 0.015), shade(topC, topKind === "lab" ? -0.06 : -0.12), { pos: [s * 0.1, 0.36, zf + 0.018], rot: [0, 0, s * -0.2], noHull: true, tiny: true }));
        for (const y of [0.12, 0.23]) spine.add(part(sph(0.02, 10, 8), shade(topC, 0.35), { pos: [0, y, frontZ(y) + 0.012], tiny: true }));
        if (topKind === "lab") spine.add(part(k.rbox(0.12, 0.1, 0.03, 0.012), shade(topC, -0.08), { pos: [-0.15, 0.1, frontZ(0.1) + 0.012], tiny: true }));
      }
      // arms: shoulder ball, upper arm, elbow, forearm, wrist, a mitten hand with a thumb and a finger for pointing
      const fingers = {};
      const arm = (side) => {
        const S2 = side < 0 ? "L" : "R", sh = grp(side * DIM.shX * W, DIM.shY, 0), el = grp(0, -DIM.upper, 0), wr = grp(0, -DIM.fore, 0), inner = -side;
        sh.add(part(sph(0.098 * lw, 20, 14), sleeveC, { noHull: true }));
        sh.add(part(cap(0.078 * lw, DIM.upper, 6, 14), sleeveC, { pos: [0, -DIM.upper / 2, 0] }));
        el.add(part(sph(0.07 * lw, 14, 10), forearmC, { noHull: true }));
        el.add(part(cap(0.066 * lw, DIM.fore, 6, 14), forearmC, { pos: [0, -DIM.fore / 2, 0] }));
        if (longSleeve && topKind !== "shirt") el.add(part(geo(`cuff|${S(8)}|${S(20)}`, () => new THREE.TorusGeometry(0.066 * lw, 0.016, S(8), S(20))), innerC, { pos: [0, -DIM.fore + 0.02, 0], rot: [Math.PI / 2, 0, 0], noHull: true, tiny: true }));
        wr.add(part(sph(0.078, 20, 14), skin, { pos: [0, -0.07, 0.004], scale: [0.95, 1.12, 0.66] }));
        wr.add(part(cap(0.026, 0.045, 4, 8), skin, { pos: [inner * 0.063, -0.065, 0.032], rot: [0, 0, inner * 0.5], noHull: true }));
        const fg = part(cap(0.024, 0.075, 4, 8), skin, { pos: [0, -0.15, 0.012], noHull: true }); fg.scale.set(1, 0.001, 1); wr.add(fg); fingers[S2] = fg;
        sh.add(el); el.add(wr); spine.add(sh); joints["sh" + S2] = sh; joints["el" + S2] = el; joints["wr" + S2] = wr;
      };
      arm(-1); arm(1);

      // ---- head: neck, skull, ears, nose, cheeks, eyes with lids, brows, mouth, hair, beard, glasses
      const neck = grp(0, DIM.neckY, 0), head = grp(0, 0.06, 0), HS = B.head; spine.add(neck); neck.add(head); head.scale.setScalar(HS);
      neck.add(part(cap(0.075, 0.06, 4, 12), skin, { pos: [0, 0.01, 0], noHull: true }));
      const R = DIM.headR, HY = DIM.headC, ys = 0.98, zs = 0.95;
      const depth = (x, y) => zs * Math.sqrt(Math.max(0, R * R - x * x - (y / ys) * (y / ys)));
      head.add(part(sph(R, 48, 32), skin, { pos: [0, HY, 0], scale: [1, ys, zs] }));
      for (const s of [-1, 1]) head.add(part(sph(0.062, 16, 12), skin, { pos: [s * R * 0.97, HY - 0.02, -0.02], scale: [0.5, 1, 0.8], noHull: true }));
      head.add(part(sph(0.046, 14, 10), shade(skin, -0.06), { pos: [0, HY - 0.075, depth(0, -0.075) + 0.012], scale: [1, 0.9, 0.9], tiny: true }));
      const blush = mix(skin, "#e8707a", 0.35);
      for (const s of [-1, 1]) head.add(part(sph(0.058, 14, 10), blush, { pos: [s * 0.205, HY - 0.105, depth(0.205, -0.105) - 0.014], scale: [1, 0.72, 0.32], tiny: true }));
      // eyes: sclera, iris, highlight, in a gaze pivot; a lid (skin sphere scaled from the top) closes for blinks
      const eyeY = HY + 0.005, eyeX = 0.15, eyes = [], lids = [];
      for (const s of [-1, 1]) {
        const ez = depth(s * eyeX, eyeY - HY) - 0.03, pivot = grp(s * eyeX, eyeY, ez), lidG = grp(0, 0.1, 0.0);
        pivot.add(part(sph(0.086, 24, 16), "#fbfaf7", { scale: [1, 1.12, 0.56], tiny: true, rough: 0.3 }));
        const iris = grp(0, 0, 0); iris.add(part(sph(0.058, 20, 14), "#2a1d17", { pos: [0, 0, 0.032], scale: [1, 1.08, 0.5], tiny: true, rough: 0.3 }));
        iris.add(part(sph(0.019, 10, 8), "#ffffff", { pos: [-0.016, 0.024, 0.062], tiny: true, rough: 0.2 }));
        pivot.add(iris);
        const lid = part(sph(0.094, 22, 14), shade(skin, -0.03), { pos: [0, -0.1, 0.004], scale: [1.02, 1.1, 0.6], tiny: true }); lidG.add(lid); pivot.add(lidG); lidG.scale.y = 0.001;
        head.add(pivot); eyes.push({ pivot, iris, lidG }); lids.push(lidG);
      }
      const browC = spec.hair.style === "bald" ? shade(skin, -0.45) : hairC, brows = [];
      for (const s of [-1, 1]) {
        const by = HY + 0.125, bg = grp(s * eyeX, by, depth(s * eyeX, 0.125) + 0.008), b = part(cap(0.019, 0.085, 4, 8), browC, { rot: [0, 0, Math.PI / 2], tiny: true, noHull: true }); bg.add(b); head.add(bg); brows.push(bg);
      }
      const mouthY = HY - 0.168, mouth = grp(0, mouthY, depth(0, -0.168) - 0.004);
      // the closed mouth: a tube along a parabola, nine curvatures (frown .. broad smile) swapped by the nearest level
      const smiles = [];
      for (let lv = 0; lv < 9; lv++) {
        const amp = ((lv - 4) / 4) * 0.045, pts = []; for (let i = 0; i <= 8; i++) { const x = (i / 8) * 2 - 1; pts.push(V3(x * 0.072, amp * (x * x - 0.4), 0)); }
        const sm = part(geo("smile" + lv + "|" + S(6), () => new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), S(14), 0.0135, S(6), false)), "#6b2d2a", { tiny: true, noHull: true }); sm.visible = false; mouth.add(sm); smiles.push(sm);
      }
      const cavityG = grp(0, 0, 0), cavity = part(sph(1, 24, 14), "#5a1c24", { scale: [0.07, 0.03, 0.03], tiny: true, noHull: true, rough: 0.5 }); cavityG.add(cavity);
      const tongue = part(sph(1, 14, 8), "#e07a82", { pos: [0, -0.012, 0.002], scale: [0.045, 0.02, 0.026], tiny: true, noHull: true }); cavityG.add(tongue);
      const teeth = part(sph(1, 14, 8), "#fbfaf7", { pos: [0, 0.008, 0.012], scale: [0.05, 0.008, 0.02], tiny: true, noHull: true }); cavityG.add(teeth);
      mouth.add(cavityG); head.add(mouth);
      // hair
      const hs = spec.hair.style, hairM = (g, o) => part(g, hairC, { noHull: false, ...o });
      const hcap = (grow, tilt, theta = 0.5) => { const m = hairM(geo(`hc${grow}|${theta}|${S(48)}`, () => new THREE.SphereGeometry(R + grow, S(48), S(24), 0, TAU, 0, Math.PI * theta)), { pos: [0, HY + 0.01, -0.01], scale: [1, ys, zs + 0.03] }); m.rotation.x = -tilt; return m; };
      if (hs === "short") { head.add(hcap(0.022, 0.5)); head.add(hairM(sph(0.13, 22, 14), { pos: [-0.09, HY + 0.285, 0.2], scale: [1.7, 0.55, 0.75], rot: [0.25, 0, -0.25] })); }
      else if (hs === "side") { head.add(hcap(0.024, 0.55)); head.add(hairM(sph(0.15, 22, 14), { pos: [-0.1, HY + 0.28, 0.2], scale: [1.9, 0.6, 0.8], rot: [0.28, 0, -0.38] })); }
      else if (hs === "buzz") head.add(hcap(0.008, 0.55, 0.5));
      else if (hs === "long") { head.add(hcap(0.026, 0.48)); head.add(hairM(cap(0.2, 0.3, 8, 20), { pos: [0, HY - 0.2, -0.13], scale: [1.32, 1, 0.55] })); for (const s of [-1, 1]) head.add(hairM(cap(0.06, 0.22, 6, 12), { pos: [s * 0.3, HY - 0.1, 0.04], scale: [0.9, 1, 0.9] })); head.add(hairM(sph(0.13, 22, 14), { pos: [0, HY + 0.29, 0.2], scale: [2.1, 0.5, 0.7], rot: [0.3, 0, 0] })); }
      else if (hs === "bun") { head.add(hcap(0.022, 0.5)); head.add(hairM(sph(0.13, 22, 16), { pos: [0, HY + R + 0.07, -0.1] })); head.add(hairM(sph(0.13, 22, 14), { pos: [0, HY + 0.285, 0.2], scale: [2, 0.5, 0.7], rot: [0.3, 0, 0] })); }
      else if (hs === "ponytail") { head.add(hcap(0.022, 0.5)); head.add(hairM(cap(0.07, 0.3, 6, 12), { pos: [0, HY - 0.06, -R - 0.06], rot: [0.35, 0, 0] })); head.add(hairM(sph(0.12, 22, 14), { pos: [0, HY + 0.285, 0.2], scale: [2, 0.5, 0.7], rot: [0.3, 0, 0] })); }
      else if (hs === "curly") {
        head.add(hcap(0.03, 0.44)); const r0 = rng(spec.seed * 31 + 5);
        for (let i = 0; i < 16; i++) { const a = (i / 16) * TAU, ph = 0.18 + 0.5 * r0(); head.add(hairM(sph(0.1, 14, 10), { pos: [Math.cos(a) * R * 0.86, HY + 0.17 + 0.17 * Math.sin(ph * 2.2) + 0.02 * r0(), Math.sin(a) * R * 0.8 * 0.95 - 0.04] })); }
        head.add(hairM(sph(0.115, 16, 12), { pos: [0, HY + 0.3, 0.12], scale: [1.8, 0.7, 0.8] }));
      }
      if (spec.beard !== "none") {
        // soft blobs that sink into the face: a chin, two cheeks running up to the ears, a moustache; the mouth stays free
        const full = spec.beard === "full", stub = spec.beard === "stubble", tone = stub ? mix(skin, hairC, 0.5) : hairC, g = full ? 1.18 : stub ? 0.9 : 1;
        const blob = (r, pos, sc, rot) => head.add(part(sph(r, 20, 14), tone, { pos, scale: sc, rot, noHull: true }));
        blob(0.17 * g, [0, HY - 0.275, 0.12], [1.05, 0.66, 0.78]);
        for (const sd of [-1, 1]) { blob(0.115 * g, [sd * 0.2, HY - 0.2, 0.07], [0.9, 1.25, 0.8], [0, 0, sd * 0.25]); if (full || !stub) blob(0.09 * g, [sd * 0.118, HY - 0.258, 0.2], [1, 0.8, 0.8]); }
        if (!stub) head.add(part(cap(0.024, 0.11, 4, 8), hairC, { pos: [0, HY - 0.118, depth(0, -0.118) + 0.012], rot: [0, 0, Math.PI / 2], noHull: true, tiny: true }));
      }
      if (spec.glasses) {
        const gc = C(spec.glasses.color || "#26252c");
        for (const s of [-1, 1]) head.add(part(geo(`gl|${S(10)}|${S(32)}`, () => new THREE.TorusGeometry(0.108, 0.012, S(10), S(32))), gc, { pos: [s * eyeX, eyeY, depth(s * eyeX, eyeY - HY) + 0.045], scale: [1, 0.92, 1], tiny: true, noHull: true, glossy: true }));
        head.add(part(cap(0.01, 0.07, 4, 6), gc, { pos: [0, eyeY + 0.02, depth(0, eyeY - HY) + 0.05], rot: [0, 0, Math.PI / 2], tiny: true, noHull: true }));
        for (const s of [-1, 1]) head.add(part(cap(0.008, 0.2, 4, 6), gc, { pos: [s * (R * 0.97), eyeY, 0.14], rot: [Math.PI / 2, 0, 0], tiny: true, noHull: true }));
      }
      body.add(spine);
      // pieces that only exist while a pose asks for them: the stool, and the soft shadow under the feet
      const stool = new THREE.Group(); stool.add(part(geo(`stool|${S(28)}`, () => new THREE.CylinderGeometry(0.3, 0.3, 0.055, S(28))), "#b98a54", { pos: [0, 0.305, -0.02], noHull: false }));
      stool.add(part(geo(`stoolleg|${S(14)}`, () => new THREE.CylinderGeometry(0.035, 0.05, 0.28, S(14))), "#5b4a3a", { pos: [0, 0.14, -0.02] }));
      stool.add(part(geo(`stoolbase|${S(24)}`, () => new THREE.CylinderGeometry(0.22, 0.24, 0.03, S(24))), "#5b4a3a", { pos: [0, 0.015, -0.02] }));
      stool.scale.setScalar(0.001); root.add(stool);
      let blob = null;
      if (mode === "solid") {
        const tex = k.texture(128, 128, (g, w, h) => { const gr = g.createRadialGradient(w / 2, h / 2, 0, w / 2, h / 2, w / 2); gr.addColorStop(0, "rgba(20,16,30,0.34)"); gr.addColorStop(0.55, "rgba(20,16,30,0.16)"); gr.addColorStop(1, "rgba(20,16,30,0)"); g.fillStyle = gr; g.fillRect(0, 0, w, h); });
        blob = new THREE.Mesh(new THREE.PlaneGeometry(1.5 * W, 1.2), new THREE.MeshBasicMaterial({ map: tex, transparent: true, depthWrite: false })); blob.rotation.x = -Math.PI / 2; blob.position.set(0, 0.006, 0.03); blob.renderOrder = -1; root.add(blob);
      }

      // ---- placement: the figure is `size` of the safe height tall (0.44 on 9:16, 0.7 on 16:9 unless told), feet on the floor
      const figH = X.figureHeight(spec), H = (fo.size ?? (k.tall ? 0.6 : 0.72)) * k.safeH, sc = H / figH;
      const floorY = fo.y ?? -H / 2 + (fo.dy || 0);
      const holder = new THREE.Group(); holder.add(root); k.scene.add(holder);
      root.scale.setScalar(B.sc);   // child figures are smaller in absolute terms; `sc` below fits the pose to the frame
      holder.scale.setScalar(sc); holder.position.set(fo.x ?? 0, floorY, fo.z ?? 0);
      k.ground({ y: floorY });
      k.camDefault({ el: 0.1, az: 0.1 });

      const F = X.figureState(spec, { pos: [fo.x ?? 0, fo.z ?? 0], yaw: (fo.facing ?? 0) * D2R, height: H, until: k.T.end });
      F.seed = spec.seed; F.floorY = floorY;
      const api = X.figureAPI(F, k), fig = Object.assign(api, { root: holder, rig: root, spec, joints, F, scale: sc, height: H, floorY, k });
      // ---- apply a sampled state to the rig (the whole per-frame job)
      const arms = { L: -1, R: 1 };
      const apply = (lt, t) => {
        const s = sampleFigure(F, t), j = s.j, W2 = s.W;
        holder.position.set(W2.x, floorY, W2.z); holder.rotation.y = s.yaw + j["hips.ry"] * D2R * 0;
        body.position.y = DIM.hip + j["hips.dy"]; body.rotation.set(j["hips.rx"] * D2R, j["hips.ry"] * D2R, j["hips.rz"] * D2R);
        spine.rotation.set(j["spine.x"] * D2R, j["spine.y"] * D2R, j["spine.z"] * D2R); spine.scale.set(1 + 0.006 * Math.sin(TAU * t / 3.8 + F.seed), 1 + 0.012 * Math.sin(TAU * t / 3.8 + F.seed), 1 + 0.008 * Math.sin(TAU * t / 3.8 + F.seed));
        neck.rotation.set(j["neck.x"] * D2R, j["neck.y"] * D2R, j["neck.z"] * D2R); head.rotation.set(j["head.x"] * D2R, j["head.y"] * D2R, j["head.z"] * D2R);
        for (const S2 of ["L", "R"]) {
          const sd = arms[S2];
          joints["sh" + S2].rotation.set(-j["sh" + S2 + ".f"] * D2R, j["sh" + S2 + ".t"] * D2R, sd * j["sh" + S2 + ".a"] * D2R, "ZXY");
          joints["el" + S2].rotation.set(-j["el" + S2 + ".b"] * D2R, 0, 0);
          joints["wr" + S2].rotation.set(-j["wr" + S2 + ".x"] * D2R, j["wr" + S2 + ".t"] * D2R, sd * j["wr" + S2 + ".z"] * D2R);
          joints["hip" + S2].rotation.set(-j["hip" + S2 + ".f"] * D2R, 0, sd * j["hip" + S2 + ".a"] * D2R);
          joints["kn" + S2].rotation.x = j["kn" + S2 + ".b"] * D2R; joints["an" + S2].rotation.x = -j["an" + S2 + ".x"] * D2R + (j["kn" + S2 + ".b"] * D2R) * 0;
          fingers[S2].scale.y = Math.max(0.001, j["pt" + S2]); fingers[S2].visible = j["pt" + S2] > 0.02;
        }
        // the face: gaze in the eyes, blink and widen with the lids, brows, the mouth
        const blink = Math.max(s.blink, clamp(j["ex.lid"], 0, 1)), wide = clamp(-j["ex.lid"], 0, 1);
        for (const e of eyes) { e.pivot.rotation.set(-s.eye.ex * D2R, s.eye.ey * D2R, 0); e.lidG.scale.y = Math.max(0.001, blink * (1 - 0.0) * 1.0 - wide * 0); e.pivot.scale.y = 1 + 0.12 * wide; }
        brows.forEach((b, i) => { const sd = i ? 1 : -1; b.position.y = HY + 0.125 + 0.03 * j["ex.brow"] + 0.012 * wide; b.rotation.z = sd * 0.35 * j["ex.tilt"]; });
        const open = s.mouth[0], wd = s.mouth[1], sm = j["ex.smile"], talkingNow = open > 0.07;
        const lvl = Math.round(clamp(sm, -1, 1) * 4) + 4; smiles.forEach((m, i) => { m.visible = !talkingNow && i === lvl; }); cavityG.visible = talkingNow;
        cavity.scale.set(0.066 * wd * (1 + 0.1 * sm), 0.014 + 0.062 * open, 0.03); cavity.position.y = -0.062 * open * 0.5 - 0.004;
        tongue.visible = open > 0.28; tongue.position.y = cavity.position.y - 0.02 * open; teeth.visible = open > 0.2; teeth.position.y = cavity.position.y + 0.062 * open * 0.5 * 0.7 - 0.004;
        for (const m of skirts) m.scale.set(W * (1 + 0.3 * j.seat), 1 - 0.5 * j.seat, 0.84 * (1 + 0.45 * j.seat));
        stool.scale.setScalar(Math.max(0.001, j.seat)); stool.visible = j.seat > 0.01;
        for (const h of F.holds) h.obj.visible = t >= h.at && t < h.until;
      };
      k.eachFrame(apply);
      fig.hold = (obj, ho = {}) => {   // hand: "R" | "L" (in that hand) | "both" (between two hands in front of the belly, with the 'hold' pose)
        if (ho.hand === "both" || ho.hand === "front") { spine.add(obj); obj.position.set(...(ho.offset || [0, 0.31, 0.47])); }
        else { const S2 = ho.hand === "L" ? "L" : "R"; joints["wr" + S2].add(obj); obj.position.set(...(ho.offset || [0, -0.12, 0.07])); }
        if (ho.rot) obj.rotation.set(...ho.rot);
        F.holds.push({ obj, at: ho.at ?? -1e9, until: ho.until ?? 1e9 }); return fig;
      };
      fig.release = (at) => { const h = F.holds[F.holds.length - 1]; if (h) h.until = at; return fig; };
      fig.headY = () => floorY + H * 0.82;
      fig.dispose = () => {};
      (k.figures || (k.figures = [])).push(fig);
      return fig;
    };

    /* ---- props to hold: small readable objects, ~0.3 figure units, built from the same primitives ---- */
    k.prop = (kind = "book", po = {}) => {
      const g = new THREE.Group(), col = po.color ? hexOf(po.color) : null, sd = k.look.shadow > 0, add = (m) => { g.add(m); return m; };
      const solid = (geo, c, o) => { const m = k.solid(geo, c, o); m.castShadow = sd; return m; };
      if (kind === "book") { add(solid(k.rbox(0.3, 0.38, 0.06, 0.012), col || pal.accent2)); add(solid(k.rbox(0.27, 0.35, 0.05, 0.008), pal.paper)).position.x = 0.012; g.rotation.x = -0.25; }
      else if (kind === "tablet") { add(solid(k.rbox(0.34, 0.46, 0.035, 0.03), "#2b2c31")); const sc = k.texture(256, 352, (c, w, h) => { const gr = c.createLinearGradient(0, 0, w, h); gr.addColorStop(0, pal.accent2); gr.addColorStop(1, pal.accent); c.fillStyle = gr; c.fillRect(0, 0, w, h); c.fillStyle = "rgba(255,255,255,.28)"; for (let i = 0; i < 4; i++) c.fillRect(24, 40 + i * 62, w - 48, 40); }); const s = new THREE.Mesh(new THREE.PlaneGeometry(0.3, 0.42), new THREE.MeshBasicMaterial({ map: sc })); s.position.z = 0.019; add(s); g.rotation.x = -0.3; }
      else if (kind === "phone") { add(solid(k.rbox(0.16, 0.32, 0.025, 0.03), "#222"));  const s = new THREE.Mesh(new THREE.PlaneGeometry(0.14, 0.29), new THREE.MeshBasicMaterial({ color: new THREE.Color(pal.accent) })); s.position.z = 0.014; add(s); g.rotation.x = -0.3; }
      else if (kind === "cup") { add(solid(new THREE.CylinderGeometry(0.075, 0.06, 0.15, 24), col || pal.paper)); const h = solid(new THREE.TorusGeometry(0.05, 0.014, 8, 16, Math.PI), col || pal.paper); h.position.set(0.075, 0, 0); h.rotation.z = -Math.PI / 2; add(h); }
      else if (kind === "bulb") { add(solid(new THREE.SphereGeometry(0.13, 24, 16), col || "#ffd25a", { rough: 0.2, glow: 0.9, emissive: col || "#ffd25a" })).position.y = 0.07; add(solid(new THREE.CylinderGeometry(0.05, 0.05, 0.09, 16), "#9aa0aa")).position.y = -0.07; g.rotation.x = 0; }
      else if (kind === "magnifier") { const r = solid(new THREE.TorusGeometry(0.12, 0.022, 10, 28), pal.ink); r.position.y = 0.17; add(r); add(solid(new THREE.CylinderGeometry(0.02, 0.026, 0.2, 10), pal.ink)).position.y = -0.02; const lens = new THREE.Mesh(new THREE.CircleGeometry(0.11, 24), new THREE.MeshBasicMaterial({ color: 0xcfe8ff, transparent: true, opacity: 0.4 })); lens.position.set(0, 0.17, 0.004); add(lens); }
      else if (kind === "clipboard") { add(solid(k.rbox(0.3, 0.42, 0.03, 0.02), "#b98a54")); add(solid(k.rbox(0.25, 0.35, 0.012, 0.005), pal.paper)).position.z = 0.02; add(solid(k.rbox(0.1, 0.04, 0.03, 0.01), "#9aa0aa")).position.y = 0.2; g.rotation.x = -0.3; }
      else throw new Error("k.prop: unknown '" + kind + "' (book, tablet, phone, cup, bulb, magnifier, clipboard)");
      g.scale.setScalar(po.scale ?? 1); return g;
    };
  });
})();
