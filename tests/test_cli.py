"""The `factory` CLI is a thin dispatcher: it must create/advance real hat projects and never invent a pipeline."""
import json

import pytest

from factory import cli
from factory.hat import project as P, runner
from line_fixtures import fake_line


def _q(module):
    """A synchronous queue like the worker: runs each stage now, so a command stops at the next gate."""
    def queue(kind, arg):
        return module.run_job(arg, queue)
    return queue


def test_help_lists_the_commands(capsys):
    assert cli.main([]) == 0
    out = capsys.readouterr().out
    for name in ("doctor", "make", "show", "run", "approve", "list", "styles", "recipes", "lab", "usage", "plan"):
        assert name in out


def test_make_manual_only_creates_the_project(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(P, "DIR", str(tmp_path / "projects"))
    assert cli.main(["make", "Roma'nın su kemerleri", "--lang", "tr", "--manual"]) == 0
    ids = P.list_ids()
    assert len(ids) == 1
    p = P.load(ids[0])
    assert p["title"] == "Roma'nın su kemerleri" and p["line"] == "explainer" and p["video_lang"] == "tr"
    assert P.next_stage(ids[0]) == ("run", "research")          # nothing ran
    assert "sonraki adım" in capsys.readouterr().out


def test_make_advances_through_the_runner_without_an_agent(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(P, "DIR", str(tmp_path / "projects"))
    calls = []

    def queue(kind, arg):
        calls.append((kind, json.loads(arg)["stage"]))
        return 1

    pid = P.create("explainer", "Roma", d=None)["id"]
    from types import SimpleNamespace
    assert cli.cmd_make(SimpleNamespace(topic="Roma", line="explainer", lang="tr", seconds=None, manual=False),
                        queue=queue) == 0
    # the project above was the first number; make created the second one
    made = [x for x in P.list_ids() if x != pid][0]
    assert calls == [("hat_stage", "research")]
    assert P.next_stage(made) == ("busy", "research")            # the queue owns it now
    assert "target_seconds" not in P.load(made)


def test_run_then_approve_reaches_the_next_gate(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "DIR", str(tmp_path / "projects"))
    runner = fake_line(monkeypatch, {"proposal": {"artifact": {"cost": {"credits": 640, "usd": 0.0}}}})
    pid = P.create("explainer", "Roma")["id"]
    q = _q(runner)
    assert runner.advance(pid, q) == ("gate", "proposal")
    from types import SimpleNamespace
    assert cli.cmd_approve(SimpleNamespace(id=pid, gate="proposal", lang="tr"), queue=q) == 0
    assert P.next_stage(pid) == ("gate", "script")


def test_show_and_list_print_a_project(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(P, "DIR", str(tmp_path / "projects"))
    pid = P.create("explainer", "Roma'nın su kemerleri")["id"]
    assert cli.main(["show", pid]) == 0
    out = capsys.readouterr().out
    assert pid in out and "Roma" in out and "research" in out
    assert cli.main(["list"]) == 0
    assert pid in capsys.readouterr().out


def test_unknown_line_and_missing_project_fail_cleanly(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(P, "DIR", str(tmp_path / "projects"))
    assert cli.main(["make", "x", "--line", "nope", "--manual"]) == 2
    assert "unknown production line" in capsys.readouterr().err
    assert cli.main(["show", "999-nope"]) == 2


def test_plan_prints_the_ranking_without_spending(capsys):
    assert cli.main(["plan", "--family", "image"]) == 0
    out = capsys.readouterr().out
    assert "image:" in out and "GPT Image 2" in out


def test_recipes_and_styles_list_from_the_catalogue(capsys):
    assert cli.main(["styles"]) == 0
    assert "noir" in capsys.readouterr().out
    assert cli.main(["recipes"]) == 0
    assert "FX." in capsys.readouterr().out
