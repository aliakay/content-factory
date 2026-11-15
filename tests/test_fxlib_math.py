"""The scene library's pure maths (springs, keyframes, pulse, cues, mouth) — checked by running the real JS in node.

These helpers are what a per-frame layer draws with, so they must be pure: same t, same value, in any order. The test
executes `motion/templates/fxlib.js` under node with a stub window (no browser, no gsap call at load time) and reads
the numbers back.
"""
import json, shutil, subprocess

import pytest

ROOT = "."


def _node(src):
    if not shutil.which("node"):
        pytest.skip("node is not installed on this machine")
    p = subprocess.run(["node", "-e", src], capture_output=True, text=True, timeout=30)
    assert p.returncode == 0, p.stderr[-500:]
    return json.loads(p.stdout.strip().splitlines()[-1])


def _fx(body):
    return _node(f'''
global.window = {{}};
const fs = require("fs");
new Function("window", fs.readFileSync("motion/templates/fxlib.js", "utf8"))(global.window);
const FX = global.window.FX;
{body}''')


def test_a_spring_starts_at_zero_and_settles_at_one():
    out = _fx('console.log(JSON.stringify({s0: FX.spring(0), early: FX.spring(0.001), late: FX.spring(2)}))')
    assert out["s0"] == 0 and out["early"] < 0.01 and out["late"] == pytest.approx(1.0, abs=1e-3)


def test_the_presets_differ_by_overshoot():
    out = _fx('''const pick = (s) => Math.max(...Array.from({length: 240}, (_, i) => FX.spring(i / 60, s)));
console.log(JSON.stringify({bouncy: pick(FX.SPRINGS.bouncy), ui: pick(FX.SPRINGS.ui), heavy: pick(FX.SPRINGS.heavy)}))''')
    assert out["bouncy"] > 1.15 and out["ui"] < 1.05 and out["heavy"] <= out["ui"]


def test_a_spring_value_does_not_depend_on_the_order_frames_are_drawn():
    out = _fx('''const ts = [0.05, 0.2, 0.4, 0.9];
const fwd = ts.map((t) => FX.spring(t));
const back = [...ts].reverse().map((t) => FX.spring(t)).reverse();
console.log(JSON.stringify({same: JSON.stringify(fwd) === JSON.stringify(back), first: fwd}))''')
    assert out["same"] is True


def test_keyframes_ease_and_a_re_aimed_target_stays_continuous():
    out = _fx('''console.log(JSON.stringify({
      mid: FX.keys(0.5, [[0, 0], [1, 10, "linear"]]),
      arr: FX.keys(0.5, [[0, [0, 0]], [1, [10, 20], "linear"]]),
      spring_to: FX.springTo(0.5, [[0, 0], [0.4, 10]])}))''')
    assert out["mid"] == pytest.approx(5.0, abs=0.01)
    assert out["arr"] == pytest.approx([5.0, 10.0], abs=0.01)
    assert 0 < out["spring_to"] < 15


def test_pulse_rises_and_falls_inside_its_window():
    out = _fx('''console.log(JSON.stringify({off: FX.pulse(-0.1, 0, 1), peak: FX.pulse(0.5, 0, 1, 0.25, 0.25), after: FX.pulse(1.2, 0, 1)}))''')
    assert out["off"] == 0 and out["peak"] == pytest.approx(1.0, abs=0.01) and out["after"] == 0


def test_a_cue_throws_when_its_word_is_gone():
    out = _fx('''let threw = false;
try { FX.cue([["a", 0, 1]], "zzz"); } catch (e) { threw = true; }
console.log(JSON.stringify({threw, at: FX.cue([["Merhaba", 1.2, 1.6]], "merh", 0.1)}))''')
    assert out["threw"] is True and out["at"] == pytest.approx(1.3)


# ---------------------------------------------------------------- the mouth curve that drives FX.mouth
def test_the_mouth_curve_follows_the_voice_and_is_deterministic(tmp_path):
    from factory import mouthcurve as M
    wav = M.write_wav(str(tmp_path / "t.wav"), 2.0)
    c = M.curve(wav)
    assert len(c["open"]) == 60 and c["fps"] == 30
    peak = max(range(len(c["open"])), key=lambda i: c["open"][i])
    assert 0.2 <= peak / c["fps"] <= 0.7                  # the burst is 0.2–0.6 s; the 40 ms lead is inside it
    assert max(c["open"]) > 0.8 and min(c["open"]) == 0.0
    assert c == M.curve(wav)                              # same wav, same curve
    assert set(c["shape"]) - {"closed", "open", "wide", "round"} == set()


def test_word_weighted_draft_timing_puts_the_long_word_last_longer():
    from factory.hat import explainer as X
    words, line_times, dur = X.draft_timing(["Elektrik faturası iki kat arttı, neden?"], "tr")
    span = {w: e - s for w, s, e in words}
    assert span["Elektrik"] >= 1.8 * span["iki"]          # letters decide the interval, not the word count
    assert dur == pytest.approx(line_times[0]["end"])


# ---------------------------------------------------------------- texture, build-in and ambience maths (F26/F37/F43)
def test_the_entrance_pace_caps_a_ghost_layer_and_keeps_an_authored_one():
    out = _fx('''const long = FX.pace(2.5, "pop"), text = FX.pace(3, "text"), kept = FX.pace(2.5, "pop", {slow: true}),
      short = FX.pace(0.3, "pop"), clamps = FX._clamps;
console.log(JSON.stringify({long, text, kept, short, clamps, n: Object.keys(clamps).length}))''')
    assert out["long"] == 0.5 and out["text"] == 0.9 and out["short"] == 0.3      # pop 0.5 s, text 0.9 s
    assert out["kept"] == 2.5                                                    # {slow: true} is the escape hatch
    assert out["n"] == 2 and out["clamps"]["pop:2.50"]["got"] == 0.5             # the clamp is reported, once


def test_the_build_in_orders_its_groups_and_fits_the_forty_percent():
    out = _fx('''const g = [{n: 4}, {n: 2}, {n: 1}, {n: 1}];
console.log(JSON.stringify({six: FX.buildPlan(g, {dur: 6}), two: FX.buildPlan(g, {dur: 2}), open: FX.buildPlan(g)}))''')
    six, two = out["six"], out["two"]
    assert [p["kind"] for p in six["plan"]] == ["room", "object", "person", "label"]
    assert [p["at"] for p in six["plan"]] == [0.15, 0.30, 0.45, 0.80]           # 0.15 / 0.15 / 0.35 s apart
    assert all(p["dur"] == 0.35 for p in six["plan"]) and six["total"] == pytest.approx(1.15)
    assert six["scale"] == 1                                                    # a 6 s shot has room for the whole build
    assert two["scale"] < 1 and two["total"] == pytest.approx(0.8)               # a 2 s shot: 40 % = 0.8 s, compressed
    assert two["plan"][-1]["at"] + two["plan"][-1]["dur"] <= 0.8 + 1e-9
    assert all(p["at"] + p["dur"] <= 0.8 + 1e-9 for p in two["plan"])
    assert out["open"]["scale"] == 1 and out["open"]["total"] == pytest.approx(1.15)


def test_value_noise_is_seeded_and_stable():
    out = _fx('''const a = FX.texNoise(3.25, 7.5, 5), b = FX.texNoise(3.25, 7.5, 5), c = FX.texNoise(3.25, 7.5, 6);
const f = FX.texFbm(12.5, 4.25, 9, 3), g = FX.texFbm(12.5, 4.25, 9, 3);
console.log(JSON.stringify({a, same: a === b, differs: a !== c, f, fsame: f === g, inRange: a >= 0 && a <= 1 && f >= 0 && f <= 1,
  rgb: [FX.rgbOf("#ff5a5f"), FX.rgbOf("rgba(0,120,191,.55)")], op: FX.TEX_OPACITY}))''')
    assert out["same"] is True and out["differs"] is True and out["fsame"] is True
    assert out["inRange"] is True and 0 < out["a"] < 1 and 0 < out["f"] < 1
    assert out["rgb"] == [[255, 90, 95], [0, 120, 191]]
    assert out["op"]["paper"] > out["op"]["scanlines"] and set(out["op"]) == {"paper", "watercolor", "chalk", "halftone",
                                                                             "hatching", "grain", "scanlines"}


def test_the_ambience_frame_is_a_pure_function_of_t_and_stays_cheap():
    out = _fx('''const a = FX.ambienceFrame("rain", "s", 1.0, 1080, 1920), b = FX.ambienceFrame("rain", "s", 1.0, 1080, 1920),
      c = FX.ambienceFrame("rain", "s", 2.5, 1080, 1920), d = FX.ambienceFrame("rain", "s", 1.0, 1080, 1920, {density: 0.3});
const counts = Object.fromEntries(["snow","dust","embers","confetti"].map((k) => [k, FX.ambienceFrame(k, "s", 2, 1080, 1920).shapes.length]));
console.log(JSON.stringify({same: JSON.stringify(a) === JSON.stringify(b), moved: JSON.stringify(a) !== JSON.stringify(c),
  n: a.shapes.length, thin: d.shapes.length, counts, blend: [a.blend, FX.ambienceFrame("dust", "s", 1, 1080, 1920).blend],
  kinds: a.shapes.map((s) => s.t).slice(0, 3)}))''')
    assert out["same"] is True and out["moved"] is True
    assert out["n"] < 500 and out["thin"] < out["n"]                  # a few hundred shapes a frame, density scales them
    assert out["blend"] == ["normal", "add"] and set(out["kinds"]) <= {"streak", "ring", "dot", "chip"}
    assert all(5 < v < 400 for v in out["counts"].values())


def test_confetti_is_thrown_once_and_lands_on_the_floor():
    out = _fx('''const f = (t) => FX.ambienceFrame("confetti", "c", t, 1080, 1920).shapes;
const early = f(0.05), mid = f(2.0), late = f(8.0);
const landed = (sh) => sh.filter((s) => s.flip === FX.AMB.confettiLie).length;
console.log(JSON.stringify({early: early.length, mid: mid.length, late: late.length, lateLanded: landed(late),
  lateY: late.map((s) => s.y), ceil: Math.max(...late.map((s) => s.y)), colours: new Set(late.map((s) => s.c)).size}))''')
    assert out["early"] < out["mid"] and out["late"] == out["mid"]          # nothing new is thrown after launch
    assert out["lateLanded"] == out["late"]                                 # every paper has settled
    assert out["ceil"] <= 1920 * 0.97 + 1                                   # none hangs in the air
    assert out["colours"] >= 4                                              # a mix, not one ink
