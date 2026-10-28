"""The director's team (scout -> memory -> art director -> sketch artists -> critic) and the studio memory."""
import json, sqlite3

import pytest

from factory import capabilities, director, llm, memory, planner, productions as P, tracking
from factory.store import SCHEMA


@pytest.fixture
def con(tmp_path, monkeypatch):
    monkeypatch.setattr(director, "PLANS", str(tmp_path / "plans"))
    c = sqlite3.connect(tmp_path / "t.db")
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    P.ensure(c)
    return c


def _made(con, title, techs, stage="ready", views=None):
    d = {"kind": "explainer", "title": title, "voice": {"lines": ["a"]}, "scenes": [], "shots": []}
    capabilities.apply({"techniques": techs, "direction": f"{title} direction"}, d)
    d["motion"] = {"concept": f"{title}: a concept"}
    pid = P.create(con, "explainer_short", d, title)
    p = P.get(con, pid)
    p["stage"] = stage
    P.save(con, p, "onay", "fikir onaylandı")
    if views is not None:
        tracking.ensure(con)
        con.execute("INSERT INTO posts (prod_id, platform, url, posted_at) VALUES (?, 'tiktok', ?, '2026-10-20')", (pid, f"u{pid}"))
        post = con.execute("SELECT post_id FROM posts WHERE prod_id=?", (pid,)).fetchone()[0]
        con.execute("INSERT INTO post_stats (post_id, at, views) VALUES (?, '2026-10-21', ?)", (post, views))
        con.commit()
    return pid


def test_memory_finds_what_is_overused_unexplored_and_what_worked(con):
    for i in range(3):
        _made(con, f"noir {i}", ["style.noir", "look.acting", "story.rules_arc"], views=1000 * (i + 1))
    _made(con, "blueprint", ["style.blueprint", "look.kinetic_headline"], views=90000)
    mem = memory.brief(con)
    assert "style.noir" in mem["overused"] and "look.acting" in mem["overused"]
    assert "style.noir" not in mem["unexplored"] and "style.riso_print" in mem["unexplored"]
    assert mem["performance"]["best"][0]["title"] == "blueprint"
    assert memory.novelty(["style.noir", "look.acting", "story.rules_arc"], mem) < memory.novelty(["style.riso_print", "look.set3d"], mem)
    assert "çok kullanılan" in memory.summary_tr(mem) and "noir 2" in memory.designer_note(con)
    assert memory.brief(sqlite3.connect(":memory:"))["made"] == 0    # an empty studio: everything is open


def test_taste_reads_picked_and_passed_treatments(con):
    planner.ensure(con)
    plan = {"chosen": 1, "treatments": [{"techniques": ["style.noir"]}, {"techniques": ["style.riso_print", "look.set3d"]}]}
    con.execute("INSERT INTO plans (prompt, plan, status) VALUES ('x', ?, 'started')", (json.dumps(plan),))
    con.commit()
    t = memory.taste(con)
    assert "style.riso_print" in t["picked"] and "style.noir" in t["passed"]


DESIGN = """@@META
{"concept": "a city cut into a grid; rain falls on 3 of 10 squares", "palette": {"bg": "#0b1020", "ink": "#ffffff", "accent": "#3df0ff"}}
@@SCENE hook
@@HTML
<div class="grid"></div>
@@CSS
.grid{position:absolute;inset:200px 100px}
@@JS
FX.sfx("pop", 0.5);
@@END"""


def _fake_team(monkeypatch, calls):
    def ask(prompt, tools=(), timeout=0, model=None, **k):
        if "researcher of a short-video studio" in prompt:
            calls.append("scout")
            return {"insight": "30 % = confidence x area: a 30 % chance at ANY point in the area",
                    "misconception": "it rains on 30 % of the city", "facts": [{"claim": "PoP = C x A", "source": "https://weather.gov"}],
                    "cliches": ["a cloud icon with a percent sign"], "metaphors": [{"idea": "a city as 10 squares"}]}, {"cost_usd": 0.1}
        if "producer AND the art director" in prompt:
            calls.append("director")
            assert "RESEARCH from the studio's scout" in prompt and "STUDIO MEMORY" in prompt
            return {"understood_tr": "x", "kind": "topic", "format": "explainer_short", "look": "auto", "seconds": 40,
                    "direction": "Rain chance as a game of squares.", "techniques": ["look.code_characters"],
                    "treatments": [{"label_tr": "Kareler", "techniques": ["look.code_characters", "look.acting"], "moment": "m1"},
                                   {"label_tr": "Blueprint", "techniques": ["style.blueprint"], "moment": "m2"},
                                   {"label_tr": "Riso", "techniques": ["style.riso_print", "look.caused_transitions"], "moment": "m3", "seconds": 45}]}, {"cost_usd": 0.4}
        if "creative director of a short-video studio" in prompt:
            calls.append("critic")
            return {"scores": [{"i": 0, "clarity": 3, "hook": 3, "novelty": 2, "feasibility": 5, "fit": 4, "why_tr": "a", "fix": "f0"},
                               {"i": 1, "clarity": 4, "hook": 3, "novelty": 3, "feasibility": 4, "fit": 4, "why_tr": "b", "fix": "f1"},
                               {"i": 2, "clarity": 5, "hook": 5, "novelty": 5, "feasibility": 4, "fit": 5, "why_tr": "c", "fix": "make the squares bigger"}],
                    "recommended": 2, "summary_tr": "Riso kazanır."}, {"cost_usd": 0.3}
        raise AssertionError("unexpected prompt")

    def ask_text(prompt, tools=(), timeout=0, model=None, **k):
        calls.append("sketch")
        assert "STYLE-FRAME artist" in prompt
        return DESIGN, {"cost_usd": 0.05}
    monkeypatch.setattr(llm, "ask", ask)
    monkeypatch.setattr(llm, "ask_text", ask_text)
    from factory import layoutlint

    def fake_run(bundle, times, out, aspect, hide=(), timing=True):
        import os
        paths = []
        for t in times:
            p = os.path.join(out, f"shot_{t:06.2f}.png")
            open(p, "wb").write(b"png")
            paths.append(p)
        return paths, [], []
    monkeypatch.setattr(layoutlint, "run", fake_run)


def test_director_team_researches_sketches_judges_and_applies_the_pick(con, monkeypatch):
    calls = []
    _fake_team(monkeypatch, calls)
    pid = planner.create(con, "Hava durumunda yüzde 30 ne demek, bütün şehri mi kapsıyor?", {"channel": None})
    p = planner.think(con, pid)
    assert calls.count("scout") == 1 and calls.count("director") == 1 and calls.count("sketch") == 3 and calls.count("critic") == 1
    assert p["research"]["insight"].startswith("30 %") and p["recommended"] == 2 and p["chosen"] == 2
    assert p["techniques"] == ["style.riso_print", "look.caused_transitions"] and p["seconds"] == 45
    assert all(t.get("sketch", {}).get("stills") for t in p["treatments"]) and p["treatments"][2]["score"]["total"] == 4.8
    assert p["team"]["cost_usd"] > 0 and all(s["status"] in ("ok", "skip") for s in p["team"]["stages"])
    rec = planner.recipe_of(p)
    assert rec["sketch"]["fix"] == "make the squares bigger" and rec["research"]["misconception"]
    d = capabilities.apply(rec, {})
    notes = capabilities.designer_notes(d)
    assert "APPROVED STYLE FRAME" in notes and "a city cut into a grid" in notes and "FX.sfx" in notes
    assert "SCOUT'S RESEARCH" in capabilities.writer_notes(d)
    # the creator switches to treatment 1 on the card: its techniques and frame become the recipe
    planner.update(con, pid, {"treatment": 1})
    q = planner.get(con, pid)["plan"]
    assert q["chosen"] == 1 and q["techniques"] == ["style.blueprint"] and planner.recipe_of(q)["sketch"]["moment"] == "m2"


def test_quick_plan_is_one_call(con, monkeypatch):
    calls = []
    _fake_team(monkeypatch, calls)
    pid = planner.create(con, "yüzde 30 yağmur", {"quick": True})
    p = planner.think(con, pid)
    assert calls == ["director"] and p["team"]["quick"] and "research" not in p
    assert [s["status"] for s in p["team"]["stages"] if s["stage"] in ("scout", "sketch", "critic")] == ["skip"] * 3


def test_a_failing_sketch_and_critic_still_give_a_plan(con, monkeypatch):
    calls = []
    _fake_team(monkeypatch, calls)
    monkeypatch.setattr(llm, "ask_text", lambda *a, **k: ("no blocks at all", {}))
    pid = planner.create(con, "yüzde 30 yağmur", {})
    p = planner.think(con, pid)
    assert planner.get(con, pid)["status"] == "ready" and all("error" in t["sketch"] for t in p["treatments"])
    assert "critic" not in calls and p["chosen"] == 0


def test_every_role_gets_a_reasoning_effort(monkeypatch):
    seen = {}

    class R:
        returncode, stderr = 0, ""
        stdout = json.dumps({"result": "{}", "total_cost_usd": 0})

    def fake_run(cmd, **k):
        seen["cmd"] = cmd
        return R()
    import subprocess
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(llm, "_record", lambda *a: None)
    from factory import accounts
    monkeypatch.setattr(accounts, "claude_env", lambda: {})
    assert llm.effort_for("motiondesign.author", "opus") == "medium" and llm.effort_for("x.y", "sonnet") == "medium"
    assert llm.effort_for("eleven.tts", "sonnet") == "low" and llm.effort_for("x.y", "opus") == "medium"
    llm.ask_text("hi", model="sonnet", effort="low")
    assert seen["cmd"][seen["cmd"].index("--effort") + 1] == "low"
    monkeypatch.setenv("CF_EFFORT_DIRECTOR_CRITIC", "max")
    assert llm.effort_for("director.critic", "opus") == "medium"     # capped: nothing runs above medium
    llm.ask_text("hi", model="sonnet", effort="xhigh")
    assert seen["cmd"][seen["cmd"].index("--effort") + 1] == "medium"


def test_split_reply_is_joined():
    """A reply over the output cap arrives as several messages; the result event holds only the last one."""
    ev = [{"type": "assistant", "message": {"id": "a", "content": [{"type": "text", "text": "looking"}],
                                             "usage": {"output_tokens": 5}}},
          {"type": "user", "message": {"content": [{"type": "tool_result", "content": "x"}]}},
          {"type": "assistant", "message": {"id": "b", "content": [{"type": "text", "text": "@@META {} @@SCENE hook @@HTML <di"}],
                                             "usage": {"output_tokens": 10}}},
          {"type": "assistant", "message": {"id": "c", "content": [{"type": "text", "text": "v></div> @@END"}],
                                             "usage": {"output_tokens": 3}}},
          {"type": "result", "result": "v></div> @@END", "total_cost_usd": 0.1}]
    out, reply, used = llm._stream("\n".join(json.dumps(e) for e in ev))
    assert out["total_cost_usd"] == 0.1 and reply == "@@META {} @@SCENE hook @@HTML <div></div> @@END"
    assert llm._stream(json.dumps({"result": "{}"}))[1] == ""
