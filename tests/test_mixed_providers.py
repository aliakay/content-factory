"""Mixed providers: one agent on Claude, another on Codex, a cheap checker on OpenRouter — in the same account.

The Studio's default CLI is only the default: `providers[step]` sends one agent elsewhere, and `models[step]` names a
model from that agent's own catalogue. These tests pin the resolution order and the dispatch of `llm.ask_text`.
"""
import json, sqlite3

import pytest

from factory import accounts, llm, openrouter


@pytest.fixture
def users(tmp_path, monkeypatch):
    f = tmp_path / "users.json"
    f.write_text(json.dumps({"secret": "x", "users": {"ali": {"name": "Ali", "role": "owner"}}}))
    monkeypatch.setattr(accounts, "USERS", str(f))
    monkeypatch.setattr(llm, "model_options", lambda provider=None: {
        "claude": [{"id": "opus", "name": "Opus"}, {"id": "sonnet", "name": "Sonnet"}],
        "codex": [{"id": "gpt-6-luna", "name": "GPT-6 Luna"}, {"id": "gpt-6-mini", "name": "GPT-6 Mini"}],
        "openrouter": [{"id": openrouter.DEFAULT_MODEL, "name": "DeepSeek"}],
    }[provider or "claude"])
    return f


# ---------------------------------------------------------------- the saved shape
def test_a_step_can_carry_its_own_cli(users):
    accounts.set_llm_settings("ali", "codex", {"scene_plan": "gpt-6-mini"},
                              {"scene_plan": "claude", "qa.review": "openrouter"})
    cfg = accounts.llm_settings("ali")
    assert cfg["provider"] == "codex"                       # the default
    assert cfg["providers"] == {"scene_plan": "claude", "qa.review": "openrouter"}
    assert cfg["models"] == {"scene_plan": "gpt-6-mini"}


def test_an_unknown_cli_is_refused(users):
    with pytest.raises(ValueError):
        accounts.set_llm_settings("ali", "codex", {}, {"script": "gemini"})
    with pytest.raises(ValueError):
        accounts.set_llm_settings("ali", "openai", {}, {})
    assert accounts.llm_settings("ali")["providers"] == {}


def test_old_settings_still_load(users, tmp_path):
    f = tmp_path / "legacy.json"
    f.write_text(json.dumps({"secret": "x", "users": {"ali": {"name": "Ali", "role": "owner",
                                                              "llm_settings": {"provider": "codex",
                                                                               "models": {"script": "gpt-6-luna"}}}}}))
    accounts.USERS = str(f)
    cfg = accounts.llm_settings("ali")
    assert cfg["provider"] == "codex" and cfg["models"] == {"script": "gpt-6-luna"} and cfg["providers"] == {}


# ---------------------------------------------------------------- which CLI and which model
def test_the_default_cli_covers_the_steps_without_a_choice(users):
    accounts.set_llm_settings("ali", "codex", {}, {"script": "claude"})
    assert llm.provider_for("script", "ali") == "claude"
    assert llm.provider_for("scene_plan", "ali") == "codex"          # no choice: the default


def test_a_default_for_every_unlisted_step(users):
    accounts.set_llm_settings("ali", "claude", {}, {"default": "openrouter", "script": "codex"})
    assert llm.provider_for("script", "ali") == "codex"
    assert llm.provider_for("scene_plan", "ali") == "openrouter"     # the catch-all


def test_each_step_gets_its_own_clis_model(users):
    accounts.set_llm_settings("ali", "codex", {"script": "opus"}, {"script": "claude", "qa.review": "openrouter"})
    assert llm.selected_model("script", None, "ali") == "opus"                     # the step's own override
    assert llm.selected_model("scene_plan", None, "ali") == "gpt-6-luna"           # codex default
    assert llm.selected_model("qa.review", None, "ali") == openrouter.DEFAULT_MODEL
    # Claude runs a manifest's `model: opus`; the other providers ignore it
    assert llm.selected_model("script", "sonnet", "ali") == "opus"


def test_a_manifest_model_never_leaks_into_another_cli(users):
    accounts.set_llm_settings("ali", "codex", {}, {"script": "claude"})
    assert llm.selected_model("script", "sonnet", "ali") == "sonnet"
    accounts.set_llm_settings("ali", "codex", {}, {})
    assert llm.selected_model("script", "sonnet", "ali") == "gpt-6-luna"


def test_a_connector_turn_uses_the_cli_that_runs_it(users):
    """An ElevenLabs turn is handed to a CLI; that CLI cannot run the other's model names."""
    accounts.set_llm_settings("ali", "openrouter", {}, {})
    accounts.set_llm_settings("ali", "openrouter", {"svg": "opus"}, {})
    assert llm.selected_model("svg", None, "ali") == "opus"
    assert llm.selected_model("svg", None, "ali", provider="codex") == "gpt-6-luna"


# ---------------------------------------------------------------- dispatch
def test_ask_text_runs_each_step_on_its_own_cli(users, monkeypatch):
    accounts.set_llm_settings("ali", "codex", {}, {"a_step": "claude", "b_step": "openrouter"})
    got = {}

    def fake_claude_run(cmd, **kw):
        got["claude"] = cmd
        return type("P", (), {"returncode": 0, "stdout": "{}", "stderr": ""})()

    monkeypatch.setattr(llm.subprocess, "run", fake_claude_run)
    monkeypatch.setattr(llm, "_stream", lambda out: ({"result": "claude-cevap", "total_cost_usd": 0.01}, "", {}))
    monkeypatch.setattr(llm, "_codex", lambda prompt, tools, timeout, model, effort, step, approve_mcp=False,
                                        servers=None: got.update({"codex": step, "model": model}) or ("codex", {}))
    monkeypatch.setattr(openrouter, "run", lambda prompt, **k: got.update({"openrouter": k.get("model")}) or ("api", {}))
    monkeypatch.setattr(llm, "_record", lambda *a, **k: None)
    monkeypatch.setattr(accounts, "claude_env", lambda: {})

    monkeypatch.setattr(llm, "_caller", lambda: "a_step")            # Claude by choice
    text, _ = llm.ask_text("x", tools=(), model=None)
    assert text == "claude-cevap" and "--model" in got["claude"]

    monkeypatch.setattr(llm, "_caller", lambda: "b_step")            # OpenRouter by choice
    text, _ = llm.ask_text("x", tools=(), model=None)
    assert text == "api" and got["openrouter"] == openrouter.DEFAULT_MODEL

    monkeypatch.setattr(llm, "_caller", lambda: "c_step")            # no choice: the default CLI (Codex)
    text, _ = llm.ask_text("x", tools=(), model=None)
    assert text == "codex" and got["codex"] == "c_step" and got["model"] == "gpt-6-luna"
