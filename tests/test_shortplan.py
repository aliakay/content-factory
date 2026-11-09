"""The short-film scene plan: one design system, the scenes in parallel, repair only what a note names."""
import json

import pytest

from factory.hat import manifest, project as P, shortplan as SP

SCRIPT = {"title": "panel güneşten mi?", "hook": "panel hemen bitti",
          "lines": ["panel hemen bitti", "fatura şişti", "sayaç durdu"]}
BOARD = {"palette": {"bg": "#101418", "ink": "#F2F0E9", "accent": "#FFD93D"}, "type": {"display": "Anton", "body": "Inter Tight"},
         "rules": [{"what": w, "says": "x"} for w in ("light", "type", "motion", "camera")], "fingerprint": "fp1",
         "summary": "s"}


def _scene(i, lines, move=None):
    return {"id": f"s{i}", "lines": lines,
            "mechanism": ["count_up", "scale_compare", "cause_chain"][i % 3],
            "shows": f"the figure {i} climbs while the label changes",
            "camera": {"move": move or ["push_in", "pan_left", "zoom_to"][i % 3],
                       "seconds": [1.5, 2.5, 3.5][i % 3],
                       "easing": "ease_out", "target": f"the figure {i}"},
            "html": f'<div class="w"><b data-e="1">{i}</b></div>', "css": "", "js": ""}


def _design(n=3):
    return {"concept": "the bill tells the truth",
            "palette": {"bg": "#101418", "ink": "#F2F0E9", "accent": "#FFD93D"},
            "global_css": "body{font-family:'Inter Tight'}", "kit": "title, figure, label, source",
            "scenes": [{"id": f"s{i}", "lines": [i, i], "brief": "the bill grows", "shows": f"a figure {i} climbs",
                        "mechanism": "count_up" if i % 2 else "scale_compare",
                        "camera": {"move": ["push_in", "pan_left", "zoom_to"][i % 3], "seconds": 1.5,
                                   "easing": "ease_out", "target": f"figure {i}"}} for i in range(n)]}


@pytest.fixture
def d(tmp_path):
    return str(tmp_path / "projects")


def _project(d, script=SCRIPT):
    pid = P.create("explainer", "ASELSAN güneşten mi?", d=d)["id"]
    P.write_artifact(pid, "script", script, d)
    P.write_artifact(pid, "direction", BOARD, d)
    return pid


def _stage():
    return manifest.stage(manifest.get("explainer"), "scene_plan")


def test_the_stage_is_a_code_step_now():
    s = _stage()
    assert s["run"] == "code" and s["call"] == "factory.hat.shortplan:build" and s["gate"] is True


def test_parts_are_balanced_by_the_lines_they_cover():
    briefs = [{"id": f"s{i}", "lines": [i, i]} for i in range(4)]
    got = SP.parts(briefs, 2)
    assert [len(p) for p in got] == [2, 2] and got[0][0]["id"] == "s0" and got[1][-1]["id"] == "s3"
    assert [len(p) for p in SP.parts(briefs, 4)] == [1, 1, 1, 1]
    assert SP.parts(briefs, 9) and all(p for p in SP.parts(briefs, 9))          # never empty parts


def test_design_then_scenes_then_a_merged_plan(d, monkeypatch):
    pid = _project(d)
    calls = []

    def fake_ask(prompt):
        calls.append(prompt)
        if "the design system only" in prompt:
            return _design(3), {"cost_usd": 0.01}
        ids = [x for x in ("s0", "s1", "s2") if f'"id": "{x}"' in prompt]
        return {"scenes": [_scene(int(i[1:]) % 3, [int(i[1:]), int(i[1:])]) for i in ids]}, {"cost_usd": 0.02}

    out = SP.build(pid, _stage(), d=d, ask=fake_ask)
    plan = P.read_artifact(pid, "scene_plan", d)
    assert [s["id"] for s in plan["scenes"]] == ["s0", "s1", "s2"]
    assert plan["palette"]["accent"] == "#FFD93D" and plan["global_css"]
    assert plan["parts"]["rebuilt"] == ["s0", "s1", "s2"] and plan["parts"]["kept"] == []
    assert P.read_artifact(pid, SP.DESIGN, d)["sig"] and out["cost"]["usd"] == pytest.approx(0.03, abs=0.05)
    assert len(calls) == 3                                                     # one design + two parts


def test_a_note_that_names_a_scene_repairs_only_its_part(d, monkeypatch):
    pid = _project(d, {**SCRIPT, "lines": SCRIPT["lines"] + ["Dördüncü satır"]})

    def fake_ask(prompt):
        if "the design system only" in prompt:
            return _design(4)
        ids = [x for x in ("s0", "s1", "s2", "s3") if f'"id": "{x}"' in prompt]
        return {"scenes": [_scene(int(i[1:]), [int(i[1:]), int(i[1:])]) for i in ids]}

    SP.build(pid, _stage(), d=d, ask=fake_ask)
    first = P.read_artifact(pid, "scene_plan", d)
    before = {s["id"]: s["html"] for s in first["scenes"]}
    # s2 lives in the second half; the first half must survive untouched
    out = SP.build(pid, _stage(), note="s2 daha büyük olsun", d=d, ask=fake_ask)
    plan = P.read_artifact(pid, "scene_plan", d)
    assert out["artifact"]["parts"]["kept"] == ["s0", "s1"]              # the other part is untouched
    assert "s2" in out["artifact"]["parts"]["rebuilt"] and "s3" in out["artifact"]["parts"]["rebuilt"]
    assert [s["html"] for s in plan["scenes"] if s["id"] == "s0"] == [before["s0"]]   # kept byte for byte


def test_the_design_system_is_cached_until_the_script_changes(d):
    pid = _project(d, {**SCRIPT, "lines": SCRIPT["lines"][:2]})
    n = {"design": 0}

    def fake_ask(prompt):
        if "the design system only" in prompt:
            n["design"] += 1
            return _design(2)
        ids = [x for x in ("s0", "s1") if f'"id": "{x}"' in prompt]
        return {"scenes": [_scene(int(i[1:]), [int(i[1:]), int(i[1:])]) for i in ids]}

    SP.build(pid, _stage(), d=d, ask=fake_ask)
    SP.build(pid, _stage(), d=d, ask=fake_ask)
    assert n["design"] == 1                                     # same script, same board: no second design pass
    P.write_artifact(pid, "script", {**SCRIPT, "lines": [SCRIPT["lines"][0] + " (yenilendi)", SCRIPT["lines"][1]]}, d)
    SP.build(pid, _stage(), d=d, ask=fake_ask)
    assert n["design"] == 2                                     # the script moved: design again


def test_a_one_based_design_is_shifted_to_zero_based_without_a_second_call(d):
    """The report from production: the model answered the numbered script from 1, and the gate refused it."""
    pid = _project(d)
    n = {"design": 0}

    def fake_ask(prompt):
        if "the design system only" in prompt:
            n["design"] += 1
            art = _design(3)
            for i, sc in enumerate(art["scenes"]):
                sc["lines"] = [i + 1, i + 1]                    # exactly the 1..n tiling the checker refuses
            return art
        ids = [x for x in ("s0", "s1", "s2") if f'"id": "{x}"' in prompt]
        return {"scenes": [_scene(int(i[1:]), [int(i[1:]), int(i[1:])]) for i in ids]}

    SP.build(pid, _stage(), d=d, ask=fake_ask)
    plan = P.read_artifact(pid, "scene_plan", d)
    assert [s["lines"] for s in plan["scenes"]] == [[0, 0], [1, 1], [2, 2]]
    assert plan["checked"] == [] and n["design"] == 1
    assert P.read_artifact(pid, SP.DESIGN, d)["scenes"][-1]["lines"] == [2, 2]   # the cache is corrected too


def test_the_design_prompt_prints_the_indices_the_checker_uses(d):
    stage = _stage()
    script = {**SCRIPT, "lines": ["sıfır", "bir", "iki"]}
    prompt = SP._design_prompt(_project(d), stage, script, BOARD, {}, d)
    assert "[0] sıfır" in prompt and "[2] iki" in prompt and "1. sıfır" not in prompt
    assert "0-based" in prompt and "last line 2" in prompt


def test_a_design_that_cannot_place_the_lines_is_sent_back_once_then_fails(d):
    pid = _project(d)
    calls = []

    def fake_ask(prompt):
        calls.append(prompt)
        return _design(2)                       # three script lines, two covered: not the 1-based tiling either

    with pytest.raises(SP.ShortError):
        SP.build(pid, _stage(), d=d, ask=fake_ask)
    assert len(calls) == 2                      # one design pass, one correction pass
    assert "0-based" in calls[-1] and "never shows line" in calls[-1]
    assert P.read_artifact(pid, "scene_plan", d) is None      # nothing was drawn against a broken plan


def test_a_plan_the_checks_refuse_never_reaches_the_gate(d):
    pid = _project(d)

    def fake_ask(prompt):
        return _design(3)

    def builder(part):                          # draws scenes the subject check will refuse (`shows` too short)
        return [dict(_scene(int(b["id"][1:]), b["lines"]), shows="x") for b in part]

    with pytest.raises(SP.ShortError):
        SP.build(pid, _stage(), d=d, ask=fake_ask, build=builder)
    plan = P.read_artifact(pid, "scene_plan", d)
    assert plan and plan["checked"]                      # the artifact is there to look at, but the stage failed
