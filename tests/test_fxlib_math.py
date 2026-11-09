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
