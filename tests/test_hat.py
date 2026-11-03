"""Production lines v2: manifests and the gate rules of a project folder."""
import json, os

import pytest
import yaml

from factory import llm as _llm
from factory.hat import manifest, project as P

_REAL_ASK_TEXT = _llm.ask_text      # for the one test that checks the CLI command with subprocess faked


# ---------------------------------------------------------------- manifests

def test_every_line_loads_with_both_languages():
    lines = manifest.all_lines()
    assert len(lines) == 14 and list(lines)[0] == "explainer"
    for m in lines.values():
        for k in manifest.TEXT:
            assert m[k]["tr"] and m[k]["en"], (m["id"], k)
        for s in m["stages"]:
            assert s["name"]["tr"] and s["name"]["en"], (m["id"], s["id"])
    ex = lines["explainer"]
    assert ex["status"] == "ready" and [s["id"] for s in ex["stages"] if s["gate"]] == \
        ["proposal", "script", "scene_plan", "assets", "publish"]


def test_localize_picks_one_language():
    tr = manifest.localize(manifest.get("explainer"), "tr")
    en = manifest.localize(manifest.get("explainer"), "en")
    assert tr["name"] == "Konu anlatımı" and en["name"] == "Explainer"
    assert tr["stages"][0]["name"] == "Araştırma" and en["stages"][0]["name"] == "Research"
    assert isinstance(tr["good_for"], list) and isinstance(tr["good_for"][0], str)


def test_manifest_errors_are_caught(tmp_path):
    (tmp_path / "_stages.yaml").write_text(open(os.path.join(manifest.DIR, "_stages.yaml"), encoding="utf-8").read())
    good = yaml.safe_load(open(os.path.join(manifest.DIR, "explainer.yaml"), encoding="utf-8"))
    bad = {**good, "tagline": {"tr": "yalnız türkçe"}}
    (tmp_path / "explainer.yaml").write_text(yaml.safe_dump(bad, allow_unicode=True))
    manifest._load.cache_clear()
    with pytest.raises(manifest.ManifestError, match="tagline"):
        manifest.all_lines(str(tmp_path))
    bad = {**good, "stages": good["stages"] + [{"id": "research", "run": "agent"}]}
    (tmp_path / "explainer.yaml").write_text(yaml.safe_dump(bad, allow_unicode=True))
    manifest._load.cache_clear()
    with pytest.raises(manifest.ManifestError, match="twice"):
        manifest.all_lines(str(tmp_path))
    manifest._load.cache_clear()


# ---------------------------------------------------------------- project gates

@pytest.fixture(autouse=True)
def no_real_llm(monkeypatch):
    """No test may reach a real model: a leak costs money and hangs the run."""
    from factory import llm
    def refuse(*a, **k):
        raise AssertionError("a test tried to call a real model")
    for name in ("ask_text", "ask", "ask_json"):
        if hasattr(llm, name):
            monkeypatch.setattr(llm, name, refuse)


@pytest.fixture
def d(tmp_path):
    return str(tmp_path / "projects")


def run(pid, sid, d, artifact=None):
    P.start(pid, sid, d=d)
    return P.finish(pid, sid, artifact if artifact is not None else {"ok": sid}, d=d)


def test_create_numbers_and_folder(d):
    p = P.create("explainer", "Avrupa gazında 100 avro eşiği", d=d)
    assert p["id"] == "001-avrupa-gazinda-100-avro-esigi"
    assert os.path.isfile(P.path(p["id"], "checkpoints", "scene_plan.json", d=d))
    q = P.create("explainer", "İkinci", d=d)
    assert q["num"] == 2 and P.list_ids(d) == [q["id"], p["id"]]


def test_stages_run_in_order_and_gates_hold(d):
    pid = P.create("explainer", "t", d=d)["id"]
    assert P.next_stage(pid, d) == ("run", "research")
    with pytest.raises(P.GateError, match="research"):
        P.start(pid, "proposal", d=d)                          # cannot skip ahead
    assert run(pid, "research", d)["status"] == "done"         # no gate: done at once
    assert run(pid, "proposal", d)["status"] == "awaiting_approval"
    assert P.next_stage(pid, d) == ("gate", "proposal")
    with pytest.raises(P.GateError):
        P.start(pid, "script", d=d)                            # the gate holds
    P.approve(pid, "proposal", by="ali", d=d)
    assert P.next_stage(pid, d) == ("run", "script")


def test_finish_needs_its_artifact(d):
    pid = P.create("explainer", "t", d=d)["id"]
    P.start(pid, "research", d=d)
    with pytest.raises(P.GateError, match="artifact"):
        P.finish(pid, "research", d=d)


def test_feedback_reruns_with_the_note_and_is_capped(d):
    pid = P.create("explainer", "t", d=d)["id"]
    run(pid, "research", d)
    run(pid, "proposal", d)
    with pytest.raises(P.GateError, match="note"):
        P.feedback(pid, "proposal", "  ", d=d)
    for i in range(P.MAX_REVISIONS):
        cp = P.feedback(pid, "proposal", f"daha cesur {i}", by="ali", d=d)
        assert cp["status"] == "pending" and cp["note"] == f"daha cesur {i}"
        assert P.start(pid, "proposal", d=d)["note"] == f"daha cesur {i}"   # the agent sees the note
        P.finish(pid, "proposal", {"v": i}, d=d)
    with pytest.raises(P.GateError, match="revisions"):
        P.feedback(pid, "proposal", "bir daha", d=d)


def test_reopen_marks_later_stages_stale_and_keeps_their_work(d):
    pid = P.create("explainer", "t", d=d)["id"]
    run(pid, "research", d)
    run(pid, "proposal", d)
    P.approve(pid, "proposal", d=d)
    run(pid, "script", d, {"lines": ["a"]})
    P.approve(pid, "script", d=d)
    P.reopen(pid, "proposal", by="ali", d=d)
    assert P.checkpoint(pid, "proposal", d)["status"] == "awaiting_approval"
    assert P.checkpoint(pid, "script", d)["status"] == "stale"
    assert P.read_artifact(pid, "script", d) == {"lines": ["a"]}       # nothing is deleted
    assert P.checkpoint(pid, "scene_plan", d)["status"] == "pending"    # never ran: stays pending
    P.approve(pid, "proposal", d=d)
    assert P.next_stage(pid, d) == ("run", "script")                   # the stale stage runs again


def test_failed_stage_takes_feedback_and_flow_view(d):
    pid = P.create("explainer", "t", video_lang="en", d=d)["id"]
    P.start(pid, "research", d=d)
    P.fail(pid, "research", "web search timed out", d=d)
    assert P.next_stage(pid, d) == ("failed", "research")
    P.feedback(pid, "research", "try fewer sources", d=d)
    f = P.flow(pid, "en", d=d)
    assert f["line"]["name"] == "Explainer" and f["stages"][0]["name"] == "Research"
    assert f["stages"][0]["note"] == "try fewer sources" and f["state"] == "run"
    assert any(e["kind"] == "stage_fail" for e in P.tail(pid, d=d))


def _planned_line(monkeypatch, tmp_path):
    """Every real line is built now: a copy of the manifests plus one line that is still only planned."""
    import shutil
    pdir = tmp_path / "pipelines"
    shutil.copytree(manifest.DIR, pdir)
    m = yaml.safe_load(open(pdir / "documentary.yaml"))
    m.update(id="later", order=99, status="planned", stages=[{"id": "idea", "gate": True, "run": "planned"}])
    yaml.safe_dump(m, open(pdir / "later.yaml", "w"), allow_unicode=True)
    monkeypatch.setattr(manifest, "DIR", str(pdir))


def test_planned_stages_cannot_run(d, monkeypatch, tmp_path):
    _planned_line(monkeypatch, tmp_path)
    pid = P.create("later", "Şehir 4'te", d=d)["id"]
    with pytest.raises(P.GateError, match="not built"):
        P.start(pid, "idea", d=d)


# ---------------------------------------------------------------- the line manager

def _fake_line(monkeypatch, outputs, fail_on=()):
    """Stand in for the stage agent and the code steps: each stage returns outputs[sid] (or a default)."""
    from factory.hat import runner

    def fake_agent(pid, s, note=None, d=None):
        if s["id"] in fail_on:
            raise RuntimeError(f"{s['id']} broke")
        out = outputs.get(s["id"], {"artifact": {"ok": s["id"], "note": note}})
        return out(note) if callable(out) else out
    import types, sys, factory.hat
    fake = types.SimpleNamespace(run_stage=fake_agent)
    monkeypatch.setitem(sys.modules, "factory.hat.agent", fake)
    monkeypatch.setattr(factory.hat, "agent", fake, raising=False)   # `from . import agent` reads the package first
    monkeypatch.setattr(runner, "_code_step", lambda call: fake_agent)
    return runner


class Q:
    """A job queue that runs each job at once, like the real worker would."""
    def __init__(self, runner, d):
        self.runner, self.d, self.jobs = runner, d, []

    def __call__(self, kind, arg):
        self.jobs.append((kind, arg))
        self.runner.run_job(arg, self, d=self.d)
        return len(self.jobs)


def test_line_runs_until_each_gate(d, monkeypatch):
    runner = _fake_line(monkeypatch, {"proposal": {"artifact": {"cost": {"credits": 640, "usd": 0.0}}}})
    pid = P.create("explainer", "t", d=d)["id"]
    q = Q(runner, d)
    assert runner.advance(pid, q, d=d) == ("gate", "proposal")   # research ran and the line stopped at the gate
    assert [j[0] for j in q.jobs] == ["hat_stage", "hat_stage"]
    assert runner.approve(pid, "proposal", q, by="ali", d=d) == ("gate", "script")
    assert P.load(pid, d)["budget"]["credits"] == 640                 # the approved proposal fixed the budget
    for sid in ("script", "scene_plan", "assets"):
        runner.approve(pid, sid, q, d=d)
    assert P.next_stage(pid, d) == ("gate", "publish")              # edit and compose ran on their own
    runner.approve(pid, "publish", q, d=d)
    assert P.next_stage(pid, d) == ("done", None)


def test_feedback_reaches_the_stage_and_failures_wait(d, monkeypatch):
    runner = _fake_line(monkeypatch, {"script": lambda note: {"artifact": {"lines": [note or "ilk"]}}},
                        fail_on=("scene_plan",))
    pid = P.create("explainer", "t", d=d)["id"]
    q = Q(runner, d)
    runner.advance(pid, q, d=d)
    runner.approve(pid, "proposal", q, d=d)
    assert P.read_artifact(pid, "script", d)["lines"] == ["ilk"]
    assert runner.feedback(pid, "script", "daha kısa", q, d=d) == ("gate", "script")
    assert P.read_artifact(pid, "script", d)["lines"] == ["daha kısa"]
    assert runner.approve(pid, "script", q, d=d) == ("failed", "scene_plan")
    assert "broke" in P.checkpoint(pid, "scene_plan", d)["error"]
    assert runner.back(pid, "script", d=d) == ("gate", "script")


def test_job_dispatch_is_wired():
    src = open(os.path.join(os.path.dirname(__file__), "..", "factory", "jobs.py"), encoding="utf-8").read()
    assert 'kind == "hat_stage"' in src


# ---------------------------------------------------------------- tools

def test_agent_stages_only_name_real_tools():
    from factory.hat import tools as T
    for m in manifest.all_lines().values():
        for s in m["stages"]:
            if s["run"] == "agent":
                for n in s["tools"]:
                    assert n in T.BUILTIN or (n in T.TOOLS and T.TOOLS[n]["agent"]), (m["id"], s["id"], n)
            elif s["run"] == "code":
                for n in s["tools"]:
                    assert n in T.TOOLS, (m["id"], s["id"], n)


def test_tool_contract_and_argument_check(d):
    from factory.hat import tools as T
    pid = P.create("explainer", "t", video_lang="en", d=d)["id"]
    ctx = T.Ctx(pid, "research", d)
    info = T.call("project_info", ctx)
    assert info["video_lang"] == "en" and info["stage"] == "research"
    with pytest.raises(T.ToolError, match="bad arguments"):
        T.call("read_artifact", ctx, {})
    with pytest.raises(T.ToolError, match="no artifact"):
        T.call("read_artifact", ctx, {"name": "script"})
    listed = {t["name"]: t for t in T.describe()}
    assert "fn" not in listed["render_stills"] and listed["render_stills"]["capability"] == "design"
    ours, builtins = T.agent_tools(["web_search", "catalog", "nope"])
    assert ours[:3] == ["project_info", "read_artifact", "submit_artifact"] and "catalog" in ours
    assert builtins == ["WebSearch"] and "nope" not in ours
    assert any(e["kind"] == "tool" and e["tool"] == "project_info" for e in P.tail(pid, d=d))


def test_submit_artifact_is_checked_against_the_schema(d):
    from factory.hat import tools as T
    pid = P.create("explainer", "t", d=d)["id"]
    ctx = T.Ctx(pid, "research", d)
    r = T.call("submit_artifact", ctx, {"data": {"insight": "short"}})
    assert not r["accepted"] and any("sources" in x for x in r["problems"])
    good = {"insight": "TTF crossed 100 EUR/MWh intraday", "summary": "ok",
            "sources": [{"url": f"https://x.org/{i}", "title": "x"} for i in range(3)],
            "data_points": [{"claim": "100.425 EUR/MWh", "source": "https://x.org/0"}],
            "angles": [{"title": "a", "grounded_in": "x"}, {"title": "b", "grounded_in": "y"}]}
    assert T.call("submit_artifact", ctx, {"data": good})["accepted"]
    assert P.read_artifact(pid, "research", d)["insight"].startswith("TTF")


def test_draft_timing_follows_the_language():
    from factory.hat import explainer as E
    words, lt, dur = E.draft_timing(["bir iki üç dört", "beş altı"], "tr")
    assert len(words) == 6 and len(lt) == 2 and lt[1]["start"] > lt[0]["end"]
    assert abs((lt[0]["end"] - lt[0]["start"]) - 4 / E.WPS["tr"]) < 0.01


PLAN = {"concept": "test", "palette": {"bg": "#14232B", "ink": "#EDF1E8", "accent": "#F5B942"}, "summary": "s",
        "scenes": [{"id": "hook", "lines": [0, 0], "html": '<div class="sc" style="background:#14232B"><h1 '
                    'style="position:absolute;left:64px;top:400px;color:#F5B942;font-size:90px">AVRUPA GAZI</h1></div>'},
                   {"id": "end", "lines": [1, 1], "html": '<div class="sc" style="background:#101E26"><h1 '
                    'style="position:absolute;left:64px;top:700px;color:#EDF1E8;font-size:80px">TAKİP ET</h1></div>'}]}


def test_render_stills_draws_the_plan(d, monkeypatch, tmp_path):
    from factory.hat import tools as T
    if not T.available("render_stills")[0]:
        pytest.skip("no chromium here")
    from factory import config
    root = os.path.realpath(config.ROOT)
    pdir = os.path.join(root, "projects", "_test_" + os.path.basename(str(tmp_path)))   # the renderer serves ROOT only
    try:
        pid = P.create("explainer", "stills", d=pdir)["id"]
        P.write_artifact(pid, "script", {"lines": ["Avrupa gazı yüz avroyu aştı.", "Takip et."]}, pdir)
        r = T.call("render_stills", T.Ctx(pid, "scene_plan", pdir), {"plan": PLAN})
        assert len(r["stills"]) == 2 and all(os.path.getsize(s) > 1000 for s in r["stills"]), r
    finally:
        import shutil
        shutil.rmtree(pdir, ignore_errors=True)


# ---------------------------------------------------------------- MCP server

def test_mcp_lists_and_calls_only_allowed_tools(d):
    from factory.hat import mcp_server as M, tools as T
    pid = P.create("explainer", "t", d=d)["id"]
    ctx, allowed = T.Ctx(pid, "research", d), ["project_info", "read_artifact", "submit_artifact"]
    init = M.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
                    ctx, allowed)
    assert init["result"]["capabilities"]["tools"] is not None
    assert M.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}, ctx, allowed) is None
    names = [t["name"] for t in M.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, ctx, allowed)["result"]["tools"]]
    assert names == allowed
    r = M.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "catalog"}}, ctx, allowed)
    assert r["result"]["isError"] and "not allowed" in r["result"]["content"][0]["text"]
    r = M.handle({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                  "params": {"name": "project_info", "arguments": {}}}, ctx, allowed)
    assert not r["result"]["isError"] and json.loads(r["result"]["content"][0]["text"])["stage"] == "research"


def test_mcp_server_speaks_stdio(d):
    import subprocess
    from factory.hat import mcp_server as M
    pid = P.create("explainer", "t", video_lang="en", d=d)["id"]
    cfg = M.config(pid, "research", ["project_info", "read_artifact", "submit_artifact"], d=d)
    msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "project_info", "arguments": {}}}]
    p = subprocess.run([cfg["command"], *cfg["args"]], input="\n".join(json.dumps(m) for m in msgs) + "\n",
                       capture_output=True, text=True, env={**os.environ, **cfg["env"]}, timeout=60)
    out = [json.loads(x) for x in p.stdout.splitlines() if x.strip()]
    assert [o["id"] for o in out] == [1, 2, 3], p.stderr
    assert json.loads(out[2]["result"]["content"][0]["text"])["video_lang"] == "en"


# ---------------------------------------------------------------- stage agent

@pytest.fixture
def skills(tmp_path, monkeypatch):
    from factory.hat import agent as A
    root = tmp_path / "skills"
    (root / "meta").mkdir(parents=True)
    (root / "pipelines" / "explainer").mkdir(parents=True)
    (root / "meta" / "stage-agent.md").write_text("CONTRACT TEXT")
    (root / "meta" / "reviewer.md").write_text("REVIEWER CONTRACT")
    (root / "pipelines" / "explainer" / "research.md").write_text("RESEARCH BRIEF")
    monkeypatch.setattr(A, "SKILLS", str(root))
    return A


GOOD_RESEARCH = {"insight": "TTF crossed 100 EUR/MWh intraday", "summary": "Kaynaklar hazır.",
                 "sources": [{"url": f"https://x.org/{i}", "title": "x"} for i in range(3)],
                 "data_points": [{"claim": "100.425 EUR/MWh", "source": "https://x.org/0"}],
                 "angles": [{"title": "a", "grounded_in": "x"}, {"title": "b", "grounded_in": "y"}]}


def test_agent_stage_counts_only_a_submitted_artifact(d, skills, monkeypatch):
    from factory import llm
    from factory.hat import tools as T
    pid = P.create("explainer", "t", video_lang="en", d=d, extra={"ui_lang": "tr"})["id"]
    s = manifest.stage(manifest.get("explainer"), "research")
    seen = {}

    def fake_cli(prompt, tools=(), servers=None, **k):
        if "REVIEWER CONTRACT" in prompt:
            return '{"verdict": "pass", "findings": [], "summary": "İyi."}', {"cost_usd": 0.03}
        seen.update(prompt=prompt, tools=tools, servers=servers, k=k)
        T.call("submit_artifact", T.Ctx(pid, "research", d), {"data": GOOD_RESEARCH})
        return "submitted", {"cost_usd": 0.12}
    monkeypatch.setattr(llm, "ask_text", fake_cli)
    out = skills.run_stage(pid, s, note="daha güncel kaynak", d=d)
    assert out["summary"] == "Kaynaklar hazır." and out["cost"]["usd"] == 0.15
    assert out["review"]["verdict"] == "pass" and out["review"]["rounds"] == 1
    assert "CONTRACT TEXT" in seen["prompt"] and "RESEARCH BRIEF" in seen["prompt"]
    assert "daha güncel kaynak" in seen["prompt"] and "Video language: English" in seen["prompt"]
    assert "Interface language for `summary`: Turkish" in seen["prompt"] and "At least 5 sources" in seen["prompt"]
    assert "WebSearch" in seen["tools"] and "mcp__factory__submit_artifact" in seen["tools"]
    assert seen["servers"]["factory"]["env"]["HAT_STAGE"] == "research" and seen["k"]["budget_usd"] == 2.0

    def lazy_cli(prompt, **k):
        return "I think it is fine.", {"cost_usd": 0.01}
    monkeypatch.setattr(llm, "ask_text", lazy_cli)
    os.utime(P.path(pid, "artifacts", "research.json", d=d), (1, 1))     # an old artifact must not count
    with pytest.raises(skills.AgentError, match="without an accepted"):
        skills.run_stage(pid, s, d=d)


def test_cli_commands_attach_our_server(monkeypatch, tmp_path):
    from factory import accounts, llm
    servers = {"factory": {"command": "/py", "args": ["-m", "factory.hat.mcp_server"], "env": {"HAT_PROJECT": "001-x"}}}
    flags = llm._codex_server_flags(servers)
    assert 'mcp_servers.factory.command="/py"' in flags
    assert 'mcp_servers.factory.env={HAT_PROJECT="001-x"}' in flags
    seen = {}

    class R:
        returncode, stderr = 0, ""
        stdout = json.dumps({"type": "result", "result": "ok", "total_cost_usd": 0, "usage": {}})

    def fake_run(cmd, **k):
        seen["cmd"] = cmd
        return R()
    import subprocess
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(llm, "_record", lambda *a, **k: None)
    monkeypatch.setattr(llm, "selected_provider", lambda *a, **k: "claude")
    monkeypatch.setattr(accounts, "claude_env", lambda: {})
    monkeypatch.setattr(llm, "WORKDIR", str(tmp_path))
    monkeypatch.setattr(llm, "ask_text", _REAL_ASK_TEXT)      # subprocess is faked above, so nothing real runs
    llm.ask_text("hi", tools=("mcp__factory__project_info",), servers=servers, budget_usd=2.0, model="sonnet")
    cmd = seen["cmd"]
    cfg = cmd[cmd.index("--mcp-config") + 1]
    assert "--strict-mcp-config" in cmd and cmd[cmd.index("--max-budget-usd") + 1] == "2.0"
    assert json.load(open(cfg))["mcpServers"]["factory"]["type"] == "stdio"


def test_reviewer_sends_critical_findings_back_once(d, skills, monkeypatch):
    from factory import llm
    from factory.hat import tools as T
    pid = P.create("explainer", "t", d=d)["id"]
    s = manifest.stage(manifest.get("explainer"), "research")
    calls = {"author": [], "review": []}
    verdicts = iter(['{"verdict": "fix", "findings": [{"severity": "critical", "item": "sources", '
                     '"problem": "only 3 sources", "fix": "add two more"}, {"severity": "nitpick", "item": "tone", '
                     '"problem": "dry", "fix": "warmer"}], "summary": "Kaynak az."}',
                     '{"verdict": "pass", "findings": [{"severity": "suggestion", "item": "angles", "problem": "x", '
                     '"fix": "y"}], "summary": "Tamam."}'])

    def fake_cli(prompt, tools=(), servers=None, model=None, **k):
        if "REVIEWER CONTRACT" in prompt:
            calls["review"].append(model)
            assert "mcp__factory__submit_artifact" not in tools        # the reviewer cannot rewrite the output
            return next(verdicts), {"cost_usd": 0.05}
        calls["author"].append(prompt)
        T.call("submit_artifact", T.Ctx(pid, "research", d), {"data": GOOD_RESEARCH})
        return "submitted", {"cost_usd": 0.1}
    monkeypatch.setattr(llm, "ask_text", fake_cli)
    out = skills.run_stage(pid, s, d=d)
    assert len(calls["author"]) == 2 and "only 3 sources -> add two more" in calls["author"][1]
    assert calls["review"] == ["opus", "opus"]                      # sonnet wrote it, opus reviews it
    assert out["review"]["verdict"] == "pass" and out["review"]["open_critical"] == 0 and out["review"]["rounds"] == 2
    assert P.checkpoint(pid, "research", d)["revisions"] == 0      # internal rounds cost the creator nothing


def test_a_broken_review_never_blocks_the_stage(d, skills, monkeypatch):
    from factory import llm
    from factory.hat import tools as T
    pid = P.create("explainer", "t", d=d)["id"]
    s = manifest.stage(manifest.get("explainer"), "research")

    def fake_cli(prompt, **k):
        if "REVIEWER CONTRACT" in prompt:
            raise llm.LLMError("claude timed out")
        T.call("submit_artifact", T.Ctx(pid, "research", d), {"data": GOOD_RESEARCH})
        return "submitted", {"cost_usd": 0.1}
    monkeypatch.setattr(llm, "ask_text", fake_cli)
    out = skills.run_stage(pid, s, d=d)
    assert out["review"]["verdict"] == "unknown" and "timed out" in out["review"]["error"]


def test_every_agent_stage_of_a_ready_line_has_a_brief_that_expands(d):
    from factory.hat import agent as A
    for m in manifest.all_lines().values():
        if m["status"] != "ready":
            continue
        pid = P.create(m["id"], "brief check", video_lang="tr", d=d)["id"]
        for s in m["stages"]:
            if s["run"] == "agent":
                text = A.task(pid, s, note=None, d=d)
                assert "{{include" not in text and len(text) > 1500, (m["id"], s["id"])
    ex = P.create("explainer", "brief check", video_lang="tr", d=d)["id"]
    sp = A.task(ex, manifest.stage(manifest.get("explainer"), "scene_plan"), d=d)
    assert "FX LIBRARY" in sp and "@@SCENE" not in sp and "stock_search" in sp


# ---------------------------------------------------------------- explainer code stages (real render, no credits)

def test_assets_edit_compose_render_for_real(monkeypatch, tmp_path):
    from factory import config, eleven, productions
    from factory.hat import explainer as E, tools as T
    if not T.available("render_stills")[0]:
        pytest.skip("no chromium here")
    voice = os.path.join(config.ROOT, "assets", "eleven", "tts_2bf8194fcfed0971.mp3")
    if not os.path.exists(voice):
        pytest.skip("no sample voice file")
    pdir = os.path.join(os.path.realpath(config.ROOT), "projects", "_test_" + os.path.basename(str(tmp_path)))
    lines = ["Avrupa gazı yüz avroyu aştı.", "Takip et."]
    spent = []

    def fake_tts(con, text, voice_id, model, approved=None, account=None):
        spent.append(approved)
        return voice, 12.0
    monkeypatch.setattr(eleven, "tts", fake_tts)
    monkeypatch.setattr(productions, "align", lambda path, ls, lang: (E.draft_timing(ls, lang)[1], 3.0,
                                                                       E.draft_timing(ls, lang)[0]))
    try:
        pid = P.create("explainer", "render", d=pdir, extra={"ui_lang": "tr"})["id"]
        P.write_artifact(pid, "script", {"title": "Avrupa gazı", "lines": lines}, pdir)
        P.write_artifact(pid, "proposal", {"music": {"use": False}, "look": "finance"}, pdir)
        P.write_artifact(pid, "scene_plan", PLAN, pdir)
        with pytest.raises(P.GateError, match="budget"):
            E.assets(pid, {}, d=pdir)                                    # no approved budget, no spending
        p = P.load(pid, pdir)
        p["budget"] = {"credits": 640}
        P.save(p, pdir)
        out = E.assets(pid, {}, d=pdir)
        assert spent == [640] and out["cost"]["credits"] == 12 and "Ses hazır" in out["summary"]
        assert os.path.getsize(P.path(pid, "renders", "preview.mp4", d=pdir)) > 10000
        P.write_artifact(pid, "assets", out["artifact"], pdir)
        P.write_artifact(pid, "edit", E.edit(pid, {}, d=pdir)["artifact"], pdir)
        fin = E.compose(pid, {}, d=pdir)["artifact"]
        assert os.path.getsize(os.path.join(config.ROOT, fin["final"])) > 10000
        assert "technical" in fin["qa"] and fin["covers"], fin
    finally:
        import shutil
        shutil.rmtree(pdir, ignore_errors=True)


def test_api_advance_starts_a_stalled_line(d, monkeypatch):
    """A line that stands still in 'run' (nothing queued it) is started by the board's advance action."""
    from studio import hat_api
    runner = _fake_line(monkeypatch, {})
    monkeypatch.setattr(hat_api, "_check", lambda pid: pid)
    monkeypatch.setattr(hat_api.accounts, "current", lambda: "ali")
    monkeypatch.setattr(runner, "advance", lambda pid, q, by=None, d_=None, **k: runner.__dict__["_adv"](pid, q, by))
    pid = P.create("explainer", "t", d=d)["id"]
    calls = []
    runner._adv = lambda pid_, q, by: calls.append((pid_, by)) or ("busy", "research")
    out = hat_api.post(None, f"/api/hat/project/{pid}", {"action": "advance"}, lambda *a: 1)
    assert out == {"id": pid, "state": "busy", "stage": "research"} and calls == [(pid, "ali")]


# ---------------------------------------------------------------- migrating the old productions

def _old_system(tmp_path):
    import sqlite3
    src = tmp_path / "old"
    (src / "data").mkdir(parents=True)
    con = sqlite3.connect(src / "data" / "factory.db")
    con.execute("""CREATE TABLE productions (prod_id INTEGER PRIMARY KEY, created_at TEXT, updated_at TEXT, format TEXT,
        title TEXT, stage TEXT, brief TEXT, data TEXT, name TEXT, preview TEXT, output TEXT, qa TEXT, verification TEXT,
        history TEXT, job_id INT, note TEXT, channel_id TEXT)""")
    data = json.dumps({"lang": "tr", "hook": "Kanca", "aspect": "9:16", "topic": "konu",
                       "voice": {"lines": ["Birinci satır.", "İkinci satır."]},
                       "facts": [{"claim": "A yüzde 5", "source": "https://x.org/a"}, {"claim": "B 7", "source": "https://x.org/b"}],
                       "post": {"caption": "Altyazı burada?", "hashtags": "#bir #iki"}})
    ver = json.dumps({"verdicts": [{"claim": "A yüzde 5", "verdict": "supported", "sources": []}]})
    rows = [(1, "explainer_short", "Yayında Olan", "published", "201_yayinda", ver, json.dumps({"pass": True})),
            (2, "explainer_short", "Önizlemedeki", "preview", "202_onizleme", None, None),
            (3, "explainer_short", "Hazır ama kaldı", "ready", "203_hazir", ver, json.dumps({"pass": False})),
            (4, "story_vo", "Hikâye", "ready", "204_hikaye", None, None)]
    for pid, fmt, title, stage, name, v, qa in rows:
        con.execute("insert into productions (prod_id,format,title,stage,data,name,output,verification,qa) values (?,?,?,?,?,?,?,?,?)",
                    (pid, fmt, title, stage, data, name, name, v, qa))
        if stage in ("ready", "published"):
            (src / "out" / name).mkdir(parents=True)
            (src / "out" / name / f"{name}.mp4").write_bytes(b"video")
            (src / "out" / name / "caption.txt").write_text("cap")
    con.commit(); con.close()
    return src


def test_migrate_dry_run_maps_states_and_writes_nothing(tmp_path, d):
    from factory.hat import migrate
    src = _old_system(tmp_path)
    rep = {r["prod"]: r for r in migrate.migrate(str(src), d)}
    assert rep[1]["states"]["publish"] == "approved" and set(rep[1]["states"].values()) == {"done", "approved"}
    assert set(rep[2]["states"].values()) == {"pending"}
    assert rep[3]["states"]["publish"] == "awaiting_approval" and "qa did not pass" in rep[3]["flags"]
    assert rep[4]["line"] == "travel_vlog" and rep[4]["states"]["idea"] == "done"
    assert P.list_ids(d) == []


def test_migrate_imports_unflagged_copies_files_and_holds_the_rest(tmp_path, d, monkeypatch):
    from factory.hat import migrate
    src = _old_system(tmp_path)
    before = sorted(str(p) for p in src.rglob("*"))
    rep = {r["prod"]: r for r in migrate.migrate(str(src), d, apply=True)}
    assert [rep[i]["result"] for i in (1, 2, 4)] == ["imported"] * 3 and rep[3]["result"] == "held (flagged)"
    assert sorted(str(p) for p in src.rglob("*")) == before                       # the old system is untouched
    assert (src / "out" / "201_yayinda" / "201_yayinda.mp4").exists()
    pid = rep[1]["project"]
    p = P.load(pid, d)
    assert p["budget"] is None and p["imported_from"]["prod_id"] == 1 and p["video_lang"] == "tr"
    assert os.path.exists(P.path(pid, "renders", "201_yayinda.mp4", d=d))
    script = P.read_artifact(pid, "script", d)
    assert script["lines"][0] == "Birinci satır." and script["caption"].startswith("Altyazı")
    # only the fact the old check marked as supported is verified
    assert [c["verified"] for c in script["claims"]] == [True, False]
    assert P.read_artifact(pid, "legacy", d)["prod_id"] == 1
    assert P.read_artifact(pid, "research", d) is None and P.read_artifact(pid, "scene_plan", d) is None
    # the in-progress one resumes at the script gate; the published one is complete
    assert P.next_stage(rep[2]["project"], d) == ("run", "research")
    assert P.next_stage(pid, d) == ("done", None)
    # idempotent: a second run skips what exists; --force redoes it
    again = {r["prod"]: r for r in migrate.migrate(str(src), d, apply=True)}
    assert again[1]["result"] == "skipped (already imported)"
    assert {r["prod"]: r for r in migrate.migrate(str(src), d, apply=True, force=True)}[1]["result"] == "imported"
    # --force refuses a project somebody worked on after the import
    P.event(rep[1]["project"], "approve", d=d, stage="publish")
    assert {r["prod"]: r for r in migrate.migrate(str(src), d, apply=True, force=True)}[1]["result"].startswith("refused")
    # the flagged row comes in only when asked for
    assert {r["prod"]: r for r in migrate.migrate(str(src), d, apply=True, include_flagged=True)}[3]["result"] == "imported"


def test_imported_projects_show_on_the_board_in_both_languages(tmp_path, d, monkeypatch):
    from factory.hat import migrate
    from studio import hat_api
    src = _old_system(tmp_path)
    migrate.migrate(str(src), d, apply=True, include_flagged=True)
    monkeypatch.setattr(P, "DIR", d)
    for lang in ("tr", "en"):
        monkeypatch.setattr(hat_api, "lang", lambda l=lang: l)
        assert len(hat_api.projects()) == 4
        for pid in P.list_ids(d):
            f = hat_api.project(pid)
            assert f["stages"] and f["state"] in ("run", "gate", "busy", "failed", "done")
            P.next_stage(pid, d)
    gate = next(i for i in P.list_ids(d) if "onizlemedeki" in i)
    assert hat_api.project(gate)["state"] == "run"


# ---------------------------------------------------------------- the board's API: gate actions and their refusals

@pytest.fixture
def api(d, monkeypatch):
    from studio import hat_api
    monkeypatch.setattr(P, "DIR", d)
    monkeypatch.setattr(hat_api.accounts, "current", lambda: "ali")
    monkeypatch.setattr(hat_api, "lang", lambda: "en")
    runner = _fake_line(monkeypatch, {"proposal": {"artifact": {"cost": {"credits": 100, "usd": 0.0}}}})
    pid = P.create("explainer", "t", d=d)["id"]
    q = Q(runner, d)
    runner.advance(pid, q, d=d)
    return hat_api, pid, q


def test_api_approve_feedback_and_back_walk_the_gates(api):
    hat_api, pid, q = api
    post = lambda **b: hat_api.post(None, f"/api/hat/project/{pid}", b, q)
    assert post(action="approve", stage="proposal") == {"id": pid, "state": "gate", "stage": "script"}
    assert P.load(pid)["budget"]["credits"] == 100 and P.load(pid)["budget"]["approved_by"] == "ali"
    assert post(action="feedback", stage="script", note="shorter")["state"] == "gate"
    assert P.checkpoint(pid, "script")["revisions"] == 1
    assert post(action="back", stage="proposal")["state"] == "gate"      # reopening marks the later stages stale
    assert P.checkpoint(pid, "script")["status"] == "stale"


def test_api_refuses_what_the_gate_rules_forbid(api):
    hat_api, pid, q = api
    post = lambda **b: hat_api.post(None, f"/api/hat/project/{pid}", b, q)
    with pytest.raises(ValueError, match="not waiting for approval"):
        post(action="approve", stage="script")                              # a stage that is not at its gate
    with pytest.raises(ValueError, match="needs a note"):
        post(action="feedback", stage="proposal", note="  ")
    with pytest.raises(ValueError, match="unknown action"):
        post(action="skip", stage="proposal")
    for i in range(P.MAX_REVISIONS):
        post(action="feedback", stage="proposal", note=f"again {i}")
    with pytest.raises(ValueError, match="revisions"):
        post(action="feedback", stage="proposal", note="once more")
    assert post(action="approve", stage="proposal")["stage"] == "script"    # the cap leaves approving possible
    with pytest.raises(ValueError, match="no such project"):
        hat_api.post(None, "/api/hat/project/nope", {"action": "approve", "stage": "proposal"}, q)


def test_api_create_checks_line_and_brief(api, monkeypatch, tmp_path):
    hat_api, _, q = api
    _planned_line(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="not ready"):
        hat_api.post(None, "/api/hat/projects", {"line": "later", "brief": "a long enough brief"}, q)
    with pytest.raises(ValueError, match="few words"):
        hat_api.post(None, "/api/hat/projects", {"line": "explainer", "brief": "x"}, q)
    monkeypatch.setattr(hat_api.accounts, "default_eleven", lambda uid: None, raising=False)
    out = hat_api.post(None, "/api/hat/projects", {"line": "explainer", "brief": "Why gas prices rose", "video_lang": "de"}, q)
    assert P.load(out["id"])["video_lang"] == "en"          # an unknown video language falls back to the interface one


def test_media_file_stays_inside_projects(api, d):
    hat_api, pid, _ = api
    open(P.path(pid, "renders", "a.mp4"), "wb").write(b"x")
    open(os.path.join(d, "..", "secret.mp4"), "wb").write(b"x")
    assert hat_api.media_file(f"{pid}/renders/a.mp4")[1] == "video/mp4"
    assert hat_api.media_file("../secret.mp4") is None and hat_api.media_file(f"{pid}/project.json") is None


def test_archive_imports_every_row_read_only(tmp_path, d, monkeypatch):
    from factory.hat import migrate
    from studio import hat_api
    src = _old_system(tmp_path)
    # a row without a recorded name whose render sits in a folder named after the title
    import sqlite3
    con = sqlite3.connect(src / "data" / "factory.db")
    con.execute("insert into productions (prod_id,format,title,stage,data) values (5,'explainer_short','Kuyt ne yaptı','voice','{}')")
    con.commit(); con.close()
    (src / "out" / "116_kuyt").mkdir(parents=True)
    (src / "out" / "116_kuyt" / "116_kuyt.mp4").write_bytes(b"v")
    rep = {r["prod"]: r for r in migrate.migrate(str(src), d, apply=True, archive=True)}
    assert all(r["result"] == "imported" for r in rep.values())                   # flags do not hold an archive
    assert rep[5]["project"].startswith("116-") and rep[5]["files"]["final"] == "out/116_kuyt/116_kuyt.mp4"
    monkeypatch.setattr(P, "DIR", d)
    monkeypatch.setattr(hat_api, "lang", lambda: "en")
    monkeypatch.setattr(hat_api.accounts, "current", lambda: "ali")
    for r in rep.values():
        assert P.load(r["project"], d)["status"] == "archived" and P.next_stage(r["project"], d)[0] == "done"
        assert hat_api.project(r["project"])["state"] == "archived"
    listed = {p["id"]: p for p in hat_api.projects()}
    assert listed[rep[1]["project"]]["state"] == "archived" and listed[rep[1]["project"]]["video"].endswith("201_yayinda.mp4")
    with pytest.raises(ValueError, match="archive"):
        hat_api.post(None, f"/api/hat/project/{rep[1]['project']}", {"action": "back", "stage": "script"}, lambda *a: 1)


# ---------------------------------------------------------------- motion graphics: music-led beats

def test_beats_hold_their_seconds_and_hide_captions(d):
    from factory.hat import explainer as X
    words, lt, dur = X.beat_timing(["Yüz avro", "%74,9", "Kim kazanır?"], [1.0, 2.0, None])
    assert dur == 1.0 + 2.0 + X.HOLD and lt[1] == {"start": 1.0, "end": 3.0}
    assert words[0] == ("Yüz", 0.0, 0.5) and words[2][1] == 1.0
    pid = P.create("animation", "t", d=d)["id"]
    P.write_artifact(pid, "script", {"lines": ["a b", "c", "d"], "narrate": False, "holds": [1, 1, 2]}, d)
    plan = {"scenes": [{"id": "s1", "lines": [0, 1]}, {"id": "s2", "lines": [2, 2]}]}
    sp = X.spec(pid, plan, d)
    assert sp["timing"] == "beats" and all(s["hide_captions"] for s in sp["scenes"])
    assert sp["scenes"][1]["start"] == round(2 + X.VOICE_START, 3)
    P.write_artifact(pid, "script", {"lines": ["a b", "c"]}, d)               # narrated: captions stay
    assert not any(s["hide_captions"] for s in X.spec(pid, {"scenes": [{"id": "s1", "lines": [0, 1]}]}, d)["scenes"])


def test_music_led_assets_make_no_voice_and_stay_in_budget(d, monkeypatch):
    from factory.hat import explainer as X
    from factory import eleven, accounts
    pid = P.create("animation", "t", d=d)["id"]
    p = P.load(pid, d); p["budget"] = {"credits": 900}; P.save(p, d)
    P.write_artifact(pid, "proposal", {"music": {"use": True, "prompt": "120 BPM synth pulse"}}, d)
    P.write_artifact(pid, "script", {"lines": ["a", "b"], "narrate": False, "holds": [2, 3]}, d)
    seen = {}
    monkeypatch.setattr(eleven, "tts", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no voice in a music-led piece")))
    def gen(con, kind, model, prompt, params, units, unit, ext=None, approved=None, account=None):
        seen.update(prompt=prompt, secs=params["duration_seconds"], approved=approved)
        return "/tmp/m.mp3", 400.0
    monkeypatch.setattr(eleven, "generate", gen)
    monkeypatch.setattr(accounts, "default_eleven", lambda u: "ali")
    monkeypatch.setattr(X, "_con", lambda: None)
    monkeypatch.setattr(X, "_render", lambda pid_, final, d=None: ({"file": "/tmp/p.mp4"}, {"duration": 6.45}))
    out = X.assets(pid, {"id": "assets"}, d=d)
    assert seen["approved"] == 900 and seen["prompt"].startswith("Instrumental") and seen["secs"] == round(5 + X.VOICE_START + X.TAIL + 1.5, 1)
    assert out["cost"] == {"credits": 400} and out["artifact"]["voice"] is None and out["artifact"]["music"]["db"] == -10


# ---------------------------------------------------------------- travel vlog: the footage engine behind the gates

@pytest.fixture
def engine(monkeypatch, tmp_path):
    """The old footage engine, faked: rows in a dict, renders as tiny files."""
    from factory import productions as PR
    from factory.hat import footage as F
    rows, calls = {}, []
    def generate(con, fmt, n=3, brief="", aspect="9:16", channel_id=None, lang=None, **k):
        calls.append(("generate", fmt, brief))
        ids = []
        for i in range(n):
            pid = len(rows) + 1
            rows[pid] = {"prod_id": pid, "title": f"Fikir {pid}", "format": fmt, "data": {"hook": f"hook {pid}",
                         "logline": "a walk", "why": "y", "shots": [{"clip_id": "IMG_1.MOV", "in": 0, "out": 3,
                         "shows": "lake", "place": "Eibsee"}], "voice": {"lines": ["bir", "iki"]} if i == 0 else None,
                         "post": {"caption": "Göl mü?", "hashtags": "#eibsee #alps"}}, "qa": None}
            ids.append(pid)
        return ids, {"cost_usd": 0.4}
    def render_file(name):
        f = tmp_path / name
        f.write_bytes(b"v")
        return str(f)
    monkeypatch.setattr(PR, "generate", generate)
    monkeypatch.setattr(PR, "get", lambda con, i: rows[i])
    monkeypatch.setattr(PR, "voice_estimate", lambda con, d: {"credits": 300})
    monkeypatch.setattr(PR, "music_estimate", lambda con, r: {"credits": 900, "seconds": 22.5, "prompt": "calm"})
    monkeypatch.setattr(PR, "voice_text", lambda d: " ".join((d.get("voice") or {}).get("lines") or []))
    monkeypatch.setattr(PR, "direct", lambda con, i, note="": calls.append(("direct", i, note)) or rows[i])
    monkeypatch.setattr(PR, "preview", lambda con, i: render_file("prev.mp4"))
    monkeypatch.setattr(PR, "timeline", lambda con, r: ({}, 21.0, [], ["shot 3 is short"]))
    def voice(con, i, approved):
        calls.append(("voice", approved)); return render_file("v.mp3"), 280.0
    def music(con, i, approved, prompt=None):
        calls.append(("music", approved)); return render_file("m.mp3"), 880.0
    monkeypatch.setattr(PR, "make_voice", voice)
    monkeypatch.setattr(PR, "make_music", music)
    def render(con, i):
        rows[i]["qa"] = {"pass": True, "technical": {"problems": []}}
        return render_file("final.mp4")
    monkeypatch.setattr(PR, "render", render)
    monkeypatch.setattr(F, "_con", lambda: None)
    return rows, calls


def test_travel_vlog_runs_on_the_footage_engine_through_every_gate(d, engine, monkeypatch):
    from factory.hat import runner
    rows, calls = engine
    pid = P.create("travel_vlog", "Eibsee", brief="Eibsee sabahı", d=d)["id"]
    q = Q(runner, d)
    assert runner.advance(pid, q, d=d) == ("gate", "idea")
    prop = P.read_artifact(pid, "proposal", d)
    assert [c["id"] for c in prop["concepts"]] == ["A", "B", "C"] and prop["chosen"] == "A"
    assert prop["cost"]["credits"] == 1200 and P.load(pid, d)["prods"] == [1, 2, 3]
    # naming a concept picks it without a new idea call
    runner.feedback(pid, "idea", "B'yi seç", q, d=d)
    assert P.read_artifact(pid, "proposal", d)["chosen"] == "B" and [c[0] for c in calls].count("generate") == 1
    runner.feedback(pid, "idea", "A", q, d=d)
    assert runner.approve(pid, "idea", q, d=d) == ("gate", "scene_plan")
    assert P.load(pid, d)["budget"]["credits"] == 1200                 # the idea's proposal fixed the budget
    cut = P.read_artifact(pid, "cut_plan", d)
    assert cut["prod_id"] == 1 and cut["warnings"] == ["shot 3 is short"] and os.path.exists(P.path(pid, "renders", "preview.mp4", d=d))
    assert runner.approve(pid, "scene_plan", q, d=d) == ("gate", "assets")
    assert ("voice", 1200) in calls and ("music", 1200 - 280) in calls     # each spend inside what is left
    assert P.checkpoint(pid, "assets", d)["cost"]["credits"] == 1160
    assert runner.approve(pid, "assets", q, d=d) == ("gate", "publish")
    assert P.read_artifact(pid, "render", d)["qa"]["pass"] and os.path.exists(P.path(pid, "renders", "final.mp4", d=d))
    pub = P.read_artifact(pid, "publish", d)
    assert pub["caption"] == "Göl mü?" and pub["hashtags"] == ["#eibsee", "#alps"]


def test_travel_vlog_refuses_a_foreign_production(d, engine):
    from factory.hat import footage as F
    pid = P.create("travel_vlog", "x", d=d)["id"]
    P.write_artifact(pid, "proposal", {"concepts": [{"id": "A", "prod_id": 99}], "chosen": "A"}, d)
    with pytest.raises(P.GateError, match="does not belong"):
        F.chosen_prod(pid, d)


# ---------------------------------------------------------------- talking head: the creator's video, cut by talk.py

def test_talking_head_cuts_at_its_gates(d, engine, monkeypatch, tmp_path):
    from factory import talk, productions as PR
    from factory.hat import runner, talkhead as T
    rows, calls = engine
    raw = os.path.join(T.ROOT, "raw", "talk")
    os.makedirs(raw, exist_ok=True)
    src = os.path.join(raw, "_test_clip.mp4")
    open(src, "wb").write(b"v")
    try:
        def create(con, path, brief, channel, aspect, lang=None):
            calls.append(("create", os.path.basename(path)))
            rows[50] = {"prod_id": 50, "title": "Kesim", "format": "talking_head", "qa": None,
                        "data": {"logline": "l", "music": {"prompt": "lofi"}, "post": {"caption": "Ne dersin?", "hashtags": "#a"}}}
            return 50
        cut = {"kept": [True, False]}
        monkeypatch.setattr(talk, "create", create)
        monkeypatch.setattr(talk, "revise", lambda con, row, note: calls.append(("revise", note)) or cut.update(kept=[True, True]))
        monkeypatch.setattr(talk, "summary", lambda dd: {"raw_s": 60.0, "kept_s": 31.0, "hook": "Dur!", "grade": "film",
            "phrases": [{"id": i, "text": f"p{i}", "kept": k, "pos": i + 1, "flags": []} for i, k in enumerate(cut["kept"])]})
        pid = P.create("talking_head", "t", d=d, extra={"source": "raw/talk/_test_clip.mp4"})["id"]
        q = Q(runner, d)
        assert runner.advance(pid, q, d=d) == ("gate", "idea")
        prop = P.read_artifact(pid, "proposal", d)
        assert prop["concepts"][0]["prod_id"] == 50 and prop["cost"]["credits"] == 900 and prop["seconds"] == 31.0
        assert runner.approve(pid, "idea", q, d=d) == ("gate", "script")
        assert [p["kept"] for p in P.read_artifact(pid, "cut", d)["phrases"]] == [True, False]
        runner.feedback(pid, "script", "ikinci cümleyi geri koy", q, d=d)
        assert ("revise", "ikinci cümleyi geri koy") in calls and P.read_artifact(pid, "cut", d)["phrases"][1]["kept"]
        assert runner.approve(pid, "script", q, d=d) == ("gate", "assets")
        assert not any(c[0] == "voice" for c in calls) and ("music", 900) in calls      # no voice: it is the creator's
        assert runner.approve(pid, "assets", q, d=d) == ("gate", "publish")
        assert P.read_artifact(pid, "publish", d)["caption"] == "Ne dersin?"
    finally:
        os.remove(src)


def test_talking_head_needs_an_uploaded_video(d, api):
    hat_api, _, q = api
    with pytest.raises(ValueError, match="Upload your video"):
        hat_api.post(None, "/api/hat/projects", {"line": "talking_head", "brief": "my talk about cities"}, q)
    with pytest.raises(ValueError, match="Upload your video"):
        hat_api.post(None, "/api/hat/projects", {"line": "talking_head", "brief": "my talk about cities",
                                                 "source": "raw/talk/../../data/users.json"}, q)
    from factory.hat import talkhead as T
    with pytest.raises(P.GateError, match="no uploaded video"):
        T._source({"source": "../data/users.json"})


# ---------------------------------------------------------------- series episode: same characters, same art

def test_series_episode_spends_plates_and_voices_inside_one_budget(d, engine, monkeypatch):
    from factory import series, illustrate, productions as PR
    from factory.hat import runner
    rows, calls = engine
    def write(con, sid, n, note=""):
        pid = 70 + len([c for c in calls if c[0] == "write"])
        calls.append(("write", sid, n, note))
        rows[pid] = {"prod_id": pid, "title": f"Bölüm {n}", "format": "series_episode", "qa": None,
                     "data": {"hook": "Önceki bölümde...", "voice": {"lines": ["Önceki bölümde...", "Kaç!"],
                              "speakers": ["narrator", "kedi"]}, "post": {"caption": "Sence ne olacak?", "hashtags": "#seri"},
                              "plates": {}, "motion": {"concept": "c"}}}
        return pid
    monkeypatch.setattr(series, "write_episode", write)
    monkeypatch.setattr(series, "cast_for", lambda con, row: ([{"id": "kedi"}], "flow1"))
    monkeypatch.setattr(illustrate, "estimate", lambda con, dd, acc, chars: {"images": 6, "credits": 600})
    def plates(con, row, approved, chars, flow):
        calls.append(("plates", approved, flow))
        row["data"]["plates"] = {"s1": {"file": "assets/x.png"}}
        return 550.0
    monkeypatch.setattr(illustrate, "make_plates", plates)
    monkeypatch.setattr(PR, "eleven_account", lambda dd: "ali")
    monkeypatch.setattr(PR, "save", lambda con, row, *a: None)
    monkeypatch.setattr(PR, "design", lambda con, prod, note="": None)
    pid = P.create("series_episode", "Kedi 3", d=d, extra={"series": {"id": 4, "episode": 3}})["id"]
    q = Q(runner, d)
    assert runner.advance(pid, q, d=d) == ("gate", "proposal")
    assert P.read_artifact(pid, "proposal", d)["cost"]["credits"] == 600 + 300 + 900
    runner.approve(pid, "proposal", q, d=d)
    assert P.read_artifact(pid, "script", d)["lines"][1] == "kedi: Kaç!"
    runner.feedback(pid, "script", "kedi daha korkak olsun", q, d=d)          # a rewrite becomes the current row
    assert ("write", 4, 3, "kedi daha korkak olsun") in calls and P.load(pid, d)["current_prod"] == 71
    runner.approve(pid, "script", q, d=d)
    assert ("plates", 1800, "flow1") in calls and P.read_artifact(pid, "plates", d)["plates"] == ["assets/x.png"]
    runner.approve(pid, "scene_plan", q, d=d)
    assert ("voice", 1800 - 550) in calls                                  # the plates' spend counts against the budget
    runner.approve(pid, "assets", q, d=d)
    assert P.read_artifact(pid, "publish", d)["caption"] == "Sence ne olacak?"


def test_series_episode_form_needs_series_and_episode(d, api):
    hat_api, _, q = api
    with pytest.raises(ValueError, match="Pick a series"):
        hat_api.post(None, "/api/hat/projects", {"line": "series_episode", "brief": "episode three please"}, q)


def test_hybrid_checks_every_fact_at_its_gate(d, engine, monkeypatch):
    from factory import productions as PR
    from factory.hat import runner
    rows, calls = engine
    def verify(con, prod):
        rows[prod]["data"]["claims"] = [{"claim": "Eibsee 973 m"}, {"claim": "En derin göl"}]
        rows[prod]["verification"] = {"verdicts": [{"claim": "Eibsee 973 m", "verdict": "supported",
                                                    "sources": [{"url": "https://de.wikipedia.org/wiki/Eibsee"}]},
                                                   {"claim": "En derin göl", "verdict": "refuted"}]}
    monkeypatch.setattr(PR, "verify", verify)
    pid = P.create("hybrid", "Eibsee", d=d)["id"]
    q = Q(runner, d)
    assert runner.advance(pid, q, d=d) == ("gate", "idea")
    assert P.load(pid, d)["format"] == "travel_facts" and calls[0] == ("generate", "travel_facts", "")
    assert runner.approve(pid, "idea", q, d=d) == ("gate", "script")
    sc = P.read_artifact(pid, "script", d)
    assert [c["verified"] for c in sc["claims"]] == [True, False] and sc["claims"][0]["source"].endswith("Eibsee")
    assert "1/2" in P.checkpoint(pid, "script", d)["summary"]


# ---------------------------------------------------------------- media models and the picker

def test_picker_filters_by_inputs_and_ranks_by_need():
    from factory.hat import media
    assert {m["family"] for m in media.MODELS} >= {"image", "video", "avatar", "lipsync"}
    ids = [m["id"] for m in media.pick("avatar", have=["image", "audio"], need=["illustration"], seconds=10, cheap=True)]
    assert ids[0] == "minimax-h3-max-lipsync"                           # the cheap no-GPU path for a drawn character
    long = media.pick("avatar", have=["image", "audio"], need=["talking_head"], seconds=40)
    assert long[0]["id"] != "minimax-h3-max-lipsync" and any("outside" in w for m in long for w in m["why"])
    assert media.pick("avatar", have=["prompt"]) == []                  # an avatar needs an image and audio
    assert [m["id"] for m in media.pick("lipsync", have=["video", "audio"])][0] == "sync-lipsync-v3"
    v = media.pick("video", need=["cinematic", "sound"], seconds=6, aspect="9:16")
    assert v[0]["id"].startswith("veo-3.1")                               # Veo for a short cinematic shot with sound


def test_video_gen_snaps_length_and_stays_in_budget(d, monkeypatch):
    from factory import eleven
    from factory.hat import tools as T, explainer as E
    pid = P.create("explainer", "t", d=d)["id"]
    p = P.load(pid, d); p["budget"] = {"credits": 5000}; P.save(p, d)
    seen = {}
    monkeypatch.setattr(E, "_con", lambda: None)
    monkeypatch.setattr(eleven, "generate", lambda con, kind, model, prompt, params, units, unit, ext=None, approved=None,
                        account=None: seen.update(kind=kind, model=model, params=params, approved=approved, ext=ext) or ("/tmp/v.mp4", 700.0))
    out = T.call("video_gen", T.Ctx(pid, "assets", d), {"prompt": "fog over a lake", "seconds": 7, "model": "veo-3.1-generate-001"})
    assert out["seconds"] == 6 and seen["params"]["duration_secs"] == 6 and seen["approved"] == 5000 and seen["ext"] == "mp4"
    picked = T.call("media_models", T.Ctx(pid, "proposal", d), {"family": "video", "need": ["long"], "seconds": 20})
    assert picked["models"][0]["id"] == "bytedance-seedance-v2.5"


# ---------------------------------------------------------------- cinematic: own clips + generated shots, paid in steps

def test_cinematic_generates_shots_in_paid_steps_behind_gates(d, engine, monkeypatch):
    from factory import credits, eleven, productions as PR
    from factory.hat import runner, cinematic as C
    rows, calls = engine
    monkeypatch.setattr(C, "_con", lambda: None)
    monkeypatch.setattr(credits, "rates", lambda: {"image:gpt-image-2": {"rate": 200}, "video:bytedance-seedance-v2.5": {"rate": 1000},
                                                   "video:bytedance-seedance-v2-fast": {"rate": 300}, "music:eleven_music_v2_5": {"rate": 10}})
    monkeypatch.setattr(PR, "inventory", lambda con: [{"clip_id": "IMG_1.MOV", "kind": "video", "duration": 6.0, "description": "lake"}])
    gen = lambda i: {"kind": "gen", "frame": f"frame {i}", "prompt": f"move {i}", "seconds": 5, "shows": f"g{i}"}
    asks = []
    def ask(prompt):
        asks.append(prompt)
        if "Rewrite this shot list" in prompt:
            return {"shots": [{"kind": "own", "clip_id": "IMG_1.MOV", "in": 0, "out": 3}, gen(1), gen(2)]}, 0.1
        return {"concepts": [{"title": "Sis", "hook": "h", "logline": "l", "music": "low strings", "caption": "c", "hashtags": ["#a"],
                              "shots": [{"kind": "own", "clip_id": "IMG_1.MOV", "in": 1, "out": 9}, {"kind": "own", "clip_id": "NOPE"},
                                        gen(1), gen(2), gen(3), gen(4)]},
                             {"title": "Göl", "hook": "h2", "shots": [{"kind": "own", "clip_id": "IMG_1.MOV"}, gen(1)]}]}, 0.3
    monkeypatch.setattr(C, "_ask", ask)
    def image(con, prompt, approved, account, aspect, flow, model=None):
        calls.append(("image", prompt, approved, flow)); f = os.path.join(str(d), f"img{len(calls)}.png"); open(f, "wb").write(b"i")
        return f, 200.0, "flow1", f"node-{prompt}"
    def video(con, prompt, approved, seconds, account, aspect, flow, start, model):
        calls.append(("video", prompt, approved, start, model)); f = os.path.join(str(d), f"v{len(calls)}.mp4"); open(f, "wb").write(b"v")
        return f, 1000.0, flow, "vnode"
    monkeypatch.setattr(eleven, "image", image)
    monkeypatch.setattr(eleven, "video", video)
    monkeypatch.setattr(C, "_register", lambda con, pid, n, path, shows: (f"gen-{n}", 5.0))
    monkeypatch.setattr(PR, "create", lambda con, fmt, data, brief="", channel_id=None: rows.update({77: {"prod_id": 77, "title": data["title"],
                        "format": fmt, "data": data, "qa": None}}) or 77)
    monkeypatch.setattr(PR, "save", lambda con, row, *a: None)

    pid = P.create("cinematic", "Sis", brief="sisli göl fragmanı", d=d)["id"]
    q = Q(runner, d)
    assert runner.advance(pid, q, d=d) == ("gate", "idea")
    prop = P.read_artifact(pid, "proposal", d)
    a = prop["concepts"][0]
    assert [c["id"] for c in prop["concepts"]] == ["A", "B"]
    assert [s["kind"] for s in a["shots"]] == ["own", "gen", "gen", "gen"]          # unknown clip dropped, at most 3 generated
    assert a["shots"][0]["out"] == 6.0 and a["seconds"] == 20.0                     # own shot clipped to the clip
    assert a["cost"]["credits"] == 3 * 200 + 15 * 1000 + round(21.5 * 10)
    runner.feedback(pid, "idea", "B", q, d=d)
    assert P.read_artifact(pid, "proposal", d)["chosen"] == "B" and len(asks) == 1
    runner.feedback(pid, "idea", "daha ucuz olsun", q, d=d)
    a = P.read_artifact(pid, "proposal", d)["concepts"][0]
    assert {s["model"] for s in a["shots"] if s["kind"] == "gen"} == {"bytedance-seedance-v2-fast"} and len(asks) == 2
    assert runner.approve(pid, "idea", q, d=d) == ("gate", "script")
    budget = P.load(pid, d)["budget"]["credits"]
    assert budget == a["cost"]["credits"]
    runner.feedback(pid, "script", "iki üretilen çekim yeter", q, d=d)
    sl = P.read_artifact(pid, "shot_list", d)
    assert [s["kind"] for s in sl["shots"]] == ["own", "gen", "gen"] and not any(c[0] in ("image", "video") for c in calls)
    assert runner.approve(pid, "script", q, d=d) == ("gate", "scene_plan")
    assert [c[2] for c in calls if c[0] == "image"] == [budget, budget - 200]          # each keyframe inside what is left
    runner.feedback(pid, "scene_plan", "3: daha karanlık", q, d=d)
    imgs = [c for c in calls if c[0] == "image"]
    assert len(imgs) == 3 and imgs[-1][1] == "frame 2. daha karanlık"                 # only shot 3 redone
    frames = P.read_artifact(pid, "plates", d)["frames"]
    assert [f["n"] for f in frames] == [2, 3] and frames[1]["node"] == "node-frame 2. daha karanlık"
    assert runner.approve(pid, "scene_plan", q, d=d) == ("gate", "assets")
    vids = [c for c in calls if c[0] == "video"]
    assert [v[3] for v in vids] == ["node-frame 1", "node-frame 2. daha karanlık"]   # each clip starts from its keyframe
    assert vids[0][2] == budget - 600 and vids[1][2] == budget - 1600
    assert ("music", budget - 2600) in calls
    row = rows[77]
    assert [s["clip_id"] for s in row["data"]["shots"]] == ["IMG_1.MOV", "gen-2", "gen-3"] and P.load(pid, d)["current_prod"] == 77
    runner.feedback(pid, "assets", "2: daha yavaş", q, d=d)
    vids = [c for c in calls if c[0] == "video"]
    assert len(vids) == 3 and vids[-1][1] == "move 1. daha yavaş"                     # only clip 2 regenerated
    runner.feedback(pid, "assets", "geçişler daha yumuşak", q, d=d)
    assert len([c for c in calls if c[0] == "video"]) == 3 and ("direct", 77, "geçişler daha yumuşak") in calls
    assert runner.approve(pid, "assets", q, d=d) == ("gate", "publish")
    assert P.read_artifact(pid, "publish", d)["caption"] == "c"


def test_avatar_line_speaks_inside_the_approved_budget(d, monkeypatch):
    from factory import credits, eleven, productions as PR, qa, thumbs
    from factory.hat import runner, avatar as A
    monkeypatch.setattr(A, "_con", lambda: None)
    monkeypatch.setattr(credits, "rates", lambda: {"tts:eleven_v4": {"rate": 1}, "image:gpt-image-2": {"rate": 200}})
    asks, calls = [], []
    def ask(prompt):
        asks.append(prompt)
        lines = ["Merhaba, bugün yeni özelliği anlatıyorum.", "Üç adımda kurulum yapılıyor ve hepsi bu kadar."]
        if "creator's note" in prompt:
            lines = lines + ["Sorularını yorumlara yaz."]
        return {"title": "Yeni özellik", "lines": lines, "presenter": "a woman in her thirties, studio",
                "caption": "c", "hashtags": ["duyuru"]}, 0.2
    monkeypatch.setattr(A, "_ask", ask)
    def fake(name, ret):
        def f(*a, **k):
            calls.append((name, a, k))
            return ret(a, k) if callable(ret) else ret
        return f
    def touch(n):
        f = os.path.join(str(d), n); open(f, "wb").write(b"x"); return f
    monkeypatch.setattr(eleven, "image", fake("image", lambda a, k: (touch("p.png"), 200.0, "flowP", "imgnode")))
    monkeypatch.setattr(eleven, "tts", fake("tts", lambda a, k: (touch("v.mp3"), 90.0)))
    monkeypatch.setattr(eleven, "upload", fake("upload", "audnode"))
    monkeypatch.setattr(eleven, "avatar", fake("avatar", lambda a, k: (touch("av.mp4"), 3000.0)))
    monkeypatch.setattr(PR, "align", lambda path, lines, lang="en": ([[0, 2], [2, 6]], 6.0, [("Merhaba", 0.0, 0.5), ("bugün", 0.5, 0.9)]))
    monkeypatch.setattr(A, "_burn", lambda src, words, out, aspect="9:16", final=False: open(out, "wb").write(b"m") and out)
    monkeypatch.setattr(qa, "technical", lambda path, expected=None: {"problems": []})
    monkeypatch.setattr(thumbs, "make", lambda *a, **k: [])

    pid = P.create("avatar", "Yeni özellik", brief="yeni özelliği anlatan sunucu", d=d)["id"]
    q = Q(runner, d)
    assert runner.advance(pid, q, d=d) == ("gate", "idea")
    prop = P.read_artifact(pid, "proposal", d)
    secs = prop["seconds"]
    assert secs == round(13 / 2.3 + 1, 1)                                      # 13 Turkish words at 2.3 a second
    assert prop["cost"]["unknown"] and prop["cost"]["credits"] == len(" ".join(prop["concepts"][0]["lines"])) + 200 + round(A.AVATAR_CEILING * secs)
    assert any("(ceiling)" in x["label"] for x in prop["cost"]["lines"])
    assert runner.approve(pid, "idea", q, d=d) == ("gate", "script")
    budget = P.load(pid, d)["budget"]["credits"]
    runner.feedback(pid, "script", "bir kapanış cümlesi ekle", q, d=d)
    assert len(P.read_artifact(pid, "script", d)["lines"]) == 3 and not calls    # rewriting pays nothing
    assert runner.approve(pid, "script", q, d=d) == ("gate", "scene_plan")
    img = [c for c in calls if c[0] == "image"]
    assert len(img) == 1 and img[0][1][2] == budget                             # the portrait inside the approval
    assert P.read_artifact(pid, "plates", d)["presenter"] == {"flow": "flowP", "node": "imgnode", "source": "generate"}
    assert runner.approve(pid, "scene_plan", q, d=d) == ("gate", "assets")
    tts = next(c for c in calls if c[0] == "tts")
    av = next(c for c in calls if c[0] == "avatar")
    assert tts[2]["approved"] == budget - 200
    assert av[1][1:4] == ("imgnode", "audnode", "flowP") and av[1][5] == budget - 200 - 90   # what is left after voice
    assert next(c for c in calls if c[0] == "upload")[1][1] == "flowP"          # the voice joins the presenter's flow
    a = P.read_artifact(pid, "assets", d)
    assert a["avatar"]["credits"] == 3000 and a["preview"].endswith("renders/preview.mp4")
    assert runner.approve(pid, "assets", q, d=d) == ("gate", "publish")
    pub = P.read_artifact(pid, "publish", d)
    assert pub["hashtags"] == ["#duyuru"] and "Yapay zekâ" in pub["notes"]
    assert P.read_artifact(pid, "render", d)["qa"]["pass"]


def test_avatar_portrait_must_be_an_upload(d, monkeypatch):
    from factory.hat import avatar as A
    pid = P.create("avatar", "Portre", brief="portreli sunucu", d=d, extra={"portrait": "data/users.json"})["id"]
    with pytest.raises(P.GateError):
        A._portrait(P.load(pid, d))
    assert A._source(P.load(pid, d)) == "upload"
    assert A._source({"presenter_asset": "x"}) == "saved" and A._source({}) == "generate"


def test_localize_segments_place_and_retime():
    from factory.hat import localize as L
    words = [["Merhaba", 0.0, 0.4, 1], ["dostlar.", 0.5, 0.9, 1], ["Bugün", 2.0, 2.3, 1], ["göl", 2.4, 2.6, 1], ["var", 2.7, 3.0, 1]]
    segs = L.segments(words, 5.0)
    assert [(x["n"], x["start"], x["slot"], x["text"]) for x in segs] == [(1, 0.0, 2.0, "Merhaba dostlar."), (2, 2.0, 3.0, "Bugün göl var")]
    places = L.placements(segs, [[0.0, 2.5], [2.6, 4.0]], 4.0)
    assert places[0]["tempo"] == 1.25 and places[1]["tempo"] == 1.0         # too long -> sped up, never above 1.25
    timed = L.retime([("Hello", 0.0, 1.0), ("lake", 2.6, 3.0)], places)
    assert timed == [("Hello", 0.0, 0.8), ("lake", 2.0, 2.4)]


def test_localize_dub_track_is_as_long_as_the_video(tmp_path):
    import subprocess
    from factory.config import FFMPEG
    from factory.audiofx import decode
    from factory.hat import localize as L
    voice = str(tmp_path / "v.wav")
    subprocess.run([FFMPEG, "-y", "-v", "error", "-f", "lavfi", "-i", "sine=d=3", voice], check=True)
    out = L.dub_track(voice, [{"n": 1, "at": 0.5, "from": 0, "to": 1.5, "tempo": 1.0},
                              {"n": 2, "at": 3.0, "from": 1.5, "to": 3.0, "tempo": 1.2}], 6.0, str(tmp_path / "d.wav"))
    import numpy as np
    a = decode(out)
    on = np.nonzero(np.abs(a) > 1e-3)[0]
    assert abs(len(a) / 16000 - 6.0) < 0.05 and abs(on[0] / 16000 - 0.5) < 0.02    # full length, line 1 at 0.5 s


def test_localize_dubs_inside_the_approved_budget(d, monkeypatch, tmp_path):
    from factory import credits, eleven, productions as PR, qa, thumbs
    from factory.hat import runner, localize as L
    monkeypatch.setattr(L, "_con", lambda: None)
    monkeypatch.setattr(L, "_source", lambda p: "/src.mp4")
    monkeypatch.setattr(L, "_duration", lambda path: 5.0)
    monkeypatch.setattr(L, "_transcribe", lambda path, lang: [["Merhaba", 0.0, 0.4, 1], ["dostlar.", 0.5, 0.9, 1],
                                                               ["Bugün", 2.0, 2.3, 1], ["göl", 2.4, 2.6, 1], ["var", 2.7, 3.0, 1]])
    monkeypatch.setattr(credits, "rates", lambda: {"tts:eleven_v4": {"rate": 1}})
    asks, calls = [], []
    def ask(prompt):
        asks.append(prompt)
        return {"lines": ["Hello friends.", "Today there is a lake" + (" here" if "note" in prompt else "")],
                "title": "Lake", "caption": "c", "hashtags": ["lake"]}, 0.1
    monkeypatch.setattr(L, "_ask", ask)
    def touch(n):
        f = str(tmp_path / n); open(f, "wb").write(b"x"); return f
    monkeypatch.setattr(eleven, "tts", lambda con, text, voice, model, approved=None, account=None: calls.append(("tts", text, approved)) or (touch("v.mp3"), 40.0))
    monkeypatch.setattr(eleven, "video", lambda *a, **k: calls.append(("video", a, k)) or (touch("l.mp4"), 900.0, "f", "n"))
    monkeypatch.setattr(eleven, "new_flow", lambda acc, name="": "flowD")
    monkeypatch.setattr(eleven, "upload", lambda path, flow, acc=None: calls.append(("upload", path, flow)) or f"node-{os.path.basename(path)}")
    monkeypatch.setattr(PR, "align", lambda path, lines, lang="en": ([[0.0, 1.0], [1.1, 2.5]], 2.5, [("Hello", 0.0, 0.5), ("lake", 2.0, 2.4)]))
    monkeypatch.setattr(L, "dub_track", lambda voice, places, dur, out: open(out, "wb").write(b"a") and out)
    monkeypatch.setattr(L, "_mux", lambda video, audio, words, out, aspect="9:16", final=False: open(out, "wb").write(b"m") and out)
    monkeypatch.setattr(qa, "technical", lambda path, expected=None: {"problems": []})
    monkeypatch.setattr(thumbs, "make", lambda *a, **k: [])

    pid = P.create("localize", "Göl", brief="İngilizce dublaj, dudak senkronu da olsun", video_lang="en", d=d,
                   extra={"source": "raw/talk/x.mp4", "source_lang": "tr"})["id"]
    q = Q(runner, d)
    assert runner.advance(pid, q, d=d) == ("gate", "idea")
    prop = P.read_artifact(pid, "proposal", d)
    assert prop["from"] == "tr" and prop["to"] == "en" and prop["lipsync"] and len(prop["segments"]) == 2
    assert prop["cost"]["credits"] == round(len("Merhaba dostlar.Bugün göl var") * 1.15) + L.LIPSYNC_CEILING * 5
    assert runner.approve(pid, "idea", q, d=d) == ("gate", "script")
    budget = P.load(pid, d)["budget"]["credits"]
    assert "at most 30 characters" in asks[0] and not calls                  # 2 s slot at 15 English chars a second; nothing paid
    runner.feedback(pid, "script", "add a note", q, d=d)
    assert P.read_artifact(pid, "script", d)["lines"][1].endswith("here")
    assert runner.approve(pid, "script", q, d=d) == ("gate", "assets")
    assert calls[0] == ("tts", "Hello friends. Today there is a lake here", budget)
    assert [c[2] for c in calls if c[0] == "upload"] == ["flowD", "flowD"]      # video and dub on one flow
    v = next(c for c in calls if c[0] == "video")
    assert v[1][1].startswith("Re-lip-sync") and v[1][2] == budget - 40 and v[2]["model"] == L.LIPSYNC_MODEL
    assert set(v[2]["inputs"]) == {"node-src.mp4", "node-dub.wav"}
    a = P.read_artifact(pid, "assets", d)
    assert a["lipsync"]["credits"] == 900 and a["picture"].endswith("renders/lipsync.mp4")
    assert runner.approve(pid, "assets", q, d=d) == ("gate", "publish")
    assert P.read_artifact(pid, "publish", d)["hashtags"] == ["#lake"]


def test_localize_refuses_the_same_language(d, monkeypatch):
    from factory.hat import localize as L
    monkeypatch.setattr(L, "_source", lambda p: "/src.mp4")
    pid = P.create("localize", "Aynı", brief="aynı dil", video_lang="tr", d=d, extra={"source": "raw/talk/x.mp4", "source_lang": "tr"})["id"]
    with pytest.raises(P.GateError):
        L.idea(pid, None, d=d)


def _clip_segs():
    return [{"n": i + 1, "start": i * 5.0, "end": i * 5.0 + 4.5, "slot": 5.0, "text": f"cümle {i + 1}."} for i in range(20)]


def test_clip_picks_are_snapped_sized_and_never_overlap():
    from factory.hat import clips as C
    raw = [{"from": 2, "to": 3, "hook": "kısa", "score": 6},             # 9.5 s -> grows to >= 15 s
           {"from": 3, "to": 6, "hook": "çakışan", "score": 5},          # overlaps the first -> dropped
           {"from": 8, "to": 20, "hook": "uzun", "score": 9},            # 64.5 s -> shrinks to <= 60 s
           {"from": 99, "to": 100, "score": 10}, {"from": "x", "to": 2}]
    out = C.pick(_clip_segs(), raw, 5)
    assert [c["hook"] for c in out] == ["uzun", "kısa"] and [c["n"] for c in out] == [1, 2]
    assert out[0]["seconds"] <= 60 and out[1]["seconds"] >= 15 and out[1]["start"] == 5.0
    assert C._count("bundan 8 klip çıkar") == 8 and C._count("12 shorts") == 10 and C._count("en iyileri") == 5
    assert C.crop_x([(1, 0.2, 0.4, 0.1), (3, 0.3, 0.4, 0.1), (50, 0.9, 0.4, 0.1)], 0, 10) == 0.3
    assert C.crop_x([], 0, 10, -0.2) == 0.3


def test_clip_factory_cuts_ranked_shorts_without_credits(d, monkeypatch, tmp_path):
    import subprocess
    from factory.config import FFMPEG
    from factory import qa, thumbs, talk
    from factory.hat import runner, clips as C
    src = str(tmp_path / "long.mp4")
    subprocess.run([FFMPEG, "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=s=320x180:d=40", "-f", "lavfi", "-i",
                    "sine=d=40", "-shortest", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", src], check=True)
    monkeypatch.setattr(C, "_source", lambda p: src)
    words = [[f"söz{i}", i * 1.0, i * 1.0 + 0.6, 1] for i in range(40)]
    words = [[w[0] + ("." if i % 5 == 4 else ""), *w[1:]] for i, w in enumerate(words)]
    monkeypatch.setattr(C, "_transcribe", lambda path, lang: words)
    monkeypatch.setattr(C, "_faces", lambda path, dur: [(12.0, 0.8, 0.5, 0.1)])
    asks = []
    def ask(prompt):
        asks.append(prompt)
        picks = [{"from": 1, "to": 3, "hook": "İlk an", "score": 7, "caption": "c1", "hashtags": ["a"]},
                 {"from": 4, "to": 6, "hook": "En iyi an", "score": 9, "caption": "c2", "hashtags": "#b #c"}]
        return {"clips": picks[1:] if "note" in prompt else picks}, 0.05
    monkeypatch.setattr(C, "_ask", ask)
    monkeypatch.setattr(qa, "technical", lambda path, expected=None: {"problems": []})
    monkeypatch.setattr(thumbs, "make", lambda *a, **k: [])
    monkeypatch.setattr(C, "ROOT", "/")
    import factory.hat.explainer as E
    monkeypatch.setattr(E, "ROOT", "/")

    pid = P.create("clip_factory", "Uzun yayın", brief="bundan 2 klip çıkar", d=d, extra={"source": "raw/talk/long.mp4"})["id"]
    q = Q(runner, d)
    assert runner.advance(pid, q, d=d) == ("gate", "idea")
    prop = P.read_artifact(pid, "proposal", d)
    assert [c["hook"] for c in prop["clips"]] == ["En iyi an", "İlk an"] and prop["cost"]["credits"] == 0
    assert "Pick the 2 strongest" in asks[0]
    assert runner.approve(pid, "idea", q, d=d) == ("gate", "scene_plan")
    fr = P.read_artifact(pid, "plates", d)["frames"]
    assert fr[0]["cx"] == 0.5 and fr[1]["cx"] == 0.8                          # the face at 12 s is in "İlk an" (grown back to 0 s)
    runner.feedback(pid, "scene_plan", "2: sol", q, d=d)
    assert P.read_artifact(pid, "plates", d)["frames"][1]["cx"] == 0.6
    assert runner.approve(pid, "scene_plan", q, d=d) == ("gate", "assets")
    a = P.read_artifact(pid, "assets", d)
    assert len(a["clips"]) == 2 and all(os.path.isfile("/" + c["file"]) for c in a["clips"])
    info = talk.probe("/" + a["clips"][0]["file"])
    assert (info["w"], info["h"]) == (1080, 1920) and 19 < info["duration"] < 20.5   # 15-34.6 s grew to 4 lines
    assert runner.approve(pid, "assets", q, d=d) == ("gate", "publish")
    pub = P.read_artifact(pid, "publish", d)
    assert [x["hashtags"] for x in pub["posts"]] == [["#b", "#c"], ["#a"]] and pub["posts"][0]["file"].endswith("clip_1.mp4")


def test_podcast_audio_becomes_waveform_clips_and_quote_cards(d, monkeypatch, tmp_path):
    import subprocess
    from PIL import Image
    from factory.config import FFMPEG
    from factory import qa, thumbs, talk
    from factory.hat import runner, clips as C, explainer as E
    src = str(tmp_path / "ep.mp3")
    subprocess.run([FFMPEG, "-y", "-v", "error", "-f", "lavfi", "-i", "sine=d=40", src], check=True)
    monkeypatch.setattr(C, "_source", lambda p: src)
    words = [[f"söz{i}" + ("." if i % 5 == 4 else ""), i * 1.0, i * 1.0 + 0.6, 1] for i in range(40)]
    monkeypatch.setattr(C, "_transcribe", lambda path, lang: words)
    monkeypatch.setattr(C, "_faces", lambda path, dur: pytest.fail("no face search on audio"))
    monkeypatch.setattr(C, "_ask", lambda prompt: ({"clips": [{"from": 1, "to": 4, "hook": "Bölümün özü", "score": 8}],
                                                    "quotes": [{"line": 2, "text": "Az ama öz konuş."}, {"line": 99, "text": "yok"},
                                                               {"line": 3, "text": ""}]}, 0.05))
    monkeypatch.setattr(qa, "technical", lambda path, expected=None: {"problems": []})
    monkeypatch.setattr(thumbs, "make", lambda *a, **k: [])
    monkeypatch.setattr(C, "ROOT", "/")
    monkeypatch.setattr(E, "ROOT", "/")

    pid = P.create("podcast", "Bölüm 12", brief="bu bölümden 1 klip", d=d, extra={"source": "raw/talk/ep.mp3"})["id"]
    q = Q(runner, d)
    assert runner.advance(pid, q, d=d) == ("gate", "idea")
    prop = P.read_artifact(pid, "proposal", d)
    assert prop["quotes"] == [{"n": 1, "line": 2, "text": "Az ama öz konuş."}]          # unknown line and empty text dropped
    assert runner.approve(pid, "idea", q, d=d) == ("gate", "scene_plan")
    pl = P.read_artifact(pid, "plates", d)
    assert len(pl["cards"]) == 1 and Image.open("/" + pl["cards"][0]).size == (1080, 1920)
    assert runner.approve(pid, "scene_plan", q, d=d) == ("gate", "assets")
    clip = "/" + P.read_artifact(pid, "assets", d)["clips"][0]["file"]
    info = talk.probe(clip)
    assert (info["w"], info["h"]) == (1080, 1920) and 19 < info["duration"] < 20.5
    assert runner.approve(pid, "assets", q, d=d) == ("gate", "publish")
    assert P.read_artifact(pid, "publish", d)["cards"] == pl["cards"]


def test_screen_demo_only_records_public_addresses(monkeypatch):
    import socket
    from factory.hat import screendemo as S
    ips = {"example.com": "93.184.215.14", "intranet.test": "10.0.0.5", "localhost": "127.0.0.1"}
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, port: [(2, 1, 6, "", (ips[host], port))])
    assert S.safe_url("https://example.com/app") == "https://example.com/app"
    for bad in ("http://localhost:8501/", "http://intranet.test/", "file:///etc/passwd", "ftp://example.com/", ""):
        with pytest.raises(P.GateError):
            S.safe_url(bad)
    with pytest.raises(P.GateError):                                          # a planned goto is checked too
        S._steps([{"action": "goto", "text": "http://localhost/admin"}])


def _demo_fakes(monkeypatch, d, tmp_path, calls):
    import subprocess
    from factory.config import FFMPEG
    from factory import qa, thumbs
    from factory.hat import screendemo as S
    import factory.hat.explainer as E
    monkeypatch.setattr(S, "safe_url", lambda u: u)
    def node(mode, *a, timeout=600):
        calls.append((mode, a))
        if mode == "survey":
            json.dump({"title": "Notlar", "text": "Hızlı not al", "items": [{"tag": "button", "label": "Ekle"}]}, open(a[1], "w"))
            open(a[2], "wb").write(b"png")
            return
        spec, out = json.load(open(a[0])), a[1]
        subprocess.run([FFMPEG, "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=s=270x480:d=7:r=30", "-pix_fmt", "yuv420p",
                        os.path.join(out, "raw.mp4")], check=True)
        log, t = [], 1.0
        for n, st in enumerate(spec["steps"], 1):
            log.append({"n": n, "t0": t, "t1": t + 1.0 + st["hold"], "box": [0.4, 0.2, 0.2, 0.05] if st["action"] == "click" else None,
                        "ok": True, "error": None})
            t += 1.0 + st["hold"]
            open(os.path.join(out, f"step_{n}.png"), "wb").write(b"png")
            open(os.path.join(out, f"f_00000{n}.jpg"), "wb").write(b"j")
        json.dump(log, open(os.path.join(out, "log.json"), "w"))
    monkeypatch.setattr(S, "_node", node)
    monkeypatch.setattr(S, "_ask", lambda prompt: ({"title": "Not uygulaması", "steps": [
        {"action": "type", "target": "Yeni not", "text": "Süt al", "say": "Önce bir not yazıyoruz.", "zoom": True},
        {"action": "click", "target": "Ekle", "say": "Sonra ekle düğmesine basıyoruz ve not listede hemen görünüyor.", "zoom": True},
        {"action": "explode", "target": "x", "say": "yok"}], "caption": "c", "hashtags": ["demo"]}, 0.1))
    monkeypatch.setattr(qa, "technical", lambda path, expected=None: {"problems": []})
    monkeypatch.setattr(thumbs, "make", lambda *a, **k: [])
    monkeypatch.setattr(S, "ROOT", "/")
    monkeypatch.setattr(E, "ROOT", "/")


def test_screen_demo_narrated_walkthrough(d, monkeypatch, tmp_path):
    from factory import credits, eleven, productions as PR, talk
    from factory.hat import runner, screendemo as S
    calls = []
    _demo_fakes(monkeypatch, d, tmp_path, calls)
    monkeypatch.setattr(S, "_con", lambda: None)
    monkeypatch.setattr(credits, "rates", lambda: {"tts:eleven_v4": {"rate": 1}})
    voice = str(tmp_path / "v.wav")
    import subprocess
    from factory.config import FFMPEG
    subprocess.run([FFMPEG, "-y", "-v", "error", "-f", "lavfi", "-i", "sine=d=4", voice], check=True)
    tts = []
    monkeypatch.setattr(eleven, "tts", lambda con, text, vid, model, approved=None, account=None: tts.append((text, approved)) or (voice, 50.0))
    monkeypatch.setattr(PR, "align", lambda path, lines, lang="en": ([{"start": 0.1, "end": 1.6}, {"start": 1.9, "end": 3.8}], 4.0,
                                                                     [("Önce", 0.1, 0.4), ("bir", 0.4, 0.6), ("Sonra", 1.9, 2.3)]))
    pid = P.create("screen_demo", "Not demosu", brief="not uygulamasını gezdir", d=d,
                   extra={"url": "https://example.com/"})["id"]
    q = Q(runner, d)
    assert runner.advance(pid, q, d=d) == ("gate", "idea")
    prop = P.read_artifact(pid, "proposal", d)
    assert len(prop["concepts"][0]["steps"]) == 2                               # the unknown action is dropped
    assert prop["cost"]["credits"] == len(" ".join(prop["concepts"][0]["lines"])) and prop["voice"]["use"]
    assert runner.approve(pid, "idea", q, d=d) == ("gate", "script")
    assert runner.approve(pid, "script", q, d=d) == ("gate", "scene_plan")      # capture runs without a gate
    run = next(c for c in calls if c[0] == "run")
    assert [s["hold"] for s in json.load(open(run[1][0]))["steps"]] == [1.0, round(9 / 2.3 - 0.7, 1)]
    cap = P.read_artifact(pid, "capture", d)
    assert not any(f.startswith("f_") for f in os.listdir(os.path.dirname("/" + cap["video"])))   # frames cleaned up
    plan = P.read_artifact(pid, "plates", d)["steps"]
    assert [x["zoom"] for x in plan] == [False, True]                           # the type step has no box to zoom to
    runner.feedback(pid, "scene_plan", "2: zoom yok", q, d=d)
    assert [x["zoom"] for x in P.read_artifact(pid, "plates", d)["steps"]] == [False, False]
    runner.feedback(pid, "scene_plan", "2: zoom", q, d=d)
    assert runner.approve(pid, "scene_plan", q, d=d) == ("gate", "assets")
    budget = P.load(pid, d)["budget"]["credits"]
    assert tts == [("Önce bir not yazıyoruz. Sonra ekle düğmesine basıyoruz ve not listede hemen görünüyor.", budget)]
    a = P.read_artifact(pid, "assets", d)
    assert a["parts"][0][2] == 1.9 and a["parts"][1][2] == round(4.6 - 1.9, 3)  # each step lasts until the next line
    info = talk.probe("/" + a["preview"])
    assert abs(info["duration"] - 4.6) < 0.15 and (info["w"], info["h"]) == (1080, 1920)
    assert runner.approve(pid, "assets", q, d=d) == ("gate", "publish")
    assert os.path.isfile("/" + P.read_artifact(pid, "render", d)["final"])
    assert P.read_artifact(pid, "publish", d)["hashtags"] == ["#demo"]


def test_screen_demo_silent_costs_nothing(d, monkeypatch, tmp_path):
    from factory import eleven, talk
    from factory.hat import runner, screendemo as S
    calls = []
    _demo_fakes(monkeypatch, d, tmp_path, calls)
    monkeypatch.setattr(eleven, "tts", lambda *a, **k: pytest.fail("a silent demo must not pay for a voice"))
    pid = P.create("screen_demo", "Sessiz", brief="sessiz demo, sadece altyazı", d=d, extra={"url": "https://example.com/"})["id"]
    q = Q(runner, d)
    runner.advance(pid, q, d=d)
    assert P.read_artifact(pid, "proposal", d)["cost"]["credits"] == 0
    for st in ("idea", "script", "scene_plan"):
        runner.approve(pid, st, q, d=d)
    a = P.read_artifact(pid, "assets", d)
    assert a["voice"] is None and a["words"][0][0] == "Önce"
    log = P.read_artifact(pid, "capture", d)["log"]
    assert a["parts"][1][2] == round(log[1]["t1"] - log[1]["t0"], 3)         # silent: as long as it was recorded
    assert abs(talk.probe("/" + a["preview"])["duration"] - a["duration"]) < 0.15


def _doc_fakes(monkeypatch, tmp_path, narrated=True):
    """Archive clips are local test videos of 3, 12 and 40 s; the model plans five beats."""
    import subprocess
    from factory.config import FFMPEG
    from factory import archive, qa, thumbs
    from factory.hat import documentary as D
    import factory.hat.explainer as E
    clips = {}
    for k, secs in (("a", 3), ("b", 12), ("c", 40)):
        f = str(tmp_path / f"{k}.mp4")
        subprocess.run([FFMPEG, "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc=s=320x180:d={secs}:r=25", "-pix_fmt",
                        "yuv420p", f], check=True)
        clips[k] = (f, secs)
    pool = [{"key": f"wm:{k}", "source": "Wikimedia Commons", "title": f"clip {k}", "author": f"Ayşe {k.upper()}",
             "license": "CC BY-SA 4.0", "page": f"https://commons.wikimedia.org/wiki/File:{k}", "url": f"https://upload.wikimedia.org/{k}.webm"}
            for k in ("a", "b", "c")]
    finds = []
    def find(look, queries, con=None, k=5, exclude=()):
        finds.append((look, list(queries), set(exclude)))
        return [c for c in pool if c["key"] not in exclude][:k]
    monkeypatch.setattr(archive, "find", find)
    monkeypatch.setattr(archive, "resolve", lambda c: dict(c))
    monkeypatch.setattr(archive, "fetch", lambda c: (clips[c["key"][3:]][0], {"w": 320, "h": 180, "duration": float(clips[c["key"][3:]][1])}))
    beats = [{"say": f"Cümle {i} burada söyleniyor.", "text": f"Yazı {i}", "look": f"view {i}", "queries": [f"q{i}"],
              "seconds": 3} for i in range(1, 4)]
    beats.append({"say": "eksik", "look": "", "queries": ["x"]})                  # no look: dropped
    monkeypatch.setattr(D, "_ask", lambda prompt: ({"title": "Boğaz", "narrated": narrated, "beats": beats,
                                                   "music": {"use": True, "prompt": "soft strings"},
                                                   "caption": "Boğaz'ın günü", "hashtags": ["istanbul"]}, 0.1))
    monkeypatch.setattr(D, "BEATS", (3, 14))
    monkeypatch.setattr(D, "_con", lambda: None)
    monkeypatch.setattr(qa, "technical", lambda path, expected=None: {"problems": []})
    monkeypatch.setattr(thumbs, "make", lambda *a, **k: [])
    monkeypatch.setattr(D, "ROOT", "/")
    monkeypatch.setattr(E, "ROOT", "/")
    return finds


def _tone(path, secs):
    import subprocess
    from factory.config import FFMPEG
    subprocess.run([FFMPEG, "-y", "-v", "error", "-f", "lavfi", "-i", f"sine=d={secs}", path], check=True)
    return path


def test_documentary_narrated_montage(d, monkeypatch, tmp_path):
    from factory import credits, eleven, productions as PR, talk
    from factory.hat import runner
    finds = _doc_fakes(monkeypatch, tmp_path)
    monkeypatch.setattr(credits, "rates", lambda: {"tts:eleven_v4": {"rate": 1}, "music:eleven_music_v2_5": {"rate": 10}})
    voice = _tone(str(tmp_path / "v.wav"), 9)
    music = _tone(str(tmp_path / "m.mp3"), 11)
    paid = []
    monkeypatch.setattr(eleven, "tts", lambda con, text, vid, model, approved=None, account=None: paid.append(("tts", approved)) or (voice, 60.0))
    monkeypatch.setattr(eleven, "generate", lambda con, kind, model, prompt, params, units, unit, ext="mp3", approved=None,
                        account=None: paid.append((kind, approved, params["duration_seconds"])) or (music, 100.0))
    monkeypatch.setattr(PR, "align", lambda path, lines, lang="en": (
        [{"start": 0.2, "end": 2.5}, {"start": 3.0, "end": 5.5}, {"start": 6.0, "end": 8.6}], 9.0,
        [("Cümle", 0.2, 0.6), ("1", 0.6, 0.9), ("Cümle", 3.0, 3.4)]))
    pid = P.create("documentary", "Boğaz", brief="Boğaz'da bir gün, sakin ve sıcak", d=d)["id"]
    q = Q(runner, d)
    assert runner.advance(pid, q, d=d) == ("gate", "idea")
    prop = P.read_artifact(pid, "proposal", d)
    beats = prop["concepts"][0]["beats"]
    assert len(beats) == 3 and prop["voice"]["use"] and prop["music"]["use"]
    secs = prop["seconds"]
    assert prop["cost"]["credits"] == len(" ".join(b["say"] for b in beats)) + round(10 * secs)
    assert runner.approve(pid, "idea", q, d=d) == ("gate", "scene_plan")
    rows = P.read_artifact(pid, "plates", d)["beats"]
    assert [r["clip"]["key"] for r in rows] == ["wm:a", "wm:b", "wm:c"]           # no clip is used twice
    assert finds[1][2] == {"wm:a"} and finds[2][2] == {"wm:a", "wm:b"}
    assert rows[2]["start"] == round(40 * 0.15, 2) and rows[0]["start"] == 0.0      # a long clip starts in, a short one at 0
    runner.feedback(pid, "scene_plan", "3: başla 20", q, d=d)
    rows = P.read_artifact(pid, "plates", d)["beats"]
    assert rows[2]["start"] == 20.0 and len(finds) == 3                             # nothing searched again
    assert runner.approve(pid, "scene_plan", q, d=d) == ("gate", "assets")
    budget = P.load(pid, d)["budget"]["credits"]
    assert paid[0] == ("tts", budget) and paid[1][:2] == ("music", budget - 60)
    a = P.read_artifact(pid, "assets", d)
    assert a["lengths"] == [3.0, 3.0, round(9.8 - 6.0, 3)] and a["duration"] == 9.8
    info = talk.probe("/" + a["preview"])
    assert abs(info["duration"] - 9.8) < 0.15 and (info["w"], info["h"]) == (1080, 1920)
    assert runner.approve(pid, "assets", q, d=d) == ("gate", "edit")
    ed = P.read_artifact(pid, "edit", d)
    assert ed["transition"] == "soft" and [x["at"] for x in ed["timeline"]] == [0.0, 3.0, 6.0]
    runner.feedback(pid, "edit", "geçiş: kesme, 2: başla 4; 3: sığdır", q, d=d)
    ed = P.read_artifact(pid, "edit", d)
    assert ed["transition"] == "cut" and ed["starts"]["2"] == 4.0 and ed["fits"] == {"3": True} and ed["preview"].endswith("preview.mp4")
    assert runner.approve(pid, "edit", q, d=d) == ("gate", "publish")
    fin = "/" + P.read_artifact(pid, "render", d)["final"]
    assert abs(talk.probe(fin)["duration"] - 9.8) < 0.15
    pub = P.read_artifact(pid, "publish", d)
    assert "Ayşe A (Wikimedia Commons, CC BY-SA 4.0)" in pub["caption"] and len(pub["credits"]) == 3


def test_documentary_music_only_has_beat_captions(d, monkeypatch, tmp_path):
    from factory import credits, eleven, talk
    from factory.hat import runner
    _doc_fakes(monkeypatch, tmp_path, narrated=False)
    monkeypatch.setattr(credits, "rates", lambda: {"music:eleven_music_v2_5": {"rate": 10}})
    monkeypatch.setattr(eleven, "tts", lambda *a, **k: pytest.fail("no narration was asked for"))
    music = _tone(str(tmp_path / "m.mp3"), 11)
    monkeypatch.setattr(eleven, "generate", lambda *a, **k: (music, 100.0))
    pid = P.create("documentary", "Boğaz", brief="Boğaz'da bir gün, yalnız müzik", d=d)["id"]
    q = Q(runner, d)
    runner.advance(pid, q, d=d)
    prop = P.read_artifact(pid, "proposal", d)
    assert not prop["voice"]["use"] and prop["music"]["use"] and all(not b["say"] for b in prop["concepts"][0]["beats"])
    runner.approve(pid, "idea", q, d=d)
    runner.feedback(pid, "scene_plan", "1: 2", q, d=d)                               # beat 1 takes its 2nd candidate
    rows = P.read_artifact(pid, "plates", d)["beats"]
    assert rows[0]["clip"]["key"] == "wm:b" and rows[0]["pick"] == 2
    runner.approve(pid, "scene_plan", q, d=d)
    a = P.read_artifact(pid, "assets", d)
    assert a["voice"] is None and a["lengths"] == [3.0, 3.0, 3.0]
    assert a["words"][0] == ["Yazı 1", 0.2, 2.8]
    assert abs(talk.probe("/" + a["preview"])["duration"] - 9.0) < 0.15


def test_archive_licences_hosts_and_meaning(monkeypatch, tmp_path):
    from factory import archive as A
    monkeypatch.setattr(A, "STORE", str(tmp_path / "store.json"))
    def page(title, lic, desc, w=1920):
        return {"title": f"File:{title}", "videoinfo": [{"width": w, "height": 1080, "duration": 20, "url": f"https://upload.wikimedia.org/{title}",
                "descriptionurl": "https://commons.wikimedia.org/x", "derivatives": [
                    {"type": "video/webm", "height": 720, "src": f"https://upload.wikimedia.org/{title}.720p.webm"},
                    {"type": "video/webm", "height": 1080, "src": f"https://upload.wikimedia.org/{title}.1080p.webm"}],
                "extmetadata": {"LicenseShortName": {"value": lic}, "ImageDescription": {"value": desc}}}]}
    wm = {"query": {"pages": {"1": page("ferry.webm", "CC BY-SA 4.0", "A ferry crossing the Bosphorus strait"),
                              "2": page("nc.webm", "CC BY-NC 4.0", "A ferry, non commercial"),
                              "3": page("tiny.webm", "CC0", "A ferry", w=320),
                              "4": page("rocket.webm", "Public domain", "Rocket launch from the pad at night")}}}
    monkeypatch.setattr(A, "_json", lambda url: wm if "wikimedia" in url else {})
    monkeypatch.setattr(A, "SOURCES", {"wikimedia": A.wikimedia, "nasa": lambda q: 1 / 0})   # a broken source is skipped
    got = A.search(["bosphorus ferry"])
    assert sorted(c["title"] for c in got) == ["ferry.webm", "rocket.webm"]                  # no NC, nothing tiny
    assert next(c for c in got if c["title"] == "ferry.webm")["url"].endswith(".1080p.webm")
    ranked = A.rank("a ferry crossing the strait", got)
    assert ranked[0]["title"] == "ferry.webm" and ranked[0]["score"] > ranked[1]["score"]
    assert set(A.load()) == {"wm:File:ferry.webm", "wm:File:rocket.webm"}                    # the local archive grows
    assert A.allowed("https://upload.wikimedia.org/a.webm") and A.allowed("https://ia800.us.archive.org/x.mp4")
    for bad in ("http://127.0.0.1/a.mp4", "https://evil.example/upload.wikimedia.org/a", "file:///etc/passwd"):
        assert not A.allowed(bad)
    with pytest.raises(ValueError):
        A.fetch({"url": "http://localhost:8501/x.mp4"})
    assert A._seconds("29:28") == 1768 and A._seconds("12.5") == 12.5 and A._seconds("n/a") is None


# ---------------------------------------------------------------- character animation: drawn once, posed, rigged

def _char_png(path, colour):
    """A drawn pose: a figure on the plain grey ground, with a grey-ish patch inside it that must stay opaque."""
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (400, 600), (217, 217, 217))
    dr = ImageDraw.Draw(img)
    dr.rectangle((140, 80, 260, 560), fill=colour)
    dr.rectangle((180, 140, 220, 180), fill=(215, 215, 215))
    img.save(path)
    return path


def _char_fakes(monkeypatch, tmp_path):
    from factory import accounts, credits, eleven, qa, thumbs
    from factory.hat import character as C, documentary as D
    import factory.hat.explainer as E
    story = {"title": "Mira ve Kedi", "logline": "Bir kız kayıp kedisini arar.", "art_style": "flat cartoon",
             "characters": [{"id": "mira", "name": "Mira", "look": "girl, red scarf", "size": "medium"},
                            {"id": "Tekir Kedi", "name": "Tekir", "look": "striped cat", "size": "small"},
                            {"id": "nolook", "name": "X", "look": ""}],                 # no look: dropped
             "places": [{"id": "park", "prompt": "a park"}, {"id": "street", "prompt": "a street"},
                        {"id": "unused", "prompt": "never used"}],
             "scenes": [{"place": "park", "cast": ["mira"], "lines": [
                            {"who": "narrator", "say": "Bir gün Mira parka gitti."},
                            {"who": "mira", "say": "Tekir nerede?", "pose": "surprised"}]},
                        {"place": "street", "cast": ["mira", "tekir-kedi"], "lines": [
                            {"who": "Tekir", "say": "Miyav, buradayım!", "pose": "dance"},  # unknown pose: talk
                            {"who": "mira", "say": "Seni buldum!", "pose": "happy"}]},
                        {"place": "nowhere", "cast": ["mira"], "lines": [{"who": "mira", "say": "x"}]}],  # no place: dropped
             "music": {"use": True, "prompt": "playful"}, "caption": "Mira'nın günü", "hashtags": ["animasyon"]}
    asks = []
    monkeypatch.setattr(C, "_ask", lambda prompt: asks.append(prompt) or (json.loads(json.dumps(story)), 0.1))
    monkeypatch.setattr(credits, "rates", lambda: {"image:gpt-image-2": {"rate": 5}, "image:gpt-image-2.5-sunburst": {"rate": 10},
                                                   "tts:eleven_v4": {"rate": 1}, "music:eleven_music_v2_5": {"rate": 2}})
    images = []
    def image(con, prompt, approved, account=None, aspect="9:16", flow_id=None, refs=(), idea_id=None, model=None):
        n = len(images) + 1
        images.append({"prompt": prompt, "approved": approved, "refs": list(refs), "flow": flow_id})
        return _char_png(str(tmp_path / f"img{n}.png"), (200, 40 + n * 10, 40)), 5.0 if not refs else 10.0, "flow1", f"node{n}"
    monkeypatch.setattr(eleven, "image", image)
    takes = []
    def tts(con, text, vid, model, approved=None, account=None):
        takes.append((text, vid, approved))
        return _tone(str(tmp_path / f"t{len(takes)}.wav"), round(0.5 * len(text.split()), 2)), float(len(text))
    monkeypatch.setattr(eleven, "tts", tts)
    music = _tone(str(tmp_path / "m.mp3"), 14)
    monkeypatch.setattr(eleven, "generate", lambda *a, approved=None, **k: takes.append(("music", approved)) or (music, 20.0))
    monkeypatch.setattr(accounts, "default_eleven", lambda uid=None: "acc")
    monkeypatch.setattr(C, "_con", lambda: None)
    monkeypatch.setattr(qa, "technical", lambda path, expected=None: {"problems": []})
    monkeypatch.setattr(thumbs, "make", lambda *a, **k: [])
    for m in (C, D, E):
        monkeypatch.setattr(m, "ROOT", "/")
    return images, takes, asks


def test_character_line_draws_once_poses_rigs_and_acts(d, monkeypatch, tmp_path):
    from PIL import Image
    from factory import talk
    from factory.hat import character as C, runner
    images, takes, asks = _char_fakes(monkeypatch, tmp_path)
    pid = P.create("character", "Mira", brief="Mira kayıp kedisini arıyor", d=d)["id"]
    q = Q(runner, d)
    assert runner.advance(pid, q, d=d) == ("gate", "proposal")
    story = P.read_artifact(pid, "proposal", d)["concepts"][0]["story"]
    assert [c["id"] for c in story["characters"]] == ["mira", "tekir-kedi"]
    assert [s["place"] for s in story["scenes"]] == ["park", "street"] and [p["id"] for p in story["places"]] == ["park", "street"]
    assert story["scenes"][1]["lines"][0] == {"who": "tekir-kedi", "say": "Miyav, buradayım!", "pose": "talk"}
    need = C.poses_needed(story)
    assert need == {"mira": ["neutral", "surprised", "happy"], "tekir-kedi": ["neutral", "talk"]}
    chars = sum(len(ln["say"]) for s in story["scenes"] for ln in s["lines"])
    cost = P.read_artifact(pid, "proposal", d)["cost"]
    assert cost["credits"] == 2 * 5 + 5 * 10 + 2 * 5 + chars + round(2 * (C._seconds(story, "tr") + 1)) and not images
    assert runner.approve(pid, "proposal", q, d=d) == ("gate", "script")
    sc = P.read_artifact(pid, "script", d)
    assert sc["lines"][1] == "Mira: Tekir nerede?" and sc["speakers"] == ["narrator", "mira", "tekir-kedi", "mira"]
    assert runner.approve(pid, "script", q, d=d) == ("gate", "character_design")
    ch = P.read_artifact(pid, "characters", d)["characters"]
    assert len(images) == 7 and images[0]["refs"] == [] and images[1]["refs"] == ["node1"]   # poses drawn FROM the sheet
    assert all(i["flow"] in (None, "flow1") for i in images)
    cut = Image.open("/" + ch[0]["poses"]["neutral"]["cut"])
    assert cut.size == (121, 481) and cut.getpixel((60, 80))[3] == 255 and cut.getpixel((0, 0))[3] < 255   # inner patch kept
    runner.feedback(pid, "character_design", "Tekir: ses v-cat\nMira: happy tekrar", q, d=d)
    ch = P.read_artifact(pid, "characters", d)["characters"]
    assert len(images) == 8 and "take 2" in images[-1]["prompt"] and ch[1]["voice_id"] == "v-cat"
    assert runner.approve(pid, "character_design", q, d=d) == ("gate", "scene_plan")
    rigs = P.read_artifact(pid, "rig_plan", d)["rigs"]
    assert rigs["mira"]["height"] == 960 and rigs["tekir-kedi"]["height"] == 768
    assert Image.open("/" + rigs["mira"]["files"]["neutral_r"]).size[1] == 960
    pl = P.read_artifact(pid, "plates", d)
    assert len(images) == 10 and set(pl["places"]) == {"park", "street"}
    assert [c["x"] for c in pl["scenes"][1]["cast"]] == [0.3, 0.7]
    runner.feedback(pid, "scene_plan", "2: Mira sağ, Tekir sol", q, d=d)
    pl = P.read_artifact(pid, "plates", d)
    assert len(images) == 10 and [c["x"] for c in pl["scenes"][1]["cast"]] == [0.75, 0.25]   # no new image for a move
    assert runner.approve(pid, "scene_plan", q, d=d) == ("gate", "assets")
    assert [t[1] for t in takes][2] == "v-cat" and len({t[1] for t in takes[:4]}) == 2
    left = P.load(pid, d)["budget"]["credits"] - 10 * 6 - 10 - 10              # sheets+poses, the redraw, backgrounds
    assert takes[4] == ("music", left - sum(len(t[0]) for t in takes[:4]))       # music gets what the voices left
    a = P.read_artifact(pid, "assets", d)
    tl = a["timeline"]
    assert tl[0]["lines"][0]["at"] == C.LEAD and tl[1]["start"] == tl[0]["end"]
    assert tl[1]["lines"][1]["pose"] == "happy" and abs(a["duration"] - tl[-1]["end"]) < 1e-6
    info = talk.probe("/" + a["preview"])
    assert abs(info["duration"] - a["duration"]) < 0.15 and (info["w"], info["h"]) == (1080, 1920)
    assert runner.approve(pid, "assets", q, d=d) == ("gate", "publish")
    assert abs(talk.probe("/" + P.read_artifact(pid, "render", d)["final"])["duration"] - a["duration"]) < 0.15
    assert P.read_artifact(pid, "publish", d)["hashtags"] == ["#animasyon"]


def test_character_spans_hold_a_pose_until_the_next_line():
    from factory.hat import character as C
    sc = {"lines": [{"who": "a", "pose": "talk", "at": 1.0, "end": 2.0}, {"who": "b", "pose": "talk", "at": 2.2, "end": 3},
                    {"who": "a", "pose": "talk", "at": 3.2, "end": 4.0}, {"who": "a", "pose": "happy", "at": 4.2, "end": 5}]}
    assert C._spans(sc, "a", "neutral", 0.0, 6.0) == [("neutral", 0.0, 1.0), ("talk", 1.0, 4.2), ("happy", 4.2, 6.0)]
    assert C._spans(sc, "c", "neutral", 0.0, 6.0) == [("neutral", 0.0, 6.0)]
    assert C.layout(["a", "b"], {"b": "left"}) == {"a": 0.3, "b": 0.25}
