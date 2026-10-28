"""Claude via the local Claude Code CLI in headless mode (no separate API key needed)."""
import json, os, re, subprocess

from .config import CLAUDE, WORK as WORKDIR
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


def _record(out, model, ok):
    """One row per headless call in factory.db llm_usage (Studio > Pano > Claude kullanımı). Never raises."""
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
                     u.get("output_tokens", 0), (out or {}).get("total_cost_usd") or 0, int(ok), "live"))
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
    cmd = [CLAUDE, "-p", prompt, "--output-format", "stream-json", "--verbose", "--allowedTools", ",".join(tools),
           "--disable-slash-commands"]
    if not mcp:  # connectors (e.g. ElevenLabs) are only loaded when a step needs them
        cmd.append("--strict-mcp-config")
    cmd += ["--model", model or MODEL]
    global _NO_EFFORT_FLAG
    level = min(effort, MAX_EFFORT, key=EFFORTS.index) if effort in EFFORTS else effort_for(_caller(), model)
    if not _NO_EFFORT_FLAG:
        cmd += ["--effort", level]
    os.makedirs(WORKDIR, exist_ok=True)
    from . import accounts
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
