"""3D characters (motion/templates/fx3d_figure.js, k.figure) and the idle layer of the 3D kit (fx3d.js).

Two levels. The animation maths (spec validation, two-bone IK, poses, gestures, walk, visemes, blinks) is plain JS with no
three.js, so it runs in node in milliseconds: determinism, joint limits and the walk's start / stop are checked there. The
look (feet on the floor, no frozen frame, a figure never static, frames a pure function of t) needs the browser and goes
through bin/htmlmotion like tests/test_three.py."""
import json, os, subprocess, sys, tempfile

import pytest

from factory import recipes as R
from factory.config import ROOT

sys.path.insert(0, os.path.join(ROOT, "bin"))
FIG = os.path.join(ROOT, "motion", "templates", "fx3d_figure.js")
CARDS = ["three.figure_explain", "three.figure_walk", "three.figure_with_object", "three.duo"]


def node(body):
    """Run `body` (JS, X = the kit's namespace) in node with a stub window; its JSON.stringify'd last value comes back."""
    src = ("global.window = {FX: {x3: {kit: []}}}; require(%s); const X = window.FX.x3; const out = (() => { %s })();"
           "console.log(JSON.stringify(out));" % (json.dumps(FIG), body))
    r = subprocess.run(["node", "-e", src], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-800:]
    return json.loads(r.stdout.strip().splitlines()[-1])


# ------------------------------------------------------------------ spec

def test_spec_defaults_aliases_and_errors():
    out = node("""
      const d = X.figureSpec({});
      const a = X.figureSpec({build: 'broad', finish: 'faceted', top: {style: 'hoodie', color: '#112233'}, bottom: '#445566', hair: 'curly', beard: true, glasses: true});
      let err = null; try { X.figureSpec({build: 'giant', skin: 'red', hair: {style: 'afro'}, top: {kind: 'cape'}, flying: 1}); } catch (e) { err = e.message; }
      return {d, a, err};""")
    d, a = out["d"], out["a"]
    assert d["build"] == "average" and d["top"]["kind"] == "shirt" and d["hair"]["style"] == "short" and d["finish"] == "auto" and d["beard"] == "none"
    assert a["build"] == "heavy" and a["finish"] == "lowpoly" and a["top"]["kind"] == "shirt" and a["bottom"] == {"kind": "trousers", "color": "#445566"}
    assert a["hair"]["style"] == "curly" and a["beard"] == "short" and a["glasses"] and out["err"].startswith("figure spec:")
    for bad in ("build 'giant'", "skin colour 'red'", "hair 'afro'", "top 'cape'", "unknown field 'flying'"):   # every problem is listed at once
        assert bad in out["err"], out["err"]


def test_every_documented_spec_value_validates():
    out = node("""
      const ok = []; const E = {build: ['slim', 'average', 'heavy', 'child'], beard: ['none', 'stubble', 'short', 'full'], finish: ['auto', 'matte', 'clay', 'glossy', 'lowpoly']};
      for (const b of E.build) for (const f of E.finish) for (const be of E.beard) ok.push(X.figureSpec({build: b, finish: f, beard: be}).build);
      for (const h of ['short', 'long', 'bun', 'bald', 'curly']) ok.push(X.figureSpec({hair: {style: h, color: '#222222'}}).hair.style);
      for (const t of ['shirt', 'jacket', 'coat', 'dress', 'lab']) ok.push(X.figureSpec({top: {kind: t, color: 'accent'}}).top.kind);
      for (const b of ['trousers', 'shorts', 'skirt']) ok.push(X.figureSpec({bottom: {kind: b, color: '#123'}}).bottom.kind);
      return ok.length;""")
    assert out == 4 * 5 * 4 + 5 + 5 + 3


# ------------------------------------------------------------------ the rig's maths

def test_arm_ik_reaches_what_it_can_reach():
    """Forward kinematics of the solved shoulder / elbow angles lands on the target (the rig's own convention)."""
    out = node("""
      const D = X.DIM, r = Math.PI / 180, res = [];
      const rotZ = (v, a) => [v[0] * Math.cos(a) - v[1] * Math.sin(a), v[0] * Math.sin(a) + v[1] * Math.cos(a), v[2]];
      const rotX = (v, a) => [v[0], v[1] * Math.cos(a) - v[2] * Math.sin(a), v[1] * Math.sin(a) + v[2] * Math.cos(a)];
      const rotY = (v, a) => [v[0] * Math.cos(a) + v[2] * Math.sin(a), v[1], -v[0] * Math.sin(a) + v[2] * Math.cos(a)];
      for (const side of [-1, 1]) for (const T of [[0.12, 0.64, 0.3], [0.19, 0.3, 0.4], [0.5, 0.95, 0.12], [0.34, 0.2, 0.44], [0.46, 0.3, 0.28]]) {
        const t = [side * T[0], T[1], T[2]], k = X.armIK(side, t), S = side > 0 ? 'R' : 'L';
        const f = k['sh' + S + '.f'] * r, a = side * k['sh' + S + '.a'] * r, psi = k['sh' + S + '.t'] * r, b = k['el' + S + '.b'] * r;
        const R1 = (v) => rotZ(rotX(rotY(v, psi), -f), a);               // the rig's shoulder: ZXY = Rz * Rx * Ry
        const e = R1([0, -D.upper, 0]);
        const w = R1(rotX([0, -(D.fore + D.hand), 0], -b));
        const hand = [side * D.shX + e[0] + w[0], D.shY + e[1] + w[1], e[2] + w[2]];
        res.push(Math.hypot(hand[0] - t[0], hand[1] - t[1], hand[2] - t[2]));
      }
      return res;""")
    assert max(out) < 0.012, out


def test_joint_limits_hold_in_every_pose_gesture_and_walk_sample():
    """The AVF anatomy rule, in 3D: nothing bends past a human range (so nothing folds through the body)."""
    out = node("""
      const bad = [];
      const chk = (name, j) => {
        for (const S of ['L', 'R']) {
          const f = j['sh' + S + '.f'], a = j['sh' + S + '.a'], b = j['el' + S + '.b'], hf = j['hip' + S + '.f'], ha = j['hip' + S + '.a'], kb = j['kn' + S + '.b'];
          if (f < -65 || f > 190) bad.push([name, 'sh.f', S, f]); if (a < -62 || a > 190) bad.push([name, 'sh.a', S, a]);
          if (b < -0.01 || b > 150.01) bad.push([name, 'el.b', S, b]); if (hf < -35 || hf > 125) bad.push([name, 'hip.f', S, hf]);
          if (ha < -15 || ha > 50) bad.push([name, 'hip.a', S, ha]); if (kb < -0.01 || kb > 140.01) bad.push([name, 'kn.b', S, kb]);
        }
        if (Math.abs(j['head.y']) > 60 || Math.abs(j['head.x']) > 45 || Math.abs(j['spine.x']) > 30) bad.push([name, 'head/spine']);
      };
      for (const [n, p] of Object.entries(X.POSES)) chk('pose ' + n, p.j);
      // every pose with its oscillation at its extremes, every gesture over every pose, the walk over a stride
      const F = X.figureState({}, {height: 5, until: 40}), A = X.figureAPI(F, null);
      for (const n of Object.keys(X.POSES)) { A.pose(null, 0, n, {dur: 0.01}); for (const g of Object.keys(X.GESTURES)) { A.gesture(null, 1, g); for (let t = 0.9; t < 3.2; t += 0.07) chk(n + '+' + g, X.sampleFigure(F, t).j); } F.gestures.length = 0; }
      const G = X.figureState({}, {height: 5, until: 40}), B = X.figureAPI(G, null); B.walk(null, 1, {to: [4, 0], dur: 3});
      for (let t = 0; t < 5; t += 0.05) chk('walk', X.sampleFigure(G, t).j);
      return bad.slice(0, 6);""")
    assert out == [], out


def test_pure_function_of_t_and_order_independent():
    out = node("""
      const mk = () => { const F = X.figureState({seed: 3, hair: {style: 'long', color: '#321'}}, {height: 5, until: 30}), A = X.figureAPI(F, null);
        A.pose(null, 0.5, 'explain'); A.talk(null, 0.8, 3, {words: [{start: 0.8, end: 1.3, text: 'hello'}, {start: 1.4, end: 2.2, text: 'world'}]});
        A.gesture(null, 2.5, 'nod'); A.pose(null, 3, 'point_right'); A.walk(null, 4, {to: [3, 1], dur: 2.5}); A.lookAt(null, 1, [4, 2, 5]); return F; };
      const A = mk(), B = mk(), ts = [0, 0.4, 0.9, 1.7, 2.6, 3.3, 4.8, 5.5, 6.9, 9.1], same = [];
      const ser = (F, t) => JSON.stringify(X.sampleFigure(F, t));
      const fwd = ts.map((t) => ser(A, t)); const back = [...ts].reverse().map((t) => ser(B, t)).reverse();
      for (let i = 0; i < ts.length; i++) same.push(fwd[i] === back[i]);
      return {same, differs: ser(A, 1.7) !== ser(A, 3.3)};""")
    assert all(out["same"]) and out["differs"]


def test_pose_transition_blend_idle_default_and_never_frozen():
    out = node("""
      const F = X.figureState({}, {height: 5, until: 40}), A = X.figureAPI(F, null);
      A.pose(null, 2, 'point_right', {dur: 1, ease: 'linear'});
      const s = (t) => X.sampleFigure(F, t).j;
      const before = s(1.0)['shR.a'], mid = s(2.5)['shR.a'], after = s(3.5)['shR.a'];
      const target = X.POSES.point_right.j['shR.a'], idle = X.POSES.idle.j['shR.a'];
      // never frozen: with nothing scheduled the body still moves second to second (breath, weight shift, gaze)
      const moves = []; for (let t = 10; t < 14; t += 0.5) { const a = s(t), b = s(t + 0.25); moves.push(Math.abs(a['spine.x'] - b['spine.x']) + Math.abs(a['hips.rz'] - b['hips.rz']) + Math.abs(a['neck.y'] - b['neck.y'])); }
      return {before, mid, after, target, idle, minMove: Math.min(...moves)};""")
    assert abs(out["before"] - out["idle"]) < 3 and out["idle"] < out["mid"] < out["target"] and abs(out["after"] - out["target"]) < 3
    assert out["minMove"] > 0.005, out


def test_walk_starts_and_stops_on_its_marks_with_feet_together():
    out = node("""
      const F = X.figureState({}, {height: 5, until: 40, pos: [-3, 0]}), A = X.figureAPI(F, null);
      A.walk(null, 1, {to: [3, 0], dur: 3});
      const w = (t) => X.walkState(F.walks, t, F.pos0), yaw = (t) => X.sampleFigure(F, t).yaw;
      const mid = w(2.5), end = w(4.2), last = w(3.99999), st = F.walks[0];
      const speeds = []; for (let t = 1.05; t < 3.95; t += 0.1) speeds.push((w(t + 0.01).x - w(t).x) / 0.01);
      const j0 = X.sampleFigure(F, 4.3).j;
      return {x0: w(0.5).x, xm: mid.x, x1: end.x, ph1: last.phase / Math.PI, steps: st.steps, mono: speeds.every((v) => v >= 0), yawMid: yaw(2.5), yawEnd: yaw(5.5), yawStart: yaw(0.2),
              legAtEnd: Math.abs(j0['hipL.f']) + Math.abs(j0['hipR.f'])};""")
    assert out["x0"] == -3 and abs(out["x1"] - 3) < 1e-9 and -3 < out["xm"] < 3 and out["mono"]
    assert abs(out["ph1"] - out["steps"]) < 1e-3 and out["steps"] >= 3                    # a whole number of steps: it ends with the feet together
    assert abs(out["yawMid"] - 0.94 * 3.14159 / 2) < 0.08 and abs(out["yawEnd"]) < 0.05 and abs(out["yawStart"]) < 0.05   # profile in the walking direction, then back to the camera
    assert out["legAtEnd"] < 6, out                                                      # the legs have settled (idle weight shift only)


def test_visemes_close_on_bilabials_open_on_vowels_and_blinks_are_seeded():
    out = node("""
      const keys = X.visemeTrack([{start: 1, end: 1.6, text: 'mama'}, {start: 2, end: 2.4, text: 'oh'}], 1);
      const m = X.visemeTrack([{start: 0, end: 0.3, text: 'm'}], 1), a = X.visemeTrack([{start: 0, end: 0.3, text: 'a'}], 1);
      const bl = X.blinkTimes(5, 40), bl2 = X.blinkTimes(5, 40), bl3 = X.blinkTimes(6, 40);
      const lids = []; for (let t = 0; t < 12; t += 0.02) lids.push(X.blinkAt(bl, t));
      const gaps = bl.slice(1).map((t, i) => t - bl[i]);
      const noText = X.visemeTrack([{start: 0, end: 1}], 2), talk = X.talkTrack(1, 3, 4), talk2 = X.talkTrack(1, 3, 4);
      return {sorted: keys.every((k, i) => !i || keys[i - 1][0] <= k[0]), mClosed: Math.min(...m.map((k) => k[1])), aOpen: Math.max(...a.map((k) => k[1])), last: keys[keys.length - 1],
              seeded: JSON.stringify(bl) === JSON.stringify(bl2), seedDiffers: JSON.stringify(bl) !== JSON.stringify(bl3), maxLid: Math.max(...lids), minGap: Math.min(...gaps.filter((g) => g > 0.5)),
              opens: Math.max(...noText.map((k) => k[1])), talkSame: JSON.stringify(talk) === JSON.stringify(talk2), talkEnd: talk[talk.length - 1], midOpen: X.mouthAt(keys, 1.3)[0], restOpen: X.mouthAt(keys, 1.8)[0]};""")
    assert out["sorted"] and out["mClosed"] < 0.05 and out["aOpen"] > 0.6 and out["last"][1] == 0
    assert out["seeded"] and out["seedDiffers"] and out["maxLid"] > 0.9 and out["minGap"] > 2
    assert out["opens"] > 0.4 and out["talkSame"] and out["talkEnd"][1] == 0 and out["restOpen"] < 0.05


def test_mirror_poses_and_pose_catalogue():
    out = node("""
      const r = X.POSES.point_right.j, l = X.POSES.point_left.j;
      return {names: Object.keys(X.POSES), gest: Object.keys(X.GESTURES), a: [r['shR.a'], l['shL.a']], pt: [r.ptR, l.ptL], hy: [r['head.y'], l['head.y']], other: l['shR.a']};""")
    for n in ("idle", "point_left", "point_right", "explain", "think", "shrug", "wave", "cheer", "hold", "sit", "look_at"):
        assert n in out["names"], n
    for g in ("nod", "shake", "wave", "beat"):
        assert g in out["gest"], g
    assert out["a"][0] == out["a"][1] and out["pt"] == [1, 1] and out["hy"][0] == -out["hy"][1] and out["other"] < 20


def test_unknown_pose_and_prop_fail_loudly():
    out = node("""
      const F = X.figureState({}, {height: 5}), A = X.figureAPI(F, null); let e1 = null, e2 = null, e3 = null;
      try { A.pose(null, 0, 'moonwalk'); } catch (e) { e1 = e.message; } try { A.gesture(null, 0, 'flip'); } catch (e) { e2 = e.message; } try { A.walk(null, 0, {}); } catch (e) { e3 = e.message; }
      return [e1, e2, e3];""")
    assert "moonwalk" in out[0] and "flip" in out[1] and "to" in out[2]


# ------------------------------------------------------------------ cards

def test_figure_cards_exist_complete_and_use_the_kit():
    cards = {c["id"]: c for c in R.cards() if c["family"] == "three"}
    for cid in CARDS:
        c = cards[cid]
        assert "FX.stage3" in c["demo"] and "k.figure(" in c["demo"] and "Math.random" not in c["demo"] and "Date" not in c["demo"], cid
    assert R.problems([cards[c] for c in CARDS]) == []
    note = open(os.path.join(R.SRC, "three_note.md"), encoding="utf-8").read()
    for word in ("k.figure", "f.walk", "f.talk", "IDLE LAYER", "k.beat", "2D character sheet"):
        assert word in note, word
    assert "RECIPE three.duo" in R.card_text(["three.duo"])


# ------------------------------------------------------------------ browser

def _bundle(js, secs, w=1080, h=1920):
    from factory import catalog
    return {"palette": catalog.PALETTE, "global_css": "", "words": [], "duration": secs, "w": w, "h": h, "lang": "en", "captions": {},
            "scenes": [{"id": "s0", "start": 0, "end": secs, "hide_captions": True, "lines_t": [], "html": "", "css": catalog.BG, "js": R.PRELUDE + js}]}


@pytest.fixture
def tmp_path():
    import shutil
    d = tempfile.mkdtemp(dir=os.path.join(ROOT, "work"), prefix="test_fig3d_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


def _shots(b, times, d, lint=False):
    import htmlmotion
    p = os.path.join(d, "b.json")
    json.dump(b, open(p, "w"))
    out = tempfile.mkdtemp(dir=d)
    r = htmlmotion.shots(p, times, out, lint=lint)
    return (r[0], r[1], json.load(open(r[2]))) if lint else r


SCENE = ("const k = FX.stage3(tl, root, T, {look: 'clay'%s});"
         "const f = k.figure({hair: {style: 'curly', color: '#2a1a12'}, top: {kind: 'jacket', color: 'accent2', inner: '#f4efe6'}, glasses: true, beard: 'short'}, {x: -2, size: 0.5});"
         "f.pose(tl, 0.3, 'explain'); f.talk(tl, 0.5, 2, {words: [{start: 0.5, end: 1.0, text: 'hello'}, {start: 1.1, end: 2.4, text: 'everyone'}]});"
         "f.walk(tl, 3, {to: [2, 0], dur: 2.5}); f.pose(tl, 5.8, 'wave'); f.gesture(tl, 7, 'nod');")


@pytest.mark.parametrize("look", ["clay", "studio", "paper", "blueprint", "neon"])
def test_a_figure_renders_in_every_look_without_page_errors(look, tmp_path):
    from PIL import Image
    js = ("const k = FX.stage3(tl, root, T, {look: '%s'}); const f = k.figure({top: {kind: 'dress', color: 'accent'}, hair: {style: 'bun', color: '#331'}}, {size: 0.6});"
          "f.pose(tl, 0.2, 'think'); f.talk(tl, 0.3, 1);" % look)
    pngs, errs = _shots(_bundle(js, 2), [1.0], str(tmp_path))
    assert pngs and not errs, (look, errs)
    lo, hi = Image.open(pngs[0]).convert("L").getextrema()
    assert hi - lo > 60


def test_a_figure_scene_is_a_pure_function_of_t(tmp_path):
    for w, h in ((1080, 1920), (1920, 1080)):
        b = _bundle(SCENE % "", 9, w, h)
        one, e1 = _shots(b, [4.1], str(tmp_path))
        many, e2 = _shots(b, [8.0, 1.2, 6.5, 0.4, 4.1], str(tmp_path))
        again, e3 = _shots(b, [1.2], str(tmp_path))
        assert not (e1 or e2 or e3)
        same = lambda p, q: open(p, "rb").read() == open(q, "rb").read()
        assert same(one[0], next(p for p in many if p.endswith("004.10.png")))
        assert same(again[0], next(p for p in many if p.endswith("001.20.png")))


def test_feet_stay_on_the_floor_walking_sitting_and_idle(tmp_path):
    """The lowest point of the figure stays within a hair of the floor in a walk, a sit and a stand (measured in the page)."""
    js = ("const k = FX.stage3(tl, root, T, {look: 'clay'});"
          "const f = k.figure({}, {x: -2, size: 0.5}); f.walk(tl, 0.2, {to: [2, 0], dur: 2.2}); f.pose(tl, 3, 'sit'); f.pose(tl, 5, 'idle');"
          "const el = D('', 'left:60px;top:600px;font:700 60px Inter Tight;color:#fff');"
          "FX.onFrame(() => { k.scene.updateMatrixWorld(true); const b = new k.THREE.Box3().setFromObject(f.rig, true);"
          "  el.textContent = 'feet ' + ((b.min.y - f.floorY) / f.scale).toFixed(3); });")
    times = [0.1, 0.9, 1.5, 2.1, 3.6, 4.5, 6.0]
    pngs, errs, lint = _shots(_bundle(js, 7), times, str(tmp_path), lint=True)
    assert not errs
    vals = []
    for t in lint:
        txt = [x["text"] for x in lint[t]["boxes"] if x["text"].startswith("feet")]
        assert txt, (t, lint[t]["boxes"][:3])
        vals.append(float(txt[0].split()[1]))
    assert all(-0.06 < v < 0.06 for v in vals), vals


def test_a_held_3d_scene_is_not_static_and_the_figure_never_freezes(tmp_path):
    """The idle layer (camera, hero, light, motes) keeps a scene that does one move and then holds alive: consecutive
    frames of a hold change (the metric qa.frame_checks calls static is a 1 s window with almost no change), and
    they do not with the layer opted out. Frames 1/10 s apart, a 3 s window of a 9 s scene."""
    import numpy as np
    from PIL import Image

    def window(extra):
        js = ("const k = FX.stage3(tl, root, T, {look: 'clay'%s}); k.bars(tl, 0.3, [{v: 12, label: 'a'}, {v: 31, label: 'b'}, {v: 58, label: 'c'}], {highlight: 2});" % extra)
        times = [round(1.5 + i * 0.1, 2) for i in range(11)]
        pngs, errs = _shots(_bundle(js, 9), times, str(tmp_path))
        assert not errs
        fr = [np.asarray(Image.open(p).convert("L").resize((108, 192)), dtype=np.float32) / 255 for p in pngs]
        return [float(np.abs(b - a).mean()) for a, b in zip(fr, fr[1:])]
    on, off = window(", cadence: false"), window(", idle: false, cadence: false")   # the layer alone: no beats, the object's own move is long over
    assert max(off) < 0.0008, off                      # no layer: a hold is a frozen picture
    assert min(on) > 0.003 and max(on) > 0.004, on      # layer: every 0.1 s step moves, and the 1 s window clears qa.frame_checks' 0.004 static line
    assert np.mean(on) > 4 * np.mean(off)
    # a figure alone on a stage: its own idle (breath, weight shift, gaze) plus the layer
    js = "const k = FX.stage3(tl, root, T, {look: 'clay', cadence: false}); k.figure({});"
    pngs, errs = _shots(_bundle(js, 9), [round(1.5 + i * 0.1, 2) for i in range(11)], str(tmp_path))
    fr = [np.asarray(Image.open(p).convert("L").resize((108, 192)), dtype=np.float32) / 255 for p in pngs]
    assert not errs and max(float(np.abs(b - a).mean()) for a, b in zip(fr, fr[1:])) > 0.004


def test_held_scene_clip_counts_less_still_with_the_idle_layer(tmp_path):
    """The real measurement, on a rendered clip (factory/qa): the same 9 s scene with the layer opted out is a 'slideshow'
    (frozen seconds, long holds); with it nothing freezes, the longest still stretch shortens and the still share drops."""
    import htmlmotion
    from factory import qa

    def clip(extra, name):
        js = ("const k = FX.stage3(tl, root, T, {look: 'clay'%s}); k.bars(tl, 0.3, [{v: 12, label: 'a'}, {v: 31, label: 'b'}, {v: 58, label: 'c'}], {highlight: 2});" % extra)
        p = os.path.join(tmp_path, name + ".json")
        json.dump(_bundle(js, 9), open(p, "w"))
        mov = os.path.join(tmp_path, name + ".mp4")
        r = htmlmotion._node(p, mov, 9, ["--opaque", "--scale=0.25"], 30)
        assert r.returncode == 0, r.stderr[-300:]
        return qa.energy(mov), qa.frame_checks(mov), qa.frozen_time(mov)
    e_off, f_off, z_off = clip(", idle: false, cadence: false", "off")
    e_on, f_on, z_on = clip("", "on")
    assert f_off["static_share"] >= 0.5 and z_off["frozen_s"] >= 4 and e_off["longest_hold_s"] >= 6
    assert f_on["static_share"] <= 0.1 and z_on["frozen_s"] == 0
    # qa.energy counts a frame as still when under 1.5 % of it changes by 24 grey levels in 1/30 s: slow, gentle motion can
    # never clear that, only the beats do. So the layer shortens the holds and lowers the share, it does not erase it.
    assert e_on["longest_hold_s"] < 0.7 * e_off["longest_hold_s"] and e_on["still_share"] < e_off["still_share"] - 0.02, (e_on, e_off)


def test_beats_are_visible_and_deterministic(tmp_path):
    """k.beat('turn') changes the picture at the beat and only then; with the idle layer off nothing else moves."""
    from PIL import Image
    import numpy as np
    js = ("const k = FX.stage3(tl, root, T, {look: 'clay', idle: false, cadence: false}); k.bars(tl, 0.1, [{v: 12}, {v: 31}, {v: 58}], {dur: 0.3});"
          "k.beat(tl, 2.0, 'turn', {amount: 0.9, dur: 1}); k.beat(tl, 4, 'pulse', {amount: 0.15, dur: 0.8});")
    pngs, errs = _shots(_bundle(js, 6), [1.0, 1.6, 2.5, 3.2, 3.9, 4.4, 5.5], str(tmp_path))
    assert not errs
    im = [np.asarray(Image.open(p).convert("L"), dtype=np.float32) for p in pngs]
    d = lambda i, j: float(np.abs(im[i] - im[j]).mean())
    assert d(0, 1) < 0.15 and d(1, 2) > 0.5 and d(2, 3) > 0.3 and d(3, 4) < 0.5      # holds, turns (and stays turned), holds
    assert d(4, 5) > 0.1 and d(4, 6) < 0.5                                           # the pulse is a transient: size changes, then settles back
    # an unknown kind is an error, not a silent no-op
    pngs, errs = _shots(_bundle("const k = FX.stage3(tl, root, T, {look: 'clay'}); k.bars(tl, 0, [1, 2]); k.beat(tl, 1, 'wiggle');", 2), [1.0], str(tmp_path))
    assert errs and "wiggle" in " ".join(errs)


@pytest.mark.parametrize("cid", CARDS)
def test_figure_cards_keep_faces_in_the_safe_area(cid, tmp_path):
    """The head of every figure of a demo stays inside the platform-safe area at the card's mid-point (9:16 and 16:9)."""
    secs = float(R.get(cid)["seconds"])
    for w, h, (x0, x1, y0, y1) in ((1080, 1920, (60, 930, 170, 1500)), (1920, 1080, (80, 1840, 60, 850))):
        b = R.bundle(cid)
        b["w"], b["h"] = w, h
        probe = ("FX.onFrame(() => { const hs = (k.figures || []).map((f) => { const c = k.px([f.root.position.x, f.headY(), f.root.position.z]); return c[0].toFixed(0) + ':' + c[1].toFixed(0); });"
                 "  el.textContent = 'heads ' + hs.join(','); });")
        b["scenes"][0]["js"] += "const el = D('', 'left:5px;top:5px;font:700 40px Inter Tight;color:#fff');" + probe
        pngs, errs, lint = _shots(b, [round(secs * 0.55, 2)], str(tmp_path), lint=True)
        assert not errs, (cid, errs)
        txt = [x["text"] for x in next(iter(lint.values()))["boxes"] if x["text"].startswith("heads")]
        assert txt and len(txt[0]) > 6, (cid, txt)
        for hd in txt[0][6:].split(","):
            px, py = (float(v) for v in hd.split(":"))
            assert x0 < px < x1 and y0 < py < y1, (cid, w, hd)
