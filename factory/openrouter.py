"""OpenRouter: the third way to run an agent step, next to the Claude Code and Codex CLIs.

The two CLIs bring their own session, their own MCP client and their own tools. An OpenRouter model is one paid
HTTP chat completion, so everything a stage agent needs is built here:

- our own tools (factory/hat/mcp_server.py) are started as a stdio MCP server and offered as function schemas
  (factory/mcpclient.py); the loop runs whatever the model calls until it answers without a call;
- `Read` is served locally (the same file the CLI would read), and `WebSearch`/`WebFetch` become OpenRouter's own
  *server tools* (`openrouter:web_search`, `openrouter:web_fetch`: the platform runs them, the model decides when and
  how often to search, and the results come back with `url_citation` annotations);
- every call's token counts and dollars go into the shared ledger (factory/store.py llm_usage) like the CLI calls.

The key is the user's own (Hesaplar → OpenRouter); the owner may instead set OPENROUTER_API_KEY in config.env. The
default model is DeepSeek V4.1 Flash: the cheapest model that keeps a long tool-driven stage moving.
"""
import json, os, time, urllib.error, urllib.request

from .config import ROOT, WORK

API = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "deepseek/deepseek-v4.1-flash-1017"
MODELS_CACHE = os.path.join(ROOT, "data", "openrouter_models.json")
MODELS_TTL = 24 * 3600
MAX_TURNS = 80                 # one tool call per turn is normal; this only stops a runaway loop
READ_CHARS = 200_000
# The CLI's built-in web tools map to OpenRouter's server tools: OpenRouter runs them itself (native search where the
# provider has it, otherwise Exa) and loops the model over the results, so nothing is executed on this machine.
SERVER_TOOLS = {
    "WebSearch": {"type": "openrouter:web_search",
                   "parameters": {"engine": "auto", "max_results": 6, "max_uses": 8, "max_total_results": 40}},
    "WebFetch": {"type": "openrouter:web_fetch"},
}
WEB_TOOLS = tuple(SERVER_TOOLS)
FALLBACK_MODELS = (
    {"id": DEFAULT_MODEL, "name": "DeepSeek V4.1 Flash"},
    {"id": "deepseek/deepseek-v4.1-flash", "name": "DeepSeek V4.1 Flash (latest)"},
    {"id": "deepseek/deepseek-v4-pro", "name": "DeepSeek V4 Pro"},
    {"id": "deepseek/deepseek-v3.2", "name": "DeepSeek V3.2"},
)
FALLBACK_ORDER = {m["id"] for m in FALLBACK_MODELS}
# The catalogue is 400+ models: list the families a film team actually reaches for first, then the rest by id.
FAMILIES = ("deepseek/", "anthropic/", "openai/", "google/", "meta-llama/", "qwen/", "mistralai/", "x-ai/",
            "nvidia/", "amazon/", "cohere/", "moonshotai/", "z-ai/", "minimax/")


def _rank(model_id):
    for i, fam in enumerate(FAMILIES):
        if str(model_id).startswith(fam):
            return (i + 1, str(model_id))
    return (len(FAMILIES) + 1, str(model_id))


class OpenRouterError(RuntimeError):
    pass


# ---------------------------------------------------------------- key, models, one call
def api_key(uid=None):
    """This user's OpenRouter key, else the owner's OPENROUTER_API_KEY from config.env."""
    from . import accounts
    key = accounts.openrouter_key(uid) or os.environ.get("OPENROUTER_API_KEY") or ""
    if not key:
        raise OpenRouterError("OpenRouter anahtarı yok: Hesaplar → OpenRouter bölümüne anahtarını gir "
                             "(ya da config.env'e OPENROUTER_API_KEY yaz)")
    return key


def _http(path, body=None, key=None, timeout=120, method=None):
    url = API + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method or ("POST" if data else "GET"),
                                 headers={"Content-Type": "application/json", "Accept": "application/json",
                                          "X-Title": "Content Factory",
                                          "HTTP-Referer": "https://github.com/sarptech/content-factory"})
    if key:
        req.add_header("Authorization", f"Bearer {key}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = json.loads(e.read().decode("utf-8") or "{}").get("error", {}).get("message") or ""
        except (ValueError, AttributeError):
            pass
        raise OpenRouterHTTP(e.code, detail or e.reason) from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise OpenRouterError(f"OpenRouter'a ulaşılamadı: {e}") from None


class OpenRouterHTTP(OpenRouterError):
    def __init__(self, code, message):
        self.code = code
        self.detail = message
        super().__init__(f"OpenRouter {code}: {message}"[:500])


def models(refresh=False):
    """The catalogue as the settings page lists it: [{id, name, context}]. Cached for a day, never fatal."""
    if not refresh:
        try:
            cached = json.load(open(MODELS_CACHE))
            if time.time() - float(cached.get("at") or 0) < MODELS_TTL and cached.get("models"):
                return cached["models"]
        except (OSError, ValueError, TypeError):
            pass
    try:
        data = _http("/models", timeout=20).get("data") or []
        out = [{"id": m["id"], "name": m.get("name") or m["id"],
                "context": (m.get("context_length") or 0) // 1000 or None}
               for m in data if isinstance(m, dict) and m.get("id")]
        out.sort(key=lambda m: (m["id"] != DEFAULT_MODEL, _rank(m["id"])))   # the default, then the usual families
        if out:
            os.makedirs(os.path.dirname(MODELS_CACHE), exist_ok=True)
            with open(MODELS_CACHE, "w") as f:
                json.dump({"at": time.time(), "models": out}, f)
            return out
    except OpenRouterError:
        pass
    return sorted((dict(m) for m in FALLBACK_MODELS), key=lambda m: (m["id"] != DEFAULT_MODEL, _rank(m["id"])))


def check(key):
    """Is this key good? -> {ok, label, usage, limit} (one free call, no credits spent)."""
    try:
        d = _http("/key", key=key, timeout=20).get("data") or {}
    except OpenRouterHTTP as e:
        if e.code in (401, 403):
            raise ValueError("OpenRouter anahtarı geçersiz (401)") from None
        raise ValueError(f"OpenRouter anahtarı doğrulanamadı: {e}") from None
    return {"ok": True, "label": d.get("label") or "", "usage": d.get("usage"), "limit": d.get("limit")}


def _usage(u):
    """OpenRouter's usage block -> the ledger's columns and a dollar amount."""
    u = u or {}
    cached = ((u.get("prompt_tokens_details") or {}).get("cached_tokens")) or 0
    counts = {"input_tokens": max(0, (u.get("prompt_tokens") or 0) - cached),
              "cache_read_input_tokens": cached, "cache_creation_input_tokens": 0,
              "output_tokens": u.get("completion_tokens") or 0}
    return counts, u.get("cost")


def chat(messages, model=None, tools=None, plugins=None, timeout=600, key=None, retries=2):
    """One chat completion (with `tools` the model may call). Returns the raw response body."""
    body = {"model": model or DEFAULT_MODEL, "messages": messages, "usage": {"include": True}}
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    if plugins:
        body["plugins"] = plugins
    key = key or api_key()
    last = ""
    for attempt in range(retries + 1):
        try:
            return _http("/chat/completions", body, key=key, timeout=timeout)
        except OpenRouterHTTP as e:
            last = str(e)
            if e.code in (400, 401, 402, 403, 404):     # a bad key, no balance, an unknown model: retrying can't help
                raise
        except OpenRouterError as e:
            last = str(e)
        if attempt < retries:
            time.sleep(5 * (attempt + 1))
    raise OpenRouterError(last or "OpenRouter çağrısı başarısız")


# ---------------------------------------------------------------- the agent loop
def _read(path):
    """`Read`: the file a CLI would open, relative to the work dir unless absolute."""
    p = path if os.path.isabs(path) else os.path.join(WORK, path)
    try:
        text = open(p, encoding="utf-8", errors="replace").read()
    except OSError as e:
        return f"cannot read {path}: {e.strerror or e}"
    return text[:READ_CHARS] + ("\n…[truncated]" if len(text) > READ_CHARS else "")


def _functions(tools, servers, listing):
    """(OpenAI function schemas, {local name: 'read' | (server, tool)}) for this step's tool list.

    `listing` is {server name: [tool dicts]}, read from each server once per run.
    """
    schemas, routes = [], {}
    for name in tools:
        if name in SERVER_TOOLS:
            if SERVER_TOOLS[name] not in schemas:
                schemas.append(SERVER_TOOLS[name])     # run by OpenRouter, not by us: no route to keep
            continue
        if name == "Read":
            routes["Read"] = "read"
            schemas.append({"type": "function", "function": {
                "name": "Read", "description": "Read a UTF-8 text file (relative to the work directory, or absolute).",
                "parameters": {"type": "object", "required": ["path"],
                               "properties": {"path": {"type": "string", "description": "File path"}}}}})
            continue
        parts = name.split("__")
        if len(parts) < 3 or parts[0] != "mcp":
            continue
        server, tool = parts[1], "__".join(parts[2:])
        srv = (servers or {}).get(server)
        if not srv:
            continue
        meta = next((t for t in listing.get(server) or [] if t.get("name") == tool), None)
        if not meta:
            continue
        routes[name] = (srv, tool)
        schemas.append({"type": "function", "function": {
            "name": name, "description": meta.get("description") or tool,
            "parameters": meta.get("inputSchema") or {"type": "object", "properties": {}}}})
    return schemas, routes


def _run_tool(routes, name, arguments):
    route = routes.get(name)
    if route == "read":
        return _read(str((arguments or {}).get("path") or ""))
    if not isinstance(route, tuple):
        return f"unknown tool {name}"
    server, tool = route
    try:
        text, failed = server.call(tool, arguments or {})
    except Exception as e:                             # a tool error goes back to the model as text, like MCP does
        return f"{type(e).__name__}: {e}"
    return ("ERROR: " + text if failed else text) or "(empty result)"


def run(prompt, tools=(), timeout=900, model=None, servers=None, budget_usd=None, effort=None):
    """One OpenRouter agent turn -> (reply text, meta). Runs the model's tool calls until it answers."""
    from . import llm, mcpclient
    started = time.time()
    model = model or DEFAULT_MODEL
    starters = mcpclient.open_servers(servers)
    try:
        listing = {name: s.tools() for name, s in starters.items()}
        schemas, routes = _functions(tools, starters, listing)
        key = api_key()
        plugins = None
        messages = [{"role": "system", "content":
                     "You are one stage agent of Content Factory. Do the work with the tools you are given; hand the "
                     "stage output in with submit_artifact and only stop when it is accepted."
                     + (" You have live web access: the web_search and web_fetch tools search and open pages yourself, "
                        "and every source you use comes back with its citation; use them instead of guessing."
                        if any(t in WEB_TOOLS for t in tools) else "")},
                    {"role": "user", "content": prompt}]
        spent, turns, reply = 0.0, 0, ""
        for turns in range(1, MAX_TURNS + 1):
            left = timeout - (time.time() - started)
            if left <= 5:
                raise OpenRouterError(f"OpenRouter turn timed out after {timeout // 60} min")
            body = chat(messages, model, schemas or None, plugins, timeout=min(600, left), key=key)
            counts, cost = _usage(body.get("usage"))
            spent += cost or 0
            llm._record({"usage": counts, "total_cost_usd": cost}, model, True, provider="openrouter")
            msg = ((body.get("choices") or [{}])[0].get("message") or {})
            calls = [c for c in (msg.get("tool_calls") or []) if isinstance(c, dict)]
            reply = str(msg.get("content") or "").strip()
            if not calls:
                if not reply:
                    raise OpenRouterError("OpenRouter boş yanıt döndü")
                return reply, {"cost_usd": round(spent, 4), "turns": turns, "effort": effort, "model": model}
            messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
            for c in calls:
                fn = c.get("function") or {}
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except ValueError:
                    args = {}
                out = _run_tool(routes, fn.get("name") or "", args if isinstance(args, dict) else {})
                messages.append({"role": "tool", "tool_call_id": c.get("id") or fn.get("name") or "call",
                                 "content": out})
            if budget_usd and spent > float(budget_usd):
                raise OpenRouterError(f"OpenRouter bütçesi aşıldı: ${spent:.2f} > ${float(budget_usd):.2f}")
        raise OpenRouterError(f"OpenRouter {MAX_TURNS} turda bitmedi (son söz: {reply[-200:]})")
    finally:
        mcpclient.close_servers(starters)
