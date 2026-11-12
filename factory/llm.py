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


SOURCES = {"codex": "live_codex", "openrouter": "live_openrouter", "gemini": "live_gemini"}
PROVIDERS = ("claude", "codex", "openrouter", "gemini")


def _record(out, model, ok, provider="claude", step=None):
    """One row per headless call in factory.db llm_usage. Never raises."""
    try:
        from .store import connect, now
        u = (out or {}).get("usage") or {}
        used = list(((out or {}).get("modelUsage") or {}).keys())
        con = connect()
        # `project`: the v2 project this call worked for (hat/runner.py exports FACTORY_PROJECT while a stage runs)
        con.execute("INSERT INTO llm_usage (at, step, model, job_id, job_kind, prod_id, user, input, cache_write, cache_read,"
                    " output, cost_usd, ok, source, project) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (now(), step or _caller(), ",".join(used) or model, os.environ.get("FACTORY_JOB_ID"),
                     os.environ.get("FACTORY_JOB_KIND"), os.environ.get("FACTORY_PROD_ID"), os.environ.get("FACTORY_USER"),
                     u.get("input_tokens", 0), u.get("cache_creation_input_tokens", 0), u.get("cache_read_input_tokens", 0),
                     u.get("output_tokens", 0), (out or {}).get("total_cost_usd") if provider != "claude" else
                     ((out or {}).get("total_cost_usd") or 0), int(ok), SOURCES.get(provider, "live"),
                     os.environ.get("FACTORY_PROJECT") or os.environ.get("HAT_PROJECT") or None))
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
    "jobs.do_describe": "Klip analizi", "router.suggest": "Hat önerici",
    "agent.review_stage": "Değerlendirici (diğer model)", "coldtest._ask": "Soğuk test okuyucusu",
    "default": "Diğer agent’lar",
}
# Light steps judge, tag or summarise: they must not burn the Claude subscription. Unless the creator routed the step
# themselves (Hesaplar: a provider or a model picked for it), it runs on a cheap Gemini model when a Gemini key exists
# (Hesaplar -> "Hafif işler": otomatik / Gemini / Claude), and on the cheapest Claude model that does the job when not.
LIGHT_STEPS = ("agent.review_stage", "coldtest._ask", "discover.make_cards", "router.suggest", "qa.review",
               "jobs.do_describe", "refs.describe")
LIGHT_PREFIXES = ("lab.",)
# (model, thinking level). The reviewer and visual QA judge quality: the best flash, the reviewer thinking "high".
# Reading a script cold, tagging clips and picking a line are reading tasks: flash-lite, 2.5x cheaper on output.
GEMINI_LIGHT = {"agent.review_stage": ("gemini-3.8-flash", "high"), "qa.review": ("gemini-3.8-flash", "medium"),
                "discover.make_cards": ("gemini-3.8-flash", "low"), "coldtest._ask": ("gemini-3.5-flash-lite", "low"),
                "router.suggest": ("gemini-3.5-flash-lite", "low"), "jobs.do_describe": ("gemini-3.5-flash-lite", "low"),
                "refs.describe": ("gemini-3.5-flash-lite", "low")}
GEMINI_LIGHT_DEFAULT = ("gemini-3.8-flash", "medium")      # lab.* and any light step added later
# A judge must not silently degrade: when every full flash is busy the reviewer does not drop to flash-lite (on
# project 121 a lite reviewer told the writer to put digits in narration); it fails over to the cheap Claude path.
# 3.6-flash is left out: on project 121 it gave 10/10 on every item three times out of three, where the recorded
# opus/sonnet reviews had found real gaps.
FULL_FLASH = ("gemini-3.8-flash", "gemini-3.7-flash", "gemini-3-flash-preview")
GEMINI_CHAIN = {"agent.review_stage": FULL_FLASH, "qa.review": FULL_FLASH}
CLAUDE_LIGHT = {"agent.review_stage": "sonnet", "qa.review": "sonnet", "router.suggest": "sonnet",
                "discover.make_cards": "haiku", "coldtest._ask": "haiku", "jobs.do_describe": "haiku",
                "refs.describe": "haiku"}
CLAUDE_RANK = ("haiku", "sonnet", "opus")
# The two judges that hold the gates stay on Claude in "otomatik": the trial on project 121 (2026-11-12) never got an
# answer from 3.8-flash (the key's daily quota was gone) and the flash models that did answer passed everything, so a
# Gemini reviewer as strict as the old one is unproven. The single-shot sonnet review found what the recorded reviews
# found at about a third of their cost. "Hafif işler: Gemini" still sends them to Gemini; run the trial again
# (docs/LIMIT.md) before making that the default.
AUTO_KEEPS_CLAUDE = ("agent.review_stage", "qa.review")


def base_step(step):
    """'agent._author:script' -> 'agent._author': the ledger keeps the stage, routing and settings use the agent."""
    return str(step or "").split(":")[0]


def is_light(step):
    b = base_step(step)
    return b in LIGHT_STEPS or b.startswith(LIGHT_PREFIXES)


def cheaper(a, b):
    """The cheaper of two Claude model names (unknown names count as opus)."""
    rank = lambda m: CLAUDE_RANK.index(m) if m in CLAUDE_RANK else len(CLAUDE_RANK)  # noqa: E731
    return a if rank(a) <= rank(b) else b


def _explicit(step, cfg):
    b = base_step(step)
    return b in (cfg.get("providers") or {}) or b in (cfg.get("models") or {})


def light_provider(step, uid=None):
    """'gemini' when this light step goes to Gemini, else None (it then follows the creator's normal routing on the
    cheapest Claude model). A step the creator routed themselves is never moved."""
    from . import accounts
    if not is_light(step):
        return None
    cfg = accounts.llm_settings(uid)
    if _explicit(step, cfg):
        return None
    mode = accounts.light_mode(uid)
    if mode == "gemini" or (mode == "auto" and base_step(step) not in AUTO_KEEPS_CLAUDE
                            and accounts.gemini_status(uid)["connected"]):
        return "gemini"
    return None
CLAUDE_DEFAULT_MODELS = {
    "director.scout": "sonnet", "director.sketch": "sonnet", "ideas.generate": "sonnet",
    "ideas.check_claims": "sonnet", "productions.plan_edit": "sonnet", "qa.review": "sonnet",
    "refs.describe": "sonnet", "refs.describe_recipes": "sonnet", "jobs.do_describe": "sonnet",
    "discover.make_cards": "sonnet", "artdirector.review": "sonnet", "router.suggest": "sonnet",
}
_CODEX_MODELS = None


def model_options(provider=None):
    """Available model IDs for the account settings page."""
    global _CODEX_MODELS
    provider = provider or "claude"
    if provider == "claude":
        return [{"id": x, "name": x.capitalize()} for x in ("opus", "sonnet", "haiku")]
    if provider == "openrouter":
        from . import openrouter
        return [{"id": m["id"], "name": m["name"]} for m in openrouter.models()]
    if provider == "gemini":
        from . import gemini_text
        return [{"id": m["id"], "name": m["name"]} for m in gemini_text.models()]
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
    """The user's default CLI (the agents that have no per-step choice)."""
    from . import accounts
    return accounts.llm_settings(uid)["provider"]


def provider_for(step, uid=None):
    """Who runs this step: the per-step CLI when the user mixed providers, else their default CLI."""
    from . import accounts
    cfg = accounts.llm_settings(uid)
    step = base_step(step)
    if light_provider(step, uid):
        return "gemini"
    chosen = (cfg.get("providers") or {}).get(step) or (cfg.get("providers") or {}).get("default")
    return chosen if chosen in PROVIDERS else cfg["provider"]


def default_model(step, provider):
    step = base_step(step)
    if provider == "gemini":
        from . import gemini_text
        return (GEMINI_LIGHT.get(step) or GEMINI_LIGHT_DEFAULT)[0] if is_light(step) else gemini_text.DEFAULT_MODEL
    if provider == "openrouter":
        from . import openrouter
        return openrouter.DEFAULT_MODEL
    if provider == "codex":
        options = model_options("codex")
        return next((m["id"] for m in options if m["id"] == "gpt-6-luna"),
                    options[0]["id"] if options else "gpt-5.5")
    return CLAUDE_DEFAULT_MODELS.get(step, MODEL)


def selected_model(step, requested=None, uid=None, provider=None):
    """The model for this step: the user's override (from that step's own CLI catalogue), else the CLI's default.

    `provider` is the CLI that actually runs it (a caller may override the step's choice)."""
    from . import accounts
    cfg = accounts.llm_settings(uid)
    own = provider_for(step, uid)
    provider = provider or own
    step = base_step(step)
    light = is_light(step) and not _explicit(step, cfg)
    override = cfg["models"].get(step) or (None if light else cfg["models"].get("default"))
    if override and provider == own and (provider != "gemini" or override.startswith("gemini")):
        return override
    if provider == "claude":
        # a light step on Claude: the cheapest model that does the job, never dearer than what the caller asked for
        return cheaper(requested or MODEL, CLAUDE_LIGHT.get(step, "sonnet")) if light else (requested or MODEL)
    return default_model(step, provider)


def effort_choice(step, uid=None):
    """This agent's reasoning effort: the user's per-agent choice, else the step table, else medium.

    A CLI is capped at MAX_EFFORT (the owner's cost rule); an API model is not, because its output price is a
    fraction of a subscription turn and the creator asked for that agent explicitly."""
    from . import accounts
    env = os.environ.get("CF_EFFORT_" + re.sub(r"\W", "_", step).upper()) or os.environ.get("CF_EFFORT")
    chosen = (accounts.llm_settings(uid).get("effort") or {}).get(step)
    return env if env in EFFORTS else (chosen if chosen in EFFORTS else (EFFORT.get(step) or "medium"))


def _toml(v):
    """A JSON value as a TOML literal for `codex -c key=value` (strings, lists, flat tables)."""
    if isinstance(v, dict):
        return "{" + ", ".join(f"{k}={_toml(x)}" for k, x in v.items()) + "}"
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_toml(x) for x in v) + "]"
    return json.dumps(v, ensure_ascii=False)


def _codex_server_flags(servers):
    """Our own stdio MCP servers ({name: {command, args, env}}) as Codex config overrides."""
    flags = []
    for name, s in (servers or {}).items():
        for k in ("command", "args", "env"):
            if s.get(k) is not None:
                flags += ["-c", f"mcp_servers.{name}.{k}={_toml(s[k])}"]
    return flags


def _codex(prompt, tools, timeout, model, effort, step, approve_mcp=False, servers=None):
    """One Codex CLI turn. MCP write tools need the CLI's automatic approval review."""
    approve_mcp = approve_mcp or bool(servers)    # our factory tools write the stage's files
    if approve_mcp:
        # ElevenLabs generation tools are write actions. With `never`, Codex rejects them
        # before they reach ElevenLabs; use its automatic review only for explicitly
        # requested MCP turns. Non-MCP work remains read-only and approval-free.
        cmd = [CODEX, "--approve-for-me"]
    else:
        cmd = [CODEX, "--ask-for-approval", "never"]
    if any(t in ("WebSearch", "WebFetch") for t in tools):
        cmd.append("--search")
    cmd += ["exec", "--json", "--ephemeral", "--sandbox", "workspace-write" if approve_mcp else "read-only", "--skip-git-repo-check",
            "--model", model, "-C", WORKDIR, "-c", f'model_reasoning_effort="{effort}"', *_codex_server_flags(servers), "-"]
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
                        "output_tokens": usage.get("output_tokens", 0)}}, model, True, provider="codex", step=step)
    return reply, {"cost_usd": None, "turns": 1, "effort": effort}


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


def ask(prompt, tools=("Read",), timeout=900, model=None, retries=2, mcp=False, effort=None, **kw):
    kw.setdefault("step", _caller())
    text, meta = ask_text(prompt, tools, timeout, model, retries, mcp, effort, json_out=True, **kw)
    return extract_json(text), meta


def _gemini(prompt, tools, timeout, model, effort, step, servers, budget_usd, max_output, images, json_out):
    """One step on Gemini: the agent loop when it has our MCP tools, else one call (images inline, Search grounding
    for a step that may search the web)."""
    from . import gemini_text
    if servers or any(str(t).startswith("mcp__") for t in tools):
        return gemini_text.run(prompt, tools=tools, timeout=timeout, model=model, servers=servers,
                               budget_usd=budget_usd, effort=effort, step=step, max_tokens=max_output)
    imgs = list(images or ()) + ([p for p in gemini_text.prompt_images(prompt) if p not in (images or ())]
                                 if "Read" in tools else [])
    return gemini_text.ask(prompt, model=model, images=imgs, json_out=json_out,
                           search=any(t in ("WebSearch", "WebFetch") for t in tools), effort=effort,
                           max_tokens=max_output, timeout=timeout, step=step,
                           fallback=GEMINI_CHAIN.get(base_step(step), True))


def ask_text(prompt, tools=("Read",), timeout=900, model=None, retries=2, mcp=False, effort=None, servers=None,
             budget_usd=None, max_output=None, images=(), step=None, json_out=False):
    """Run one headless Claude turn; ask() returns (parsed_json, meta), ask_text() the raw reply text.

    Slim mode: no skills/slash commands and no MCP connectors are loaded (the craft rules travel in the prompt),
    which cuts the per-call context ~8x. Built-in tools (Read, WebSearch, WebFetch) still work.
    Transient failures (rate limits, concurrent sessions) are retried with backoff.
    `servers` attaches our own stdio MCP servers ({name: {command, args, env}}, e.g. factory/hat/mcp_server.py) and
    nothing else; their tools are named mcp__<name>__<tool> in `tools`. `budget_usd` caps a Claude run's spend.
    `images` are picture files the model must look at (inline for an API model, Read for a CLI). `step` names the
    call in the ledger ('agent._author:script'); routing and settings use the part before the colon.
    """
    import time
    from . import accounts
    step = step or _caller()
    route = base_step(step)
    provider = provider_for(route)          # mixed providers: this step's own CLI, else the user's default
    requested = model
    model = (selected_model(route, model, provider=provider) if provider != "claude" or not mcp
             else (model or MODEL))
    if provider == "gemini":
        light = light_provider(route)
        own = effort if effort in EFFORTS else (accounts.llm_settings().get("effort") or {}).get(route) or \
            ((GEMINI_LIGHT.get(route) or GEMINI_LIGHT_DEFAULT)[1] if light else effort_choice(route))
        try:
            return _gemini(prompt, tools, timeout, model, own if own in ("low", "medium", "high") else None, step,
                           servers, budget_usd, max_output, images, json_out)
        except Exception as e:
            from . import gemini_text
            if not (light and accounts.light_mode() == "auto" and isinstance(e, gemini_text.GeminiTextError)):
                raise LLMError(str(e)) from None
            # automatic light routing must never strand a step: Gemini busy or out of quota -> the cheap Claude path
            provider = accounts.llm_settings()["provider"]
            model = selected_model(route, requested, provider=provider)
    if images:                              # a CLI looks at pictures with Read
        prompt += "\n\nOpen these images with Read before you answer:\n" + "\n".join(f"- {p}" for p in images)
        tools = tuple(tools) + (() if "Read" in tools else ("Read",))
    level = min(effort, MAX_EFFORT, key=EFFORTS.index) if effort in EFFORTS else effort_for(route, model)
    if provider == "codex":
        return _codex(prompt, tools, timeout, model, level, step, approve_mcp=mcp, servers=servers)
    if provider == "openrouter":
        from . import openrouter
        # an API model gets the agent's own level (low/medium/high); the CLI cap does not apply to it
        own = effort if effort in EFFORTS else effort_choice(route)
        return openrouter.run(prompt, tools=tools, timeout=timeout, model=model, servers=servers,
                              budget_usd=budget_usd, effort=own if own in ("low", "medium", "high") else None,
                              step=step, max_tokens=max_output)
    cmd = [CLAUDE, "-p", prompt, "--output-format", "stream-json", "--verbose", "--allowedTools", ",".join(tools),
           "--disable-slash-commands"]
    if servers:   # only our own servers
        os.makedirs(WORKDIR, exist_ok=True)
        cfg = os.path.join(WORKDIR, f"mcp-{os.getpid()}-{abs(hash(json.dumps(servers, sort_keys=True))) % 10**8}.json")
        with open(cfg, "w") as f:
            json.dump({"mcpServers": {n: {"type": "stdio", **s} for n, s in servers.items()}}, f)
        cmd += ["--mcp-config", cfg, "--strict-mcp-config"]
    else:
        cmd.append("--strict-mcp-config")
    if budget_usd:
        cmd += ["--max-budget-usd", str(budget_usd)]
    cmd += ["--model", model or MODEL]
    global _NO_EFFORT_FLAG
    level = min(effort, MAX_EFFORT, key=EFFORTS.index) if effort in EFFORTS else effort_for(route, model)
    if not _NO_EFFORT_FLAG:
        cmd += ["--effort", level]
    os.makedirs(WORKDIR, exist_ok=True)
    try:
        env = {**os.environ, **accounts.claude_env()}   # the member's own Claude subscription, if a member started it
    except accounts.NoClaude as e:
        raise LLMError(str(e)) from None
    last = ""
    for attempt in range(retries + 1):
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=WORKDIR,
                               stdin=subprocess.DEVNULL, env=env)
        except subprocess.TimeoutExpired as e:  # the tokens were spent anyway: put them in the ledger, don't retry
            partial = e.stdout.decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
            used = _stream(partial)[2]
            _record({"usage": used, "total_cost_usd": _estimate(used, model)}, model or MODEL, False, step=step)
            raise LLMError(f"claude timed out after {timeout // 60} min") from None
        out, reply, _ = _stream(p.stdout)
        if "--effort" in cmd and not out and "effort" in (p.stderr or "").lower() and "unknown" in (p.stderr or "").lower():
            _NO_EFFORT_FLAG = True        # an older CLI: drop the flag and try again
            i = cmd.index("--effort")
            del cmd[i:i + 2]
            continue
        if out:
            _record(out, model or MODEL, p.returncode == 0 and not out.get("is_error"), step=step)
        if p.returncode == 0 and out and not out.get("is_error"):
            result = out.get("result", "")
            if len(reply) > len(result):   # a long answer the CLI split over several messages: "result" is only the last one
                result = reply
            return result, {"cost_usd": out.get("total_cost_usd"), "turns": out.get("num_turns"),
                            "effort": level, "model": model or MODEL, "provider": "claude"}
        last = (f"exit {p.returncode}: " + ((out or {}).get("result") or p.stderr[-300:] or p.stdout[-300:])).strip()
        if "limit" in last.lower() and "usage" in last.lower():
            break  # subscription usage limit: retrying won't help
        if attempt < retries:
            time.sleep(10 * (attempt + 1))
    raise LLMError(f"claude failed: {last}")
