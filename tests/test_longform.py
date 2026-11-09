"""The long explainer line (t507): chapters, parts, the outline check, parallel designers, chapter cards, the progress
bar, chunked narration, sliced capture and the YouTube chapter marks."""
import json, os, shutil, subprocess

import pytest

from factory.hat import explainer as X, longform as LF, project as P


@pytest.fixture(autouse=True)
def no_real_llm(monkeypatch):
    from factory import llm
    def refuse(*a, **k):
        raise AssertionError("a test tried to call a real model")
    for name in ("ask_text", "ask", "ask_json"):
        if hasattr(llm, name):
            monkeypatch.setattr(llm, name, refuse)


@pytest.fixture
def d(tmp_path):
    return str(tmp_path / "projects")


LINES = ["Gas crossed one hundred euros today.", "Here is why, and what comes next.",
         "Part one: why it rose.", "Storage was low after a cold March.", "Then a pipeline stopped for repairs.",
         "Part two: who pays.", "Factories pay first.", "Households pay later.",
         "Part three: what next.", "Summer refills decide the winter.", "Watch the storage number.", "Subscribe for more."]
def _cam(move, target):
    return {"move": move, "seconds": 1.5, "easing": "ease_out", "target": target}


SCRIPT = {"title": "Gas at 100", "hook": LINES[0], "lines": LINES, "summary": "s", "claims": [],
          "chapters": [{"title": "Why it rose", "line": 2}, {"title": "Who pays", "line": 5}, {"title": "What next", "line": 8}]}
OUTLINE = {"concept": "c", "palette": {"bg": "#0b0d12", "ink": "#ffffff", "accent": "#2ee6c5"}, "global_css": "",
           "kit": "Titles 72px Inter Tight 800; figures 160px accent; sources 22px muted bottom left.", "summary": "s",
           "scenes": [{"id": "hook", "lines": [0, 1], "brief": "the price ticker climbs past 100",
                       "shows": "the ticker climbs past the 100 line", "camera": _cam("push_in", "the 100 line")},
                      {"id": "storage", "lines": [3, 4], "brief": "storage gauge drains, a pipe closes",
                       "shows": "the march storage gauge drains while a pipe closes", "camera": _cam("pan_left", "the pipe")},
                      {"id": "factories", "lines": [6, 6], "brief": "a factory roof with a meter",
                       "shows": "a factory meter climbs past 100 on the wall", "camera": _cam("tilt_up", "the meter")},
                      {"id": "homes", "lines": [7, 7], "brief": "a house with a bill arriving",
                       "shows": "a household bill drops through the door showing 60 euros", "camera": _cam("pull_out", "the door")},
                      {"id": "refill", "lines": [9, 11], "brief": "a tank refills over the summer months",
                       "shows": "a tank fills month by month through the summer", "camera": _cam("zoom_to", "the tank")}]}


def _scene(sc, text=None, mechanism="build_up"):
    return {"id": sc["id"], "lines": list(sc["lines"]), "trigger": "", "mechanism": mechanism,
            "shows": sc["shows"], "camera": dict(sc["camera"]),
            "html": f'<h1 style="position:absolute;left:200px;top:300px;color:#fff;font-size:80px">{text or sc["id"]}</h1>',
            "css": "", "js": ""}


def _project(d, lang="en"):
    pid = P.create("long_explainer", "gas", d=d, video_lang=lang, aspect="16:9", extra={"ui_lang": "en"})["id"]
    P.write_artifact(pid, "script", SCRIPT, d)
    P.write_artifact(pid, "outline", OUTLINE, d)
    return pid


# ---------------------------------------------------------------- chapters and parts

def test_chapters_and_parts_follow_the_title_lines():
    chs = LF.chapters(SCRIPT)
    assert [(c["n"], c["line"], c["end"]) for c in chs] == [(1, 2, 4), (2, 5, 7), (3, 8, 11)]
    assert [(p["k"], p["lines"]) for p in LF.parts(SCRIPT)] == [(0, [0, 1]), (1, [3, 4]), (2, [6, 7]), (3, [9, 11])]
    assert LF.script_problems(SCRIPT) == []


def test_script_problems_name_what_is_wrong():
    bad = {**SCRIPT, "chapters": [{"title": "B", "line": 5}, {"title": "A", "line": 2}, {"title": "C", "line": 6}]}
    probs = " ".join(LF.script_problems(bad))
    assert "rise strictly" in probs and "only its title line" in probs
    long_title = {**SCRIPT, "lines": LINES[:2] + ["Part one is a very long sentence that goes on and on and on."] + LINES[3:]}
    assert any("more than" in x for x in LF.script_problems(long_title))


def test_outline_must_cover_every_line_but_the_titles():
    assert LF.outline_problems(SCRIPT, OUTLINE) == []
    gap = {**OUTLINE, "scenes": [s for s in OUTLINE["scenes"] if s["id"] != "homes"]}
    assert any("next uncovered line is 7" in x for x in LF.outline_problems(SCRIPT, gap))
    cross = {**OUTLINE, "scenes": [OUTLINE["scenes"][0], {"id": "x", "lines": [3, 6], "brief": "too long a scene"}]
             + OUTLINE["scenes"][3:]}
    assert any("chapter title line" in x for x in LF.outline_problems(SCRIPT, cross))
    card = {**OUTLINE, "scenes": [{**OUTLINE["scenes"][0], "id": "chapter-x"}] + OUTLINE["scenes"][1:]}
    assert any("must not start with" in x for x in LF.outline_problems(SCRIPT, card))
    short = {**OUTLINE, "scenes": OUTLINE["scenes"][:-1]}
    assert any("not covered" in x for x in LF.outline_problems(SCRIPT, short))


def test_a_part_keeps_the_outline_ids_and_lines():
    mine = OUTLINE["scenes"][2:4]
    assert LF.part_problems(mine, {"scenes": [_scene(s) for s in mine]}) == []
    assert LF.part_problems(mine, {"scenes": [_scene(mine[0])]})
    assert LF.part_problems(mine, {"scenes": [_scene(mine[0]), {**_scene(mine[1]), "html": " "}]}) == ["scene 'homes': empty html"]


def test_named_parts_from_the_creator_note():
    assert LF.named("storage looks flat", SCRIPT, OUTLINE) == {1}
    assert LF.named("Bölüm 3 ve giriş daha hızlı olsun", SCRIPT, OUTLINE) == {0, 3}
    assert LF.named("chapter 9 please", SCRIPT, OUTLINE) == set() and LF.named(None, SCRIPT, OUTLINE) == set()


# ---------------------------------------------------------------- the plan

def test_plan_merges_cards_parts_and_placeholders(d):
    pid = _project(d, "tr")
    p1 = {"scenes": [_scene(OUTLINE["scenes"][1], "BUILT")], "summary": "s",
          "sig": LF.sig(OUTLINE, LF.parts(SCRIPT)[1], SCRIPT)}
    P.write_artifact(pid, LF.part_art(1), p1, d)
    P.write_artifact(pid, LF.part_art(2), {**p1, "sig": "stale"}, d)            # outline changed since: not used
    pl = LF.plan(pid, d)
    ids = [s["id"] for s in pl["scenes"]]
    assert ids == ["hook", "chapter-1", "storage", "chapter-2", "factories", "homes", "chapter-3", "refill"]
    by = {s["id"]: s for s in pl["scenes"]}
    assert "BUILT" in by["storage"]["html"] and by["hook"].get("placeholder") and by["factories"].get("placeholder")
    card = by["chapter-2"]
    assert card["hide_captions"] and card["lines"] == [5, 5] and "BÖLÜM 2" in card["html"] and "Who pays" in card["html"]
    assert 'class="on"' in card["html"] and 'class="done"' in card["html"]
    assert pl["chrome"] == {"progress": True} and [c["line"] for c in pl["chapters"]] == [2, 5, 8]
    sp = X.spec(pid, pl, d)
    assert [c["title"] for c in sp["chapters"]] == ["Why it rose", "Who pays", "What next"]
    assert 0 < sp["chapters"][0]["start"] < sp["chapters"][1]["start"] < sp["chapters"][2]["start"] < sp["duration"]
    assert sp["chrome"] == {"progress": True}


def test_build_scenes_runs_parts_at_once_and_keeps_the_rest(d, monkeypatch):
    from factory import layoutlint
    pid = _project(d)
    monkeypatch.setattr(X, "bundle", lambda pid, pl, d=None: "b.json")
    monkeypatch.setattr(layoutlint, "run", lambda *a, **k: ([], [], []))
    calls = []

    def build(part):
        calls.append(part["k"])
        mine = [s for s in OUTLINE["scenes"] if LF._in(s, part)]
        P.write_artifact(pid, LF.part_art(part["k"]), {"scenes": [_scene(s, f"v{len(calls)}") for s in mine], "summary": "x",
                                                        "sig": LF.sig(OUTLINE, part, SCRIPT)}, d)
        return {"k": part["k"], "usd": 0.5, "summary": "x"}
    out = LF.build_scenes(pid, {"id": "scene_plan"}, d=d, build=build)
    assert sorted(calls) == [0, 1, 2, 3] and out["cost"]["usd"] == 2.0
    pl = out["artifact"]
    assert pl["parts"] == {"built": [0, 1, 2, 3], "kept": []} and not any(s.get("placeholder") for s in pl["scenes"])
    by = {s["id"]: s for s in pl["scenes"]}
    by["storage"]["html"] = "<h1>HAND EDIT</h1>"                     # the creator edits a scene by hand
    P.write_artifact(pid, "scene_plan", {**pl, "edits": [{"scene": "storage"}]}, d)
    calls.clear()
    out = LF.build_scenes(pid, {"id": "scene_plan"}, note="Chapter 2: the homes scene needs a bill", d=d, build=build)
    assert calls == [2] and out["artifact"]["parts"] == {"built": [2], "kept": [0, 1, 3]}
    by = {s["id"]: s for s in out["artifact"]["scenes"]}
    assert by["storage"]["html"] == "<h1>HAND EDIT</h1>" and out["artifact"]["edits"] == [{"scene": "storage"}]


def test_build_scenes_retries_once_then_stops(d, monkeypatch):
    from factory import layoutlint
    pid = _project(d)
    monkeypatch.setattr(X, "bundle", lambda pid, pl, d=None: "b.json")
    monkeypatch.setattr(layoutlint, "run", lambda *a, **k: ([], [], []))

    def build(part):
        if part["k"] == 3:
            raise RuntimeError("designer gave up")
        P.write_artifact(pid, LF.part_art(part["k"]), {"scenes": [_scene(s) for s in OUTLINE["scenes"] if LF._in(s, part)],
                                                        "summary": "", "sig": LF.sig(OUTLINE, part, SCRIPT)}, d)
        return {"k": part["k"], "usd": 0, "summary": ""}
    with pytest.raises(LF.LongError, match="What next"):
        LF.build_scenes(pid, {"id": "scene_plan"}, d=d, build=build)
    P.write_artifact(pid, "outline", {**OUTLINE, "scenes": OUTLINE["scenes"][:-1]}, d)
    with pytest.raises(LF.LongError, match="does not fit"):
        LF.build_scenes(pid, {"id": "scene_plan"}, d=d, build=build)


def test_submit_artifact_checks_scripts_outlines_and_parts(d):
    import line_fixtures as F
    from factory.hat import tools as T
    pid = _project(d)
    F.cold_evidence(pid, d)                      # the agent's `cold_test` verdict on these exact lines
    bad = {**SCRIPT, "chapters": SCRIPT["chapters"][:2] + [{"title": "Again", "line": 5}]}
    r = T.call("submit_artifact", T.Ctx(pid, "script", d), {"data": bad})
    assert not r["accepted"] and any("rise strictly" in x for x in r["problems"])
    assert T.call("submit_artifact", T.Ctx(pid, "script", d), {"data": SCRIPT})["accepted"]
    gap = {**OUTLINE, "scenes": [s for s in OUTLINE["scenes"] if s["id"] != "homes"]}
    assert not T.call("submit_artifact", T.Ctx(pid, "outline", d), {"data": gap})["accepted"]
    assert T.call("submit_artifact", T.Ctx(pid, "outline", d), {"data": OUTLINE})["accepted"]
    ctx = T.Ctx(pid, "scene_plan", d, part=2)
    r = T.call("submit_artifact", ctx, {"data": {"scenes": [_scene(OUTLINE["scenes"][2])], "summary": "x"}})
    assert not r["accepted"]
    r = T.call("submit_artifact", ctx, {"data": {"scenes": [_scene(OUTLINE["scenes"][2], mechanism="chart_build"),
                                                           _scene(OUTLINE["scenes"][3], mechanism="cause_chain")],
                                                  "summary": "x"}})
    assert r == {"accepted": True, "artifact": "scene_part_2"} and not P.read_artifact(pid, "scene_plan", d)


def test_chapter_marks_start_at_zero(d):
    pid = _project(d, "tr")
    P.write_artifact(pid, "scene_plan", LF.plan(pid, d), d)
    ms = LF.marks(pid, d)
    assert ms[0] == {"t": 0.0, "title": "Giriş"} and [m["title"] for m in ms[1:]] == ["Why it rose", "Who pays", "What next"]
    txt = LF.marks_text(pid, d).splitlines()
    assert txt[0] == "0:00 Giriş" and txt[1].endswith(" Why it rose") and len(txt) == 4
    assert LF.stamp(65.4) == "1:05" and LF.stamp(3725) == "1:02:05"


# ---------------------------------------------------------------- narration in pieces

def test_pieces_cut_at_chapters_and_before_the_limit(monkeypatch):
    assert X.pieces(LINES) == [[0, 11]]
    assert X.pieces(LINES, [2, 5, 8]) == [[0, 1], [2, 4], [5, 7], [8, 11]]
    monkeypatch.setattr(X, "TTS_MAX", 60)
    ps = X.pieces(LINES)
    assert ps[0][0] == 0 and ps[-1][1] == 11 and all(b >= a for a, b in ps)
    assert all(sum(len(LINES[i]) + 1 for i in range(a, b + 1)) <= 60 or a == b for a, b in ps)


def test_narrate_voices_each_piece_inside_the_budget(d, monkeypatch, tmp_path):
    from factory import config, eleven
    tone = str(tmp_path / "tone.m4a")
    subprocess.run([config.FFMPEG, "-y", "-v", "error", "-f", "lavfi", "-i", "sine=f=440:d=1.5", "-c:a", "aac", tone], check=True)
    pid = _project(d)
    p = P.load(pid, d)
    p["budget"] = {"credits": 1000}
    P.save(p, d)
    asked = []

    def fake_tts(con, text, voice_id, model, approved=None, account=None):
        asked.append((text, approved))
        return tone, 100.0
    monkeypatch.setattr(eleven, "tts", fake_tts)
    path, cost = X.narrate(pid, None, LINES, "v", None, [2, 5, 8], d)
    assert len(asked) == 4 and cost == 400 and [a for _, a in asked] == [1000, 900, 800, 700]
    assert asked[1][0].startswith("Part one:")
    from factory import fftools
    assert abs(fftools.measure(path)["duration"] - (4 * 1.5 + 3 * X.PIECE_GAP)) < 0.2
    asked.clear()
    assert X.narrate(pid, None, LINES[:3], "v", None, [], d) == (tone, 100.0) and len(asked) == 1


def test_loop_music_reaches_the_length(tmp_path):
    from factory import config, fftools
    one = str(tmp_path / "m.m4a")
    subprocess.run([config.FFMPEG, "-y", "-v", "error", "-f", "lavfi", "-i", "sine=f=220:d=10", "-c:a", "aac", one], check=True)
    out = X.loop_music(one, 27, str(tmp_path / "long.m4a"))
    assert abs(fftools.measure(out)["duration"] - 27) < 0.3


# ---------------------------------------------------------------- rendering

def _render_project(tmp_path):
    from factory import config
    pdir = os.path.join(os.path.realpath(config.ROOT), "projects", "_test_" + os.path.basename(str(tmp_path)))
    pid = _project(pdir)
    for part in LF.parts(SCRIPT):
        P.write_artifact(pid, LF.part_art(part["k"]), {"scenes": [_scene(s) for s in OUTLINE["scenes"] if LF._in(s, part)],
                                                        "summary": "", "sig": LF.sig(OUTLINE, part, SCRIPT)}, pdir)
    pl = LF.plan(pid, pdir)
    P.write_artifact(pid, "scene_plan", pl, pdir)
    return pdir, pid, pl


def test_progress_bar_and_chapter_card_render(tmp_path):
    from factory.hat import tools as T
    if not T.available("render_stills")[0]:
        pytest.skip("no chromium here")
    import importlib.util
    from PIL import Image
    from factory import config
    spec_ = importlib.util.spec_from_file_location("htmlmotion", os.path.join(config.ROOT, "bin", "htmlmotion.py"))
    hm = importlib.util.module_from_spec(spec_)
    spec_.loader.exec_module(hm)
    pdir, pid, pl = _render_project(tmp_path)
    try:
        sp = X.spec(pid, pl, pdir)
        b = X.bundle(pid, pl, pdir)
        c2 = sp["chapters"][1]["start"]
        shots, errs = hm.shots(b, [round(c2 + 1.5, 2), round(sp["duration"] - 0.3, 2)], str(tmp_path / "shots"))
        assert len(shots) == 2 and not errs, errs
        card, end = Image.open(shots[0]).convert("RGB"), Image.open(shots[1]).convert("RGB")
        assert card.size == (1920, 1080)
        accent = (0x2e, 0xe6, 0xc5)
        near = lambda px: sum(abs(a - b) for a, b in zip(px, accent)) < 60
        assert near(card.getpixel((100, 1076))) and not near(card.getpixel((1800, 1076)))   # first chapters filled only
        assert near(end.getpixel((1800, 1076)))                                             # full at the end
        assert near(card.getpixel((300, 300)))                                              # the big chapter number
    finally:
        shutil.rmtree(pdir, ignore_errors=True)


def test_sliced_capture_joins_to_the_full_length(tmp_path):
    from factory.hat import tools as T
    if not T.available("render_stills")[0]:
        pytest.skip("no chromium here")
    import importlib.util
    from factory import config, fftools
    spec_ = importlib.util.spec_from_file_location("htmlmotion", os.path.join(config.ROOT, "bin", "htmlmotion.py"))
    hm = importlib.util.module_from_spec(spec_)
    spec_.loader.exec_module(hm)
    pdir, pid, pl = _render_project(tmp_path)
    try:
        b = X.bundle(pid, pl, pdir)
        out = str(tmp_path / "cap.mp4")
        hm.capture(b, out, 4.0, ["--opaque"], fps=30, slices=2)
        m = fftools.measure(out)
        assert abs(m["duration"] - 4.0) < 0.1 and not [f for f in os.listdir(tmp_path) if ".part" in f]
    finally:
        shutil.rmtree(pdir, ignore_errors=True)
