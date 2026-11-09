"""The structural check on a scene plan: it covers the script, in order, with a pace a viewer can watch."""
import pytest

from factory import shotplan
from factory.hat import project as P, tools as T

SCRIPT = {"title": "t", "hook": "a", "lines": [f"cümle {i}" for i in range(12)]}


def _plan(ranges):
    return [{"id": f"s{i + 1}", "lines": list(r)} for i, r in enumerate(ranges)]


def test_a_plan_that_covers_the_script_in_order_is_clean():
    ranges = [(0, 2), (3, 5), (6, 8), (9, 11)]
    assert shotplan.problems(_plan(ranges), SCRIPT["lines"], 55) == []


def test_a_skipped_line_is_refused():
    found = shotplan.problems(_plan([(0, 2), (4, 5)]), SCRIPT["lines"])
    assert any("never shows line" in f and "3" in f for f in found)


def test_a_repeated_line_an_out_of_order_scene_and_a_runaway_range_are_refused():
    assert any("appear twice" in f for f in shotplan.problems(_plan([(0, 2), (2, 4)]), SCRIPT["lines"]))
    assert any("not in script order" in f for f in shotplan.problems(_plan([(5, 6), (0, 2)]), SCRIPT["lines"]))
    assert any("run past the script" in f for f in shotplan.problems(_plan([(0, 2), (3, 40)]), SCRIPT["lines"]))
    assert any("starts on line 0 again" in f for f in shotplan.problems(_plan([(0, 2), (0, 3)]), SCRIPT["lines"]))


def test_the_count_has_to_fit_the_length():
    many = _plan([(i, i) for i in range(12)])
    found = shotplan.problems(many, SCRIPT["lines"], 25)
    assert any("12 scenes for 25 s" in f for f in found)
    few = _plan([(0, 2), (3, 5)])
    assert any("2 scenes for 25 s" in f for f in shotplan.problems(few, SCRIPT["lines"], 25))


def test_a_part_of_the_script_covers_only_its_own_lines():
    part = _plan([(6, 6), (7, 7)])                  # one designer's slice of a long explainer
    assert any("never shows line" in f for f in shotplan.problems(part, SCRIPT["lines"]))
    assert shotplan.problems(part, SCRIPT["lines"], partial=True) == []
    assert any("run past the script" in f for f in shotplan.problems(_plan([(10, 12)]), SCRIPT["lines"], partial=True))
    assert any("appear twice" in f for f in shotplan.problems(_plan([(6, 7), (7, 7)]), SCRIPT["lines"], partial=True))


def test_an_empty_plan_says_so():
    assert shotplan.problems([], SCRIPT["lines"]) == ["the plan has no scenes"]


def test_submit_artifact_refuses_a_plan_with_a_hole(d):
    pid = P.create("explainer", "t", d=d)["id"]
    P.write_artifact(pid, "script", SCRIPT, d)
    plan = {"concept": "c", "summary": "s", "palette": {"bg": "#101418", "ink": "#F2F0E9", "accent": "#FFD93D"},
            "scenes": [{"id": "s1", "lines": [0, 1], "html": "<b>x</b>", "shows": "a figure climbs",
                        "mechanism": "count_up",
                        "camera": {"move": "push_in", "seconds": 1.5, "easing": "ease_out", "target": "the figure"}},
                       {"id": "s2", "lines": [5, 6], "html": "<b>y</b>", "shows": "a counter stops",
                        "mechanism": "scale_compare",
                        "camera": {"move": "pan_left", "seconds": 2.0, "easing": "ease_in_out", "target": "the counter"}}]}
    r = T.call("submit_artifact", T.Ctx(pid, "scene_plan", d), {"data": plan})
    assert not r["accepted"] and any("never shows line" in x for x in r["problems"])


@pytest.fixture
def d(tmp_path):
    return str(tmp_path / "projects")
