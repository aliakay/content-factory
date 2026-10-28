"""The editing capabilities: technique catalogue + recipes, the sound kit, sound-effect rules, the layout / reading /
motion checks, the ears (sound QA), review sheets and the talking-head editor."""
import json, os, shutil, subprocess

import numpy as np
import pytest

from factory import audiofx, capabilities, layoutlint, planner, sfx, sheets, soundqa, talk
from factory.config import FFMPEG, ROOT

HAVE_FFMPEG = shutil.which(FFMPEG) or os.path.exists(FFMPEG)
needs_ffmpeg = pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg not installed")


# ---------- techniques + recipes ----------
def test_catalogue_combines_freely_with_one_shape_and_one_style():
    ids = capabilities.clean(["style.noir", "style.blueprint", "story.rules_arc", "story.problem_fix", "look.acting",
                              "edit.jump_cuts", "nope"], "topic")
    assert ids == ["style.noir", "story.rules_arc", "look.acting"]   # planner order wins, talk-only and unknown dropped
    assert "edit.jump_cuts" in capabilities.clean(["edit.jump_cuts"], "talk")
    assert capabilities.clean([], "talk") == capabilities.clean(capabilities.DEFAULTS["talk"], "talk")
    assert all(not c.get("always") for c in capabilities.CAPS.values() if c["area"] != "check")
    assert any(k.startswith("style.") for k in capabilities.CAPS)       # film styles come from data/film_styles.json


def test_apply_pins_switches_and_length_and_notes_reach_every_stage():
    d = capabilities.apply({"direction": "Night shift at a gas station; the radio is the clock.",
                            "techniques": ["story.rules_arc", "style.archive_film", "voice.tighten", "look.story_hud"]}, {})
    assert d["fiction"] and d["voice_fx"] == {"tighten": True} and d["captions"]["pos"] == "mid"
    assert d["post_fx"]["grain"] > 0 and d["duration_cap"] == 98
    assert capabilities.words(d) == (200, 245) and capabilities.seconds(d, [28, 36]) == [78, 98]
    w, ds = capabilities.writer_notes(d), capabilities.designer_notes(d)
    assert "Night shift" in w and "STORY SHAPE" in w and "hud" in w
    assert "FILM STYLE Archive newsreel" in ds and "FX.hud" in ds and "STORY SHAPE" not in ds
    d2 = capabilities.apply({"techniques": [], "seconds": 30}, {})
    assert d2["recipe"]["seconds"] == [25, 35] and not capabilities.fiction(d2)


def test_planner_keeps_the_art_direction_as_a_recipe():
    cat = {"channels": [{"id": "bilgi", "mode": "topic"}], "looks": ["auto"], "series": [], "refs": [], "voices": [],
           "presets": [{"id": "explainer_short", "mode": "topic"}, {"id": "talking_head", "mode": "talk"}],
           "footage": {"places": []}}
    p = planner.clean({"kind": "topic", "direction": "d", "techniques": ["look.acting", "edit.jump_cuts"], "seconds": 45,
                       "benchmark": {"learn": "Kurzgesagt pacing", "avoid": "their characters"},
                       "treatments": [{"label_tr": "A", "techniques": ["style.noir"], "seconds": 60}]}, {}, cat)
    assert p["techniques"] == ["look.acting"] and p["seconds"] == 45 and p["treatments"][0]["techniques"] == ["style.noir"]
    r = planner.recipe_of(p)
    assert r["techniques"] == ["look.acting"] and "Kurzgesagt" in r["direction"] and r["seconds"] == 45
    t = planner.clean({"kind": "topic"}, {"talk": "raw/talk/x.mp4"}, cat)   # an uploaded talking video makes it a talk edit
    assert t["kind"] == "talk" and t["format"] == "talking_head" and "edit.jump_cuts" in t["techniques"]
    assert planner.clean({"kind": "talk"}, {}, cat)["kind"] == "topic"


# ---------- sound kit ----------
def _tone(path, spans, dur, f=220, gain=1):
    expr = "+".join(f"between(t,{a},{b})" for a, b in spans)
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", f"sine=f={f}:d={dur}", "-af",
                    f"volume='if({expr},{gain},0)':eval=frame", "-ar", "48000", str(path)], check=True)


@needs_ffmpeg
def test_tighten_cuts_only_real_silences_and_remaps_words(tmp_path):
    src = tmp_path / "v.wav"
    _tone(src, [(0.2, 0.8), (1.8, 2.4), (2.6, 3.2)], 4)
    words = [["a", 0.2, 0.8], ["b", 1.8, 2.4], ["c", 2.6, 3.2]]
    dst, ranges, w2 = audiofx.tighten(str(src), str(tmp_path / "t.wav"), words)
    assert len(ranges) == 2                                       # the 1 s gap was cut, the 0.2 s gap kept
    assert abs((w2[1][1] - w2[0][2]) - 0.16) < 0.03               # it keeps ~0.16 s of air
    assert abs((w2[2][1] - w2[1][2]) - 0.2) < 0.01
    assert abs(len(audiofx.decode(dst)) / 16000 - (4 - (1.0 - 0.16))) < 0.05


def test_gaps_keep_a_breath_that_is_not_silence():
    sr = 16000
    y = np.zeros(sr * 3, np.float32)
    y[int(0.2 * sr):int(0.8 * sr)] = 0.5
    y[int(1.2 * sr):int(1.4 * sr)] = 0.08                         # a breath inside the gap
    y[int(1.8 * sr):int(2.4 * sr)] = 0.5
    assert audiofx.gaps([["a", 0.2, 0.8], ["b", 1.8, 2.4]], y, sr) == []


def test_drop_offset_music_automation_and_tempo_pitch():
    assert audiofx.drop_offset(12.0, 9.5) == {"seek": 2.5, "delay": 0.0}
    assert audiofx.drop_offset(4.0, 9.0) == {"seek": 0.0, "delay": 5.0}
    assert "between(t,3.400,6.200)" in audiofx.mute_expr([[3.4, 6.2]])
    assert audiofx.tempo_pitch(1.0, 0) == "" and "atempo=1.0400" in audiofx.tempo_pitch(1.04, 0)
    assert "asetrate" in audiofx.tempo_pitch(1.0, -1)


@needs_ffmpeg
def test_drop_time_finds_the_jump(tmp_path):
    p = tmp_path / "m.wav"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "anoisesrc=d=14:c=pink:a=0.3", "-af",
                    "volume='if(gt(t,6),1,0.08)':eval=frame", str(p)], check=True)
    t = audiofx.drop_time(str(p))
    assert t is not None and abs(t - 6.0) < 0.35


# ---------- sound effects ----------
def test_cues_thin_busy_windows_rotate_takes_and_climb():
    raw = [{"kind": "pop", "t": 1 + i * 0.3} for i in range(14)] + [{"kind": "impact", "t": 2.05}, {"kind": "nope", "t": 3}]
    c = sfx.clean_cues(raw, 30)
    assert len(c) <= 9 and any(x["kind"] == "impact" for x in c)  # the story sound survives the thinning
    pops = [x for x in c if x["kind"] == "pop"]
    assert pops[1].get("take") == 1 and pops[1].get("semitones") == 1
    r = sfx.to_render([sfx.cue("click", 1.0), sfx.cue("impact", 2.0)])
    assert r[0]["start"] < 1.0 and r[1]["start"] > 2.0           # clicks lead their press, impacts land a frame after


def test_no_mask_moves_small_cues_into_gaps_and_lowers_big_ones():
    words = [["a", 0.0, 1.0], ["b", 1.2, 2.0]]
    out = audiofx.no_mask([{"t": 0.95, "kind": "pop", "gain_db": -8}, {"t": 0.5, "kind": "impact", "gain_db": -6}], words)
    assert out[0]["t"] > 1.0 and out[0]["gain_db"] == -8
    assert out[1]["t"] == 0.5 and out[1]["gain_db"] < -6


def test_library_has_the_story_and_ad_kit():
    sfx.build_library()
    for k in ("knock", "clunk", "glass", "impact", "logo_hit", "notify", "flip", "drone"):
        assert os.path.exists(os.path.join(sfx.LIB, f"{k}.wav")) and k in sfx.KINDS
    assert os.path.exists(sfx.take_file("pop", 1, 2))


# ---------- layout / reading / motion checks ----------
def test_layout_check_finds_safe_zone_overlap_contrast_and_tiny(tmp_path):
    from PIL import Image
    img = tmp_path / "s.png"
    Image.new("RGB", (1080, 1920), (20, 20, 20)).save(img)
    lint = {"1.00": {"file": str(img), "cap": {"x": 40, "y": 1540, "w": 1000, "h": 170}, "boxes": [
        {"scene": "a", "text": "EDGE TEXT", "x": 900, "y": 600, "w": 170, "h": 60, "color": "rgb(255, 255, 255)", "size": 50},
        {"scene": "a", "text": "ONE", "x": 100, "y": 400, "w": 300, "h": 80, "color": "rgb(255, 255, 255)", "size": 60},
        {"scene": "a", "text": "TWO", "x": 150, "y": 420, "w": 300, "h": 80, "color": "rgb(255, 255, 255)", "size": 60},
        {"scene": "a", "text": "dark on dark", "x": 100, "y": 800, "w": 300, "h": 40, "color": "rgb(30, 30, 30)", "size": 32},
        {"scene": "a", "text": "fine print", "x": 100, "y": 900, "w": 200, "h": 20, "color": "rgb(255, 255, 255)", "size": 16},
        {"scene": "a", "text": "LOW", "x": 100, "y": 1560, "w": 300, "h": 80, "color": "rgb(255, 255, 255)", "size": 60}]}}
    kinds = {(f["kind"], f["text"]) for f in layoutlint.check(lint)}
    assert ("safe", "EDGE TEXT") in kinds and ("overlap", "ONE") in kinds and ("contrast", "dark on dark") in kinds
    assert ("tiny", "fine print") in kinds and ("caption", "LOW") in kinds
    assert not any(f["text"] == "LOW" and f["kind"] == "caption" for f in layoutlint.check(lint, hide_caps=("a",)))


def test_readcheck_flags_lines_too_short_to_read_and_passes_motion_findings():
    samples = [[round(t * 0.2, 2), [["a", "A LONG LINE OF SEVEN WORDS HERE"]] if 5 <= t < 8 else [["a", "HELD TITLE"]]]
               for t in range(20)]
    out = layoutlint.readcheck({"step": 0.2, "samples": samples, "motion": [{"kind": "dead", "scene": "b", "t": 2, "detail": "x"}]})
    kinds = {(f["kind"], f["text"]) for f in out}
    assert ("unread", "A LONG LINE OF SEVEN WORDS HERE") in kinds and ("unread", "HELD TITLE") not in kinds
    assert ("dead", "") in kinds and layoutlint.hold_needed("one two") == 1.2


def test_review_sheet_times_and_tiling(tmp_path):
    from PIL import Image
    times, labels = sheets.review_times([{"id": "a", "start": 0, "end": 4}, {"id": "b", "start": 4, "end": 8}])
    assert 3.8 in times and 4.2 in times and len(times) == len(labels) == 7
    paths = []
    for i, t in enumerate(times):
        p = tmp_path / f"shot_{t:06.2f}.png"
        Image.new("RGB", (108, 192), (i * 30 % 255, 80, 120)).save(p)
        paths.append(str(p))
    assert set(sheets.by_time(paths)) == {round(t, 2) for t in times}
    out = sheets.tile(paths, str(tmp_path / "sheet.png"), cols=4, width=100, labels=labels, title="t")
    assert Image.open(out).size[0] == 4 * 108 + 8


# ---------- the ears ----------
@needs_ffmpeg
def test_ears_hear_clicks_a_cut_tail_and_density(tmp_path):
    p = tmp_path / "mix.wav"
    _tone(p, [(0.5011, 3.0013), (3.5017, 9.99)], 10, f=233, gain=5)   # hard gates off a zero crossing; ends mid-sound
    cues = [{"t": 4.2 + i * 0.45, "kind": "pop", "gain_db": -8} for i in range(12)]
    r = soundqa.review(str(p), cues, [["w", 0.5, 9.9]], lufs=(-14.0, -2.0))
    kinds = {f["kind"] for f in r["findings"]}
    assert {"clicks", "tail", "density", "machinegun", "masked"} <= kinds
    out = soundqa.sheet(str(p), str(tmp_path / "s.png"), cues, [["w", 0.5, 9.9]])
    assert os.path.getsize(out) > 1000 and soundqa.as_text(r)


def test_ears_flag_a_silent_film(tmp_path):
    r = soundqa.review(str(tmp_path / "missing.mp4"), total=30)
    assert r["findings"][0]["kind"] == "silent"


# ---------- talking head ----------
def _words(text, gap=0.1, start=0.3, wd=0.3):
    out, t = [], start
    for w in text.split():
        out.append([w, round(t, 3), round(t + wd, 3), 0.9])
        t += wd + gap
    return out


def test_phrases_flag_retakes_false_starts_fillers_and_stutters():
    w = (_words("So um the big idea", start=0.5) + _words("The big idea is simple.", start=3.4) +
         _words("You should", start=6.0) + _words("You ship daily.", start=7.2) + _words("uh", start=9.0) +
         _words("the plan the plan is ready.", start=10.0))
    ph = talk.phrases(w, "en")
    assert ph[0]["flags"] == ["retake"] and ph[0]["fillers"] == [1]
    assert ph[2]["flags"] == ["false_start"] and ph[4]["flags"] == ["filler_only"]
    assert [w[i][0] for i in ph[5]["repeats"]] == ["the", "plan"]


def test_segments_are_frame_aligned_and_words_follow_the_cut():
    w = _words("one two three", start=0.5) + _words("four five six.", start=3.0)
    a = {"words": w, "phrases": talk.phrases(w, "en"), "duration": 6, "fps": 30, "faces": [(1, 0.6, 0.4, 0.2)]}
    e = talk.rough_edit(a, [2, 30])
    e["order"] = list(reversed(e["order"]))                        # the stronger line first
    e["punch"] = [{"id": e["order"][0], "word": 1, "zoom": 1.2}]
    segs, ow, total, starts = talk.segments(a, e, 30)
    assert [x[0] for x in ow] == ["four", "five", "six.", "one", "two", "three"]
    assert abs(total - sum(s["frames"] for s in segs) / 30) < 1e-3
    assert any(s["zoom"] == 1.2 for s in segs) and all(s["cx"] == 0.6 for s in segs)
    assert all(ow[i][1] <= ow[i + 1][1] for i in range(len(ow) - 1))


def test_clean_edit_keeps_real_ids_and_clamps():
    w = _words("a b c d e f.", start=0.2)
    a = {"words": w, "phrases": talk.phrases(w, "en"), "duration": 4, "fps": 30, "faces": []}
    e = talk.clean_edit({"order": [0, 0, 7, "x"], "punch": [{"id": 0, "word": 99, "zoom": 3}],
                         "broll": [{"id": 0, "word": 2, "kind": "weird", "text": "hi", "dur": 9}], "grade": "neon"}, a)
    assert e["order"] == [0] and e["punch"][0] == {"id": 0, "word": 5, "zoom": 1.25}
    assert e["broll"][0]["kind"] == "kinetic" and e["broll"][0]["dur"] == 2.4 and e["grade"] == "film"


@needs_ffmpeg
def test_talk_compiles_and_renders_end_to_end(tmp_path):
    """A synthetic raw video through compile_spec + bin/talkcut.py (preview): cuts, crop, overlay, mix."""
    if not shutil.which("node") or not os.path.exists(os.path.join(ROOT, "motion", "node_modules", "playwright")):
        pytest.skip("node + playwright not installed")
    os.makedirs(os.path.join(ROOT, "raw", "talk"), exist_ok=True)
    src = os.path.join(ROOT, "raw", "talk", "pytest_talk.mp4")
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=1280x720:r=30:d=6", "-f", "lavfi",
                    "-i", "sine=f=200:d=6", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", src],
                   check=True)
    w = _words("ship every single day.", start=0.3) + _words("you learn ten times faster.", start=3.0)
    a = {"src": os.path.relpath(src, ROOT), "lang": "en", "w": 1280, "h": 720, "fps": 30, "duration": 6, "words": w,
         "phrases": talk.phrases(w, "en"), "faces": [], "accent": "#ff8a3d"}
    ap = tmp_path / "a.json"
    json.dump(a, open(ap, "w"))
    e = talk.rough_edit(a, [2, 30])
    e["broll"] = [{"id": 1, "word": 2, "kind": "stat", "text": "10x", "label": "faster", "accent": "", "items": [], "dur": 1.2}]
    e["keywords"] = {"key": ["faster"], "danger": []}
    p = {"name": "pytest_talk", "data": {"kind": "talk", "analysis": str(ap), "edit": e, "aspect": "9:16"}}
    spec, total, starts, warn = talk.compile_spec(None, p)
    assert spec["engine"] == "talk" and spec["broll"] and spec["keys"].get("faster") == "key"
    path = tmp_path / "spec.json"
    json.dump(spec, open(path, "w"))
    import sys
    sys.path.insert(0, os.path.join(ROOT, "bin"))
    import talkcut
    dst, dur = talkcut.main(str(path), preview=True)
    assert os.path.exists(dst) and abs(dur - total) < 0.01
    os.remove(src)
