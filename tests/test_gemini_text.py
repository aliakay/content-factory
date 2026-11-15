"""Gemini as a text/agent provider (factory/gemini_text.py) and the light-step routing in llm.py: fake transports only."""
import json

import pytest

from factory import accounts, gemini_text as GT, llm


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    rec = []
    monkeypatch.setattr(GT, "_guard", lambda body, model: None)
    monkeypatch.setattr(GT, "_ledger", lambda model, counts, usd, step: rec.append((model, usd, step)))
    monkeypatch.setattr(GT.G, "key", lambda *a, **k: "k")
    monkeypatch.setattr(GT.time, "sleep", lambda s: None)
    GT._DEAD.clear()
    GT._NO_SEARCH.clear()
    GT._BUSY_UNTIL.clear()
    monkeypatch.setattr(GT, "BUSY_FILE", str(tmp_path / "busy.json"))
    return rec


def _chunk(parts, usage=None, finish="STOP", grounding=None):
    c = {"candidates": [{"content": {"parts": parts}, "finishReason": finish,
                         **({"groundingMetadata": grounding} if grounding else {})}]}
    if usage:
        c["usageMetadata"] = usage
    return c


def test_a_call_is_priced_from_its_usage_metadata():
    u = GT.usage({"promptTokenCount": 10_000, "cachedContentTokenCount": 2_000, "candidatesTokenCount": 300,
                  "thoughtsTokenCount": 700})
    assert u == {"input_tokens": 8_000, "cache_read_input_tokens": 2_000, "cache_creation_input_tokens": 0,
                 "output_tokens": 1_000, "prompt": 10_000}
    # 3.8 flash, introductory price: 8k x 0.75 + 2k x 0.075 + 1k x 3.75 per 1M
    assert GT.price("gemini-3.8-flash", 10_000, 2_000, 1_000, day="2026-11-12") == pytest.approx(0.00990)
    assert GT.price("gemini-3.8-flash", 1_000_000, 0, 0, day="2027-02-01") == 1.5          # after the step up
    assert GT.price("gemini-flash-latest", 1_000_000, day="2026-11-12") == 0.75             # alias: never under-counted


def test_ask_streams_merges_and_writes_the_ledger(monkeypatch, offline):
    sent = []

    def sse(model, body, key, timeout):
        sent.append((model, body))
        return [_chunk([{"text": "{\"a\":"}]), _chunk([{"text": " 1}"}],
                                                      {"promptTokenCount": 100, "candidatesTokenCount": 10})]
    monkeypatch.setattr(GT, "_sse", sse)
    text, meta = GT.ask("hi", model="gemini-3.5-flash-lite", json_out=True, effort="low", max_tokens=500, step="s")
    assert json.loads(text) == {"a": 1} and meta["model"] == "gemini-3.5-flash-lite" and meta["cost_usd"] > 0
    gc = sent[0][1]["generationConfig"]
    assert gc["responseMimeType"] == "application/json" and gc["maxOutputTokens"] == 500
    assert gc["thinkingConfig"] == {"thinkingLevel": "low"} and "_thinking" not in gc
    assert offline == [("gemini-3.5-flash-lite", meta["cost_usd"], "s")]


def test_a_busy_model_falls_through_the_chain(monkeypatch):
    tried = []

    def sse(model, body, key, timeout):
        tried.append(model)
        if model == "gemini-3.8-flash":
            raise GT._Busy("503")
        return [_chunk([{"text": "ok"}], {"promptTokenCount": 1, "candidatesTokenCount": 1})]
    monkeypatch.setattr(GT, "_sse", sse)
    text, meta = GT.ask("x")
    assert text == "ok" and tried == ["gemini-3.8-flash", "gemini-3.6-flash"] and meta["model"] == "gemini-3.6-flash"
    monkeypatch.setattr(GT, "_sse", lambda *a: (_ for _ in ()).throw(GT._Busy("503")))
    with pytest.raises(GT.GeminiTextError):
        GT.ask("x")


def test_images_go_inline(monkeypatch, tmp_path):
    img = tmp_path / "sheet.png"
    img.write_bytes(b"\x89PNG")
    seen = {}
    monkeypatch.setattr(GT, "_sse", lambda m, body, k, t: seen.update(body=body) or
                        [_chunk([{"text": "ok"}], {"promptTokenCount": 1})])
    GT.ask("look", images=[str(img)])
    parts = seen["body"]["contents"][0]["parts"]
    assert parts[0]["text"] == "look" and "sheet.png" in parts[1]["text"] and parts[2]["inlineData"]["mimeType"] == "image/png"
    assert GT.prompt_images(f"open {img} and /no/such.png") == [str(img)]


def test_the_agent_transport_keeps_function_calls_and_signatures(monkeypatch):
    replies = iter([[_chunk([{"functionCall": {"id": "c1", "name": "project_info", "args": {}}, "thoughtSignature": "SIG"}],
                            {"promptTokenCount": 50, "candidatesTokenCount": 5})],
                    [_chunk([{"text": "done"}], {"promptTokenCount": 80, "candidatesTokenCount": 2})]])
    bodies = []
    monkeypatch.setattr(GT, "_sse", lambda m, body, k, t: bodies.append((m, body)) or next(replies))
    tools = [{"type": "function", "function": {"name": "project_info", "description": "d", "parameters": {"type": "object"}}}]
    msgs = [{"role": "system", "content": "SYS"}, {"role": "user", "content": "go"}]
    r = GT.chat(msgs, model="gemini-3.8-flash", tools=tools)
    msg = r["choices"][0]["message"]
    assert msg["tool_calls"][0]["id"] == "c1" and msg["tool_calls"][0]["function"]["name"] == "project_info"
    assert bodies[0][1]["systemInstruction"]["parts"][0]["text"] == "SYS"
    assert bodies[0][1]["tools"][0]["functionDeclarations"][0]["name"] == "project_info"
    msgs += [msg, {"role": "tool", "tool_call_id": "c1", "content": "{\"title\": \"t\"}"}]
    r = GT.chat(msgs, model="gemini-3.8-flash", tools=tools)
    replay = bodies[1][1]["contents"]
    assert replay[1] == {"role": "model", "parts": [{"functionCall": {"id": "c1", "name": "project_info", "args": {}},
                                                     "thoughtSignature": "SIG"}]}
    assert replay[2]["parts"][0]["functionResponse"] == {"name": "project_info", "id": "c1",
                                                         "response": {"result": "{\"title\": \"t\"}"}}
    assert r["choices"][0]["message"]["content"] == "done" and r["usage"]["cost"] > 0


def test_the_model_list_is_cached_and_never_fatal(monkeypatch, tmp_path):
    monkeypatch.setattr(GT, "MODELS_CACHE", str(tmp_path / "m.json"))
    monkeypatch.setattr(GT.G, "_req", lambda *a, **k: {"models": [
        {"name": "models/gemini-3.8-flash", "displayName": "Gemini 3.8 Flash", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/gemini-3.1-flash-tts", "supportedGenerationMethods": ["generateContent"]}]})
    assert [m["id"] for m in GT.models()] == ["gemini-3.8-flash"]
    monkeypatch.setattr(GT.G, "_req", lambda *a, **k: (_ for _ in ()).throw(OSError("offline")))
    assert [m["id"] for m in GT.models()] == ["gemini-3.8-flash"]                 # from the cache
    assert GT.models(refresh=True)[0]["id"] == GT.CHAIN[0]                          # the built-in fallback


# ---------------------------------------------------------------- light-step routing
@pytest.fixture
def users(tmp_path, monkeypatch):
    f = tmp_path / "users.json"
    f.write_text(json.dumps({"secret": "x", "users": {"ali": {"name": "Ali", "role": "owner"}}}))
    monkeypatch.setattr(accounts, "USERS", str(f))
    monkeypatch.setattr(accounts, "current", lambda: "ali")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    return f


def test_light_steps_go_to_gemini_only_when_a_key_exists_and_the_creator_did_not_route_them(users, monkeypatch):
    assert llm.provider_for("agent.review_stage") == "claude"                    # no key: Claude ...
    assert llm.selected_model("agent.review_stage", "opus") == "sonnet"           # ... on its cheapest working model
    assert llm.selected_model("coldtest._ask", "sonnet") == "haiku"
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-test")
    assert llm.provider_for("coldtest._ask") == "gemini" and llm.provider_for("lab.distill") == "gemini"
    assert llm.selected_model("coldtest._ask") == "gemini-3.5-flash-lite"
    # the two judges that hold the gates stay on Claude in "otomatik" (a Gemini reviewer is unproven) ...
    assert llm.provider_for("agent.review_stage") == "claude" and llm.provider_for("qa.review") == "claude"
    assert llm.selected_model("agent.review_stage", "opus") == "sonnet"
    accounts.set_light_mode("ali", "gemini")                                       # ... until the creator says Gemini
    assert llm.provider_for("agent.review_stage") == "gemini"
    assert llm.selected_model("agent.review_stage", "opus") == "gemini-3.8-flash"
    accounts.set_light_mode("ali", "auto")
    assert llm.provider_for("script") == "claude" and llm.provider_for("shortplan._ask") == "claude"   # creative stays
    accounts.set_light_mode("ali", "claude")
    assert llm.provider_for("agent.review_stage") == "claude"
    accounts.set_light_mode("ali", "auto")
    accounts.set_llm_settings("ali", "claude", {"agent.review_stage": "opus"}, {})     # the creator chose: kept
    assert llm.provider_for("agent.review_stage") == "claude" and llm.selected_model("agent.review_stage") == "opus"
    with pytest.raises(ValueError):
        accounts.set_light_mode("ali", "cheap")


def test_a_failing_gemini_light_call_falls_back_to_claude(users, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-test")
    monkeypatch.setattr(llm, "_gemini", lambda *a, **k: (_ for _ in ()).throw(GT.GeminiTextError("quota")))
    ran = {}

    class P:
        returncode, stderr = 0, ""
        stdout = json.dumps({"type": "result", "result": "ok", "total_cost_usd": 0.01, "usage": {}})
    monkeypatch.setattr(llm.subprocess, "run", lambda cmd, **k: ran.update(cmd=cmd) or P())
    monkeypatch.setattr(llm, "_record", lambda *a, **k: None)
    monkeypatch.setattr(accounts, "claude_env", lambda uid=None: {})
    text, _ = llm.ask_text("x", tools=(), model="opus", step="agent.review_stage")
    assert text == "ok" and ran["cmd"][ran["cmd"].index("--model") + 1] == "sonnet"


def test_a_busy_model_waits_at_the_back_of_the_chain(monkeypatch):
    GT._BUSY_UNTIL.clear()
    assert GT._chain(None)[0] == "gemini-3.8-flash"
    GT._BUSY_UNTIL["gemini-3.8-flash"] = GT.time.time() + 60
    assert GT._chain(None)[0] == "gemini-3.6-flash" and GT._chain(None)[-1] == "gemini-3.8-flash"
    assert GT._chain("gemini-3.8-flash", fallback=False) == ["gemini-3.8-flash"]
    GT._BUSY_UNTIL.clear()
    assert GT._chain("gemini-3.8-flash", fallback=("gemini-3.8-flash", "gemini-3.6-flash")) == \
        ["gemini-3.8-flash", "gemini-3.6-flash"]                      # a judge's quality floor: no flash-lite


def test_a_grounded_prompt_on_2_5_is_billed_once():
    assert GT.price("gemini-2.5-flash", 0, 0, 0, searches=5) == 0.035
    assert GT.price("gemini-3.8-flash", 0, 0, 0, searches=2, day="2026-11-12") == 0.028


def test_a_day_quota_parks_the_model_until_it_resets(monkeypatch):
    import io, urllib.error
    body = json.dumps({"error": {"code": 429, "message": "quota", "details": [{"retryDelay": "45584s"}]}}).encode()

    def boom(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 429, "x", {}, io.BytesIO(body))
    monkeypatch.setattr(GT.urllib.request, "urlopen", boom)
    with pytest.raises(GT._Busy):
        GT._sse("gemini-3.8-flash", {}, "k", 5)
    assert GT._BUSY_UNTIL["gemini-3.8-flash"] > GT.time.time() + 40_000
    assert GT._chain(None)[-1] == "gemini-3.8-flash"
