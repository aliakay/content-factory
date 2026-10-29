"""Per-user headless Claude Code or Codex CLI calls for Content Factory agents."""
import json, os, re, subprocess

from .config import CLAUDE, CODEX, WORK as WORKDIR
MODEL = "opus"  # creative steps (script, motion design, art direction, revise, style); checks/tools pass "sonnet"
EFFORTS = ("low", "medium", "high", "xhigh", "max")
MAX_EFFORT = "medium"
# Reasoning effort per agent role (the calling step, "module.function"). The owner's rule (2026-10-28): nothing runs above
# medium (MAX_EFFORT) -- an xhigh motion design thought for 30 min, cost ~$6 and overflowed one reply. Connector / tagging
# calls stay light; unlisted steps get medium. Override one step with CF_EFFORT_<MODULE>_<FUNCTION>=level, or every call
# with CF_EFFORT=level (both still capped at MAX_EFFORT).
EFFORT = {
    "planner.draft": "medium",          # art director: direction + three treatments
    "director.scout": "medium",         # research brief (mostly searching and reading)
    "director.sketch": "medium",        # one style frame each, three in parallel
    "director.critic": "medium",        # judging the three frames
    "explainer.generate": "medium",     # research + script
    "explainer.revise": "medium",
    "motiondesign.author": "medium",    # writes every scene as code: the most decisive creative call
    "motiondesign.critique": "medium",
    "artdirector.direct": "medium",
    "artdirector.review": "medium",
    "talk.decide": "medium",            # the edit decision of a talking-head video
    "series.write_bible": "medium",
    "series.write_episode": "medium",
    "productions.generate": "medium",
    "productions.revise": "medium",
    "productions.plan_edit": "medium",
    "ideas.check_claims": "medium",
    "qa.review": "medium",
    "discover.make_cards": "medium",
    "refs.describe": "low",
    "refs.describe_recipes": "medium",
}
_NO_EFFORT_FLAG = False   # set when the installed CLI does not know --effort (then calls run without it)


def effort_for(step, model):
    """The reasoning effort for a call: env override > per-step table > model default."""
    env = os.environ.get("CF_EFFORT_" + re.sub(r"\W", "_", step).upper()) or os.environ.get("CF_EFFORT")
    level = env if env in EFFORTS else EFFORT.get(step) or ("low" if step.startswith("eleven") else "medium")
    return min(level, MAX_EFFORT, key=EFFORTS.index)


class LLMError(RuntimeError):
    pass


def _caller():
    """'module.function' of the factory code that asked Claude (the step name in the usage ledger)."""
    import inspect
    for fr in inspect.stack()[2:]:
        mod = os.path.splitext(os.path.basename(fr.filename))[0]
        if mod != "llm":
            return f"{mod}.{fr.function}"
    return "?"


def _record(out, model, ok, provider="claude"):
    """One row per headless call in factory.db llm_usage. Never raises."""
    try:
        from .store import connect, now
        u = (out or {}).get("usage") or {}
        used = list(((out or {}).get("modelUsage") or {}).keys())
        con = connect()
        con.execute("INSERT INTO llm_usage (at, step, model, job_id, job_kind, prod_id, user, input, cache_write, cache_read,"
                    " output, cost_usd, ok, source) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (now(), _caller(), ",".join(used) or model, os.environ.get("FACTORY_JOB_ID"),
                     os.environ.get("FACTORY_JOB_KIND"), os.environ.get("FACTORY_PROD_ID"), os.environ.get("FACTORY_USER"),
                     u.get("input_tokens", 0), u.get("cache_creation_input_tokens", 0), u.get("cache_read_input_tokens", 0),
                     u.get("output_tokens", 0), (out or {}).get("total_cost_usd") if provider == "codex" else
                     ((out or {}).get("total_cost_usd") or 0), int(ok), "live_codex" if provider == "codex" else "live"))
        con.commit()
        con.close()
    except Exception:
        pass


def _stream(stdout):
    """(result event, the whole final answer, summed usage) from `--output-format stream-json` output (or one json
    object). The final answer is every text block after the last tool call: when a reply hits the output cap the CLI
    continues it in a new message, and the result event only carries that last piece (prod 17 lost its hook scene)."""
    try:
        one = json.loads(stdout) if stdout.strip() else None
        if isinstance(one, dict):
            return one, "", one.get("usage") or {}
    except ValueError:
        pass
    out, parts, usage, seen = None, [], {}, set()
    for line in stdout.splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if not isinstance(e, dict):
            continue
        if e.get("type") == "result":
            out = e
        m = e.get("message") if isinstance(e.get("message"), dict) else {}
        blocks = m.get("content") if isinstance(m.get("content"), list) else []
        if e.get("type") == "user" and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in blocks):
            parts = []
        if e.get("type") == "assistant":
            parts += [b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text"]
            if m.get("usage") and m.get("id") not in seen:
                seen.add(m.get("id"))
                for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens"):
                    usage[k] = usage.get(k, 0) + (m["usage"].get(k) or 0)
    return out, "".join(parts), (out or {}).get("usage") or usage


def _estimate(u, model):
    """List-price dollars for token counts (the CLI's own total is missing when a call is killed)."""
    pi, po = {"sonnet": (3, 15), "haiku": (1, 5)}.get(model or MODEL, (5, 25))
    return round((u.get("input_tokens", 0) * pi + u.get("cache_creation_input_tokens", 0) * pi * 1.25
                  + u.get("cache_read_input_tokens", 0) * pi * 0.1 + u.get("output_tokens", 0) * po) / 1e6, 4)


AGENT_STEPS = {
    "planner.draft": "İçerik planı", "director.scout": "Araştırma", "director.sketch": "Görsel tasarım taslağı",
    "director.critic": "Görsel tasarım değerlendirmesi", "explainer.generate": "Açıklayıcı video senaryosu",
    "explainer.revise": "Açıklayıcı senaryo düzenleme", "motiondesign.author": "Hareketli tasarım yazımı",
    "motiondesign.critique": "Hareketli tasarım değerlendirmesi", "artdirector.direct": "Sanat yönetimi",
    "artdirector.review": "Kurgu değerlendirmesi", "talk.decide": "Konuşmalı video kurgusu",
    "series.write_bible": "Seri dünyası", "series.write_episode": "Bölüm senaryosu",
    "productions.generate": "Video üretimi", "productions.revise": "Video düzenleme",
    "productions.plan_edit": "Kurgu planı", "ideas.generate": "Çekimli video fikirleri",
    "ideas.check_claims": "İddia kontrolü", "qa.review": "Kalite kontrol",
    "discover.make_cards": "Fikir keşfi", "refs.describe": "Referans analizi",
    "refs.describe_recipes": "Referans tarif analizi", "styles.extract": "Stil analizi",
    "jobs.do_describe": "Klip analizi", "default": "Diğer agent’lar",
}
CLAUDE_DEFAULT_MODELS = {
    "director.scout": "sonnet", "director.sketch": "sonnet", "ideas.generate": "sonnet",
    "ideas.check_claims": "sonnet", "productions.plan_edit": "sonnet", "qa.review": "sonnet",
    "refs.describe": "sonnet", "refs.describe_recipes": "sonnet", "jobs.do_describe": "sonnet",
    "discover.make_cards": "sonnet", "artdirector.review": "sonnet",
}
_CODEX_MODELS = None


def model_options(provider=None):
    """Available model IDs for the account settings page."""
    global _CODEX_MODELS
    provider = provider or "claude"
    if provider == "claude":
        return [{"id": x, "name": x.capitalize()} for x in ("opus", "sonnet", "haiku")]
    if _CODEX_MODELS is None:
        try:
            p = subprocess.run([CODEX, "debug", "models", "--bundled"], capture_output=True, text=True, timeout=8)
            models = json.loads(p.stdout).get("models", []) if p.returncode == 0 else []
            _CODEX_MODELS = [{"id": m["slug"], "name": m.get("display_name") or m["slug"]}
                             for m in models if m.get("visibility") == "list" and m.get("slug")]
        except (OSError, subprocess.TimeoutExpired, ValueError):
            _CODEX_MODELS = [{"id": "gpt-5.5", "name": "GPT-5.5"}]
    return _CODEX_MODELS


def selected_provider(uid=None):
    from . import accounts
    return accounts.llm_settings(uid)["provider"]


def default_model(step, provider):
    if provider == "codex":
        options = model_options("codex")
        return next((m["id"] for m in options if m["id"] == "gpt-6-luna"),
                    options[0]["id"] if options else "gpt-5.5")
    return CLAUDE_DEFAULT_MODELS.get(step, MODEL)


def selected_model(step, requested=None, uid=None):
    from . import accounts
    cfg = accounts.llm_settings(uid)
    override = cfg["models"].get(step) or cfg["models"].get("default")
    if override:
        return override
    if cfg["provider"] == "claude":
        return requested or MODEL
    return default_model(step, "codex")


def _codex(prompt, tools, timeout, model, effort, step):
    """One read-only Codex CLI turn. WebSearch/WebFetch map to Codex's live web search."""
    cmd = [CODEX, "--ask-for-approval", "never"]
    if any(t in ("WebSearch", "WebFetch") for t in tools):
        cmd.append("--search")
    cmd += ["exec", "--json", "--ephemeral", "--sandbox", "read-only", "--skip-git-repo-check",
            "--model", model, "-C", WORKDIR, "-c", f'model_reasoning_effort="{effort}"', "-"]
    os.makedirs(WORKDIR, exist_ok=True)
    try:
        p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=timeout, cwd=WORKDIR)
    except FileNotFoundError:
        raise LLMError("Codex CLI bulunamadı; sunucuya Codex CLI kurup giriş yap") from None
    except subprocess.TimeoutExpired:
        raise LLMError(f"codex timed out after {timeout // 60} min") from None
    texts, usage = [], {}
    for line in p.stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        item = event.get("item") or {}
        if item.get("type") == "agent_message" and isinstance(item.get("text"), str):
            texts.append(item["text"])
        if event.get("type") == "turn.completed":
            usage = event.get("usage") or {}
    reply = "\n".join(texts).strip()
    if p.returncode or not reply:
        detail = p.stderr[-500:] or p.stdout[-500:] or f"exit {p.returncode}"
        raise LLMError(f"codex failed: {detail.strip()}")
    # Codex may report token counts without a dollar amount; preserve those in the shared usage ledger.
    _record({"usage": {"input_tokens": usage.get("input_tokens", 0),
                        "output_tokens": usage.get("output_tokens", 0)}}, model, True, provider="codex")
    return reply, {"cost_usd": None, "turns": 1, "effort": effort}


def codex_elevenlabs_status():
    """Return the ElevenLabs MCP server and OAuth state configured in this Codex CLI profile."""
    try:
        p = subprocess.run([CODEX, "mcp", "list", "--json"], capture_output=True, text=True, timeout=10)
        servers = json.loads(p.stdout) if p.returncode == 0 else []
    except (OSError, subprocess.TimeoutExpired, ValueError):
        servers = []
    if isinstance(servers, dict):
        servers = servers.get("servers", [])
    for server in servers if isinstance(servers, list) else []:
        if isinstance(server, dict) and "elevenlabs" in json.dumps(server).lower():
            name = server.get("name")
            if name:
                return {"configured": True, "name": name,
                        "connected": server.get("auth_status") == "logged_in",
                        "auth_status": server.get("auth_status") or "unknown"}
    return {"configured": False, "name": None, "connected": False, "auth_status": "not_configured"}


def _codex_elevenlabs_server():
    """Find the ElevenLabs MCP server configured in this Codex CLI profile."""
    status = codex_elevenlabs_status()
    if status["configured"]:
        return status["name"]
    raise LLMError("Codex CLI'da ElevenLabs connector bulunamadı. Bir kez şu komutları çalıştırıp ElevenLabs'e giriş yap: "
                   "codex mcp add elevenlabs --url https://api.elevenlabs.io/v1/mcp; codex mcp login elevenlabs")


def _codex_mcp_prompt(prompt, tools, server):
    """Translate Claude's connector-qualified tool list into instructions for Codex MCP tools."""
    names = []
    for tool in tools:
        # Claude names are mcp__claude_ai_ElevenLabs__<tool>; Codex exposes the same MCP tool names
        # under the configured server and discovers the actual schema directly from that server.
        name = str(tool).rsplit("__", 1)[-1]
        if name not in names:
            names.append(name)
    allow = ", ".join(names)
    return (f"Use the ElevenLabs MCP server named {server!r}. Its available tool names for this step are: {allow}. "
            f"Call only the needed tools from that list and follow the request exactly.\n\n{prompt}")


def extract_json(text):
    """First JSON object/array in `text` (handles ```json fences and surrounding prose)."""
    m = re.search(r"```(?:json)?\s*(.+?)```", text, re.S)
    if m:
        text = m.group(1)
    starts = [i for i in (text.find("{"), text.find("[")) if i >= 0]
    if not starts:
        raise LLMError("no JSON in model output: " + text.strip()[:300].replace("\n", " "))
    s = min(starts)
    opener = text[s]
    closer = "}" if opener == "{" else "]"
    depth, in_str, esc = 0, False, False
    for i in range(s, len(text)):
        ch = text[i]
        if in_str:
            esc = (ch == "\\") and not esc
            if ch == '"' and not esc:
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return json.loads(text[s:i + 1])
    raise LLMError("unterminated JSON in model output")


def ask(prompt, tools=("Read",), timeout=900, model=None, retries=2, mcp=False, effort=None):
    text, meta = ask_text(prompt, tools, timeout, model, retries, mcp, effort)
    return extract_json(text), meta


def ask_text(prompt, tools=("Read",), timeout=900, model=None, retries=2, mcp=False, effort=None):
    """Run one headless Claude turn; ask() returns (parsed_json, meta), ask_text() the raw reply text.

    Slim mode: no skills/slash commands and no MCP connectors are loaded (the craft rules travel in the prompt),
    which cuts the per-call context ~8x. Built-in tools (Read, WebSearch, WebFetch) still work.
    Transient failures (rate limits, concurrent sessions) are retried with backoff.
    """
    import time
    from . import accounts
    step = _caller()
    provider = selected_provider()
    if provider == "codex" and mcp:
        server = _codex_elevenlabs_server()
        prompt = _codex_mcp_prompt(prompt, tools, server)
        # Preserve the exact MCP tool allowlist in the request instructions. Codex uses the
        # server's own tool schemas and OAuth session rather than Claude's connector namespace.
        tools = tuple(str(t).rsplit("__", 1)[-1] for t in tools)
    model = selected_model(step, model) if provider == "codex" or not mcp else (model or MODEL)
    level = min(effort, MAX_EFFORT, key=EFFORTS.index) if effort in EFFORTS else effort_for(step, model)
    if provider == "codex":
        return _codex(prompt, tools, timeout, model, level, step)
    cmd = [CLAUDE, "-p", prompt, "--output-format", "stream-json", "--verbose", "--allowedTools", ",".join(tools),
           "--disable-slash-commands"]
    if not mcp:  # connectors (e.g. ElevenLabs) are only loaded when a step needs them
        cmd.append("--strict-mcp-config")
    cmd += ["--model", model or MODEL]
    global _NO_EFFORT_FLAG
    level = min(effort, MAX_EFFORT, key=EFFORTS.index) if effort in EFFORTS else effort_for(step, model)
    if not _NO_EFFORT_FLAG:
        cmd += ["--effort", level]
    os.makedirs(WORKDIR, exist_ok=True)
    try:
        env = {**os.environ, **accounts.claude_env()}   # the member's own Claude subscription, if a member started it
    except accounts.NoClaude as e:
        raise LLMError(str(e)) from None
    if mcp and env.get("CLAUDE_CODE_OAUTH_TOKEN"):
        raise LLMError("claude.ai connectors only work on the owner's login; use an ElevenLabs API-key account")
    last = ""
    for attempt in range(retries + 1):
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=WORKDIR,
                               stdin=subprocess.DEVNULL, env=env)
        except subprocess.TimeoutExpired as e:  # the tokens were spent anyway: put them in the ledger, don't retry
            partial = e.stdout.decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
            used = _stream(partial)[2]
            _record({"usage": used, "total_cost_usd": _estimate(used, model)}, model or MODEL, False)
            raise LLMError(f"claude timed out after {timeout // 60} min") from None
        out, reply, _ = _stream(p.stdout)
        if "--effort" in cmd and not out and "effort" in (p.stderr or "").lower() and "unknown" in (p.stderr or "").lower():
            _NO_EFFORT_FLAG = True        # an older CLI: drop the flag and try again
            i = cmd.index("--effort")
            del cmd[i:i + 2]
            continue
        if out:
            _record(out, model or MODEL, p.returncode == 0 and not out.get("is_error"))
        if p.returncode == 0 and out and not out.get("is_error"):
            result = out.get("result", "")
            if len(reply) > len(result):   # a long answer the CLI split over several messages: "result" is only the last one
                result = reply
            return result, {"cost_usd": out.get("total_cost_usd"), "turns": out.get("num_turns"),
                                           "effort": level}
        last = (f"exit {p.returncode}: " + ((out or {}).get("result") or p.stderr[-300:] or p.stdout[-300:])).strip()
        if "limit" in last.lower() and "usage" in last.lower():
            break  # subscription usage limit: retrying won't help
        if attempt < retries:
            time.sleep(10 * (attempt + 1))
    raise LLMError(f"claude failed: {last}")
