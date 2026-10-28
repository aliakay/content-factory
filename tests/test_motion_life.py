"""The alive kit (living characters, idle loops, the illustrated rig), the kinetic kit (type on the beat), the reference
motion study and the measured motion gates the designer checks before a preview."""
import math, os, re, subprocess

import numpy as np

from factory import capabilities, motiondesign, motionref, qa

ROOT = os.path.join(os.path.dirname(__file__), "..")


def _clip(path, frame, n=120, fps=30, size=(320, 480)):
    """A synthetic clip: frame(i) -> HxWx3 uint8."""
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{size[0]}x{size[1]}",
                          "-r", str(fps), "-i", "-", "-pix_fmt", "yuv420p", path], stdin=subprocess.PIPE)
    for i in range(n):
        p.stdin.write(frame(i).tobytes())
    p.stdin.close()
    p.wait()
    return path


def _bob(i):
    f = np.full((480, 320, 3), 235, np.uint8)
    dy = round(2 * math.sin(2 * math.pi * i / 60))       # ±2 px on a 100 px body, a 2 s period
    f[200 + dy:300, 110:210] = (40, 60, 200)
    return f


def test_fxlib_has_life_kinetic_and_rig():
    js = open(os.path.join(ROOT, "motion", "templates", "fxlib.js")).read()
    names = set(re.findall(r"FX\.(\w+) = ", js))
    assert {"alive", "act", "land", "hop", "float", "sway", "breathe", "bob", "flicker", "glow", "spin", "drift", "steam",
            "ripples", "weather", "buzz", "jiggle", "character", "kinetic", "ground", "hitFx", "charge", "cutRun", "tvOff",
            "zoomLetter", "typePrompt", "picture", "B"} <= names
    for fn in ("wave", "loop", "bell", "seg", "seeded", "track", "flow"):
        assert re.search(rf"\b{fn}[:(]", js)
    assert "Math.random" not in js and "setTimeout" not in js and "requestAnimationFrame" not in js


def test_motion_study_measures_a_subtle_bob():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        clip = _clip(os.path.join(tmp, "bob.mp4"), _bob)
        m = motionref.study(clip)
        assert m["verdict"] == "subtle idle life"
        assert 3 <= m["bob_pct"] <= 5.5 and m["sway_pct"] < 1
        assert abs(m["period_s"] - 2.0) < 0.15
        assert motionref.colors(clip, 1.0, [(150, 250), (5, 5)])[1][2] == "#EBEBEB"
        en = qa.energy(clip)
        assert en["still_share"] > 0.9 and en["cuts_per_10s"] == 0     # a 2 px bob is "still" for a kinetic reel
        assert "subtle idle life" in motionref.summary({**m, "energy": en})


def test_energy_counts_cuts_and_holds():
    import tempfile
    def flips(i):      # a colour flip every 0.5 s, then a 1.5 s hold
        f = np.zeros((480, 320, 3), np.uint8)
        f[:] = (250, 200, 30) if (i // 15) % 2 and i < 75 else (10, 16, 32)
        return f
    with tempfile.TemporaryDirectory() as tmp:
        en = qa.energy(_clip(os.path.join(tmp, "flip.mp4"), flips, n=120))
        assert en["cuts_per_10s"] >= 10
        assert en["longest_hold_s"] >= 1.4


def test_window_is_inside_the_longest_shot():
    a, d = motionref.window(10.0, [2.0, 3.0])
    assert 3.0 <= a and a + d <= 10.0 and d <= 3.0


def test_alive_and_kinetic_techniques_reach_the_designer_and_renderer():
    techs = [c["id"] for c in capabilities.catalogue("topic")]
    for k in ("look.alive", "look.living_world", "look.kinetic_type", "look.picture_alive", "look.motion_blur",
              "story.beat_film"):
        assert k in techs
    d = capabilities.apply({"techniques": ["story.beat_film", "look.kinetic_type", "look.alive"],
                            "ref_motion": [{"ref": "r1.mp4", "motion": "subtle idle life: bob 3 %"}]}, {})
    assert d["motion_blur"] == 4 and d["post_fx"]["bloom"] and d["duration_cap"] == 50
    notes = capabilities.designer_notes(d)
    assert "FX.alive" in notes and "FX.kinetic" in notes and "REFERENCE MOTION" in notes and "bob 3 %" in notes
    assert "hide_captions" in capabilities.writer_notes(d)
    assert "FX.character" in motiondesign.fx_doc() and "FX.kinetic" in motiondesign.fx_doc()
    assert "ALIVE" in motiondesign.MOTION_DOCTRINE and "KINETIC" in motiondesign.MOTION_DOCTRINE


def test_bloom_and_beat_grid():
    import sys
    sys.path.insert(0, os.path.join(ROOT, "bin"))
    import htmlmotion
    vf = htmlmotion.post_vf({"bloom": 0.4, "grain": 0.2})
    assert vf.startswith("split[bl_a][bl_b]") and "blend=all_mode=screen" in vf and "noise=" in vf
    assert htmlmotion.beat_grid({}) == {}
    assert htmlmotion.beat_grid({"music": {"file": "does/not/exist.mp3"}}) == {}
