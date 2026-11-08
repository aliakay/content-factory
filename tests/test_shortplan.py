"""The short-film scene plan: one design system, the scenes in parallel, repair only what a note names."""
import json

import pytest

from factory.hat import manifest, project as P, shortplan as SP

SCRIPT = {"title": "ASELSAN güneşten mi?", "hook": "ASELSAN 3 günde bitti",
          "lines": ["ASELSAN 3 günde bitti", "Fatura 120 milyon kWh", "Sayaç 40 günü gösteriyor"]}
BOARD = {"palette": {"bg": "#101418", "ink": "#F2F0E9", "accent": "#FFD93D"}, "type": {"display": "Anton", "body": "Inter Tight"},
         "rules": [{"what": w, "says": "x"} for w in ("light", "type", "motion", "camera")], "fingerprint": "fp1",
         "summary": "s"}


def _scene(i, lines, move="push_in"):
    return {"id": f"s{i}", "lines": lines, "mechanism": "count_up" if i % 2 else "scale_compare",
            "shows": f"the figure {i} climbs while the label changes",
            "camera": {"move": move, "seconds": 1.5, "easing": "ease_out", "target": f"the figure {i}"},
            "html": f'<div class="w"><b data-e="1">{i}</b></div>', "css": "", "js": ""}


def _design(n=3):
    return {"concept": "the bill tells the truth",
            "palette": {"bg": "#101418", "ink": "#F2F0E9", "muted": "#8A8279", "accent": "#FFD93D", "accent2": "#4CC9F0"},
            "global_css": "body{font-family:'Inter Tight'}", "kit": "title, figure, label, source",
            "scenes": [{"id": f"s{i}", "lines": [i, i], "brief": "the bill grows", "shows": f"a figure {i} climbs",
                        "mechanism": "count_up" if i % 2 else "scale_compare",
                        "camera": {"move": ["push_in", "pan_left", "zoom_to"][i % 3], "seconds": 1.5,
                                   "easing": "ease_out", "target": f"figure {i}"}} for i in range(n)]}


@pytest.fixture
def d(tmp_path):
    return str(tmp_path / "projects")


def _project(d):
    pid = P.create("explainer", "ASELSAN güneşten mi?", d=d)["id"]
    P.write_artifact(pid, "script", SCRIPT, d)
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
    pid = _project(d)

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
    pid = _project(d)
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
    P.write_artifact(pid, "script", {**SCRIPT, "lines": SCRIPT["lines"] + ["Yeni satır 5 saniye"]}, d)
    SP.build(pid, _stage(), d=d, ask=fake_ask)
    assert n["design"] == 2                                     # the script moved: design again
