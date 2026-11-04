"""Partial render (t511): a fixed scene re-renders itself and its neighbours, the rest of the capture is reused, the
parts join to the exact frame count and the result shows the fix."""
import importlib.util, json, os, shutil, subprocess, uuid

import pytest

from factory import config


def _hm():
    spec_ = importlib.util.spec_from_file_location("htmlmotion", os.path.join(config.ROOT, "bin", "htmlmotion.py"))
    hm = importlib.util.module_from_spec(spec_)
    spec_.loader.exec_module(hm)
    return hm


COLOURS = ["#ff0000", "#00ff00", "#0000ff", "#ffff00"]


def _bundle(colours):
    scenes = [{"id": f"s{i}", "start": i * 1.0, "end": (i + 1) * 1.0, "hide_captions": True, "lines_t": [], "html": "",
               "css": f"position:absolute;inset:0;background:{c}", "js": ""} for i, c in enumerate(colours)]
    return {"palette": {}, "global_css": "", "words": [], "duration": float(len(colours)), "w": 1080, "h": 1920,
            "lang": "en", "captions": {}, "scenes": scenes}


def test_parts_follow_scene_starts_and_neighbours():
    hm = _hm()
    a = hm.scene_parts(_bundle(COLOURS), 40, 10)
    assert [(x, y) for x, y, _ in a] == [(0, 10), (10, 20), (20, 30), (30, 40)]
    b = hm.scene_parts(_bundle(COLOURS[:3] + ["#ffffff"]), 40, 10)
    assert [x[2] == y[2] for x, y in zip(a, b)] == [True, True, False, False]       # scene 4 and its neighbour
    c = hm.scene_parts(_bundle(["#ffffff"] + COLOURS[1:]), 40, 10)
    assert [x[2] == y[2] for x, y in zip(a, c)] == [False, False, True, True]
    g = _bundle(COLOURS)
    g["global_css"] = ".x{}"
    assert all(x[2] != y[2] for x, y in zip(a, hm.scene_parts(g, 40, 10)))          # a shared change: every part
    same = hm.scene_parts(_bundle(["#000000"] * 6), 60, 10)
    assert len({x[2] for x in same}) == 6                                           # identical scenes, distinct parts


def _pixel(path, t):
    r = subprocess.run([config.FFMPEG, "-v", "error", "-ss", str(t), "-i", path, "-frames:v", "1", "-vf", "scale=1:1",
                        "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True)
    return tuple(r.stdout[:3])


def test_a_fixed_scene_re_renders_only_its_parts(tmp_path):
    from factory.hat import tools as T
    if not T.available("render_stills")[0]:
        pytest.skip("no chromium here")
    hm = _hm()
    work = os.path.join(config.ROOT, "work", "test_parts_" + uuid.uuid4().hex[:8])
    os.makedirs(work)
    try:
        bp, cache, out, cues = (os.path.join(work, x) for x in ("bundle.json", "parts", "silent.mp4", "cues.json"))
        flags = ["--opaque", "--scale=0.25"]
        json.dump(_bundle(COLOURS), open(bp, "w"))
        r = hm.capture_parts(bp, out, 4.0, flags, 10, cues, cache)
        assert r == {"parts": 4, "rendered": 4} and hm.frame_count(out) == 40 and os.path.exists(cues)
        assert _pixel(out, 3.5)[2] < 60 and _pixel(out, 3.5)[0] > 200                   # yellow at the end
        assert hm.capture_parts(bp, out, 4.0, flags, 10, cues, cache) == {"parts": 4, "rendered": 0}
        json.dump(_bundle(COLOURS[:3] + ["#ffffff"]), open(bp, "w"))
        assert hm.capture_parts(bp, out, 4.0, flags, 10, cues, cache) == {"parts": 4, "rendered": 2}
        assert hm.frame_count(out) == 40 and min(_pixel(out, 3.5)) > 200                 # the fix shows
        assert _pixel(out, 0.5)[0] > 200 and _pixel(out, 0.5)[1] < 60                    # the reused start is intact
        assert len([f for f in os.listdir(cache) if f.endswith(".mp4")]) == 4            # no stale parts kept
        assert hm.capture_parts(bp, out, 4.0, ["--opaque", "--scale=0.5"], 10, cues, cache)["rendered"] == 4
    finally:
        shutil.rmtree(work, ignore_errors=True)
