"""Production lines v2: manifests and the gate rules of a project folder."""
import json, os

import pytest
import yaml

from factory.hat import manifest, project as P


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


def test_planned_stages_cannot_run(d):
    pid = P.create("documentary", "Şehir 4'te", d=d)["id"]
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
    import types, sys
    monkeypatch.setitem(sys.modules, "factory.hat.agent", types.SimpleNamespace(run_stage=fake_agent))
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
    sp = A.task(pid, manifest.stage(manifest.get("explainer"), "scene_plan"), d=d)
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


def test_api_create_checks_line_and_brief(api, monkeypatch):
    hat_api, _, q = api
    with pytest.raises(ValueError, match="not ready"):
        hat_api.post(None, "/api/hat/projects", {"line": "animation", "brief": "a long enough brief"}, q)
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
