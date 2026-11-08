"""The third provider: OpenRouter (an API key, DeepSeek V4.1 Flash by default) next to the two CLIs.

Nothing here reaches the network: the HTTP layer is faked and the MCP server is a stub. What is checked is the wiring
the Studio depends on — the key per user, the default model, the provider routing, and the tool loop that lets an
OpenRouter model use the factory's own tools.
"""
import json, os

import pytest

from factory import accounts, llm, mcpclient, openrouter


@pytest.fixture
def users(tmp_path, monkeypatch):
    f = tmp_path / "users.json"
    f.write_text(json.dumps({"secret": "x", "users": {"ali": {"name": "Ali", "role": "owner"},
                                                      "cem": {"name": "Cem", "role": "member"}}}))
    monkeypatch.setattr(accounts, "USERS", str(f))
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    return f


# ---------------------------------------------------------------- the key
def test_a_member_saves_their_own_key(users):
    assert not accounts.openrouter_status("cem")["connected"]
    st = accounts.set_openrouter_key("cem", "sk-or-v1-" + "a" * 40)
    assert st["connected"] and st["mine"] and st["tail"].endswith("aaaaaa")
    assert accounts.openrouter_key("cem").startswith("sk-or-v1-")
    assert not accounts.openrouter_key("ali")          # one user's key is not another's
    assert accounts.set_openrouter_key("cem", "")["connected"] is False
    with pytest.raises(ValueError):
        accounts.set_openrouter_key("cem", "too-short")


def test_the_owner_may_use_an_env_key(users, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-" + "b" * 40)
    st = accounts.openrouter_status("ali")
    assert st["connected"] and st["env"] and not st["mine"]
    assert openrouter.api_key("ali").endswith("bbbbbb")


def test_no_key_says_how_to_add_one(users):
    with pytest.raises(openrouter.OpenRouterError) as e:
        openrouter.api_key("cem")
    assert "Hesaplar" in str(e.value)


# ---------------------------------------------------------------- provider and model
def test_openrouter_is_a_provider_with_deepseek_as_default(users, monkeypatch):
    monkeypatch.setattr(openrouter, "models", lambda refresh=False: [{"id": openrouter.DEFAULT_MODEL, "name": "DeepSeek"}])
    accounts.set_openrouter_key("cem", "sk-or-v1-" + "c" * 40)
    accounts.set_llm_settings("cem", "openrouter", {})
    assert accounts.llm_settings("cem")["provider"] == "openrouter"
    assert llm.selected_provider("cem") == "openrouter"
    assert openrouter.DEFAULT_MODEL == "deepseek/deepseek-v4.1-flash-1017"
    assert llm.default_model("scene_plan", "openrouter") == openrouter.DEFAULT_MODEL
    assert llm.selected_model("scene_plan", "opus", uid="cem") == openrouter.DEFAULT_MODEL   # a manifest's `model: opus` is ignored
    assert llm.model_options("openrouter")[0]["id"] == openrouter.DEFAULT_MODEL


def test_one_agent_can_override_the_model(users):
    accounts.set_llm_settings("cem", "openrouter", {"scene_plan": "deepseek/deepseek-v4-pro"})
    assert llm.selected_model("scene_plan", None, uid="cem") == "deepseek/deepseek-v4-pro"
    assert llm.selected_model("script", None, uid="cem") == openrouter.DEFAULT_MODEL


def test_the_cli_choices_still_work(users):
    accounts.set_llm_settings("cem", "claude", {})
    assert llm.selected_model("script", "opus", uid="cem") == "opus"
    with pytest.raises(ValueError):
        accounts.set_llm_settings("cem", "openai", {})


# ---------------------------------------------------------------- the call itself
def test_chat_asks_for_tools_web_and_a_cost(monkeypatch):
    seen = {}

    def fake_http(path, body=None, key=None, timeout=120, method=None):
        seen.update({"path": path, "body": body, "key": key})
        return {"choices": [{"message": {"content": "ok"}}], "usage": {"cost": 0.01}}

    monkeypatch.setattr(openrouter, "_http", fake_http)
    out = openrouter.chat([{"role": "user", "content": "hi"}], "m", tools=[{"type": "function"}],
                          plugins=[{"id": "web"}], key="k")
    assert out["choices"][0]["message"]["content"] == "ok"
    assert seen["path"] == "/chat/completions" and seen["key"] == "k"
    assert seen["body"]["usage"] == {"include": True} and seen["body"]["tool_choice"] == "auto"
    assert seen["body"]["plugins"] == [{"id": "web"}]


def test_usage_is_mapped_to_the_ledger_columns():
    counts, cost = openrouter._usage({"prompt_tokens": 1000, "completion_tokens": 200, "cost": 0.0042,
                                      "prompt_tokens_details": {"cached_tokens": 800}})
    assert counts == {"input_tokens": 200, "cache_read_input_tokens": 800, "cache_creation_input_tokens": 0,
                      "output_tokens": 200}
    assert cost == 0.0042


def test_a_bad_key_is_not_retried(monkeypatch):
    calls = []

    def fake_http(path, body=None, key=None, timeout=120, method=None):
        calls.append(path)
        raise openrouter.OpenRouterHTTP(401, "no auth")

    monkeypatch.setattr(openrouter, "_http", fake_http)
    with pytest.raises(openrouter.OpenRouterHTTP):
        openrouter.chat([{"role": "user", "content": "hi"}], "m", key="k")
    assert calls == ["/chat/completions"]


# ---------------------------------------------------------------- the tool loop
class StubServer:
    """An MCP server that lists one tool and records what the model called."""

    def __init__(self):
        self.calls = []

    def tools(self):
        return [{"name": "submit_artifact", "description": "hand in the stage output",
                 "inputSchema": {"type": "object", "properties": {"summary": {"type": "string"}}}}]

    def call(self, name, args):
        self.calls.append((name, args))
        return '{"accepted": true}', False


def test_tools_become_functions_and_read_is_local(tmp_path, monkeypatch):
    monkeypatch.setattr(openrouter, "WORK", str(tmp_path))
    (tmp_path / "note.txt").write_text("hello")
    srv = StubServer()
    schemas, routes = openrouter._functions(["Read", "WebSearch", "mcp__factory__submit_artifact"],
                                            {"factory": srv}, {"factory": srv.tools()})
    names = [s["function"]["name"] for s in schemas]
    assert names == ["Read", "mcp__factory__submit_artifact"]      # web is the plugin, not a function
    assert routes["mcp__factory__submit_artifact"] == (srv, "submit_artifact")
    assert "hello" in openrouter._run_tool(routes, "Read", {"path": "note.txt"})
    assert "cannot read" in openrouter._run_tool(routes, "Read", {"path": "missing.txt"})
    text = openrouter._run_tool(routes, "mcp__factory__submit_artifact", {"summary": "s"})
    assert "accepted" in text and srv.calls == [("submit_artifact", {"summary": "s"})]


def test_the_loop_runs_the_tool_then_returns_the_answer(tmp_path, monkeypatch):
    monkeypatch.setattr(openrouter, "WORK", str(tmp_path))
    srv = StubServer()
    monkeypatch.setattr(mcpclient, "open_servers", lambda servers: {"factory": srv})
    monkeypatch.setattr(mcpclient, "close_servers", lambda started: None)
    monkeypatch.setattr(openrouter, "api_key", lambda uid=None: "k")
    monkeypatch.setattr(llm, "_record", lambda *a, **k: None)
    turns = [
        {"choices": [{"message": {"content": "", "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "mcp__factory__submit_artifact",
                                                          "arguments": '{"summary": "done"}'}}]}}],
         "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.001}},
        {"choices": [{"message": {"content": "Bitti."}}], "usage": {"prompt_tokens": 20, "completion_tokens": 5,
                                                                   "cost": 0.002}},
    ]
    seen = []

    def fake_chat(messages, model=None, tools=None, plugins=None, timeout=600, key=None, retries=2):
        seen.append([dict(m) for m in messages])
        return turns.pop(0)

    monkeypatch.setattr(openrouter, "chat", fake_chat)
    reply, meta = openrouter.run("yaz", tools=("mcp__factory__submit_artifact",), timeout=60,
                                 servers={"factory": {"command": "x"}}, budget_usd=1.0)
    assert reply == "Bitti." and meta["cost_usd"] == 0.003 and meta["turns"] == 2
    assert srv.calls == [("submit_artifact", {"summary": "done"})]
    assert seen[1][-1]["role"] == "tool" and "accepted" in seen[1][-1]["content"]


def test_the_budget_stops_a_runaway_loop(tmp_path, monkeypatch):
    monkeypatch.setattr(openrouter, "WORK", str(tmp_path))
    monkeypatch.setattr(mcpclient, "open_servers", lambda servers: {})
    monkeypatch.setattr(mcpclient, "close_servers", lambda started: None)
    monkeypatch.setattr(openrouter, "api_key", lambda uid=None: "k")
    monkeypatch.setattr(llm, "_record", lambda *a, **k: None)
    monkeypatch.setattr(openrouter, "chat", lambda *a, **k: {
        "choices": [{"message": {"content": "", "tool_calls": [
            {"id": "c", "type": "function", "function": {"name": "Read", "arguments": '{"path": "x"}'}}]}}],
        "usage": {"cost": 0.5}})
    with pytest.raises(openrouter.OpenRouterError) as e:
        openrouter.run("yaz", tools=("Read",), timeout=60, budget_usd=0.4)
    assert "bütçe" in str(e.value).lower()


def test_ask_text_routes_an_openrouter_user_to_openrouter(users, monkeypatch):
    accounts.set_openrouter_key("cem", "sk-or-v1-" + "d" * 40)
    accounts.set_llm_settings("cem", "openrouter", {})
    got = {}

    def fake_run(prompt, tools=(), timeout=900, model=None, servers=None, budget_usd=None, effort=None):
        got.update({"prompt": prompt, "model": model, "servers": servers})
        return '{"ok": true}', {"cost_usd": 0.001}

    monkeypatch.setattr(openrouter, "run", fake_run)
    with accounts.as_user("cem"):
        data, meta = llm.ask_text("merhaba", tools=("Read",), mcp=False, servers={"factory": {"command": "x"}})
    assert data == '{"ok": true}' and llm.extract_json(data) == {"ok": True} and meta["cost_usd"] == 0.001
    assert got["model"] == openrouter.DEFAULT_MODEL and got["servers"] == {"factory": {"command": "x"}}
