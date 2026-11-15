"""The Claude-limit diet: a single-shot reviewer that lets code settle what code can measure, authors handed their
inputs and the gate's numbers up front, cold reads remembered, and the ledger split by project and provider."""
import json, os, sqlite3

import pytest

from factory import llm
from factory.hat import manifest, project as P


@pytest.fixture(autouse=True)
def no_real_llm(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("a test tried to call a real model")
    for name in ("ask_text", "ask"):
        monkeypatch.setattr(llm, name, refuse)


@pytest.fixture
def d(tmp_path):
    return str(tmp_path / "projects")


@pytest.fixture
def A(tmp_path, monkeypatch):
    from factory.hat import agent
    root = tmp_path / "skills"
    (root / "meta").mkdir(parents=True)
    (root / "meta" / "stage-agent.md").write_text("CONTRACT TEXT")
    (root / "meta" / "reviewer.md").write_text("REVIEWER CONTRACT")
    monkeypatch.setattr(agent, "SKILLS", str(root))
    return agent


def _stage(sid):
    return manifest.stage(manifest.get("explainer"), sid)


def test_a_fully_measured_rubric_costs_no_model_call(d, A, monkeypatch):
    from factory.hat import rubriccheck
    pid = P.create("explainer", "t", d=d)["id"]
    s = _stage("publish")
    P.write_artifact(pid, "publish", {"caption": "x?"}, d)
    n = len(s["review"])
    monkeypatch.setattr(rubriccheck, "settle", lambda pid, st, d=None: [{"score": 10, "note": "ok"}] * n)
    r = A.review_stage(pid, s, d)                     # llm.ask_text refuses: reaching it fails the test
    assert r["verdict"] == "pass" and r["score"] == 100 and r["model_used"] == "code" and r["cost_usd"] == 0
    assert r["settled"] == n and r["findings"] == []
    # a measured miss is a finding of its own (critical under 5), and the next review closes it by measurement
    monkeypatch.setattr(rubriccheck, "settle", lambda pid, st, d=None: [{"score": 3, "note": "2 hashtags"}] +
                        [{"score": 10, "note": ""}] * (n - 1))
    r = A.review_stage(pid, s, d)
    assert r["verdict"] == "fix" and r["findings"][0]["severity"] == "critical" and "2 hashtags" in r["findings"][0]["problem"]
    from factory.hat import gauntlet as G
    G.record(pid, s, r, 0, d)
    r = A.review_stage(pid, s, d)                     # still failing: the old entry stays open, no duplicate
    assert r["findings"] == [] and r["ledger_marks"] == [{"id": "f1", "status": "open"}] and r["verdict"] == "fix"
    monkeypatch.setattr(rubriccheck, "settle", lambda pid, st, d=None: [{"score": 10, "note": ""}] * n)
    r = A.review_stage(pid, s, d)
    assert r["ledger_marks"] == [{"id": "f1", "status": "fixed"}] and r["verdict"] == "pass"


def test_the_reviewer_is_one_call_with_everything_in_the_prompt(d, A, monkeypatch, tmp_path):
    from factory.hat import gauntlet as G, rubriccheck
    pid = P.create("explainer", "t", video_lang="tr", d=d)["id"]
    P.write_artifact(pid, "research", {"insight": "NVIDIA", "sources": [{"url": "https://a.b"}]}, d)
    P.write_artifact(pid, "proposal", {"chosen": "c1", "seconds": 45}, d)
    P.write_artifact(pid, "script", {"title": "T", "lines": ["bir", "iki"], "html": "x" * 5000}, d)
    s = {**_stage("script"), "model": "sonnet"}
    n = len(s["review"])
    monkeypatch.setattr(rubriccheck, "settle", lambda pid, st, d=None: [{"score": 10, "note": "fits"}] + [None] * (n - 1))
    sheet = tmp_path / "sheet.jpg"
    sheet.write_bytes(b"jpg")
    monkeypatch.setattr(G, "fresh_render", lambda *a, **k: {"stills": ["/x/a.png"], "sheet": str(sheet),
                                                            "js_errors": [], "times": [1.0]})
    seen = {}

    def fake(prompt, tools=(), model=None, servers=None, images=(), **k):
        seen.update(prompt=prompt, tools=tools, model=model, servers=servers, images=images, step=k.get("step"))
        return json.dumps({"scores": [9] * (n - 1), "findings": [], "summary": "iyi"}), {"cost_usd": 0.004}
    monkeypatch.setattr(llm, "ask_text", fake)
    r = A.review_stage(pid, s, d)
    assert seen["tools"] == () and not seen["servers"] and seen["images"] == [str(sheet)]
    assert seen["model"] == "sonnet" and seen["step"] == "agent.review_stage"     # never dearer than the sonnet author
    p = seen["prompt"]
    assert f"{n - 1} marks in `scores`" in p and "Settled by code" in p and "fits" in p
    assert '"lines":["bir","iki"]' in p and "more chars]" in p                  # the artifact, code bodies trimmed
    assert "`proposal`" in p and "`research`" in p and "attached to this message" in p
    assert [x["score"] for x in r["rubric"]] == [10] + [9] * (n - 1) and r["settled"] == 1 and r["cost_usd"] == 0.004


def test_a_missing_rubriccheck_sends_every_line_to_the_model(d, A, monkeypatch):
    import builtins
    real = builtins.__import__

    def no_module(name, *a, **k):
        if name.endswith("rubriccheck") or (a and a[2] and "rubriccheck" in a[2]):
            raise ImportError("gone")
        return real(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", no_module)
    pid = P.create("explainer", "t", d=d)["id"]
    assert A.settled(pid, _stage("script"), d) == [None] * len(_stage("script")["review"])


def test_the_author_gets_its_inputs_and_the_gate_numbers_up_front(d, A, monkeypatch):
    from factory import hookrule
    pid = P.create("explainer", "t", video_lang="tr", d=d)["id"]
    P.write_artifact(pid, "proposal", {"chosen": "c1", "seconds": 40}, d)
    p = P.load(pid, d)
    rules = A.gate_rules(p, _stage("script"), d)
    assert f"at most {hookrule.word_limit('tr')} words" in rules and "96 words" in rules and "cold_test" in rules
    big = {"scenes": [{"html": "<div>" + "x" * 3000 + "</div>", "say": "s"}]}
    c = A.compact(big)
    assert len(c) < 700 and "more chars]" in c and '"say":"s"' in c
    assert A.compact({"a": "y" * 100}, limit=40).endswith("chars]")


def test_lessons_join_the_contract_when_they_exist(A, tmp_path):
    assert A.contract() == "CONTRACT TEXT"
    (tmp_path / "skills" / "meta" / "lessons.md").write_text("LESSON ONE")
    assert A.contract().endswith("LESSON ONE\n") and A.contract().startswith("CONTRACT TEXT")


def test_a_cold_read_is_asked_once_per_text(tmp_path, monkeypatch):
    from factory import coldtest
    monkeypatch.setattr(coldtest, "CACHE", str(tmp_path / "cache.json"))
    calls = []

    def ask(prompt):
        calls.append(prompt)
        return {"one_sentence": "NVIDIA'nın patronu evlendi", "subject_match": True}
    monkeypatch.setattr(coldtest, "_ask", ask)
    script = {"title": "NVIDIA CEO'su", "lines": ["Jensen Huang evlendi.", "Kiminle mi?"]}
    a = coldtest.cold_read(script, "tr")
    b = coldtest.cold_read(script, "tr")
    assert len(calls) == 1 and a == b
    coldtest.cold_read({**script, "lines": ["Jensen Huang evlendi!", "Kiminle mi?"]}, "tr")
    assert len(calls) == 2                            # one character changed: a new reader
    coldtest.cold_read(script, "tr", ask=lambda p: {"one_sentence": "x"})   # an injected reader is never cached
    assert len(json.load(open(coldtest.CACHE))) == 2


def test_usage_splits_a_project_by_provider(tmp_path, monkeypatch):
    from factory import store, usage
    con = store.connect(str(tmp_path / "f.db"))
    rows = [("agent._author:script", "opus", 1000, 50_000, 0.88, "live", "121"),
            ("agent.review_stage", "gemini-3.8-flash", 9000, 0, 0.011, "live_gemini", "121"),
            ("coldtest._ask", "gemini-3.5-flash-lite", 800, 0, 0.0004, "live_gemini", "121"),
            ("discover.make_cards", "sonnet", 100, 0, 0.1, "live", None)]
    for step, model, inp, cr, usd, src, proj in rows:
        con.execute("INSERT INTO llm_usage (at, step, model, input, cache_write, cache_read, output, cost_usd, ok, source,"
                    " project) VALUES (?,?,?,?,0,?,10,?,1,?,?)", (store.now(), step, model, inp, cr, usd, src, proj))
    monkeypatch.setattr(usage, "_title", lambda pid: "NVIDIA")
    rep = usage.report(con, project="121")
    p = rep["projects"][0]
    assert len(rep["projects"]) == 1 and p["claude_usd"] == 0.88 and p["usd"]["gemini"] == 0.0114 and p["calls"] == 3
    assert p["steps"][0]["step"] == "agent._author:script" and p["steps"][0]["tokens"] == 51_010
    assert "Claude limit: $0.88" in usage.text(rep) and "Gemini API $0.01" in usage.text(rep)
    assert usage.report(con)["totals"] == {"claude": 0.88, "gemini": 0.0114}      # untagged rows stay out
    assert usage._family("gemini-3.8-flash") == "gemini" and usage.provider_of("transcript:x") == "claude"


def test_scheduled_discovery_is_capped_per_day(tmp_path):
    from factory import discover, store
    con = store.connect(str(tmp_path / "f.db"))
    assert discover.runs_last_day(con) == 0
    for _ in range(3):
        con.execute("INSERT INTO disc_runs (at, items, candidates, cards, cost_usd, note, scope) VALUES (?,0,0,0,0,'','x')",
                    (store.now(),))
    con.execute("INSERT INTO disc_runs (at, items, candidates, cards, cost_usd, note, scope) VALUES "
                "('2020-01-01T00:00:00+00:00',0,0,0,0,'','x')")
    assert discover.runs_last_day(con) == 3 >= discover.MAX_PER_DAY
    assert llm.is_light("discover.make_cards")       # and each run goes to the light route (Gemini / cheapest Claude)
